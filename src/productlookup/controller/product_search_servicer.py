# controller/product_search_servicer.py
import logging
import asyncio
import os
from typing import List
import grpc
from productlookup.protos import product_search_pb2
from productlookup.protos.product_search_pb2_grpc import ProductSearchServicer
from productlookup.services.google_search import GoogleSearchService
from productlookup.services.product_crawler_service import ProductCrawlerService

logger = logging.getLogger(__name__)


class ProductSearchServicer(ProductSearchServicer):
    """gRPC service implementation for product search with crawl4ai + Ollama"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.google_search = GoogleSearchService()
        self.product_crawler = ProductCrawlerService()
        # Get max_results from environment variable
        self.max_results = int(os.getenv("MAX_SEARCH_RESULTS", "10"))

    async def initialize(self):
        """Initialize the service"""
        await self.product_crawler.initialize()
        self.logger.info(f"Initialized ProductSearchServicer with crawl4ai + Ollama (max_results: {self.max_results})")

    async def cleanup(self):
        """Cleanup the service"""
        await self.product_crawler.cleanup()
        self.logger.info("Cleaned up ProductSearchServicer")

    async def SearchProduct(self, request, context):
        """Search for products using Google Search and enrich with crawl4ai + Ollama"""
        try:
            self.logger.info(f"Search request received: {request.query}")

            # Step 1: Search for products using Google with max_results from env
            search_results = await self.google_search.search(request.query, self.max_results)

            if not search_results:
                self.logger.warning("No search results found")
                return product_search_pb2.SearchProductResponse(products=[])

            self.logger.info(f"Found {len(search_results)} products via Google Search")

            # Step 2: Enrich product data using crawl4ai + Ollama
            enriched_products = await self.product_crawler.enrich_products(search_results)

            # Step 3: Return enriched results
            response = product_search_pb2.SearchProductResponse(products=enriched_products)
            self.logger.info(f"Returning {len(enriched_products)} enriched products")

            return response

        except Exception as e:
            self.logger.error(f"Error in SearchProduct: {str(e)}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return product_search_pb2.SearchProductResponse(products=[])