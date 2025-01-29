from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional, List, Union
from sandbox.core.docker import docker_manager
from sandbox.config import settings
from sandbox.scheduler.tasks import scheduler  # Import scheduler instance
import os
from pathlib import Path
import logging
from fastapi.responses import StreamingResponse
import zipfile
import io
import tarfile

logger = logging.getLogger(__name__)


# Create routers for different endpoint groups
sandbox_router = APIRouter(prefix="/api/v1/sandboxes", tags=["Sandboxes"])
volume_router = APIRouter(prefix="/api/v1/volumes", tags=["Volumes"])
metrics_router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])

# Validate settings
if not hasattr(settings, 'DOMAIN'):
    raise RuntimeError("DOMAIN setting is required for Traefik integration")
if not hasattr(settings, 'VOLUMES_ROOT'):
    raise RuntimeError("VOLUMES_ROOT setting is required for volume management")

class ResourceConfig(BaseModel):
    cpu: float = Field(default=1.0, ge=0.1, le=8.0, description="Number of CPU cores")
    memory: str = Field(default="512m", description="Memory limit (e.g. 512m, 1g)")
    gpu: Optional[str] = Field(default=None, description="GPU type (e.g. H100, A100)")
    timeout: Optional[int] = Field(default=None, ge=1, description="Execution timeout in seconds")
    max_retries: Optional[int] = Field(default=None, ge=0, description="Maximum number of retries")

    @validator('memory')
    def validate_memory(cls, v):
        if not any(v.endswith(unit) for unit in ['k', 'm', 'g', 'K', 'M', 'G']):
            raise ValueError("Memory must end with k, m, or g (case insensitive)")
        try:
            size = int(v[:-1])
            if size <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("Invalid memory size format")
        return v

class VolumeConfig(BaseModel):
    size: str
    driver: Optional[str] = "local"
    network: bool = False

    @validator('size')
    def validate_size(cls, v):
        if not any(v.endswith(unit) for unit in ['k', 'm', 'g', 'K', 'M', 'G']):
            raise ValueError("Size must end with k, m, or g (case insensitive)")
        try:
            size = int(v[:-1])
            if size <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("Invalid size format")
        return v

class PortConfig(BaseModel):
    port: int = Field(ge=1, le=65535)
    protocol: str = Field(default="http", pattern="^(http|https|tcp|udp)$")
    external: Optional[int] = Field(default=None, ge=1, le=65535)
    subdomain: Optional[str] = Field(default=None, pattern="^[a-z0-9-]+$")

    @validator('subdomain')
    def validate_subdomain(cls, v):
        if v and (len(v) < 3 or len(v) > 63):
            raise ValueError("Subdomain must be between 3 and 63 characters")
        return v

class CreateSandboxRequest(BaseModel):
    image: str = Field(..., pattern="^[a-zA-Z0-9][a-zA-Z0-9_.-]+(/[a-zA-Z0-9_.-]+)*:[a-zA-Z0-9_.-]+$")
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
            used_subdomains = set()
            for port in v:
                if port.port in used_ports:
                    raise ValueError(f"Duplicate port: {port.port}")
                if port.external and port.external in used_ports:
                    raise ValueError(f"Duplicate external port: {port.external}")
                if port.subdomain and port.subdomain in used_subdomains:
                    raise ValueError(f"Duplicate subdomain: {port.subdomain}")
                used_ports.add(port.port)
                if port.external:
                    used_ports.add(port.external)
                if port.subdomain:
                    used_subdomains.add(port.subdomain)
        return v

    @validator('environment')
    def validate_env(cls, v):
        if v:
            for key in v.keys():
                if not key.isidentifier() and not all(c.isalnum() or c == '_' for c in key):
                    raise ValueError(f"Invalid environment variable name: {key}")
        return v

class VolumeOperation(BaseModel):
    sandbox_id: str
    volume_id: str
    path: str

class FileContent(BaseModel):
    content: str

class EntrypointUpdate(BaseModel):
    entrypoint: Optional[Union[str, List[str]]] = None
    command: Optional[Union[str, List[str]]] = None

