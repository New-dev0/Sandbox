import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sandbox.api.routes import router
from sandbox.config import settings
from sandbox.monitor.metrics import MetricsCollector
from sandbox.scheduler.tasks import SandboxScheduler
from sandbox.core.docker import docker_manager
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Sandbox API",
    description="Docker sandbox management API with Traefik integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create monitoring and scheduler instances
metrics_collector = MetricsCollector(docker_manager)
scheduler = SandboxScheduler(docker_manager)

@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup"""
    await metrics_collector.start()
    await scheduler.start()
    logger.info("Background tasks started")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop background tasks on app shutdown"""
    await metrics_collector.stop()
    await scheduler.stop()
    logger.info("Background tasks stopped")

# Include API routes
app.include_router(router)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "metrics_enabled": settings.METRICS_ENABLED,
        "auto_cleanup": settings.AUTO_CLEANUP_ENABLED
    }

def main():
    """Main entry point"""
    try:
        # Start Uvicorn server
        uvicorn.run(
            "sandbox.__main__:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=settings.RELOAD,
            ssl_keyfile=settings.SSL_KEY_FILE if settings.TRAEFIK_ENTRYPOINT == "websecure" else None,
            ssl_certfile=settings.SSL_CERT_FILE if settings.TRAEFIK_ENTRYPOINT == "websecure" else None,
            log_level=settings.LOG_LEVEL,
            workers=settings.WORKERS
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise

if __name__ == "__main__":
    main()
