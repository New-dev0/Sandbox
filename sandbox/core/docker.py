from typing import Optional, Dict, Any, List
import docker
from docker.errors import APIError, NotFound as  ImageNotFound
from sandbox.config import settings
from sandbox.core.metadata import DOCKER_API_VERSION
from pathlib import Path
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DockerManager:
    def __init__(self):
        try:
            # Try using direct socket connection first
            self.client = docker.DockerClient(
                base_url='unix:///var/run/docker.sock',
                version='auto',
                use_ssh_client=False
            )
            logger.info("Connected to Docker using Unix socket")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {str(e)}")
            raise
        
        self.volumes_root = Path(settings.VOLUMES_ROOT)
        
    async def initialize(self):
        """Initialize Docker manager and ensure network exists"""
        try:
            # Test connection
            self.client.ping()
            logger.info("Successfully pinged Docker daemon")
            
            # Ensure network exists
            network_id = await self.ensure_network(
                "traefik-net",
                driver="bridge",
                labels={
                    "traefik.enable": "true"
                }
            )
            logger.info(f"Ensured network traefik-net exists with ID: {network_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Docker manager: {str(e)}")
            return False

    async def pull_image(self, image: str) -> bool:
        """Pull Docker image if not exists"""
        try:
            self.client.images.get(image)
            return True
        except ImageNotFound:
            try:
                self.client.images.pull(image)
                return True
            except APIError as e:
                return False

    async def create_container(
        self,
        image: str,
        command: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        resources: Optional[Dict[str, Any]] = None,
        labels: Optional[Dict[str, str]] = None,
        host_config: Optional[Dict[str, Any]] = None,
        ports: Optional[Dict[str, int]] = None,
        network: Optional[str] = None
    ) -> str:
        """Create a new container"""
        try:
            # Convert resources to Docker API parameters
            if resources:
                if hasattr(resources, 'dict'):
                    resources = resources.dict()
                    
                mem_limit = resources.get("memory", "512m")
                cpu_quota = int(resources.get("cpu", 1) * 100000)
                pids_limit = resources.get("pids", 100)
            else:
                mem_limit = "512m"
                cpu_quota = 100000
                pids_limit = 100

            # Prepare port bindings and exposed ports
            port_bindings = {}
            exposed_ports = {}
            if ports:
                for port_spec, host_port in ports.items():
                    exposed_ports[port_spec] = {}
                    port_bindings[port_spec] = [{"HostPort": str(host_port)}]

            # Create host config
            host_config_params = {
                "mem_limit": mem_limit,
                "cpu_quota": cpu_quota,
                "cpu_period": 100000,
                "pids_limit": pids_limit,
                "network_mode": network or "traefik-net",
                "port_bindings": port_bindings
            }
            
            # Add volume bindings if present
            if host_config and 'binds' in host_config:
                host_config_params['binds'] = host_config['binds']

            # Create container with proper parameters using low-level API
            container = self.client.api.create_container(
                image=image,
                command=command,
                environment=environment,
                labels=labels,
                host_config=self.client.api.create_host_config(**host_config_params),
                ports=list(exposed_ports.keys()) if exposed_ports else None,
                detach=True
            )
            
            return container['Id']
        except APIError as e:
            logger.error(f"Failed to create container: {str(e)}")
            raise RuntimeError(f"Failed to create container: {str(e)}")

    def _prepare_host_config(self, resources: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Prepare container host config with resource limits"""
        if resources is None:
            resources = {}
            
        # Convert Pydantic model to dict if needed
        if hasattr(resources, 'dict'):
            resources = resources.dict()
        
        return {
            "mem_limit": resources.get("memory", "512m"),
            "cpu_quota": int(resources.get("cpu", 1) * 100000),  # Convert CPU cores to quota
            "cpu_period": 100000,
            "pids_limit": resources.get("pids", 100),
            "read_only": resources.get("read_only", True),
            "network_mode": "traefik-net" if resources.get("network", True) else "none"
        }

    def start_container(self, container_id: str) -> None:
        """Start a container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
        except APIError as e:
            raise RuntimeError(f"Failed to start container: {str(e)}")

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
        except APIError as e:
            raise RuntimeError(f"Failed to stop container: {str(e)}")

    def remove_container(self, container_id: str, force: bool = True) -> None:
        """Remove a container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
        except APIError as e:
            raise RuntimeError(f"Failed to remove container: {str(e)}")

    def get_container_logs(self, container_id: str, tail: int = 100) -> tuple[str, str]:
        """Get container logs"""
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(
                stdout=True,
                stderr=True,
                tail=tail,
                stream=False
            ).decode('utf-8')
            
            # Split logs into stdout and stderr
            stdout_logs = []
            stderr_logs = []
            
            for line in logs.splitlines():
                if line.startswith('stderr'):
                    stderr_logs.append(line[6:])
                else:
                    stdout_logs.append(line[6:])
                    
            return '\n'.join(stdout_logs), '\n'.join(stderr_logs)
        except APIError as e:
            raise RuntimeError(f"Failed to get container logs: {str(e)}")

    def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """Get container status"""
        try:
            container = self.client.containers.get(container_id)
            # Parse dates safely
            started_at = container.attrs['State'].get('StartedAt', '')
            finished_at = container.attrs['State'].get('FinishedAt', '')
            
            # Handle timezone format
            def format_date(date_str: str) -> str:
                if not date_str or date_str == "0001-01-01T00:00:00Z":
                    return ""
                try:
                    # Remove nanoseconds and normalize timezone
                    if "." in date_str:
                        date_str = date_str.split(".")[0]
                    if "+" in date_str:
                        date_str = date_str.split("+")[0]
                    return date_str + "Z"
                except Exception:
                    return ""
                
            return {
                "status": container.status,
                "running": container.status == "running",
                "exit_code": container.attrs['State'].get('ExitCode'),
                "started_at": format_date(started_at),
                "finished_at": format_date(finished_at)
            }
        except APIError as e:
            raise RuntimeError(f"Failed to get container status: {str(e)}")

    async def get_container_stats_async(self, container_id: str) -> Dict[str, Any]:
        """Async wrapper for get_container_stats"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_container_stats, container_id)

    def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """Get container resource usage statistics"""
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            # Calculate CPU percentage safely
            cpu_percent = 0.0
            try:
                cpu_stats = stats.get("cpu_stats", {})
                precpu_stats = stats.get("precpu_stats", {})
                
                cpu_usage = cpu_stats.get("cpu_usage", {})
                precpu_usage = precpu_stats.get("cpu_usage", {})
                
                cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
                system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
                
                if system_delta > 0 and cpu_usage.get("percpu_usage"):
                    cpu_percent = (cpu_delta / system_delta) * len(cpu_usage["percpu_usage"]) * 100.0
            except (KeyError, TypeError, ZeroDivisionError) as e:
                logger.warning(f"Error calculating CPU stats: {e}")

            # Memory usage in bytes safely
            memory_stats = stats.get("memory_stats", {})
            mem_usage = memory_stats.get("usage", 0)
            mem_limit = memory_stats.get("limit", 0)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0
            
            # Network stats safely
            networks = stats.get("networks", {})
            net_rx = networks.get("eth0", {}).get("rx_bytes", 0)
            net_tx = networks.get("eth0", {}).get("tx_bytes", 0)
            
            return {
                "cpu_percent": round(cpu_percent, 2),
                "mem_usage": mem_usage,
                "mem_limit": mem_limit,
                "mem_percent": round(mem_percent, 2),
                "net_rx": net_rx,
                "net_tx": net_tx
            }
        except Exception as e:
            logger.error(f"Failed to get container stats: {str(e)}")
            return {
                "cpu_percent": 0,
                "mem_usage": 0,
                "mem_limit": 0,
                "mem_percent": 0,
                "net_rx": 0,
                "net_tx": 0
            }

    def get_volume_path(self, sandbox_id: str, volume_id: str, path: str = "/") -> str:
        """Get absolute path for a volume path"""
        volume_root = Path(settings.VOLUMES_ROOT) / sandbox_id / volume_id
        if not volume_root.exists():
            raise RuntimeError(f"Volume {volume_id} not found for sandbox {sandbox_id}")
            
        target_path = (volume_root / path.lstrip("/")).resolve()
        if not str(target_path).startswith(str(volume_root)):
            raise RuntimeError("Path traversal not allowed")
            
        return str(target_path)

    def create_volume(self, sandbox_id: str, volume_id: str) -> str:
        """Create a new volume directory"""
        volume_path = self.volumes_root / sandbox_id / volume_id
        volume_path.mkdir(parents=True, exist_ok=True)
        return str(volume_path)
        
    def delete_volume(self, sandbox_id: str, volume_id: str) -> None:
        """Delete a volume directory"""
        volume_path = self.volumes_root / sandbox_id / volume_id
        if volume_path.exists():
            import shutil
            shutil.rmtree(str(volume_path))
            
    def list_volumes(self, sandbox_id: str) -> List[str]:
        """List all volumes for a sandbox"""
        sandbox_path = self.volumes_root / sandbox_id
        if not sandbox_path.exists():
            return []
        return [d.name for d in sandbox_path.iterdir() if d.is_dir()]

    async def create_docker_volume(self, size: str) -> str:
        """Create a Docker volume with size limit"""
        try:
            volume = self.client.volumes.create(
                driver='local',
                driver_opts={
                    'size': size,
                    'type': 'tmpfs',
                    'device': 'tmpfs'
                }
            )
            return volume.name
        except APIError as e:
            raise RuntimeError(f"Failed to create volume: {str(e)}")

    async def remove_docker_volume(self, volume_id: str) -> None:
        """Remove a Docker volume"""
        try:
            volume = self.client.volumes.get(volume_id)
            volume.remove(force=True)
        except APIError as e:
            raise RuntimeError(f"Failed to remove volume: {str(e)}")

    def get_container_volumes(self, container_id: str) -> List[str]:
        """Get volume IDs attached to a container"""
        try:
            container = self.client.containers.get(container_id)
            mounts = container.attrs.get('Mounts', [])
            return [m['Name'] for m in mounts if m['Type'] == 'volume']
        except APIError as e:
            raise RuntimeError(f"Failed to get container volumes: {str(e)}")

    async def build_image(
        self, 
        tag: str, 
        dockerfile: Optional[str] = None,
        context_path: Optional[str] = "."
    ) -> bool:
        """Build Docker image from Dockerfile"""
        try:
            # If dockerfile content is provided, write it to a temp file
            if dockerfile:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.dockerfile') as f:
                    f.write(dockerfile)
                    f.flush()
                    self.client.images.build(
                        path=context_path,
                        dockerfile=f.name,
                        tag=tag,
                        rm=True,  # Remove intermediate containers
                        forcerm=True  # Force remove intermediate containers
                    )
            else:
                # Use existing Dockerfile in context path
                self.client.images.build(
                    path=context_path,
                    tag=tag,
                    rm=True,
                    forcerm=True
                )
            return True
        except APIError as e:
            return False

    async def exec_command(self, container_id: str, command: str) -> str:
        """Execute a command in a running container and return the output"""
        try:
            container = self.client.containers.get(container_id)
            if container.status != "running":
                raise RuntimeError("Container is not running")
                
            exec_id = self.client.api.exec_create(
                container_id,
                command,
                stdout=True,
                stderr=True
            )
            output = self.client.api.exec_start(exec_id)
            return output.decode('utf-8')
        except APIError as e:
            raise RuntimeError(f"Failed to execute command: {str(e)}")

    async def stream_output(self, container_id: str, command: str):
        """Stream command output from a container"""
        try:
            container = self.client.containers.get(container_id)
            if container.status != "running":
                raise RuntimeError("Container is not running")
                
            exec_id = self.client.api.exec_create(
                container_id,
                command,
                stdout=True,
                stderr=True
            )
            
            for chunk in self.client.api.exec_start(exec_id, stream=True):
                yield chunk.decode('utf-8')
        except APIError as e:
            raise RuntimeError(f"Failed to stream output: {str(e)}")

    async def list_containers(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all containers with optional status filter"""
        try:
            filters = {}
            if status:
                filters["status"] = status
                
            containers = self.client.containers.list(all=True, filters=filters)
            return [
                {
                    "container_id": c.id,
                    "image": c.image.tags[0] if c.image.tags else c.image.id,
                    "status": c.status,
                    "name": c.name,
                    "created": c.attrs["Created"],
                    "state": {
                        "running": c.attrs["State"]["Running"],
                        "exit_code": c.attrs["State"]["ExitCode"],
                        "started_at": c.attrs["State"]["StartedAt"],
                        "finished_at": c.attrs["State"]["FinishedAt"]
                    }
                }
                for c in containers
            ]
        except APIError as e:
            raise RuntimeError(f"Failed to list containers: {str(e)}")

    async def create_network_volume(self, name: str, driver: str = "local", size: Optional[str] = None) -> str:
        """Create a network volume with optional size limit"""
        try:
            opts = {}
            if size:
                opts["size"] = size
                
            volume = self.client.volumes.create(
                name=name,
                driver=driver,
                driver_opts=opts
            )
            return volume.name
        except APIError as e:
            raise RuntimeError(f"Failed to create network volume: {str(e)}")

    async def mount_network_volume(self, container_id: str, volume_name: str, mount_path: str) -> None:
        """Mount a network volume to a running container"""
        try:
            container = self.client.containers.get(container_id)
            if container.status != "running":
                raise RuntimeError("Container is not running")
                
            # Update container with new mount
            self.client.api.update_container(
                container_id,
                mounts=[{
                    "Type": "volume",
                    "Source": volume_name,
                    "Target": mount_path,
                }]
            )
        except APIError as e:
            raise RuntimeError(f"Failed to mount network volume: {str(e)}")

    async def unmount_network_volume(self, container_id: str, volume_name: str) -> None:
        """Unmount a network volume from a container"""
        try:
            container = self.client.containers.get(container_id)
            current_mounts = container.attrs.get("Mounts", [])
            
            # Filter out the specified volume
            new_mounts = [
                mount for mount in current_mounts 
                if mount.get("Name") != volume_name
            ]
            
            # Update container with remaining mounts
            self.client.api.update_container(
                container_id,
                mounts=new_mounts
            )
        except APIError as e:
            raise RuntimeError(f"Failed to unmount network volume: {str(e)}")

    async def get_container_urls(self, container_id: str) -> Dict[str, str]:
        """Get all URLs for a container's exposed ports"""
        try:
            container = self.client.containers.get(container_id)
            labels = container.labels or {}
            
            urls = {}
            for label, value in labels.items():
                if label.startswith("traefik.http.routers.") and label.endswith(".rule"):
                    # Extract port and domain from label
                    route_name = label.split(".")[3]
                    port = labels.get(f"traefik.http.services.{route_name}.loadbalancer.server.port")
                    
                    # Parse Host rule to get domain
                    if "Host(`" in value:
                        domain = value.split("Host(`")[1].split("`)")[0]
                        urls[port] = f"https://{domain}"
                        
            return urls
        except APIError as e:
            raise RuntimeError(f"Failed to get container URLs: {str(e)}")

    async def ensure_network(self, name: str, driver: str = "bridge", labels: Optional[Dict[str, str]] = None) -> str:
        """Create network if it doesn't exist"""
        try:
            try:
                network = self.client.networks.get(name)
                logger.info(f"Found existing network: {name}")
                return network.id
            except APIError:
                logger.info(f"Creating new network: {name}")
                network = self.client.networks.create(
                    name=name,
                    driver=driver,
                    labels=labels,
                    attachable=True,  # Allow containers to be attached
                    check_duplicate=True  # Prevent duplicates
                )
                return network.id
        except APIError as e:
            logger.error(f"Failed to ensure network: {str(e)}")
            raise RuntimeError(f"Failed to ensure network: {str(e)}")

    async def connect_to_network(self, container_id: str, network_name: str) -> None:
        """Connect container to network"""
        try:
            network = self.client.networks.get(network_name)
            network.connect(container_id)
        except APIError as e:
            raise RuntimeError(f"Failed to connect to network: {str(e)}")

    async def disconnect_from_network(self, container_id: str, network_name: str) -> None:
        """Disconnect container from network"""
        try:
            network = self.client.networks.get(network_name)
            network.disconnect(container_id)
        except APIError as e:
            raise RuntimeError(f"Failed to disconnect from network: {str(e)}")

# Global docker manager instance
docker_manager = DockerManager() 