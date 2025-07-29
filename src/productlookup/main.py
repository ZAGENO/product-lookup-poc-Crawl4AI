# main.py
import asyncio
import logging
import signal
import sys
import os
from concurrent.futures import ThreadPoolExecutor
import grpc
from productlookup.protos import product_search_pb2_grpc
from productlookup.controller.product_search_servicer import ProductSearchServicer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProductSearchServer:
    """Async gRPC server for product search with crawl4ai + Ollama"""

    def __init__(self):
        self.server = None
        self.servicer = None
        self.executor = ThreadPoolExecutor(max_workers=10)

    async def start(self, port: int = None):
        """Start the gRPC server"""
        try:
            # Get port from environment or use default
            port = port or int(os.getenv("GRPC_PORT", "50051"))

            # Create the servicer
            self.servicer = ProductSearchServicer()
            await self.servicer.initialize()
            logger.info("Initialized ProductSearchServicer with crawl4ai + Ollama")

            # Create the gRPC server
            self.server = grpc.aio.server(self.executor)
            product_search_pb2_grpc.add_ProductSearchServicer_to_server(self.servicer, self.server)

            # Listen on port
            listen_addr = f'[::]:{port}'
            self.server.add_insecure_port(listen_addr)

            # Start the server
            await self.server.start()
            logger.info(f"Product Search Server started on {listen_addr}")
            logger.info("Server is ready to handle requests...")

            # Setup signal handlers for graceful shutdown
            def signal_handler(signum, frame):
                logger.info(f"Received shutdown signal {signum}")
                asyncio.create_task(self.stop())

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # Keep the server running
            await self.server.wait_for_termination()

        except Exception as e:
            logger.error(f"Error starting server: {str(e)}", exc_info=True)
            await self.stop()
            sys.exit(1)

    async def stop(self):
        """Stop the gRPC server gracefully"""
        try:
            logger.info("Shutting down server...")

            # Stop accepting new requests
            if self.server:
                await self.server.stop(grace=5)
                logger.info("gRPC server stopped")

            # Cleanup servicer
            if self.servicer:
                await self.servicer.cleanup()
                logger.info("ProductSearchServicer cleaned up")

            # Shutdown thread pool
            if self.executor:
                self.executor.shutdown(wait=True)
                logger.info("Thread pool shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}", exc_info=True)


async def serve():
    """Main entry point for the server"""
    server = ProductSearchServer()
    await server.start()


def main():
    """Synchronous entry point for compatibility"""
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()