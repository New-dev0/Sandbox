from typing import AsyncGenerator, Any, Dict
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload, sessionmaker
from sandbox.config import settings
from sqlalchemy.ext.declarative import declarative_base
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get DB session"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except:
        await session.rollback()
        raise
    finally:
        await session.close()

class DatabaseManager:
    _engine = None
    _sessionmaker = None

    @classmethod
    async def initialize(cls):
        """Initialize database connection"""
        try:
            if not cls._engine:
                cls._engine = create_async_engine(
                    settings.DATABASE_URL,
                    pool_size=settings.DB_POOL_SIZE,
                    max_overflow=settings.DB_MAX_OVERFLOW,
                    pool_timeout=settings.DB_POOL_TIMEOUT,
                    pool_recycle=settings.DB_POOL_RECYCLE,
                    echo=settings.DEBUG
                )
                
                cls._sessionmaker = async_sessionmaker(
                    cls._engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )
                
                # Test connection
                async with cls._engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                    
                return True
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            return False

    @classmethod
    async def create_tables(cls):
        """Create all tables"""
        try:
            async with cls._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return True
        except Exception as e:
            logger.error(f"Failed to create tables: {str(e)}")
            return False

    @classmethod
    async def get_session(cls) -> AsyncSession:
        """Get database session"""
        if not cls._sessionmaker:
            raise RuntimeError("Database not initialized")
        return cls._sessionmaker()

    @classmethod
    async def close(cls):
        """Close database connection"""
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._sessionmaker = None

    @staticmethod
    async def drop_tables():
        """Drop all tables"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    @staticmethod
    async def check_connection() -> bool:
        """Check database connection"""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    @staticmethod
    async def get_table_sizes() -> Dict[str, int]:
        """Get sizes of all tables"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT relname as table_name,
                       pg_total_relation_size(c.oid) as total_size
                FROM pg_class c
                LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE relkind = 'r'
                AND nspname = 'public'
            """))
            return {row.table_name: row.total_size for row in result}
    
    @staticmethod
    async def vacuum_analyze():
        """Run VACUUM ANALYZE on all tables"""
        async with engine.connect() as conn:
            await conn.execute(text("VACUUM ANALYZE"))

class Repository:
    """Base repository class with common CRUD operations"""
    
    def __init__(self, model: Any):
        self.model = model
    
    async def create(self, session: AsyncSession, **kwargs) -> Any:
        """Create new record"""
        obj = self.model(**kwargs)
        session.add(obj)
        await session.flush()
        return obj
    
    async def get(self, session: AsyncSession, id: int) -> Any:
        """Get record by ID"""
        stmt = select(self.model).where(self.model.id == id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self, session: AsyncSession) -> list[Any]:
        """Get all records"""
        stmt = select(self.model)
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def update(self, session: AsyncSession, id: int, **kwargs) -> Any:
        """Update record"""
        stmt = select(self.model).where(self.model.id == id)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            for key, value in kwargs.items():
                setattr(obj, key, value)
            await session.flush()
        return obj
    
    async def delete(self, session: AsyncSession, id: int) -> bool:
        """Delete record"""
        stmt = select(self.model).where(self.model.id == id)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            await session.delete(obj)
            await session.flush()
            return True
        return False

# Create repositories for each model
from sandbox.db.models import User, Sandbox, Volume, Port, SandboxLog, SandboxMetric, Alert

class UserRepository(Repository):
    def __init__(self):
        super().__init__(User)
    
    async def get_by_api_key(self, session: AsyncSession, api_key: str) -> User:
        stmt = select(User).where(User.api_key == api_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

class SandboxRepository(Repository):
    def __init__(self):
        super().__init__(Sandbox)
    
    async def get_with_relations(self, session: AsyncSession, id: int) -> Sandbox:
        stmt = select(Sandbox).where(Sandbox.id == id).options(
            selectinload(Sandbox.volumes),
            selectinload(Sandbox.ports),
            selectinload(Sandbox.logs),
            selectinload(Sandbox.metrics)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

# Initialize repositories
user_repository = UserRepository()
sandbox_repository = SandboxRepository()
volume_repository = Repository(Volume)
port_repository = Repository(Port)
log_repository = Repository(SandboxLog)
metric_repository = Repository(SandboxMetric)
alert_repository = Repository(Alert) 