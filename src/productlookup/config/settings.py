import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Google Search API settings
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_PSE_ID = os.getenv("GOOGLE_PSE_ID")

# gRPC server settings
GRPC_PORT = os.getenv("GRPC_PORT", "50051")

# Crawler settings
CRAWLER_CONFIG_PATH = os.getenv("CRAWLER_CONFIG_PATH", "src/productlookup/config/crawler_config.json")

# Ollama settings
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")

# Search settings
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "8"))


# Extraction settings
EXTRACTION_TIMEOUT = int(os.getenv("EXTRACTION_TIMEOUT", "45000"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2"))
BATCH_DELAY = int(os.getenv("BATCH_DELAY", "3"))