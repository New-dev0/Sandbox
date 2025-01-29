from typing import Dict, List, Optional, Union, Any, Annotated
from datetime import datetime
from pydantic import BaseModel, Field, validator

class ResourceConfig(BaseModel):
    cpu: float = Field(default=1.0, ge=0.1, le=8.0)
    memory: str = Field(default="512m")
    gpu: Optional[str] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None

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
    driver: str = "local"
    mount_path: str
    name: str

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
    port: int = Field(ge=1, le=65535, description="Port to expose from container")
    protocol: str = Field(default="http", pattern="^(http|https|tcp|udp)$")

    @validator('port')
    def validate_port(cls, v):
        if v in [22, 80, 443, 2375, 2376, 2377, 2378, 2379, 2380, 3375]:  # Reserved ports
            raise ValueError(f"Port {v} is reserved")
        return v

class UserQuota(BaseModel):
    max_containers: int = Field(default=10, ge=1)
    max_cpu: float = Field(default=4.0, ge=0.1)
    max_memory: int = Field(default=8192, ge=512)  # MB
    max_storage: int = Field(default=10240, ge=1024)  # MB

class User(BaseModel):
    id: Optional[int] = None
    username: str = Field(..., min_length=3, max_length=50)
    api_key: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    quotas: Optional[UserQuota] = None

class CreateSandboxRequest(BaseModel):
    image: str = Field(..., pattern="^[a-zA-Z0-9][a-zA-Z0-9_.-]+(/[a-zA-Z0-9_.-]+)*:[a-zA-Z0-9_.-]+$")
    name: Optional[str] = None
    command: Optional[str] = None
    entrypoint: Optional[Union[str, List[str]]] = None
    volumes: Optional[Dict[str, VolumeConfig]] = None
    environment: Optional[Dict[str, str]] = None
    resources: Optional[ResourceConfig] = None
    ports: Optional[List[PortConfig]] = None
    auto_remove: bool = True

    @validator('environment')
    def validate_env(cls, v):
        if v:
            for key in v.keys():
                if not key.isidentifier() and not all(c.isalnum() or c == '_' for c in key):
                    raise ValueError(f"Invalid environment variable name: {key}")
        return v

class VolumeInfo(BaseModel):
    id: int
    volume_id: str
    name: str
    mount_path: str
    size: int  # MB
    driver: str
    created_at: datetime

class PortInfo(BaseModel):
    id: int
    internal_port: int
    external_port: int
    protocol: str
    url: Optional[str]

class LogEntry(BaseModel):
    timestamp: datetime
    log_type: str  # stdout, stderr, system
    level: str  # info, warning, error
    message: str

class MetricData(BaseModel):
    timestamp: datetime
    cpu_usage: float  # percentage
    memory_usage: int  # bytes
    memory_limit: int  # bytes
    network_rx_bytes: int
    network_tx_bytes: int
    block_read_bytes: int
    block_write_bytes: int

class Alert(BaseModel):
    timestamp: datetime
    alert_type: str  # cpu_high, memory_high, etc.
    severity: str  # warning, critical
    message: str
    resolved: bool
    resolved_at: Optional[datetime]

class TimeoutUpdate(BaseModel):
    timeout: int = Field(ge=0, description="Timeout in seconds (0 for no timeout)")

class EntrypointUpdate(BaseModel):
    entrypoint: Optional[Union[str, List[str]]] = None
    command: Optional[Union[str, List[str]]] = None

class EnvUpdate(BaseModel):
    environment: Dict[str, str]
    merge: bool = True  # If True, merge with existing env vars. If False, replace all

class SandboxStatus(BaseModel):
    id: int
    container_id: str
    name: str
    status: str
    image: str
    command: Optional[str]
    entrypoint: Optional[str]
    resources: Dict[str, Any]
    environment: Optional[Dict[str, str]]
    created_at: datetime
    started_at: Optional[datetime]
    terminated_at: Optional[datetime]
    last_active: datetime
    auto_remove: bool
    volumes: List[VolumeInfo]
    ports: List[PortInfo] 