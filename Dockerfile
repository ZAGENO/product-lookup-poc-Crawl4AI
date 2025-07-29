FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for grpcio and web crawling
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    wget \
    gnupg \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.5.1

# Copy Poetry configuration
COPY pyproject.toml poetry.lock* /app/

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY src /app/src

# Generate gRPC code (corrected path)
WORKDIR /app/src/productlookup/protos
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. product_search.proto

WORKDIR /app

# Create config directory
RUN mkdir -p /app/config

# Expose gRPC port
EXPOSE 50051

# Run the server
CMD ["python", "-m", "src.productlookup.main"]