class EnvUpdate(BaseModel):
    environment: Dict[str, str]
    merge: bool = True  # If True, merge with existing env vars. If False, replace all

@sandbox_router.post("", summary="Create Sandbox", description="Create a new sandbox container with specified image and volumes")
async def create_sandbox(request: CreateSandboxRequest):
    """Create a new sandbox container with specified image and volumes"""
    try:
        # Build or pull image
        if request.force_build and request.build_context:
            if not await docker_manager.build_image(
                request.image, 
                dockerfile=request.build_context.get('dockerfile'),
                context_path=request.build_context.get('context_path')
            ):
                raise HTTPException(status_code=400, detail="Failed to build image")
        elif not await docker_manager.pull_image(request.image):
            raise HTTPException(status_code=400, detail="Failed to pull image")
            
        # Create volumes first
        volume_binds = {}
        if request.volumes:
            for vol_name, config in request.volumes.items():
                volume_id = await docker_manager.create_docker_volume(config.size)
                volume_binds[volume_id] = {
                    'bind': f'/mnt/{vol_name}',
                    'mode': 'rw'
                }

        # Prepare Traefik labels and port bindings
        labels = {
            "traefik.enable": "true",
            # Global HTTPS redirect
            "traefik.http.routers.http-catchall.rule": "hostregexp(`{host:.+}`)",
            "traefik.http.routers.http-catchall.entrypoints": "web",
            "traefik.http.routers.http-catchall.middlewares": "redirect-to-https",
            "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme": "https",
            # Security headers
            "traefik.http.middlewares.security-headers.headers.forcestsheader": "true",
            "traefik.http.middlewares.security-headers.headers.sslredirect": "true",
            "traefik.http.middlewares.security-headers.headers.stsincludesubdomains": "true",
            "traefik.http.middlewares.security-headers.headers.stsseconds": "31536000",
            "traefik.http.middlewares.security-headers.headers.stspreload": "true",
            "traefik.http.middlewares.security-headers.headers.customframeoptions": "SAMEORIGIN"
        }
        ports = {}
        urls = {}
        port_info = []
        
        if request.ports:
            for port in request.ports:
                # Port binding
                ports[f"{port.port}/{port.protocol}"] = port.external or port.port
                
                # Traefik routing
                if port.protocol == "http":
                    route_name = f"sandbox-{port.port}"
                    subdomain = port.subdomain or f"s-{port.port}"
                    domain = f"{subdomain}.{settings.DOMAIN}"
                    
                    labels.update({
                        f"traefik.http.routers.{route_name}.rule": f"Host(`{domain}`)",
                        f"traefik.http.routers.{route_name}.entrypoints": settings.TRAEFIK_ENTRYPOINT,
                        f"traefik.http.routers.{route_name}.tls": "true",
                        f"traefik.http.routers.{route_name}.tls.certresolver": settings.TRAEFIK_CERT_RESOLVER,
                        f"traefik.http.routers.{route_name}.middlewares": "security-headers",
                        f"traefik.http.services.{route_name}.loadbalancer.server.port": str(port.port),
                        f"traefik.http.services.{route_name}.loadbalancer.server.scheme": "http"
                    })
                    
                    urls[str(port.port)] = f"https://{domain}"
                    port_info.append({
                        "id": len(port_info) + 1,
                        "internal_port": port.port,
                        "external_port": port.external or port.port,
                        "protocol": port.protocol,
                        "url": f"https://{domain}"
                    })

        # Create container with volumes and Traefik config
        container_id = await docker_manager.create_container(
            image=request.image,
            command=request.command,
            environment=request.environment,
            resources=request.resources,
            host_config={'binds': volume_binds} if volume_binds else None,
            labels=labels,
            ports=ports,
            network="traefik-net"  # Traefik network
        )
        
        # Start container
        docker_manager.start_container(container_id)

        # Get container info
        container = docker_manager.client.containers.get(container_id)
        
        # Convert volumes to VolumeInfo
        volume_info = []
        for vol_id, bind in volume_binds.items():
            volume_info.append({
                "id": len(volume_info) + 1,
                "volume_id": vol_id,
                "name": bind['bind'].split('/')[-1],
                "mount_path": bind['bind'],
                "size": 0,  # TODO: Get actual size
                "driver": "local",
                "created_at": container.attrs['Created']
            })
        
        # Return SandboxStatus format
        return {
            "id": 1,  # TODO: Use actual ID from DB
            "container_id": container_id,
            "name": container.name,
            "status": container.status,
            "image": request.image,
            "command": request.command,
            "entrypoint": container.attrs.get('Config', {}).get('Entrypoint'),
            "resources": request.resources.dict() if request.resources else {},
            "environment": request.environment or {},
            "created_at": container.attrs['Created'],
            "started_at": container.attrs['State']['StartedAt'],
            "terminated_at": None,
            "last_active": container.attrs['Created'],
            "auto_remove": True,
            "volumes": volume_info,
            "ports": port_info,
            "urls": urls
        }
        
    except Exception as e:
        # Cleanup volumes on failure
        logger.exception(e)
        if 'volume_binds' in locals():
            for volume_id in volume_binds.keys():
                await docker_manager.remove_docker_volume(volume_id)
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.delete("/{sandbox_id}", summary="Delete Sandbox", description="Delete a sandbox and its associated volumes")
async def delete_sandbox(sandbox_id: str):
    """Delete a sandbox and its associated volumes"""
    try:
        # Get container info to find associated volumes
        volumes = docker_manager.get_container_volumes(sandbox_id)
        
        # Stop and remove container
        docker_manager.stop_container(sandbox_id)
        docker_manager.remove_container(sandbox_id)
        
        # Remove associated volumes
        for volume_id in volumes:
            await docker_manager.remove_docker_volume(volume_id)
            
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@volume_router.get("/{sandbox_id}/{volume_id}/ls", summary="List Directory", description="List contents of a directory in the volume")
async def list_directory(sandbox_id: str, volume_id: str, path: str = "/"):
    """List contents of a directory in the volume"""
    try:
        volume_path = docker_manager.get_volume_path(sandbox_id, volume_id, path)
        entries = os.listdir(volume_path)
        return {
            "entries": [
                {
                    "name": entry,
                    "type": "directory" if os.path.isdir(os.path.join(volume_path, entry)) else "file"
                }
                for entry in entries
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/volumes/{volume_id}/mkdir")
async def make_directory(sandbox_id: str, volume_id: str, path: str):
    """Create a directory in the volume"""
    try:
        volume_path = docker_manager.get_volume_path(sandbox_id, volume_id, path)
        os.makedirs(volume_path, exist_ok=True)
        return {"status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}/volumes/{volume_id}/read")
async def read_file(sandbox_id: str, volume_id: str, path: str):
    """Read file content from the volume"""
    try:
        volume_path = docker_manager.get_volume_path(sandbox_id, volume_id, path)
        if not os.path.isfile(volume_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        with open(volume_path, 'r') as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/volumes/{volume_id}/write")
async def write_file(
    sandbox_id: str, 
    volume_id: str, 
    path: str,
    content: FileContent
):
    """Write content to a file in the volume"""
    try:
        volume_path = docker_manager.get_volume_path(sandbox_id, volume_id, path)
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)
        
        with open(volume_path, 'w') as f:
            f.write(content.content)
        return {"status": "written"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/volumes/{volume_id}/upload")
async def upload_file(
    sandbox_id: str,
    volume_id: str,
    path: str,
    file: UploadFile = File(...)
):
    """Upload a file to the volume"""
    try:
        volume_path = docker_manager.get_volume_path(sandbox_id, volume_id, path)
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)
        
        with open(volume_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        return {"status": "uploaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ExecRequest(BaseModel):
    command: str

@sandbox_router.post("/{sandbox_id}/exec")
async def execute_command(sandbox_id: str, request: ExecRequest):
    """Execute a command in a sandbox container"""
    try:
        output = await docker_manager.exec_command(sandbox_id, request.command)
        return {"output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/exec/stream")
async def stream_command(sandbox_id: str, request: ExecRequest):
    """Stream command output from a sandbox container"""
    try:
        return StreamingResponse(
            docker_manager.stream_output(sandbox_id, request.command),
            media_type="text/plain"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}")
async def get_sandbox_status(sandbox_id: str):
    """Get detailed sandbox status"""
    try:
        status = docker_manager.get_container_status(sandbox_id)
        volumes = docker_manager.get_container_volumes(sandbox_id)
        return {
            "container_id": sandbox_id,
            "status": status,
            "volumes": volumes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/")
async def list_sandboxes(status: Optional[str] = None):
    """List all sandboxes with optional status filter"""
    try:
        sandboxes = await docker_manager.list_containers(status)
        return {
            "sandboxes": sandboxes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/stop")
async def stop_sandbox(sandbox_id: str, timeout: Optional[int] = 10):
    """Stop a sandbox container"""
    try:
        docker_manager.stop_container(sandbox_id, timeout)
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/start")
async def start_sandbox(sandbox_id: str):
    """Start a stopped sandbox container"""
    try:
        docker_manager.start_container(sandbox_id)
        return {"status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/restart")
async def restart_sandbox(sandbox_id: str, timeout: Optional[int] = 10):
    """Restart a sandbox container"""
    try:
        docker_manager.stop_container(sandbox_id, timeout)
        docker_manager.start_container(sandbox_id)
        return {"status": "restarted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NetworkVolumeRequest(BaseModel):
    name: str
    driver: Optional[str] = "local"
    size: Optional[str] = None
    mount_path: Optional[str] = None

@volume_router.post("/network")
async def create_network_volume(request: NetworkVolumeRequest):
    """Create a new network volume"""
    try:
        volume_name = await docker_manager.create_network_volume(
            request.name,
            request.driver,
            request.size
        )
        return {"volume_name": volume_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/volumes/{volume_name}/mount")
async def mount_volume(sandbox_id: str, volume_name: str, mount_path: str):
    """Mount a network volume to a sandbox"""
    try:
        await docker_manager.mount_network_volume(sandbox_id, volume_name, mount_path)
        return {"status": "mounted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/volumes/{volume_name}/unmount")
async def unmount_volume(sandbox_id: str, volume_name: str):
    """Unmount a network volume from a sandbox"""
    try:
        await docker_manager.unmount_network_volume(sandbox_id, volume_name)
        return {"status": "unmounted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}/urls")
async def get_sandbox_urls(sandbox_id: str):
    """Get all URLs for a sandbox's exposed ports"""
    try:
        urls = await docker_manager.get_container_urls(sandbox_id)
        return {"urls": urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NetworkRequest(BaseModel):
    name: str
    driver: Optional[str] = "bridge"
    labels: Optional[Dict[str, str]] = None

@volume_router.post("/network")
async def create_network(request: NetworkRequest):
    """Create a new network"""
    try:
        network_id = await docker_manager.ensure_network(
            request.name,
            request.driver,
            request.labels
        )
        return {"network_id": network_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/networks/{network_name}/connect")
async def connect_to_network(sandbox_id: str, network_name: str):
    """Connect sandbox to network"""
    try:
        await docker_manager.connect_to_network(sandbox_id, network_name)
        return {"status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/networks/{network_name}/disconnect")
async def disconnect_from_network(sandbox_id: str, network_name: str):
    """Disconnect sandbox from network"""
    try:
        await docker_manager.disconnect_from_network(sandbox_id, network_name)
        return {"status": "disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TimeoutUpdate(BaseModel):
    timeout: int = Field(ge=0, description="Timeout in seconds (0 for no timeout)")

@sandbox_router.post("/{sandbox_id}/timeout")
async def update_timeout(sandbox_id: str, request: TimeoutUpdate):
    """Update sandbox timeout"""
    try:
        await scheduler.update_container_timeout(sandbox_id, request.timeout)
        return {"status": "updated", "timeout": request.timeout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@metrics_router.get("/{sandbox_id}")
async def get_sandbox_stats(sandbox_id: str):
    """Get sandbox resource usage stats"""
    try:
        stats = await docker_manager.get_container_stats_async(sandbox_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Stats not available")
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/entrypoint")
async def update_entrypoint(sandbox_id: str, request: EntrypointUpdate):
    """Update container entrypoint and/or command"""
    try:
        container = docker_manager.client.containers.get(sandbox_id)
        
        config = {}
        if request.entrypoint is not None:
            config["Entrypoint"] = request.entrypoint if isinstance(request.entrypoint, list) else [request.entrypoint]
        if request.command is not None:
            config["Cmd"] = request.command if isinstance(request.command, list) else [request.command]
            
        container.update(
            entrypoint=config.get("Entrypoint"),
            command=config.get("Cmd")
        )
        
        # Restart container to apply changes
        container.restart()
        
        return {
            "status": "updated",
            "entrypoint": config.get("Entrypoint"),
            "command": config.get("Cmd")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.post("/{sandbox_id}/env")
async def update_environment(sandbox_id: str, request: EnvUpdate):
    """Update container environment variables"""
    try:
        container = docker_manager.client.containers.get(sandbox_id)
        current_env = {}
        
        # Parse current environment
        for env in container.attrs.get("Config", {}).get("Env", []):
            if "=" in env:
                key, value = env.split("=", 1)
                current_env[key] = value
        
        # Merge or replace environment
        if request.merge:
            new_env = {**current_env, **request.environment}
        else:
            new_env = request.environment
            
        # Format environment for update
        env_list = [f"{k}={v}" for k, v in new_env.items()]
        
        # Update container
        container.update(env=env_list)
        
        # Restart container to apply changes
        container.restart()
        
        return {
            "status": "updated",
            "environment": new_env
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}/env")
async def get_environment(sandbox_id: str):
    """Get container environment variables"""
    try:
        container = docker_manager.client.containers.get(sandbox_id)
        env_dict = {}
        
        # Parse environment variables
        for env in container.attrs.get("Config", {}).get("Env", []):
            if "=" in env:
                key, value = env.split("=", 1)
                env_dict[key] = value
                
        return {"environment": env_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}/entrypoint")
async def get_entrypoint(sandbox_id: str):
    """Get container entrypoint and command"""
    try:
        container = docker_manager.client.containers.get(sandbox_id)
        config = container.attrs.get("Config", {})
        
        return {
            "entrypoint": config.get("Entrypoint"),
            "command": config.get("Cmd")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@sandbox_router.get("/{sandbox_id}/export")
async def export_container_folder(sandbox_id: str, folder_path: str = "/"):
    """Export a container folder as zip file"""
    try:
        container = docker_manager.client.containers.get(sandbox_id)
        memory_file = io.BytesIO()
        
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Get files from container using tar archive
            bits, stat = container.get_archive(folder_path)
            
            # Create temporary tar file
            tar_bytes = io.BytesIO()
            for chunk in bits:
                tar_bytes.write(chunk)
            tar_bytes.seek(0)
            
            # Extract tar and add to zip
            with tarfile.open(fileobj=tar_bytes) as tar:
                for member in tar.getmembers():
                    # Skip if directory
                    if member.isdir():
                        continue
                    # Extract file from tar
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    # Add to zip with relative path
                    rel_path = os.path.relpath(member.name, folder_path)
                    zf.writestr(rel_path, f.read())
        
        # Prepare zip file for response
        memory_file.seek(0)
        
        # Generate filename based on container name/id and folder
        container_name = container.name or container.short_id
        safe_folder = folder_path.replace('/', '_').strip('_')
        filename = f"{container_name}_{safe_folder}.zip" if safe_folder else f"{container_name}.zip"
        
        return StreamingResponse(
            iter([memory_file.getvalue()]),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Combine routers
router = APIRouter()
router.include_router(sandbox_router)
router.include_router(volume_router)
router.include_router(metrics_router) 
