from enum import Enum
from typing import Dict, Any

class SandboxStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"

class LogType(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    SYSTEM = "system"

DEFAULT_RESOURCE_LIMITS: Dict[str, Any] = {
    "cpu": 1.0,
    "memory": "512m",
    "pids": 100,
    "network": False,
    "read_only": True
}

DOCKER_API_VERSION = "1.41"
CONTAINER_LABEL_PREFIX = "sandbox"
CLEANUP_GRACE_PERIOD = 300  # 5 minutes 