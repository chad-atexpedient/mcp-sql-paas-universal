"""
Connection Pool Manager
Provides connection pooling for database connections.

Best practice: Use 5-20 connections for MCP servers to handle
concurrent LLM requests without overwhelming the database.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class PoolConfig(BaseModel):
    """Configuration for connection pools."""
    
    min_size: int = Field(default=2, ge=1, le=10)
    max_size: int = Field(default=10, ge=1, le=50)
    max_idle_time_seconds: int = Field(default=300)
    connection_timeout_seconds: int = Field(default=30)
    health_check_interval_seconds: int = Field(default=60)
    recycle_connections_seconds: int = Field(default=3600)


T = TypeVar("T")


@dataclass
class PooledConnection(Generic[T]):
    """Wrapper for a pooled database connection."""
    
    connection: T
    created_at: datetime
    last_used_at: datetime
    use_count: int = 0
    is_healthy: bool = True


class ConnectionPoolManager(ABC, Generic[T]):
    """
    Abstract connection pool manager.
    
    Implements best practices for MCP database connections:
    - Connection reuse to reduce overhead
    - Health checks to detect stale connections
    - Automatic recycling of old connections
    - Configurable pool sizing
    """
    
    def __init__(self, config: PoolConfig):
        self.config = config
        self._pool: asyncio.Queue[PooledConnection[T]] = asyncio.Queue(maxsize=config.max_size)
        self._active_connections: int = 0
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    async def _create_connection(self) -> T:
        """Create a new database connection."""
        pass
    
    @abstractmethod
    async def _close_connection(self, connection: T) -> None:
        """Close a database connection."""
        pass
    
    @abstractmethod
    async def _is_connection_healthy(self, connection: T) -> bool:
        """Check if a connection is still healthy."""
        pass
    
    async def initialize(self) -> None:
        """Initialize the connection pool with minimum connections."""
        self.logger.info(
            "Initializing connection pool",
            min_size=self.config.min_size,
            max_size=self.config.max_size
        )
        
        # Create initial connections
        for _ in range(self.config.min_size):
            conn = await self._create_connection()
            pooled = PooledConnection(
                connection=conn,
                created_at=datetime.utcnow(),
                last_used_at=datetime.utcnow()
            )
            await self._pool.put(pooled)
            self._active_connections += 1
        
        # Start health check background task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        self.logger.info(
            "Connection pool initialized",
            active_connections=self._active_connections
        )
    
    async def close(self) -> None:
        """Close all connections and shut down the pool."""
        self.logger.info("Closing connection pool")
        
        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        while not self._pool.empty():
            try:
                pooled = self._pool.get_nowait()
                await self._close_connection(pooled.connection)
            except asyncio.QueueEmpty:
                break
        
        self._active_connections = 0
        self.logger.info("Connection pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.
        
        Usage:
            async with pool.acquire() as conn:
                # use connection
        """
        pooled: Optional[PooledConnection[T]] = None
        
        try:
            # Try to get existing connection
            try:
                pooled = await asyncio.wait_for(
                    self._pool.get(),
                    timeout=self.config.connection_timeout_seconds
                )
            except asyncio.TimeoutError:
                # Pool exhausted, try to create new connection
                async with self._lock:
                    if self._active_connections < self.config.max_size:
                        conn = await self._create_connection()
                        pooled = PooledConnection(
                            connection=conn,
                            created_at=datetime.utcnow(),
                            last_used_at=datetime.utcnow()
                        )
                        self._active_connections += 1
                    else:
                        raise TimeoutError("Connection pool exhausted")
            
            # Check if connection needs recycling
            if self._should_recycle(pooled):
                await self._close_connection(pooled.connection)
                conn = await self._create_connection()
                pooled = PooledConnection(
                    connection=conn,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow()
                )
            
            # Verify connection health
            if not await self._is_connection_healthy(pooled.connection):
                await self._close_connection(pooled.connection)
                conn = await self._create_connection()
                pooled = PooledConnection(
                    connection=conn,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow()
                )
            
            pooled.last_used_at = datetime.utcnow()
            pooled.use_count += 1
            
            yield pooled.connection
            
        finally:
            # Return connection to pool
            if pooled is not None:
                try:
                    self._pool.put_nowait(pooled)
                except asyncio.QueueFull:
                    # Pool is full, close the connection
                    await self._close_connection(pooled.connection)
                    async with self._lock:
                        self._active_connections -= 1
    
    def _should_recycle(self, pooled: PooledConnection[T]) -> bool:
        """Check if a connection should be recycled."""
        age = datetime.utcnow() - pooled.created_at
        return age.total_seconds() > self.config.recycle_connections_seconds
    
    async def _health_check_loop(self) -> None:
        """Background task to check connection health."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)
                
                # Check all connections in pool
                checked = 0
                to_check = self._pool.qsize()
                
                while checked < to_check:
                    try:
                        pooled = self._pool.get_nowait()
                        
                        # Check health
                        if await self._is_connection_healthy(pooled.connection):
                            self._pool.put_nowait(pooled)
                        else:
                            # Replace unhealthy connection
                            self.logger.warning("Replacing unhealthy connection")
                            await self._close_connection(pooled.connection)
                            conn = await self._create_connection()
                            new_pooled = PooledConnection(
                                connection=conn,
                                created_at=datetime.utcnow(),
                                last_used_at=datetime.utcnow()
                            )
                            self._pool.put_nowait(new_pooled)
                        
                        checked += 1
                    except asyncio.QueueEmpty:
                        break
                
                self.logger.debug(f"Health check completed: {checked} connections verified")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        return {
            "active_connections": self._active_connections,
            "available_connections": self._pool.qsize(),
            "max_size": self.config.max_size,
            "min_size": self.config.min_size,
        }
