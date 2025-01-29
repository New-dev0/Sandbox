import asyncio
import logging
from datetime import datetime, timedelta
from sandbox.config import settings
from sandbox.core.docker import docker_manager

logger = logging.getLogger(__name__)

class SandboxScheduler:
    def __init__(self, docker_manager):
        self.docker_manager = docker_manager
        self.running = False
        
    async def start(self):
        """Start scheduler tasks"""
        if settings.AUTO_CLEANUP_ENABLED:
            self.running = True
            asyncio.create_task(self._cleanup_task())
            asyncio.create_task(self._timeout_check_task())
            logger.info("Scheduler tasks started")
            
    async def stop(self):
        """Stop scheduler tasks"""
        self.running = False
        
    async def _cleanup_task(self):
        """Cleanup old and inactive containers"""
        while self.running:
            try:
                containers = await self.docker_manager.list_containers()
                now = datetime.now()
                
                for container in containers:
                    container_id = container["container_id"]
                    
                    # Check container age
                    created = datetime.fromisoformat(container["created"].replace('Z', '+00:00'))
                    age = (now - created).total_seconds()
                    
                    if age > settings.MAX_CONTAINER_AGE:
                        logger.info(f"Removing old container {container_id}")
                        await self.docker_manager.remove_container(container_id, force=True)
                        continue
                        
                    # Check inactivity
                    if container["state"]["running"]:
                        stats = await self.docker_manager.get_container_stats(container_id)
                        if stats and stats["inactive_time"] > settings.INACTIVE_TIMEOUT:
                            logger.info(f"Stopping inactive container {container_id}")
                            await self.docker_manager.stop_container(container_id)
                            
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                
            await asyncio.sleep(settings.CLEANUP_INTERVAL)
            
    async def _timeout_check_task(self):
        """Check and enforce container timeouts"""
        while self.running:
            try:
                containers = await self.docker_manager.list_containers("running")
                
                for container in containers:
                    container_id = container["container_id"]
                    labels = container.get("labels", {})
                    
                    # Check timeout
                    timeout = int(labels.get("sandbox.timeout", 0))
                    if timeout > 0:
                        started = datetime.fromisoformat(container["state"]["started_at"].replace('Z', '+00:00'))
                        runtime = (datetime.now() - started).total_seconds()
                        
                        if runtime > timeout:
                            logger.info(f"Container {container_id} reached timeout, stopping")
                            await self.docker_manager.stop_container(container_id)
                            
            except Exception as e:
                logger.error(f"Error in timeout check task: {str(e)}")
                
            await asyncio.sleep(10)  # Check every 10 seconds
            
    async def update_container_timeout(self, container_id: str, timeout: int):
        """Update container timeout"""
        try:
            await self.docker_manager.update_container_labels(
                container_id,
                {"sandbox.timeout": str(timeout)}
            )
            logger.info(f"Updated timeout for container {container_id} to {timeout}s")
        except Exception as e:
            logger.error(f"Error updating container timeout: {str(e)}")
            raise 


scheduler = SandboxScheduler(
    docker_manager=docker_manager
)