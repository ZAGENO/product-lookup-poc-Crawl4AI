import logging
import json
import aiohttp
import os
import re
from typing import Dict
from productlookup.protos import product_search_pb2

logger = logging.getLogger(__name__)

class OllamaContentFilter:
    """Enhanced content filter for Ollama LLM integration with medical/lab focus"""

    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "mistral:latest")
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initialized OllamaContentFilter with {self.ollama_host} and model: {self.ollama_model}")

    async def enrich_content(self, markdown_content: str, product: product_search_pb2.ProductData) -> Dict[str, str]:
        """Use Ollama to extract additional product information from markdown content"""
        try:
            prompt = self._create_medical_extraction_prompt(product, markdown_content)
            async with aiohttp.ClientSession() as session:
                url = f"{self.ollama_host}/api/generate"
                payload = {
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1
                }
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        self.logger.error(f"Ollama API error: {response.status}")
                        return {}
                    result = await response.json()
                    llm_response = result.get("response", "")
                    try:
                        json_start = llm_response.find('{')
                        json_end = llm_response.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            json_str = llm_response[json_start:json_end]
                            extracted_data = json.loads(json_str)
                            self.logger.info(f"Ollama extracted data: {extracted_data}")
                            cleaned_data = self._validate_extracted_data(extracted_data)
                            attributes = extracted_data.get("attributes", [])
                            if not isinstance(attributes, list):
                                attributes = []
                            cleaned_data["attributes"] = attributes
                            return cleaned_data
                        else:
                            self.logger.warning("No JSON found in Ollama response")
                            return {}
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse Ollama response as JSON: {str(e)}")
                        return {}
        except Exception as e:
            self.logger.error(f"Error enriching with Ollama: {str(e)}")
            return {}

    # python
    async def verify_and_clean_data(self, scraped_data, markdown_content, original_product):
        """
        Use Ollama to verify and clean scraped data.
        If LLM returns nothing or 'Not found', fall back to scraped_data.
        """
        enriched = await self.enrich_content(markdown_content, original_product)

        def pick(field):
            val = (enriched.get(field) or "").strip()
            if not val or val.lower() == "not found":
                return (scraped_data.get(field) or "").strip()
            return val

        # Add attributes, fallback to empty list if not present
        attributes = enriched.get("attributes", [])
        if not isinstance(attributes, list):
            attributes = []
        return {
            "sku_id": pick("sku_id"),
            "part_number": pick("part_number"),
            "brand": pick("brand"),
            "description": pick("description"),
            "attributes": attributes
        }

    def _create_medical_extraction_prompt(self, product, markdown_content):
        """Create an enhanced prompt for extracting structured data from medical/lab products"""
        truncated_content = markdown_content[:4000] if len(markdown_content) > 4000 else markdown_content
        prompt = f"""
        You are an expert at extracting product information from medical and laboratory equipment websites.

        Extract structured product information from the following markdown content for a medical/lab product.
        The product appears to be: {product.product_name}

        CRITICAL EXTRACTION RULES FOR MEDICAL/LAB PRODUCTS:

        1. SKU ID (Stock Keeping Unit):
       - Look for: SKU, Item #, Product Code, Catalog Number, Product ID
       - Also check for product identifiers in JavaScript blocks, such as 'item_id', 'psku', 'product_id', or similar keys, even if not visible on the page.
       - Common formats: ABC123, 123456, ABC-123, 123-456

        2. Part Number:
       - Look for: Part #, Model #, Catalog Number, Item Number, MPN (Manufacturer Part Number)
       - Also check for part numbers in JavaScript or data attributes.
       - Common formats: 960A/10, 0.1-10uL, TIP-123, ABC123

        3. Brand/Manufacturer:
           - Look for: Brand name, Manufacturer, Company name
           - Cross-check with the main product title, meta tags, or page header.
           - If not found, try to infer from copyright, footer, or page title.
           - Example: "Brand: Eppendorf", "Manufacturer: Gilson", "by Thermo Fisher Scientific"

        4. Description:
           - Look for: Product description, Features, Specifications summary
           - Focus on key technical details, capacity, volume, or specifications
           - If not found, summarize the most relevant technical or usage info in under 200 characters.

        5. Product Name:
       - Extract the main product name as shown on the product page or title.
       - Remove marketing phrases, taglines, or extra descriptions (e.g., remove text after a dash or ellipsis).
       - Focus on the concise, core product identifier (e.g., '0.1-10uL Certified Pipette Tips').
       - Cross-check with the page header or main title.
       
       
       6. Key Attributes:
       - Extract key attributes (such as volume, type, color, pack size, material, etc.) from the product name and description.
       - Return as a list of key-value pairs, e.g., [{{"key": "volume", "value": "10uL"}}, {{"key": "type", "value": "pipette tip"}}].
       - Only include attributes that are clearly present in the text.


        For each field, only extract if you are confident it matches the visible content on the product page. If not found or unsure, return "Not found".

        Return ONLY a valid JSON object with these exact fields:
        {{
            "sku_id": "extracted SKU or 'Not found'",
            "part_number": "extracted part number or 'Not found'",
            "brand": "brand/manufacturer name or 'Not found'",
            "description": "brief description under 200 chars or 'Not found'",
            "product_name": "main product name or 'Not found'",
            "attributes": [
            {{"key": "attribute name", "value": "attribute value"}},
            ...
        ]
        }}

        Markdown Content:
        {truncated_content}

        Respond with valid JSON only. No introduction or explanation.
        """
        return prompt

    def _validate_extracted_data(self, data: Dict[str, str]) -> Dict[str, str]:
        """Validate and clean extracted data"""
        validated_data = {}
        validation_rules = {
            "sku_id": {"min_length": 2, "max_length": 20, "patterns": [r'^[A-Z0-9\-_/]+$']},
            "part_number": {"min_length": 2, "max_length": 25, "patterns": [r'^[A-Z0-9\-_/\.]+$']},
            "brand": {"min_length": 2, "max_length": 50},
            "description": {"max_length": 200}
        }
        for field, value in data.items():
            if field in validation_rules:
                rules = validation_rules[field]
                if "min_length" in rules and len(value) < rules["min_length"]:
                    value = "Not found"
                elif "max_length" in rules and len(value) > rules["max_length"]:
                    value = value[:rules["max_length"]]
                if "patterns" in rules and value != "Not found":
                    pattern_matches = False
                    for pattern in rules["patterns"]:
                        if re.match(pattern, value, re.IGNORECASE):
                            pattern_matches = True
                            break
                    if not pattern_matches:
                        value = "Not found"
                validated_data[field] = value
            else:
                validated_data[field] = value
        return validated_data