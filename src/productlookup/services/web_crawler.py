# services/web_crawler.py
import logging
import asyncio
import os
import json
import re
from typing import Dict, Any, Optional, List
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, DefaultMarkdownGenerator
from crawl4ai import JsonCssExtractionStrategy
from productlookup.exceptions import ProductLookupError
from productlookup.protos import product_search_pb2
from productlookup.services.ollama_content_filter import OllamaContentFilter

logger = logging.getLogger(__name__)


class WebCrawlerService:
    """Enhanced service for crawling medical/lab product pages using crawl4ai"""

    def __init__(self):
        """Initialize the web crawler service"""
        self.logger = logging.getLogger(__name__)
        self.crawler = None

        # Load config from file
        self._load_extraction_config()

        # Initialize crawl4ai components
        self._setup_crawl4ai()

        # Medical/lab specific patterns
        self._setup_medical_patterns()

        # Load site-specific strategies and validation rules
        self._load_site_specific_strategies()
        self._load_validation_rules()

    def _load_extraction_config(self):
        """Load extraction configuration from environment variables"""
        config_path = os.getenv("CRAWLER_CONFIG_PATH")

        if not config_path:
            raise ProductLookupError("CRAWLER_CONFIG_PATH environment variable is not set")

        if not os.path.exists(config_path):
            raise ProductLookupError(f"Extraction config file not found at: {config_path}")

        try:
            with open(config_path, 'r') as f:
                self.extraction_config = json.load(f)
                self.logger.info(f"Loaded extraction config from {config_path}")
        except Exception as e:
            raise ProductLookupError(f"Failed to load extraction config: {str(e)}")

    def _setup_medical_patterns(self):
        """Setup patterns specific to medical/lab equipment"""
        self.medical_patterns = {
            'sku_patterns': [
                r'[A-Z]{2,4}\d{3,6}[A-Z]?',  # e.g., BMSP7700T10M
                r'\d{6,8}',  # e.g., 02681437
                r'[A-Z]+\d+[A-Z]+',  # e.g., ABC123DEF
                r'\d{3,4}-\d{3,4}',  # e.g., 123-456
            ],
            'part_number_patterns': [
                r'\d{3,4}[A-Z]?/\d{1,3}',  # e.g., 960A/10
                r'[A-Z]+\d{2,4}[A-Z]?',  # e.g., ABC123
                r'\d{1,2}\.\d{1,2}-\d{1,2}[A-Z]?[L|ul]',  # e.g., 0.1-10uL
                r'[A-Z]+-\d{3,4}',  # e.g., TIP-123
            ],
            'volume_patterns': [
                r'\d{1,3}[\.\d]*\s*[µμ]?[Ll]',  # e.g., 10µL, 100mL
                r'\d{1,3}[\.\d]*\s*microliter',
                r'\d{1,3}[\.\d]*\s*milliliter',
            ],
            'price_patterns': [
                r'\$\d+[,\d]*\.?\d*',  # e.g., $161.70
                r'\$\s*\d+[,\d]*\.?\d*',  # e.g., $ 161.70
                r'\d+[,\d]*\.?\d*\s*USD',
            ]
        }

        # Load additional patterns from config file if available
        self._load_additional_patterns()

    def _load_additional_patterns(self):
        """Load additional patterns from medical_lab_config.json"""
        try:
            config_path = os.getenv("MEDICAL_LAB_CONFIG_PATH", "src/productlookup/config/medical_lab_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)

                # Load product patterns
                if "product_patterns" in config:
                    for category, patterns in config["product_patterns"].items():
                        for pattern_type, pattern_list in patterns.items():
                            # Convert JSON escaped patterns to Python regex patterns
                            python_patterns = []
                            for pattern in pattern_list:
                                # Convert escaped patterns back to Python regex format
                                python_pattern = pattern.replace('\\\\', '\\')
                                python_patterns.append(python_pattern)

                            # Add to medical patterns
                            if category not in self.medical_patterns:
                                self.medical_patterns[category] = {}
                            self.medical_patterns[category][pattern_type] = python_patterns

                self.logger.info(f"Loaded additional patterns from {config_path}")
        except Exception as e:
            self.logger.warning(f"Failed to load additional patterns: {str(e)}")

    def _load_site_specific_strategies(self):
        """Load site-specific extraction strategies from medical_lab_config.json"""
        try:
            config_path = os.getenv("MEDICAL_LAB_CONFIG_PATH", "src/productlookup/config/medical_lab_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)

                if "extraction_strategies" in config:
                    self.site_strategies = config["extraction_strategies"]
                    self.logger.info(f"Loaded site-specific strategies for {len(self.site_strategies)} sites")
                else:
                    self.site_strategies = {}
        except Exception as e:
            self.logger.warning(f"Failed to load site-specific strategies: {str(e)}")
            self.site_strategies = {}

    def _load_validation_rules(self):
        """Load validation rules from medical_lab_config.json"""
        try:
            config_path = os.getenv("MEDICAL_LAB_CONFIG_PATH", "src/productlookup/config/medical_lab_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)

                if "validation_rules" in config:
                    self.validation_rules = config["validation_rules"]
                    self.logger.info(f"Loaded validation rules for {len(self.validation_rules)} fields")
                else:
                    self.validation_rules = {}
        except Exception as e:
            self.logger.warning(f"Failed to load validation rules: {str(e)}")
            self.validation_rules = {}

    def _setup_crawl4ai(self):
        """Setup crawl4ai components"""
        # Browser configuration
        self.browser_config = BrowserConfig(
            headless=True,
            viewport_width=1280,
            viewport_height=720
        )

        # Create extraction strategy from config
        self.extraction_strategy = self._create_extraction_strategy()

        # Create Ollama content filter
        self.content_filter = OllamaContentFilter()

        # Create markdown generator
        self.markdown_generator = DefaultMarkdownGenerator(
            content_filter=self.content_filter,
            options={"ignore_links": True}
        )

        # Create crawler run configuration
        self.run_config = CrawlerRunConfig(
            markdown_generator=self.markdown_generator,
            extraction_strategy=self.extraction_strategy,
            cache_mode=CacheMode.BYPASS,  # Disable caching for fresh results
        )

    def _create_extraction_strategy(self):
        """Create enhanced JSON CSS extraction strategy from config"""
        fields = []

        # Map config fields to extraction strategy fields
        field_mapping = {
            "title": "product_name",
            "brand": "brand",
            "price": "price",
            "description": "description",
            "part_number": "part_number",
            "sku_id": "sku_id"
        }

        for config_field, strategy_field in field_mapping.items():
            if config_field in self.extraction_config["fields"]:
                field_config = self.extraction_config["fields"][config_field]
                if field_config.get("enabled", False):
                    # Handle both single selector and array of selectors
                    selectors = field_config["selectors"]
                    if isinstance(selectors, str):
                        selectors = [selectors]

                    fields.append({
                        "name": strategy_field,
                        "selector": selectors,
                        "type": "text"
                    })

        # Add medical/lab specific fields if enabled
        if self.extraction_config.get("medical_lab_specific", {}).get("enabled", False):
            additional_fields = self.extraction_config["medical_lab_specific"]["additional_selectors"]
            for field_name, selectors in additional_fields.items():
                fields.append({
                    "name": field_name,
                    "selector": selectors,
                    "type": "text"
                })

        schema = {
            "name": "ProductData",
            "baseSelector": "body",  # Start from body to capture all fields
            "fields": fields
        }

        return JsonCssExtractionStrategy(schema)

    def _get_site_specific_selectors(self, url: str) -> Dict[str, List[str]]:
        """Get site-specific selectors based on URL"""
        for site_name, strategies in self.site_strategies.items():
            if site_name.lower() in url.lower():
                return strategies
        return {}

    def _validate_field_with_rules(self, value: str, field_type: str) -> bool:
        """Validate field using rules from medical_lab_config.json"""
        if field_type not in self.validation_rules:
            return True  # No rules defined, accept any value

        rules = self.validation_rules[field_type]

        # Check length constraints
        if "min_length" in rules and len(value) < rules["min_length"]:
            return False
        if "max_length" in rules and len(value) > rules["max_length"]:
            return False

        # For SKU and part number, be more lenient with character requirements
        if field_type in ["sku_id", "part_number"]:
            # Only check if there's at least one alphanumeric character
            if not re.search(r'[A-Za-z0-9]', value):
                return False

            # Allow common medical/lab product characters
            allowed_chars = r'[A-Za-z0-9\-/\.\s]+'
            if not re.match(f'^{allowed_chars}$', value):
                return False

        # For price, use the pattern validation
        elif field_type == "price":
            if "pattern" in rules:
                pattern = rules["pattern"].replace('\\\\', '\\')
                if not re.match(pattern, value):
                    return False

        return True

    async def initialize(self):
        """Initialize the crawl4ai crawler"""
        if not self.crawler:
            self.crawler = AsyncWebCrawler(config=self.browser_config)
            await self.crawler.__aenter__()
            self.logger.info("Initialized crawl4ai crawler")

    async def cleanup(self):
        """Cleanup the crawler"""
        if self.crawler:
            await self.crawler.__aexit__(None, None, None)
            self.crawler = None
            self.logger.info("Cleaned up crawl4ai crawler")

    async def get_detailed_product_info(self, products: List[product_search_pb2.ProductData]) -> List[
        product_search_pb2.ProductData]:
        """Scrape detailed information from each product URL using crawl4ai"""
        if not self.crawler:
            await self.initialize()

        enriched_products = []
        batch_size = 2  # Reduced batch size for better reliability

        # Process products in batches
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            batch_results = []

            for product in batch:
                try:
                    self.logger.info(f"Scraping details for: {product.product_url}")

                    # Use crawl4ai to crawl the page
                    result = await self.crawler.arun(
                        url=product.product_url,
                        config=self.run_config
                    )

                    if result.success:
                        enriched_product = await self._process_crawl_result(product, result)
                        batch_results.append(enriched_product)
                    else:
                        self.logger.error(f"Failed to crawl {product.product_url}: {result.error_message}")
                        # Try fallback extraction
                        fallback_product = await self._fallback_extraction(product, result)
                        batch_results.append(fallback_product)

                except Exception as e:
                    self.logger.error(f"Error crawling {product.product_url}: {str(e)}")
                    batch_results.append(self._create_error_product(product))

            # Add all results from this batch
            enriched_products.extend(batch_results)

            # Add delay between batches if not the last batch
            if i + batch_size < len(products):
                await asyncio.sleep(3)  # Increased delay between batches

        return enriched_products

    async def _process_crawl_result(self, original_product: product_search_pb2.ProductData,
                                    result) -> product_search_pb2.ProductData:
        """Process crawl4ai result and extract product information with enhanced logic"""
        try:
            # Extract data from the crawl result
            extracted_data = {}

            # Get extracted content from JSON strategy
            if result.extracted_content:
                # Handle the case where extracted_content is a list
                if isinstance(result.extracted_content, list) and result.extracted_content:
                    extracted_data = result.extracted_content[0]  # Take the first item
                    self.logger.info(f"Extracted data from list: {extracted_data}")
                elif isinstance(result.extracted_content, dict):
                    extracted_data = result.extracted_content
                    self.logger.info(f"Extracted data from dict: {extracted_data}")
                else:
                    extracted_data = {}
                    self.logger.info(f"Unexpected extracted_content type: {type(result.extracted_content)}")
            else:
                self.logger.warning("No extracted_content found in result")

            # Get cleaned markdown content
            markdown_content = result.markdown if result.markdown else ""

            # Get site-specific selectors if available
            site_selectors = self._get_site_specific_selectors(original_product.product_url)

            # Extract product information with enhanced fallbacks
            sku_id = self._extract_field_with_patterns(extracted_data, "sku_id", original_product.sku_id,
                                                       markdown_content, "sku_patterns")
            part_number = self._extract_field_with_patterns(extracted_data, "part_number", original_product.part_number,
                                                            markdown_content, "part_number_patterns")
            product_name = self._extract_field(extracted_data, "product_name", original_product.product_name)
            brand = self._extract_field(extracted_data, "brand", original_product.brand)
            price = self._extract_field_with_patterns(extracted_data, "price", original_product.price, markdown_content,
                                                      "price_patterns")
            description = self._extract_field(extracted_data, "description", original_product.description)

            # Apply site-specific extraction if available
            if site_selectors:
                sku_id = self._apply_site_specific_extraction(sku_id, site_selectors.get("sku_selectors", []),
                                                              markdown_content, "sku_id")
                part_number = self._apply_site_specific_extraction(part_number,
                                                                   site_selectors.get("part_number_selectors", []),
                                                                   markdown_content, "part_number")
                price = self._apply_site_specific_extraction(price, site_selectors.get("price_selectors", []),
                                                             markdown_content, "price")

            self.logger.info(
                f"Extracted fields - sku_id: {sku_id}, part_number: {part_number}, product_name: {product_name}")

            # Use Ollama to further enrich if we have markdown content
            if markdown_content:
                try:
                    enriched_data = await self.content_filter.enrich_content(markdown_content, original_product)
                    self.logger.info(f"Ollama enriched data: {enriched_data}")
                    # Merge Ollama results with extracted data, preferring extracted data
                    sku_id = enriched_data.get("sku_id", sku_id) if sku_id == "Not found" else sku_id
                    part_number = enriched_data.get("part_number",
                                                    part_number) if part_number == "Not found" else part_number
                    product_name = enriched_data.get("product_name",
                                                     product_name) if product_name == "Not found" else product_name
                    brand = enriched_data.get("brand", brand) if brand == "Not found" else brand
                    price = enriched_data.get("price", price) if price == "Not found" else price
                    description = enriched_data.get("description",
                                                    description) if description == "Not found" else description
                except Exception as e:
                    self.logger.warning(f"Ollama enrichment failed: {str(e)}")

            # Final validation and cleaning
            sku_id = self._clean_and_validate_field(sku_id, "sku_id")
            part_number = self._clean_and_validate_field(part_number, "part_number")
            price = self._clean_and_validate_price(price)

            return product_search_pb2.ProductData(
                sku_id=sku_id,
                part_number=part_number,
                product_name=product_name or original_product.product_name,
                brand=brand or original_product.brand or "Not found",
                price=price,
                description=description or original_product.description,
                product_url=original_product.product_url
            )

        except Exception as e:
            self.logger.error(f"Error processing crawl result: {str(e)}", exc_info=True)
            return self._create_error_product(original_product)

    def _apply_site_specific_extraction(self, current_value: str, selectors: List[str], content: str,
                                        field_type: str) -> str:
        """Apply site-specific extraction using selectors"""
        if current_value and current_value != "Not found":
            return current_value  # Already have a value, don't override

        # For now, we'll use pattern matching since we don't have direct CSS selector access
        # In a full implementation, you might want to re-crawl with site-specific selectors
        for selector in selectors:
            # Extract potential values from content based on selector patterns
            if "data-" in selector:
                # Look for data attributes in content
                attr_name = selector.replace("[data-", "").replace("]", "")
                pattern = rf'data-{attr_name}="([^"]+)"'
                matches = re.findall(pattern, content)
                if matches:
                    return matches[0]
            elif selector.startswith("."):
                # Look for class-based content
                class_name = selector.replace(".", "")
                pattern = rf'class="[^"]*{class_name}[^"]*"[^>]*>([^<]+)'
                matches = re.findall(pattern, content)
                if matches:
                    return matches[0].strip()

        return current_value

    async def _fallback_extraction(self, original_product: product_search_pb2.ProductData,
                                   result) -> product_search_pb2.ProductData:
        """Fallback extraction when primary extraction fails"""
        try:
            markdown_content = result.markdown if result.markdown else ""

            if markdown_content:
                # Try to extract using patterns from markdown content
                sku_id = self._extract_from_text(markdown_content, "sku_patterns")
                part_number = self._extract_from_text(markdown_content, "part_number_patterns")
                price = self._extract_from_text(markdown_content, "price_patterns")

                # Use Ollama as last resort
                try:
                    enriched_data = await self.content_filter.enrich_content(markdown_content, original_product)
                    sku_id = enriched_data.get("sku_id", sku_id) if not sku_id else sku_id
                    part_number = enriched_data.get("part_number", part_number) if not part_number else part_number
                    price = enriched_data.get("price", price) if not price else price
                except Exception as e:
                    self.logger.warning(f"Ollama fallback failed: {str(e)}")

                return product_search_pb2.ProductData(
                    sku_id=sku_id or "Not found",
                    part_number=part_number or "Not found",
                    product_name=original_product.product_name,
                    brand=original_product.brand or "Not found",
                    price=price or "Not found",
                    description=original_product.description,
                    product_url=original_product.product_url
                )

            return self._create_error_product(original_product)

        except Exception as e:
            self.logger.error(f"Fallback extraction failed: {str(e)}")
            return self._create_error_product(original_product)

    def _extract_field_with_patterns(self, data: Dict, field_name: str, fallback: str,
                                     markdown_content: str, pattern_key: str) -> str:
        """Extract field from data with pattern matching fallback"""
        # First try normal extraction
        value = self._extract_field(data, field_name, fallback)

        # If not found or is "Not found", try pattern matching
        if not value or value == "Not found":
            pattern_value = self._extract_from_text(markdown_content, pattern_key)
            if pattern_value:
                return pattern_value

        return value

    def _extract_from_text(self, text: str, pattern_key: str) -> str:
        """Extract value from text using regex patterns"""
        if not text or pattern_key not in self.medical_patterns:
            return ""

        patterns = self.medical_patterns[pattern_key]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Return the first match, cleaned up
                match = str(matches[0]).strip()
                if match and len(match) > 2:  # Ensure meaningful match
                    return match

        return ""

    def _extract_field(self, data: Dict, field_name: str, fallback: str) -> str:
        """Extract field from data with fallback"""
        if not data:
            return fallback

        # Handle both single values and arrays
        value = data.get(field_name)
        if isinstance(value, list) and value:
            return str(value[0])
        elif value:
            return str(value)
        else:
            return fallback

    def _clean_and_validate_field(self, value: str, field_type: str) -> str:
        """Clean and validate extracted field values"""
        if not value or value == "Not found":
            return "Not found"

        # Clean up common issues
        value = str(value).strip()

        # For SKU and part number, be more careful with cleaning
        if field_type in ["sku_id", "part_number"]:
            # Only remove obvious prefixes/suffixes, not the actual content
            value = re.sub(r'^(sku|part|number|id|code|item)[:\s]*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'[:\s]*(sku|part|number|id|code|item)$', '', value, flags=re.IGNORECASE)
            value = value.strip()

            # Ensure it's not empty after cleaning
            if not value or len(value) < 2:
                return "Not found"

        # Apply validation rules if available
        if not self._validate_field_with_rules(value, field_type):
            return "Not found"

        return value

    def _clean_and_validate_price(self, price: str) -> str:
        """Clean and validate price field"""
        if not price or price == "Not found":
            return "Not found"

        price = str(price).strip()

        # More lenient price validation - accept various formats
        price_patterns = [
            r'^\$\d+[,\d]*\.?\d*$',  # $145.00
            r'^\$\s*\d+[,\d]*\.?\d*$',  # $ 145.00
            r'^\d+[,\d]*\.?\d*\s*USD$',  # 145.00 USD
            r'^\d+[,\d]*\.?\d*$',  # 145.00 (without currency)
        ]

        for pattern in price_patterns:
            if re.match(pattern, price):
                return price

        # Try to extract price from text
        price_match = re.search(r'\$\d+[,\d]*\.?\d*', price)
        if price_match:
            return price_match.group()

        # If it looks like a price but doesn't match patterns, still accept it
        if re.search(r'\d+\.?\d*', price) and ('$' in price or 'USD' in price.upper()):
            return price

        return "Not found"

    def _create_error_product(self, original_product: product_search_pb2.ProductData) -> product_search_pb2.ProductData:
        """Create a product with error indication"""
        return product_search_pb2.ProductData(
            sku_id="Not found",
            part_number="Not found",
            product_name=original_product.product_name,
            brand=original_product.brand or "Not found",
            price=original_product.price or "Not found",
            description=original_product.description or "Error occurred during extraction",
            product_url=original_product.product_url
        )