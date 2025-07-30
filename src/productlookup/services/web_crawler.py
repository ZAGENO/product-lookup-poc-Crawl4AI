import logging
import asyncio
import os
import json
from typing import List
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, JsonCssExtractionStrategy
from productlookup.exceptions import ProductLookupError
from productlookup.protos import product_search_pb2
from productlookup.services.ollama_content_filter import OllamaContentFilter

logger = logging.getLogger(__name__)


class WebCrawlerService:
    """Simple config-driven web crawler using crawl4ai"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.crawler = None
        self.content_filter = OllamaContentFilter()
        self._load_config()
        self._setup_extraction_strategy()

    def _load_config(self):
        """Load simple extraction configuration"""
        config_path = os.getenv("CRAWLER_CONFIG_PATH", "config/crawler_config.json")

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
                    self.logger.info(f"Loaded config from {config_path}")
            else:
                self.logger.warning(f"Config file not found at {config_path}, using default config")
                self.config = {}
        except Exception as e:
            self.logger.error(f"Error loading config: {str(e)}, using default config")
            self.config = {}

        # Ensure selectors exist in config
        if "selectors" not in self.config:
            self.logger.info("Using default selectors configuration")
            self.config["selectors"] = {
                "sku_id": [".sku", "[data-sku]", ".product-code", ".item-code", ".sku-number", "[class*='sku']"],
                "part_number": [".part-number", "[data-part-number]", ".model-number", ".catalog-number",
                                ".item-number"],
                "brand": [".brand", ".manufacturer", "[data-brand]", ".company-name", ".vendor"],
                "description": [".description", ".product-description", ".product-summary", ".product-details"]
            }

        self.logger.info(
            f"Loaded config with {len(self.config['selectors'])} field types: {list(self.config['selectors'].keys())}")

    def _setup_extraction_strategy(self):
        """Setup JSON CSS extraction strategy from config - ENHANCED VERSION"""
        fields = []

        for field_name, selectors in self.config["selectors"].items():
            selector_chain = []
            for selector in selectors:
                selector_chain.append(f"{selector}")
            fields.append({
                "name": field_name,
                "selector": ", ".join(selector_chain),  # OR logic
                "type": "text",
                "attribute": "text"
            })

        schema = {
            "name": "ProductData",
            "baseSelector": "body",
            "fields": fields,
            "description": "Extract product information from web pages"
        }

        self.extraction_strategy = JsonCssExtractionStrategy(schema)
        self.logger.info(f"Created extraction strategy with fields: {[f['name'] for f in fields]}")
        for field in fields:
            self.logger.debug(f"Field '{field['name']}' selectors: {field['selector']}")

    def _create_fallback_extraction_strategy(self):
        """Create a simpler fallback extraction strategy for difficult sites"""
        fallback_selectors = {
            "sku_id": "h1, .title, [class*='product'] [class*='name'], [id*='product']",
            "part_number": "h1, .title, [class*='model'], [class*='part'], [class*='item']",
            "brand": "[class*='brand'], [class*='manufacturer'], [class*='company']",
            "description": "p, [class*='description'], [class*='summary'], [class*='detail']"
        }
        fields = []
        for field_name, selector in fallback_selectors.items():
            fields.append({
                "name": field_name,
                "selector": selector,
                "type": "text"
            })
        schema = {
            "name": "FallbackProductData",
            "baseSelector": "body",
            "fields": fields
        }
        return JsonCssExtractionStrategy(schema)

    async def initialize(self):
        """Initialize the crawler"""
        if not self.crawler:
            browser_config = BrowserConfig(headless=True)
            self.crawler = AsyncWebCrawler(config=browser_config)
            await self.crawler.__aenter__()
            self.logger.info("Crawler initialized")

    async def cleanup(self):
        """Cleanup the crawler"""
        if self.crawler:
            await self.crawler.__aexit__(None, None, None)
            self.crawler = None
            self.logger.info("Crawler cleaned up")

    async def get_detailed_product_info(self, products: List[product_search_pb2.ProductData]) -> List[
        product_search_pb2.ProductData]:
        """Main scraping method"""
        if not self.crawler:
            await self.initialize()

        enriched_products = []

        for i, product in enumerate(products):
            self.logger.info(f"[{i + 1}/{len(products)}] Scraping: {product.product_url}")

            try:
                # Step 1: Crawl with extraction strategy
                run_config = CrawlerRunConfig(
                    extraction_strategy=self.extraction_strategy,
                    cache_mode=CacheMode.BYPASS
                )

                result = await self.crawler.arun(
                    url=product.product_url,
                    config=run_config
                )

                if result.success:
                    self.logger.info("=" * 80)
                    self.logger.info(f"CRAWLING SUCCESSFUL FOR: {product.product_url}")

                    # Step 2: Extract data from crawl4ai result
                    scraped_data = self._extract_scraped_data(result)

                    self.logger.info("SCRAPED DATA (Before LLM Verification):")
                    self.logger.info(f"  SKU ID: '{scraped_data.get('sku_id', 'EMPTY')}'")
                    self.logger.info(f"  Part Number: '{scraped_data.get('part_number', 'EMPTY')}'")
                    self.logger.info(f"  Brand: '{scraped_data.get('brand', 'EMPTY')}'")
                    self.logger.info(
                        f"  Description: '{scraped_data.get('description', 'EMPTY')[:100]}{'...' if len(scraped_data.get('description', '')) > 100 else ''}'")

                    # Step 3: Use LLM to verify and clean the data
                    self.logger.info("Sending data to LLM for verification...")
                    verified_data = await self._verify_with_llm(scraped_data, result.markdown, product)

                    self.logger.info("VERIFIED DATA (After LLM Processing):")
                    self.logger.info(f"  SKU ID: '{verified_data.get('sku_id', 'EMPTY')}'")
                    self.logger.info(f"  Part Number: '{verified_data.get('part_number', 'EMPTY')}'")
                    self.logger.info(f"  Brand: '{verified_data.get('brand', 'EMPTY')}'")
                    self.logger.info(
                        f"  Description: '{verified_data.get('description', 'EMPTY')[:100]}{'...' if len(verified_data.get('description', '')) > 100 else ''}'")

                    # Log changes made by LLM
                    changes_made = []
                    for field in ['sku_id', 'part_number', 'brand', 'description']:
                        scraped_val = scraped_data.get(field, '')
                        verified_val = verified_data.get(field, '')
                        if scraped_val != verified_val:
                            changes_made.append(f"{field}: '{scraped_val}' → '{verified_val}'")

                    if changes_made:
                        self.logger.info("LLM CHANGES MADE:")
                        for change in changes_made:
                            self.logger.info(f"  {change}")
                    else:
                        self.logger.info("LLM MADE NO CHANGES - Data was already correct")

                    # Step 4: Create final product
                    final_product = self._create_final_product(verified_data, product)
                    enriched_products.append(final_product)
                    self.logger.info("=" * 80)

                else:
                    self.logger.error(f"Crawl failed: {result.error_message}")
                    enriched_products.append(self._create_fallback_product(product))

            except Exception as e:
                self.logger.error(f"Error processing {product.product_url}: {str(e)}")
                enriched_products.append(self._create_fallback_product(product))

            # Small delay between requests
            await asyncio.sleep(1)

        return enriched_products

    def _extract_scraped_data(self, result):
        """Extract data from crawl4ai result - FIXED VERSION"""
        scraped_data = {
            "sku_id": "",
            "part_number": "",
            "brand": "",
            "description": ""
        }

        self.logger.debug(f"Raw extracted_content type: {type(result.extracted_content)}")
        self.logger.debug(f"Raw extracted_content: {result.extracted_content}")

        if result.extracted_content:
            try:
                extracted = None

                # Handle different response types
                if isinstance(result.extracted_content, str):
                    self.logger.debug("Parsing string extracted_content as JSON")
                    extracted = json.loads(result.extracted_content)
                elif isinstance(result.extracted_content, list):
                    self.logger.debug(f"Got list with {len(result.extracted_content)} items")
                    if result.extracted_content:
                        # Take the first item if it exists
                        first_item = result.extracted_content[0]
                        if isinstance(first_item, dict):
                            extracted = first_item
                        elif isinstance(first_item, str):
                            try:
                                extracted = json.loads(first_item)
                            except json.JSONDecodeError:
                                self.logger.warning("First list item is not valid JSON")
                                extracted = {}
                        else:
                            self.logger.warning(f"First list item is unexpected type: {type(first_item)}")
                            extracted = {}
                    else:
                        self.logger.warning("Empty list in extracted_content")
                        extracted = {}
                elif isinstance(result.extracted_content, dict):
                    self.logger.debug("Using dict extracted_content directly")
                    extracted = result.extracted_content
                else:
                    self.logger.warning(f"Unexpected extracted_content type: {type(result.extracted_content)}")
                    extracted = {}

                self.logger.debug(f"Parsed extracted data: {extracted}")

                # Extract each field, handling nested structures
                for field_name in scraped_data.keys():
                    value = extracted.get(field_name, "")

                    # Handle different value types
                    if isinstance(value, list):
                        # Take first non-empty value from list
                        for item in value:
                            if item and str(item).strip():
                                value = str(item).strip()
                                break
                        else:
                            value = ""
                    elif isinstance(value, dict):
                        # If it's a dict, try to get meaningful text
                        if 'text' in value:
                            value = str(value['text']).strip()
                        elif 'value' in value:
                            value = str(value['value']).strip()
                        else:
                            # Take first non-empty value from dict
                            for v in value.values():
                                if v and str(v).strip():
                                    value = str(v).strip()
                                    break
                            else:
                                value = ""
                    else:
                        value = str(value).strip() if value else ""

                    scraped_data[field_name] = value

                # Log what we actually extracted
                self.logger.info("Raw CSS extraction results:")
                for field, value in scraped_data.items():
                    self.logger.info(f"  {field}: '{value}'")

            except Exception as e:
                self.logger.warning(f"Failed to parse extracted_content: {str(e)}")
                self.logger.debug(f"Raw content that failed: {result.extracted_content}")
        else:
            self.logger.warning("No extracted_content found in crawl result")

        return scraped_data

    async def _verify_with_llm(self, scraped_data, markdown_content, original_product):
        """Use LLM to verify and clean scraped data"""
        try:
            verified_data = await self.content_filter.verify_and_clean_data(
                scraped_data,
                markdown_content,
                original_product
            )
            return verified_data
        except Exception as e:
            self.logger.warning(f"LLM verification failed: {str(e)}")
            return scraped_data

    def _create_final_product(self, data, original_product):
        return product_search_pb2.ProductData(
            sku_id=data.get("sku_id") or original_product.sku_id or "Not found",
            part_number=data.get("part_number") or original_product.part_number or "Not found",
            product_name=original_product.product_name,
            brand=data.get("brand") or original_product.brand or "Not found",
            price=original_product.price or "Not found",
            description=data.get("description") or original_product.description or "Not found",
            product_url=original_product.product_url,
            attributes=[
                product_search_pb2.ProductAttribute(key=attr.get("key", ""), value=attr.get("value", ""))
                for attr in data.get("attributes", [])
                if attr.get("key") and attr.get("value")
            ]
        )

    def _create_fallback_product(self, original_product):
        """Create fallback product when scraping fails"""
        return product_search_pb2.ProductData(
            sku_id=original_product.sku_id or "Not found",
            part_number=original_product.part_number or "Not found",
            product_name=original_product.product_name,
            brand=original_product.brand or "Not found",
            price=original_product.price or "Not found",
            description=original_product.description or "Scraping failed",
            product_url=original_product.product_url
        )