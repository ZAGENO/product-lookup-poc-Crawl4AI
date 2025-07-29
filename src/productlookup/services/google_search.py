# services/google_search.py
import requests
import logging
import os
import asyncio
from typing import List, Dict, Any
from productlookup.exceptions import ProductLookupError
from productlookup.protos import product_search_pb2

logger = logging.getLogger(__name__)


class GoogleSearchService:
    """Enhanced service for searching medical/lab products using Google Programmable Search Engine"""

    def __init__(self):
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "d3daf05153a424949")
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.base_url = "https://customsearch.googleapis.com/customsearch/v1"
        self.logger = logging.getLogger(__name__)

        # Enhanced configuration for medical/lab products
        max_allowed = 10
        default_max = 8  # Increased default for better coverage
        configured_max = int(os.getenv("MAX_SEARCH_RESULTS", default_max))
        self.max_search_results = min(configured_max, max_allowed)
        self.logger.info(f"Maximum search results set to: {self.max_search_results}")

        # Medical/lab specific search sites to prioritize
        self.medical_sites = [
            "fishersci.com",
            "sigmaaldrich.com",
            "thermofisher.com",
            "vwr.com",
            "usascientific.com",
            "eppendorf.com",
            "gilson.com",
            "celltreat.com",
            "globescientific.com",
            "shoprainin.com"
        ]

    async def search(self, query: str, max_results: int = 8) -> List[product_search_pb2.ProductData]:
        """
        Enhanced async method to search for medical/lab products and return them as ProductData objects
        """
        try:
            # Use configured value if max_results not explicitly provided
            if max_results is None:
                max_results = self.max_search_results
            else:
                # Ensure we don't exceed the configured limit
                max_results = min(max_results, self.max_search_results)

            # Use original query without enhancement for now to debug
            self.logger.info(f"Searching for query: {query}")

            # Call the synchronous method in a thread pool
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None, self.search_products, query, max_results
            )

            self.logger.info(f"Raw search results count: {len(search_results)}")

            # Convert search results to ProductData objects with less restrictive filtering
            products = []
            for result in search_results:
                url = result.get("link")
                title = result.get("title", "")
                snippet = result.get("snippet", "")

                # Log each result for debugging
                self.logger.info(f"Processing result: {title} - {url}")

                # Use less restrictive filtering - accept all results for now
                if url:
                    product = product_search_pb2.ProductData(
                        sku_id="",
                        product_name=title,
                        brand="",
                        description=snippet,
                        price="",
                        product_url=url
                    )
                    products.append(product)

            self.logger.info(f"Found {len(products)} products via Google Search API")
            return products

        except Exception as e:
            self.logger.error(f"Error in async search: {str(e)}", exc_info=True)
            return []

    def _enhance_query_for_medical_products(self, query: str) -> str:
        """Enhance search query for better medical/lab product results"""
        # For now, return the original query to avoid over-filtering
        return query

    def _is_relevant_medical_product(self, url: str, title: str, snippet: str) -> bool:
        """Check if the search result is relevant for medical/lab products"""
        # For now, accept all results to debug the issue
        return True

    def search_products(self, query: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """
        Enhanced synchronous method to search for medical/lab products
        Returns raw search results as dictionaries
        """
        try:
            # Use configured value if max_results not explicitly provided
            if max_results is None:
                max_results = self.max_search_results
            else:
                # Ensure we don't exceed the configured limit
                max_results = min(max_results, self.max_search_results)

            params = {
                "key": self.api_key,
                "cx": self.search_engine_id,
                "q": query,
                "num": max_results
            }

            self.logger.info(f"Making Google Search API request with params: {params}")

            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            self.logger.info(f"Google Search API response status: {response.status_code}")
            self.logger.info(f"Google Search API response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

            if "items" in data:
                self.logger.info(f"Found {len(data['items'])} items in Google Search response")
                return data["items"]
            else:
                self.logger.warning(f"No 'items' found in Google Search response. Response: {data}")
                return []

        except Exception as e:
            self.logger.error(f"Error searching products: {str(e)}")
            return []