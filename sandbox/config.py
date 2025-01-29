from typing import List, Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
import os

class Settings(BaseSettings):
    DEBUG: bool = Field(default=False, env="SANDBOX_DEBUG")

    # Server settings
    HOST: str = Field(default="0.0.0.0", env="SANDBOX_HOST")
    PORT: int = Field(default=8000, env="SANDBOX_PORT")
    WORKERS: int = Field(default=4, env="SANDBOX_WORKERS")
    RELOAD: bool = Field(default=True, env="SANDBOX_RELOAD")
    LOG_LEVEL: str = Field(default="info", env="SANDBOX_LOG_LEVEL")
    SSL_CERT_FILE: Optional[str] = Field(default=None, env="SANDBOX_SSL_CERT_FILE")
    SSL_KEY_FILE: Optional[str] = Field(default=None, env="SANDBOX_SSL_KEY_FILE")
    CORS_ORIGINS: List[str] = Field(default=["*"], env="SANDBOX_CORS_ORIGINS")
    
    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sandbox",
        env="SANDBOX_DATABASE_URL"
    )
    DB_POOL_SIZE: int = Field(default=5, env="SANDBOX_DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(default=10, env="SANDBOX_DB_MAX_OVERFLOW")
    DB_POOL_TIMEOUT: int = Field(default=30, env="SANDBOX_DB_POOL_TIMEOUT")
    DB_POOL_RECYCLE: int = Field(default=1800, env="SANDBOX_DB_POOL_RECYCLE")
    
    # Monitoring settings
    MONITOR_INTERVAL: int = Field(default=10, env="SANDBOX_MONITOR_INTERVAL")
    METRICS_ENABLED: bool = Field(default=True, env="SANDBOX_METRICS_ENABLED")
    PROMETHEUS_PORT: int = Field(default=9090, env="SANDBOX_PROMETHEUS_PORT")
    MONITOR_CPU_THRESHOLD: float = Field(default=90.0, env="SANDBOX_MONITOR_CPU_THRESHOLD")
    MONITOR_MEMORY_THRESHOLD: float = Field(default=90.0, env="SANDBOX_MONITOR_MEMORY_THRESHOLD")
    MONITOR_DISK_THRESHOLD: float = Field(default=90.0, env="SANDBOX_MONITOR_DISK_THRESHOLD")
    
    # Scheduler settings
    CLEANUP_INTERVAL: int = Field(default=300, env="SANDBOX_CLEANUP_INTERVAL")
    MAX_CONTAINER_AGE: int = Field(default=86400, env="SANDBOX_MAX_CONTAINER_AGE")
    INACTIVE_TIMEOUT: int = Field(default=3600, env="SANDBOX_INACTIVE_TIMEOUT")
    AUTO_CLEANUP_ENABLED: bool = Field(default=True, env="SANDBOX_AUTO_CLEANUP_ENABLED")
    
    # Domain settings
    DOMAIN: str = Field(default="sandbox.local", env="SANDBOX_DOMAIN")
    DOMAIN_SCHEME: str = Field(default="https", env="SANDBOX_DOMAIN_SCHEME")
    
    # Volume settings
    VOLUMES_ROOT: Path = Field(
        default=Path("/var/lib/sandbox/volumes"),
        env="SANDBOX_VOLUMES_ROOT"
    )
    
    # Docker settings
    DOCKER_API_VERSION: str = Field(default="1.41", env="SANDBOX_DOCKER_API_VERSION")
    DOCKER_MAX_CPU: float = Field(default=8.0, env="SANDBOX_DOCKER_MAX_CPU")
    DOCKER_MAX_MEMORY: str = Field(default="16g", env="SANDBOX_DOCKER_MAX_MEMORY")
    DOCKER_DEFAULT_NETWORK: str = Field(default="traefik-net", env="SANDBOX_DOCKER_DEFAULT_NETWORK")
    
    # Traefik settings
    TRAEFIK_ENTRYPOINT: str = Field(default="websecure", env="SANDBOX_TRAEFIK_ENTRYPOINT")
    TRAEFIK_CERT_RESOLVER: str = Field(default="letsencrypt", env="SANDBOX_TRAEFIK_CERT_RESOLVER")
    TRAEFIK_HTTP_ENTRYPOINT: str = Field(default="web", env="SANDBOX_TRAEFIK_HTTP_ENTRYPOINT")
    TRAEFIK_HTTPS_PORT: int = Field(default=443, env="SANDBOX_TRAEFIK_HTTPS_PORT")
    TRAEFIK_HTTP_PORT: int = Field(default=80, env="SANDBOX_TRAEFIK_HTTP_PORT")
    TRAEFIK_ACME_EMAIL: str = Field(default="admin@example.com", env="SANDBOX_TRAEFIK_ACME_EMAIL")
    TRAEFIK_SSL_MIN_VERSION: str = Field(default="VersionTLS12", env="SANDBOX_TRAEFIK_SSL_MIN_VERSION")
    TRAEFIK_SSL_CIPHERS: List[str] = Field(
        default=[
            "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305",
            "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305"
        ],
        env="SANDBOX_TRAEFIK_SSL_CIPHERS"
    )
    
    # Security settings
    MAX_CONTAINERS_PER_USER: int = Field(default=10, env="SANDBOX_MAX_CONTAINERS_PER_USER")
    ENABLE_GPU: bool = Field(default=False, env="SANDBOX_ENABLE_GPU")
    BLOCKED_PORTS: List[int] = Field(default=[22, 80, 443], env="SANDBOX_BLOCKED_PORTS")
    
    # Resource defaults
    DEFAULT_CPU: float = Field(default=1.0, env="SANDBOX_DEFAULT_CPU")
    DEFAULT_MEMORY: str = Field(default="512m", env="SANDBOX_DEFAULT_MEMORY")
    DEFAULT_TIMEOUT: int = Field(default=3600, env="SANDBOX_DEFAULT_TIMEOUT")
    
    # Network settings
    ENABLE_NETWORK: bool = Field(default=True, env="SANDBOX_ENABLE_NETWORK")
    NETWORK_ISOLATION: bool = Field(default=True, env="SANDBOX_NETWORK_ISOLATION")
    
    # Port settings
    PORT_RANGE_START: int = Field(default=10000, env="SANDBOX_PORT_RANGE_START")
    PORT_RANGE_END: int = Field(default=20000, env="SANDBOX_PORT_RANGE_END")
    RESERVED_PORTS: List[int] = Field(
        default=[22, 80, 443, 2375, 2376, 2377, 2378, 2379, 2380, 3375],
        env="SANDBOX_RESERVED_PORTS"
    )

    @validator("VOLUMES_ROOT")
    def create_volumes_dir(cls, v):
        v.mkdir(parents=True, exist_ok=True)
        return v

    @validator("BLOCKED_PORTS", "RESERVED_PORTS", "TRAEFIK_SSL_CIPHERS", pre=True)
    def parse_list(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_prefix="",  # We're handling prefixes in Field definitions
        env_nested_delimiter="__"
    )

# Create settings instance
settings = Settings(_env_file=os.getenv("ENV_FILE", ".env")) 