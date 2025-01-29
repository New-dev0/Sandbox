from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, String, Integer, JSON, ForeignKey, Float, Boolean, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    api_key: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    sandboxes: Mapped[list["Sandbox"]] = relationship(back_populates="user")
    quotas: Mapped["UserQuota"] = relationship(back_populates="user")

class UserQuota(Base):
    __tablename__ = "user_quotas"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    max_containers: Mapped[int] = mapped_column(Integer, default=10)
    max_cpu: Mapped[float] = mapped_column(Float, default=4.0)
    max_memory: Mapped[int] = mapped_column(Integer, default=8192)  # MB
    max_storage: Mapped[int] = mapped_column(Integer, default=10240)  # MB

    user: Mapped[User] = relationship(back_populates="quotas")

class Sandbox(Base):
    __tablename__ = "sandboxes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    container_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))  # running, stopped, failed, terminated
    image: Mapped[str] = mapped_column(String(255))
    command: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    entrypoint: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    resources: Mapped[dict] = mapped_column(JSON)  # CPU, memory, etc.
    environment: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    auto_remove: Mapped[bool] = mapped_column(Boolean, default=True)
    
    user: Mapped[User] = relationship(back_populates="sandboxes")
    volumes: Mapped[list["Volume"]] = relationship(back_populates="sandbox")
    ports: Mapped[list["Port"]] = relationship(back_populates="sandbox")
    logs: Mapped[list["SandboxLog"]] = relationship(back_populates="sandbox")
    metrics: Mapped[list["SandboxMetric"]] = relationship(back_populates="sandbox")

class Volume(Base):
    __tablename__ = "volumes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandboxes.id"))
    volume_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    mount_path: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)  # MB
    driver: Mapped[str] = mapped_column(String(50), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    sandbox: Mapped[Sandbox] = relationship(back_populates="volumes")

class Port(Base):
    __tablename__ = "ports"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandboxes.id"))
    internal_port: Mapped[int] = mapped_column(Integer)
    external_port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(10))  # http, tcp, udp
    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    sandbox: Mapped[Sandbox] = relationship(back_populates="ports")

class SandboxLog(Base):
    __tablename__ = "sandbox_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandboxes.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    log_type: Mapped[str] = mapped_column(String(10))  # stdout, stderr, system
    level: Mapped[str] = mapped_column(String(10), default="info")  # info, warning, error
    message: Mapped[str] = mapped_column(String)
    
    sandbox: Mapped[Sandbox] = relationship(back_populates="logs")

class SandboxMetric(Base):
    __tablename__ = "sandbox_metrics"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandboxes.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cpu_usage: Mapped[float] = mapped_column(Float)  # percentage
    memory_usage: Mapped[int] = mapped_column(Integer)  # bytes
    memory_limit: Mapped[int] = mapped_column(Integer)  # bytes
    network_rx_bytes: Mapped[int] = mapped_column(Integer)
    network_tx_bytes: Mapped[int] = mapped_column(Integer)
    block_read_bytes: Mapped[int] = mapped_column(Integer)
    block_write_bytes: Mapped[int] = mapped_column(Integer)
    
    sandbox: Mapped[Sandbox] = relationship(back_populates="metrics")

class Alert(Base):
    __tablename__ = "alerts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sandbox_id: Mapped[int] = mapped_column(ForeignKey("sandboxes.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    alert_type: Mapped[str] = mapped_column(String(50))  # cpu_high, memory_high, etc.
    severity: Mapped[str] = mapped_column(String(20))  # warning, critical
    message: Mapped[str] = mapped_column(String)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    sandbox: Mapped[Sandbox] = relationship() 