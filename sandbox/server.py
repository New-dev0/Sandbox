import uvicorn
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sandbox.config import settings
from sandbox.api.routes import router
from sandbox.db.database import DatabaseManager
from sandbox.core.docker import docker_manager
from sandbox.monitor.metrics import MetricsCollector
from sandbox.scheduler.tasks import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    metrics_collector = MetricsCollector(docker_manager=docker_manager)
    
    # Startup
    try:
        # Initialize Docker manager
        if not await docker_manager.initialize():
            raise RuntimeError("Docker manager initialization failed")
            
        # Initialize database
        if not await DatabaseManager.initialize():
            raise RuntimeError("Database initialization failed")
        
        # Create tables if they don't exist
        if not await DatabaseManager.create_tables():
            raise RuntimeError("Failed to create database tables")
        
        # Start metrics collector
        if settings.METRICS_ENABLED:
            await metrics_collector.start()
        
        # Start scheduler
        if settings.AUTO_CLEANUP_ENABLED:
            await scheduler.start()
            
        print("✨ Server initialized successfully!")
        yield
        
    except Exception as e:
        print(f"❌ Server initialization failed: {str(e)}")
        raise
    
    finally:
        # Shutdown
        if settings.METRICS_ENABLED:
            await metrics_collector.stop()
        if settings.AUTO_CLEANUP_ENABLED:
            await scheduler.stop()
        await DatabaseManager.close()
        print("👋 Server shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Sandbox API",
    description="Docker sandbox management API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "metrics_enabled": settings.METRICS_ENABLED,
        "cleanup_enabled": settings.AUTO_CLEANUP_ENABLED
    }

def start():
    """Start the server"""
    uvicorn.run(
        "sandbox.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS,
        ssl_keyfile=settings.SSL_KEY_FILE,
        ssl_certfile=settings.SSL_CERT_FILE,
        log_level=settings.LOG_LEVEL.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*"
    )

if __name__ == "__main__":
    start() 