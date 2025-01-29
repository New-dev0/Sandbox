from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class SandboxCreate(BaseModel):
    image: str
    resources: Dict[str, Any] = Field(
        default_factory=lambda: {"cpu": 1, "memory": "512m"}
    )
    command: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)

class SandboxResponse(BaseModel):
    id: int
    container_id: str
    status: str
    image: str
    resources: Dict[str, Any]
    created_at: datetime
    terminated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class LogCreate(BaseModel):
    log_type: str
    message: str

class LogResponse(BaseModel):
    id: int
    sandbox_id: int
    timestamp: datetime
    log_type: str
    message: str

    class Config:
        from_attributes = True 