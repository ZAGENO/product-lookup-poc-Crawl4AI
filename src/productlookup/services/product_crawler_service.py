# services/product_crawler_service.py
import logging
import asyncio
from typing import List
from productlookup.protos import product_search_pb2
from productlookup.services.web_crawler import WebCrawlerService

logger = logging.getLogger(__name__)


class ProductCrawlerService:
    """Service for crawling and enriching product data using crawl4ai with Ollama"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.web_crawler = WebCrawlerService()

    async def initialize(self):
        """Initialize the crawler service"""
        await self.web_crawler.initialize()
        self.logger.info("Initialized ProductCrawlerService with crawl4ai + Ollama")

    async def cleanup(self):
        """Cleanup the crawler service"""
        await self.web_crawler.cleanup()
        self.logger.info("Cleaned up ProductCrawlerService")

    async def enrich_products(self, products: List[product_search_pb2.ProductData]) -> List[
        product_search_pb2.ProductData]:
        """Enrich product data by crawling their URLs"""
        if not products:
            return []

        self.logger.info(f"Starting enrichment for {len(products)} products using crawl4ai + Ollama")

        try:
            enriched_products = await self.web_crawler.get_detailed_product_info(products)

            # Log enrichment results
            successful_enrichments = sum(
                1 for p in enriched_products if p.sku_id != "Not found" or p.part_number != "Not found")
            self.logger.info(f"Successfully enriched {successful_enrichments}/{len(products)} products")

            return enriched_products

        except Exception as e:
            self.logger.error(f"Error during product enrichment: {str(e)}")
            # Return original products with error indication
            return [self._create_error_product(p) for p in products]

    def _create_error_product(self, product: product_search_pb2.ProductData) -> product_search_pb2.ProductData:
        """Create a product with error indication"""
        return product_search_pb2.ProductData(
            sku_id="Not found",
            part_number="Not found",
            product_name=product.product_name,
            brand=product.brand or "Not found",
            price=product.price or "Not found",
            description=product.description or "Error occurred during enrichment",
            product_url=product.product_url
        )