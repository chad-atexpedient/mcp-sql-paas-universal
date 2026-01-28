"""
Base MCP Server Implementation
Provides common functionality for all database-specific MCP servers.

Based on MCP best practices from 2024:
- Read-only access with views/stored procedures
- Configurable timeouts (90-120 seconds recommended)
- Connection pooling (5-20 connections)
- Comprehensive logging and auditing
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)
from pydantic import BaseModel, Field

from .connection_pool import ConnectionPoolManager
from .logging_config import setup_logging
from .security import SecurityManager


class ServerConfig(BaseModel):
    """Configuration model for MCP servers."""
    
    server_name: str = Field(default="mcp-sql-server")
    server_mode: str = Field(default="database")  # "database" or "server"
    timeout_seconds: int = Field(default=120, ge=30, le=300)
    pool_size: int = Field(default=10, ge=1, le=50)
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = None
    console_logging: bool = True
    read_only: bool = True
    audit_queries: bool = True


class QueryResult(BaseModel):
    """Standardized query result model."""
    
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool = False
    message: Optional[str] = None


class BaseMCPServer(ABC):
    """
    Abstract base class for all database MCP servers.
    
    Implements MCP best practices:
    - Security through read-only access
    - Performance via timeouts and pooling
    - Operational efficiency with logging
    """
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.server = Server(config.server_name)
        self.logger = setup_logging(
            config.log_level,
            config.log_file,
            config.console_logging
        )
        self.security = SecurityManager(read_only=config.read_only)
        self.pool_manager: Optional[ConnectionPoolManager] = None
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Register MCP protocol handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """Return available tools for this server."""
            return ListToolsResult(tools=self.get_tools())
        
        @self.server.call_tool()
        async def call_tool(request: CallToolRequest) -> CallToolResult:
            """Handle tool invocation with timeout and auditing."""
            tool_name = request.params.name
            arguments = request.params.arguments or {}
            
            # Log the tool call
            self.logger.info(
                "Tool called",
                tool=tool_name,
                arguments=self._sanitize_args(arguments)
            )
            
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    self._execute_tool(tool_name, arguments),
                    timeout=self.config.timeout_seconds
                )
                
                # Audit successful query
                if self.config.audit_queries:
                    self._audit_query(tool_name, arguments, success=True)
                
                return CallToolResult(
                    content=[TextContent(type="text", text=result)]
                )
                
            except asyncio.TimeoutError:
                self.logger.error(
                    "Tool timeout",
                    tool=tool_name,
                    timeout=self.config.timeout_seconds
                )
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=f"Error: Operation timed out after {self.config.timeout_seconds}s"
                    )],
                    isError=True
                )
            except Exception as e:
                self.logger.error(
                    "Tool execution failed",
                    tool=tool_name,
                    error=str(e)
                )
                if self.config.audit_queries:
                    self._audit_query(tool_name, arguments, success=False, error=str(e))
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {str(e)}")],
                    isError=True
                )
    
    @abstractmethod
    def get_tools(self) -> List[Tool]:
        """Return the list of tools available for this database type."""
        pass
    
    @abstractmethod
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a specific tool with the given arguments."""
        pass
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if database connection is working."""
        pass
    
    def _sanitize_args(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from arguments for logging."""
        sensitive_keys = {"password", "secret", "token", "key", "credential"}
        return {
            k: "***" if any(s in k.lower() for s in sensitive_keys) else v
            for k, v in arguments.items()
        }
    
    def _audit_query(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """Record query execution for audit purposes."""
        audit_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "server_name": self.config.server_name,
            "tool": tool_name,
            "arguments": self._sanitize_args(arguments),
            "success": success,
            "error": error
        }
        self.logger.info("Audit record", **audit_record)
    
    async def run(self) -> None:
        """Start the MCP server."""
        self.logger.info(
            "Starting MCP server",
            name=self.config.server_name,
            mode=self.config.server_mode
        )
        
        try:
            await self.connect()
            
            # Verify connection
            if await self.test_connection():
                self.logger.info("Database connection verified")
            else:
                raise ConnectionError("Failed to verify database connection")
            
            # Run the server
            async with self.server:
                await self.server.run()
                
        finally:
            await self.disconnect()
            self.logger.info("MCP server stopped")


class BaseToolDefinitions:
    """Common tool definitions shared across database types."""
    
    @staticmethod
    def query_tool() -> Tool:
        """Standard SQL query tool."""
        return Tool(
            name="execute_query",
            description="Execute a read-only SQL query and return results",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute (SELECT only)"
                    },
                    "parameters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Query parameters for parameterized queries"
                    },
                    "max_rows": {
                        "type": "integer",
                        "default": 1000,
                        "description": "Maximum rows to return"
                    }
                },
                "required": ["query"]
            }
        )
    
    @staticmethod
    def list_tables_tool() -> Tool:
        """Tool to list available tables."""
        return Tool(
            name="list_tables",
            description="List all tables accessible to the MCP user",
            inputSchema={
                "type": "object",
                "properties": {
                    "schema": {
                        "type": "string",
                        "description": "Schema to list tables from (optional)"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Filter pattern for table names"
                    }
                }
            }
        )
    
    @staticmethod
    def describe_table_tool() -> Tool:
        """Tool to describe table structure."""
        return Tool(
            name="describe_table",
            description="Get column information for a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to describe"
                    },
                    "schema": {
                        "type": "string",
                        "description": "Schema containing the table"
                    }
                },
                "required": ["table_name"]
            }
        )
    
    @staticmethod
    def sample_data_tool() -> Tool:
        """Tool to get sample data from a table."""
        return Tool(
            name="sample_data",
            description="Get sample rows from a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to sample"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Number of sample rows"
                    }
                },
                "required": ["table_name"]
            }
        )
    
    @staticmethod
    def count_rows_tool() -> Tool:
        """Tool to count rows in a table."""
        return Tool(
            name="count_rows",
            description="Count total rows in a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table"
                    },
                    "where_clause": {
                        "type": "string",
                        "description": "Optional WHERE clause for filtering"
                    }
                },
                "required": ["table_name"]
            }
        )
    
    @staticmethod
    def test_connection_tool() -> Tool:
        """Tool to verify database connectivity."""
        return Tool(
            name="test_connection",
            description="Test database connectivity and return status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
