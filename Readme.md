# Product Search Microservice (gRPC)

A gRPC microservice that searches for products using Google Programmable Search Engine (PSE) and extracts structured data using Amazon Bedrock's Titan LLM.

## Features

- Query Google PSE with search terms
- Crawl resulting webpages to extract content
- Use LLM locally via Ollama (Mistral) to extract structured product data
- Return clean, structured product data via gRPC

## Local Setup 

### Prerequisites

- Python 3.9+
- Poetry (for dependency management)
- Ollama (for local LLM processing)

### Step 1: Install Ollama

1. **Install Ollama**:
   ```bash
   # macOS
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Linux
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Windows
   # Download from https://ollama.ai/download
   ```

2. **Start Ollama and pull Mistral model**:
   ```bash
   # Start Ollama service
   ollama serve
   
   # In a new terminal, pull the Mistral model
   ollama pull mistral:latest
   ```

### Step 2: Clone and Setup Project

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd product-lookup-poc-crawl4ai
   ```

2. **Install dependencies with Poetry**:
   ```bash
   # Install Poetry if not already installed
   pip install poetry==1.5.1
   
   # Install project dependencies
   poetry install
   ```

### Step 3: Environment Configuration

1. **Create a `.env` file** in the project root:
   ```bash
   # Google Search API Configuration
   GOOGLE_API_KEY=your_google_api_key_here
   GOOGLE_SEARCH_ENGINE_ID=your_google_search_engine_id_here
   
   # Ollama Configuration
   OLLAMA_HOST=http://localhost:11434
   OLLAMA_MODEL=mistral:latest
   
   # Crawler Configuration
   CRAWLER_CONFIG_PATH=src/productlookup/config/crawler_config.json
   MEDICAL_LAB_CONFIG_PATH=src/productlookup/config/medical_lab_config.json
   
   # Search Configuration
   MAX_SEARCH_RESULTS=8
   GRPC_PORT=50051
   
   # Extraction Configuration
   EXTRACTION_TIMEOUT=45000
   BATCH_SIZE=2
   BATCH_DELAY=3
   ```

2. **Get Google API credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Enable Custom Search API
   - Create API key
   - Create a Custom Search Engine at [Google Programmable Search Engine](https://programmablesearchengine.google.com/)
   - Get your Search Engine ID

### Step 4: Generate gRPC Code

```bash
# Navigate to protos directory
cd src/productlookup/protos

# Generate gRPC code
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. product_search.proto

# Return to project root
cd ../../../
```

### Step 5: Run the Service

1. **Activate Poetry shell**:
   ```bash
   poetry shell
   ```

2. **Start the gRPC server**:
   ```bash
   python -m src.productlookup.main
   ```

3. **Verify the service is running**:
   ```bash
   # Test with grpcurl (install if needed: brew install grpcurl)
   grpcurl -import-path src \
     -proto productlookup/protos/product_search.proto \
     -plaintext \
     -d '{"query": "pipette tips 10ul"}' \
     localhost:50051 \
     productlookup.ProductSearch/SearchProduct
   ```

### Step 6: Development Workflow

1. **For development**, you can run the service with auto-reload:
   ```bash
   # Install watchdog for auto-reload
   poetry add watchdog
   
   # Run with auto-reload (create a script or use your IDE)
   watchmedo auto-restart --patterns="*.py" --recursive -- python -m src.productlookup.main
   ```

2. **Testing the service**:
   ```bash
   # Run tests
   poetry run pytest tests/
   
   # Run specific test
   poetry run pytest tests/test_product_search.py -v
   ```

## Troubleshooting

### Common Issues

1. **Ollama not running**:
   ```bash
   # Check if Ollama is running
   curl http://localhost:11434/api/tags
   
   # Start Ollama if not running
   ollama serve
   ```

2. **gRPC code not generated**:
   ```bash
   # Install grpcio-tools if missing
   poetry add grpcio-tools
   
   # Regenerate gRPC code
   cd src/productlookup/protos
   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. product_search.proto
   ```

3. **Google API errors**:
   - Verify your API key is correct
   - Check if Custom Search API is enabled
   - Verify your Search Engine ID is correct
   - Check API quotas and billing

4. **Port already in use**:
   ```bash
   # Check what's using port 50051
   lsof -i :50051
   
   # Kill the process or change GRPC_PORT in .env
   ```

### Environment Variables

Required environment variables:

- `GOOGLE_API_KEY` - Your Google API key
- `GOOGLE_SEARCH_ENGINE_ID` - Your Google Custom Search Engine ID
- `GRPC_PORT` - Port for gRPC server (default: 50051)
- `MAX_WORKERS` - Maximum worker threads (default: 10)
- `CRAWLER_CONFIG_PATH` - Path to crawler configuration JSON
- `OLLAMA_HOST` - Ollama service URL (default: http://localhost:11434)
- `OLLAMA_MODEL` - Ollama model to use (default: mistral:latest)
- `MAX_SEARCH_RESULTS` - Maximum search results to return (default: 8)

## API Usage

### Using grpcurl

```bash
# Basic search
grpcurl -import-path src \
  -proto productlookup/protos/product_search.proto \
  -plaintext \
  -d '{"query": "pipette tips 10ul"}' \
  localhost:50051 \
  productlookup.ProductSearch/SearchProduct

# Search with different query
grpcurl -import-path src \
  -proto productlookup/protos/product_search.proto \
  -plaintext \
  -d '{"query": "microscope slides"}' \
  localhost:50051 \
  productlookup.ProductSearch/SearchProduct
```


```