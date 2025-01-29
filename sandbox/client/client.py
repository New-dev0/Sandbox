from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
import httpx
import asyncio
from pathlib import Path
from .models import (
    CreateSandboxRequest, SandboxStatus, VolumeInfo, PortInfo,
    LogEntry, MetricData, Alert, TimeoutUpdate, EntrypointUpdate,
    EnvUpdate, User, UserQuota, VolumeConfig, ResourceConfig
)

class PortConfig(BaseModel):
    port: int = Field(ge=1, le=65535, description="Port to expose from container")

    protocol: str = Field(default="http", pattern="^(http|https|tcp|udp)$")

    @validator('port')
    def validate_port(cls, v):
        if v in [22, 80, 443, 2375, 2376, 2377, 2378, 2379, 2380, 3375]:  # Reserved ports
            raise ValueError(f"Port {v} is reserved")
        return v

class CreateSandboxRequest(BaseModel):
    image: str
    volumes: Optional[Dict[str, VolumeConfig]] = None
    environment: Optional[Dict[str, str]] = None
    resources: Optional[ResourceConfig] = None
    command: Optional[str] = None
    force_build: Optional[bool] = False
    build_context: Optional[Dict[str, str]] = None
    ports: Optional[List[PortConfig]] = None

    @validator('ports')
    def validate_ports(cls, v):
        if v:
            used_ports = set()
            for port in v:
                if port.port in used_ports:
                    raise ValueError(f"Duplicate port: {port.port}")
                used_ports.add(port.port)
        return v

class SandboxError(Exception):
    """Base exception for sandbox operations"""
    pass

class SandboxConnectionError(SandboxError):
    """Raised when connection to sandbox API fails"""
    pass

class SandboxTimeoutError(SandboxError):
    """Raised when sandbox operation times out"""
    pass

class SandboxNotFoundError(SandboxError):
    """Raised when sandbox container is not found"""
    pass

class SandboxOperationError(SandboxError):
    """Raised when sandbox operation fails"""
    pass

class SandboxValidationError(SandboxError):
    """Raised when request validation fails"""
    pass

class SandboxVolumeError(SandboxError):
    """Raised when volume operation fails"""
    pass

class SandboxClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        try:
            self.client = httpx.AsyncClient(timeout=timeout)
        except Exception as e:
            raise SandboxConnectionError(f"Failed to initialize client: {str(e)}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        await self.client.aclose()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    async def create_sandbox(self, request: CreateSandboxRequest) -> SandboxStatus:
        """Create a new sandbox container"""
        try:
            response = await self.client.post(self._url("/sandboxes"), json=request.dict(exclude_none=True))
            print(response.json())

            response.raise_for_status()
            return SandboxStatus(**response.json())
        except httpx.TimeoutException as e:
            raise SandboxTimeoutError(f"Create sandbox operation timed out: {str(e)}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox not found: {str(e)}")
            elif e.response.status_code == 422:
                raise SandboxValidationError(f"Invalid request: {str(e)}")
            else:
                raise SandboxOperationError(f"Failed to create sandbox: {str(e)}")
        except Exception as e:
            raise SandboxOperationError(f"Unexpected error: {str(e)}")

    async def get_sandbox_status(self, sandbox_id: str) -> SandboxStatus:
        """Get sandbox status"""
        try:
            response = await self.client.get(self._url(f"/sandboxes/{sandbox_id}"))
            response.raise_for_status()
            return SandboxStatus(**response.json())
        except httpx.TimeoutException as e:
            raise SandboxTimeoutError(str(e))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def list_sandboxes(self, status: Optional[str] = None) -> List[SandboxStatus]:
        """List all sandboxes"""
        params = {"status": status} if status else None
        try:
            response = await self.client.get(self._url("/sandboxes"), params=params)
            response.raise_for_status()
            return [SandboxStatus(**item) for item in response.json()["sandboxes"]]
        except Exception as e:
            raise SandboxOperationError(str(e))

    async def delete_sandbox(self, sandbox_id: str) -> Dict[str, str]:
        """Delete a sandbox"""
        try:
            response = await self.client.delete(self._url(f"/sandboxes/{sandbox_id}"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def get_sandbox_logs(self, sandbox_id: str, since: Optional[str] = None) -> List[LogEntry]:
        """Get sandbox logs"""
        params = {"since": since} if since else None
        try:
            response = await self.client.get(self._url(f"/sandboxes/{sandbox_id}/logs"), params=params)
            response.raise_for_status()
            return [LogEntry(**entry) for entry in response.json()["logs"]]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def get_sandbox_metrics(self, sandbox_id: str) -> MetricData:
        """Get sandbox metrics"""
        try:
            response = await self.client.get(self._url(f"/sandboxes/{sandbox_id}/metrics"))
            response.raise_for_status()
            return MetricData(**response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def get_sandbox_alerts(self, sandbox_id: str, resolved: Optional[bool] = None) -> List[Alert]:
        """Get sandbox alerts"""
        params = {"resolved": resolved} if resolved is not None else None
        try:
            response = await self.client.get(self._url(f"/sandboxes/{sandbox_id}/alerts"), params=params)
            response.raise_for_status()
            return [Alert(**alert) for alert in response.json()["alerts"]]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def update_timeout(self, sandbox_id: str, timeout: int) -> Dict[str, Any]:
        """Update sandbox timeout"""
        request = TimeoutUpdate(timeout=timeout)
        try:
            response = await self.client.post(
                self._url(f"/sandboxes/{sandbox_id}/timeout"),
                json=request.dict()
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def update_entrypoint(self, sandbox_id: str, request: EntrypointUpdate) -> Dict[str, Any]:
        """Update sandbox entrypoint/command"""
        try:
            response = await self.client.post(
                self._url(f"/sandboxes/{sandbox_id}/entrypoint"),
                json=request.dict(exclude_none=True)
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def update_environment(self, sandbox_id: str, request: EnvUpdate) -> Dict[str, Any]:
        """Update sandbox environment variables"""
        try:
            response = await self.client.post(
                self._url(f"/sandboxes/{sandbox_id}/env"),
                json=request.dict()
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

    async def export_container(self, sandbox_id: str, folder_path: str = "/", output_path: Optional[str] = None) -> Any:
        """Export container folder as zip"""
        try:
            response = await self.client.get(
                self._url(f"/sandboxes/{sandbox_id}/export"),
                params={"folder_path": folder_path}
            )
            response.raise_for_status()
            
            if output_path:
                Path(output_path).write_bytes(response.content)
                return output_path
            return response.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            raise SandboxOperationError(str(e))

