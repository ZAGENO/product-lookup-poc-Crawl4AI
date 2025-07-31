import logging
import asyncio
from typing import List
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from productlookup.protos import product_search_pb2
from productlookup.services.ollama_content_filter import OllamaContentFilter

logger = logging.getLogger(__name__)


class WebCrawlerService:
    """Simplified web crawler that relies on LLM for data extraction"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.crawler = None
        self.content_filter = OllamaContentFilter()

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
        """Main scraping method - simplified to focus on LLM extraction"""
        if not self.crawler:
            await self.initialize()

        enriched_products = []

        for i, product in enumerate(products):
            self.logger.info(f"[{i + 1}/{len(products)}] Scraping: {product.product_url}")

            try:
                # Simple crawl without CSS extraction strategy
                run_config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    verbose=True
                )

                result = await self.crawler.arun(
                    url=product.product_url,
                    config=run_config
                )

                if result.success:
                    self.logger.info("=" * 80)
                    self.logger.info(f"CRAWLING SUCCESSFUL FOR: {product.product_url}")

                    # Log basic info about what we got
                    markdown_length = len(result.markdown) if result.markdown else 0
                    self.logger.info(f"Extracted markdown content: {markdown_length} characters")

                    # Use LLM to extract all data from markdown content
                    self.logger.info("Sending content to LLM for data extraction...")

                    # Create empty scraped data since we're not using CSS selectors
                    empty_scraped_data = {
                        "sku_id": "",
                        "part_number": "",
                        "brand": "",
                        "description": ""
                    }

                    extracted_data = await self._extract_with_llm(
                        empty_scraped_data,
                        result.markdown,
                        product
                    )

                    self.logger.info("LLM EXTRACTED DATA:")
                    self.logger.info(f"  SKU ID: '{extracted_data.get('sku_id', 'Not found')}'")
                    self.logger.info(f"  Part Number: '{extracted_data.get('part_number', 'Not found')}'")
                    self.logger.info(f"  Brand: '{extracted_data.get('brand', 'Not found')}'")
                    description = extracted_data.get('description', 'Not found')
                    truncated_desc = description[:100] + '...' if len(description) > 100 else description
                    self.logger.info(f"  Description: '{truncated_desc}'")

                    # Create final product
                    final_product = self._create_final_product(extracted_data, product)
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

    async def _extract_with_llm(self, scraped_data, markdown_content, original_product):
        """Use LLM to extract all data from markdown content"""
        try:
            extracted_data = await self.content_filter.verify_and_clean_data(
                scraped_data,
                markdown_content,
                original_product
            )
            return extracted_data
        except Exception as e:
            self.logger.warning(f"LLM extraction failed: {str(e)}")
            return {
                "sku_id": "Not found",
                "part_number": "Not found",
                "brand": "Not found",
                "description": "Not found"
            }

    def _create_final_product(self, data, original_product):
        """Create final product with extracted data"""
        return product_search_pb2.ProductData(
            sku_id=data.get("sku_id") or original_product.sku_id or "Not found",
            part_number=data.get("part_number") or original_product.part_number or "Not found",
            product_name=original_product.product_name,
            brand=data.get("brand") or original_product.brand or "Not found",
            price=original_product.price or "Not found",
            description=data.get("description") or original_product.description or "Not found",
            product_url=original_product.product_url
        )

    def _create_fallback_product(self, original_product):
        """Create fallback product when scraping fails"""
        return product_search_pb2.ProductData(
            sku_id=original_product.sku_id or "Not found",
            part_number=original_product.part_number or "Not found",
            product_name=original_product.product_name,
            brand=original_product.brand or "Not found",
            price=original_product.price or "Not found",
            description=original_product.description or "Not found",
            product_url=original_product.product_url
        )