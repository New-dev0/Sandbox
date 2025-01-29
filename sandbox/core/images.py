from typing import List, Dict, Any
import asyncio
from sandbox.core.docker import docker_manager
from sandbox.core.metadata import DEFAULT_RESOURCE_LIMITS

class ImageManager:
    def __init__(self):
        self._image_cache: Dict[str, bool] = {}
        
    async def ensure_image(self, image: str) -> bool:
        """Ensure image is available locally"""
        if image not in self._image_cache:
            self._image_cache[image] = await docker_manager.pull_image(image)
        return self._image_cache[image]

    async def validate_image(self, image: str) -> bool:
        """Validate if image is safe to use"""
        # Add validation logic here (e.g. whitelist check)
        return True

    def get_image_config(self, image: str) -> Dict[str, Any]:
        """Get image configuration and metadata"""
        try:
            img = docker_manager.client.images.get(image)
            return {
                "id": img.id,
                "tags": img.tags,
                "created": img.attrs['Created'],
                "size": img.attrs['Size'],
                "config": img.attrs.get('Config', {})
            }
        except:
            return {}

# Global image manager instance
image_manager = ImageManager() 