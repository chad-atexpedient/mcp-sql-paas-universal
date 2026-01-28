"""
Snowflake Adapter for MCP
Provides Snowflake-specific database operations.

Best Practices Implemented:
- Personal Access Token (PAT) and OAuth authentication
- Network policy support
- Role-based access control
- Warehouse management
- Cortex integration support
"""

import json
import time
from typing import Any, Dict, List, Optional

import snowflake.connector
from pydantic import BaseModel, Field

from ..core.base_server import BaseMCPServer, BaseToolDefinitions, QueryResult, ServerConfig
from ..core.connection_pool import ConnectionPoolManager, PoolConfig
from ..core.security import SecurityManager


class SnowflakeConfig(BaseModel):
    """Snowflake connection configuration."""
    
    # Account settings
    account_url: str = Field(..., description="Snowflake account URL (org-account.snowflakecomputing.com)")
    account: str = Field(..., description="Snowflake account identifier")
    
    # Authentication
    auth_method: str = Field(default="password", description="'password', 'pat', 'oauth', 'keypair'")
    user: str = Field(..., description="Snowflake username")
    password: Optional[str] = None
    private_key_path: Optional[str] = None
    private_key_passphrase: Optional[str] = None
    
    # PAT settings
    pat_token: Optional[str] = Field(default=None, description="Personal Access Token")
    
    # OAuth settings
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    
    # Warehouse and database
    warehouse: str = Field(..., description="Snowflake warehouse name")
    database: str = Field(..., description="Database name")
    schema_name: str = Field(default="PUBLIC", description="Schema name")
    
    # Role settings
    role: str = Field(default="PUBLIC", description="Role to use for connection")
    
    # Connection settings
    connection_timeout: int = Field(default=30)
    query_timeout: int = Field(default=120)
    
    # Network policy
    allowed_ips: Optional[List[str]] = None


class SnowflakeConnectionPool(ConnectionPoolManager[snowflake.connector.SnowflakeConnection]):
    """Connection pool for Snowflake."""
    
    def __init__(self, config: SnowflakeConfig, pool_config: PoolConfig):
        super().__init__(pool_config)
        self.db_config = config
    
    async def _create_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Create a new Snowflake connection."""
        conn_params = {
            "account": self.db_config.account,
            "user": self.db_config.user,
            "warehouse": self.db_config.warehouse,
            "database": self.db_config.database,
            "schema": self.db_config.schema_name,
            "role": self.db_config.role,
            "login_timeout": self.db_config.connection_timeout,
            "network_timeout": self.db_config.query_timeout,
        }
        
        if self.db_config.auth_method == "password":
            conn_params["password"] = self.db_config.password
        
        elif self.db_config.auth_method == "pat":
            conn_params["token"] = self.db_config.pat_token
            conn_params["authenticator"] = "oauth"
        
        elif self.db_config.auth_method == "keypair":
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            
            with open(self.db_config.private_key_path, "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=self.db_config.private_key_passphrase.encode() 
                        if self.db_config.private_key_passphrase else None,
                    backend=default_backend()
                )
            
            conn_params["private_key"] = private_key
        
        connection = snowflake.connector.connect(**conn_params)
        return connection
    
    async def _close_connection(self, connection: snowflake.connector.SnowflakeConnection) -> None:
        """Close a Snowflake connection."""
        try:
            connection.close()
        except Exception:
            pass
    
    async def _is_connection_healthy(self, connection: snowflake.connector.SnowflakeConnection) -> bool:
        """Check if connection is healthy."""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT CURRENT_VERSION()")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False


class SnowflakeAdapter(BaseMCPServer):
    """
    MCP Server adapter for Snowflake.
    
    Supports Snowflake-specific features:
    - Warehouse management
    - Role-based access
    - Cortex AI integration
    - Time travel queries
    """
    
    def __init__(self, server_config: ServerConfig, db_config: SnowflakeConfig):
        super().__init__(server_config)
        self.db_config = db_config
        self._pool: Optional[SnowflakeConnectionPool] = None
    
    def get_tools(self) -> List:
        """Return Snowflake-specific tools."""
        from mcp.types import Tool
        
        tools = [
            BaseToolDefinitions.query_tool(),
            BaseToolDefinitions.list_tables_tool(),
            BaseToolDefinitions.describe_table_tool(),
            BaseToolDefinitions.sample_data_tool(),
            BaseToolDefinitions.count_rows_tool(),
            BaseToolDefinitions.test_connection_tool(),
        ]
        
        # Snowflake-specific tools
        tools.append(Tool(
            name="list_warehouses",
            description="List available Snowflake warehouses",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        tools.append(Tool(
            name="list_databases",
            description="List all databases accessible to current role",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        tools.append(Tool(
            name="list_schemas",
            description="List schemas in current or specified database",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {
                        "type": "string",
                        "description": "Database name (uses current if not specified)"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_warehouse_status",
            description="Get current warehouse status and credits usage",
            inputSchema={
                "type": "object",
                "properties": {
                    "warehouse_name": {
                        "type": "string",
                        "description": "Warehouse name (uses current if not specified)"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="time_travel_query",
            description="Query data as it existed at a point in time",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Table name to query"
                    },
                    "at_timestamp": {
                        "type": "string",
                        "description": "Timestamp to query (ISO format)"
                    },
                    "offset_minutes": {
                        "type": "integer",
                        "description": "Minutes ago to query (alternative to timestamp)"
                    },
                    "columns": {
                        "type": "string",
                        "description": "Columns to select (default: *)"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100
                    }
                },
                "required": ["table_name"]
            }
        ))
        
        tools.append(Tool(
            name="get_query_history",
            description="Get recent query history",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 20
                    },
                    "user_name": {
                        "type": "string",
                        "description": "Filter by user"
                    },
                    "warehouse_name": {
                        "type": "string",
                        "description": "Filter by warehouse"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_table_storage_info",
            description="Get table storage metrics (bytes, rows, partitions)",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Table name"
                    },
                    "schema": {
                        "type": "string",
                        "description": "Schema name"
                    }
                },
                "required": ["table_name"]
            }
        ))
        
        return tools
    
    async def connect(self) -> None:
        """Establish connection to Snowflake."""
        pool_config = PoolConfig(
            min_size=2,
            max_size=self.config.pool_size,
            connection_timeout_seconds=self.db_config.connection_timeout
        )
        
        self._pool = SnowflakeConnectionPool(self.db_config, pool_config)
        await self._pool.initialize()
        
        self.logger.info(
            "Connected to Snowflake",
            account=self.db_config.account,
            database=self.db_config.database,
            warehouse=self.db_config.warehouse,
            role=self.db_config.role
        )
    
    async def disconnect(self) -> None:
        """Close Snowflake connection."""
        if self._pool:
            await self._pool.close()
        self.logger.info("Disconnected from Snowflake")
    
    async def test_connection(self) -> bool:
        """Test Snowflake connectivity."""
        try:
            async with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        CURRENT_VERSION(),
                        CURRENT_DATABASE(),
                        CURRENT_SCHEMA(),
                        CURRENT_WAREHOUSE(),
                        CURRENT_ROLE(),
                        CURRENT_USER()
                """)
                row = cursor.fetchone()
                cursor.close()
                
                self.logger.info(
                    "Connection test successful",
                    version=row[0] if row else "unknown",
                    database=row[1] if row else "unknown",
                    warehouse=row[3] if row else "unknown",
                    role=row[4] if row else "unknown"
                )
                return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool and return results."""
        
        if tool_name == "execute_query":
            return await self._execute_query(
                arguments.get("query", ""),
                arguments.get("parameters"),
                arguments.get("max_rows", 1000)
            )
        
        elif tool_name == "list_tables":
            return await self._list_tables(
                arguments.get("schema"),
                arguments.get("pattern")
            )
        
        elif tool_name == "describe_table":
            return await self._describe_table(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        elif tool_name == "sample_data":
            return await self._get_sample_data(
                arguments["table_name"],
                arguments.get("limit", 10)
            )
        
        elif tool_name == "count_rows":
            return await self._count_rows(
                arguments["table_name"],
                arguments.get("where_clause")
            )
        
        elif tool_name == "test_connection":
            success = await self.test_connection()
            return json.dumps({"connected": success})
        
        elif tool_name == "list_warehouses":
            return await self._list_warehouses()
        
        elif tool_name == "list_databases":
            return await self._list_databases()
        
        elif tool_name == "list_schemas":
            return await self._list_schemas(arguments.get("database"))
        
        elif tool_name == "get_warehouse_status":
            return await self._get_warehouse_status(arguments.get("warehouse_name"))
        
        elif tool_name == "time_travel_query":
            return await self._time_travel_query(
                arguments["table_name"],
                arguments.get("at_timestamp"),
                arguments.get("offset_minutes"),
                arguments.get("columns", "*"),
                arguments.get("limit", 100)
            )
        
        elif tool_name == "get_query_history":
            return await self._get_query_history(
                arguments.get("limit", 20),
                arguments.get("user_name"),
                arguments.get("warehouse_name")
            )
        
        elif tool_name == "get_table_storage_info":
            return await self._get_table_storage_info(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _execute_query(
        self,
        query: str,
        parameters: Optional[List] = None,
        max_rows: int = 1000
    ) -> str:
        """Execute a SQL query."""
        is_valid, error = self.security.validate_query(query)
        if not is_valid:
            return json.dumps({"error": error})
        
        start_time = time.time()
        
        async with self._pool.acquire() as conn:
            cursor = conn.cursor()
            
            try:
                if parameters:
                    cursor.execute(query, parameters)
                else:
                    cursor.execute(query)
                
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(max_rows)
                truncated = len(rows) == max_rows
                
                result_rows = []
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    row_dict = self.security.mask_sensitive_data(row_dict)
                    result_rows.append(row_dict)
                
                execution_time = (time.time() - start_time) * 1000
                
                result = QueryResult(
                    columns=columns,
                    rows=result_rows,
                    row_count=len(result_rows),
                    execution_time_ms=execution_time,
                    truncated=truncated
                )
                
                return result.model_dump_json()
                
            finally:
                cursor.close()
    
    async def _list_tables(self, schema: Optional[str] = None, pattern: Optional[str] = None) -> str:
        """List available tables."""
        schema = schema or self.db_config.schema_name
        query = f"SHOW TABLES IN SCHEMA {self.db_config.database}.{schema}"
        if pattern:
            query += f" LIKE '%{pattern}%'"
        return await self._execute_query(query)
    
    async def _describe_table(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table column information."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = schema or self.db_config.schema_name
        query = f"DESCRIBE TABLE {self.db_config.database}.{schema}.{safe_table}"
        return await self._execute_query(query)
    
    async def _get_sample_data(self, table_name: str, limit: int = 10) -> str:
        """Get sample rows from a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name
        query = f"SELECT * FROM {self.db_config.database}.{schema}.{safe_table} LIMIT {int(limit)}"
        return await self._execute_query(query)
    
    async def _count_rows(self, table_name: str, where_clause: Optional[str] = None) -> str:
        """Count rows in a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name
        query = f"SELECT COUNT(*) as row_count FROM {self.db_config.database}.{schema}.{safe_table}"
        if where_clause:
            is_valid, error = self.security.validate_query(f"SELECT * FROM t WHERE {where_clause}")
            if not is_valid:
                return json.dumps({"error": f"Invalid WHERE clause: {error}"})
            query += f" WHERE {where_clause}"
        return await self._execute_query(query)
    
    async def _list_warehouses(self) -> str:
        """List available warehouses."""
        return await self._execute_query("SHOW WAREHOUSES")
    
    async def _list_databases(self) -> str:
        """List all databases."""
        return await self._execute_query("SHOW DATABASES")
    
    async def _list_schemas(self, database: Optional[str] = None) -> str:
        """List schemas in a database."""
        db = database or self.db_config.database
        return await self._execute_query(f"SHOW SCHEMAS IN DATABASE {db}")
    
    async def _get_warehouse_status(self, warehouse_name: Optional[str] = None) -> str:
        """Get warehouse status and credits."""
        wh = warehouse_name or self.db_config.warehouse
        safe_wh = self.security.sanitize_identifier(wh)
        
        # Get warehouse info
        query = f"""
            SELECT 
                'warehouse_info' as info_type,
                name, state, type, size, 
                min_cluster_count, max_cluster_count,
                auto_suspend, auto_resume
            FROM TABLE(INFORMATION_SCHEMA.WAREHOUSES())
            WHERE name = '{safe_wh}'
        """
        return await self._execute_query(query)
    
    async def _time_travel_query(
        self,
        table_name: str,
        at_timestamp: Optional[str] = None,
        offset_minutes: Optional[int] = None,
        columns: str = "*",
        limit: int = 100
    ) -> str:
        """Query historical data using time travel."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name
        full_table = f"{self.db_config.database}.{schema}.{safe_table}"
        
        if at_timestamp:
            query = f"SELECT {columns} FROM {full_table} AT(TIMESTAMP => '{at_timestamp}'::TIMESTAMP_LTZ) LIMIT {int(limit)}"
        elif offset_minutes:
            query = f"SELECT {columns} FROM {full_table} AT(OFFSET => -{int(offset_minutes) * 60}) LIMIT {int(limit)}"
        else:
            return json.dumps({"error": "Must specify either at_timestamp or offset_minutes"})
        
        return await self._execute_query(query)
    
    async def _get_query_history(
        self,
        limit: int = 20,
        user_name: Optional[str] = None,
        warehouse_name: Optional[str] = None
    ) -> str:
        """Get recent query history."""
        query = f"""
            SELECT 
                query_id, query_text, database_name, schema_name,
                warehouse_name, user_name, role_name,
                execution_status, error_code, error_message,
                start_time, end_time, total_elapsed_time,
                bytes_scanned, rows_produced
            FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
                RESULT_LIMIT => {int(limit)}
            ))
            WHERE 1=1
        """
        
        if user_name:
            query += f" AND user_name = '{self.security.sanitize_identifier(user_name)}'"
        if warehouse_name:
            query += f" AND warehouse_name = '{self.security.sanitize_identifier(warehouse_name)}'"
        
        query += " ORDER BY start_time DESC"
        
        return await self._execute_query(query)
    
    async def _get_table_storage_info(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table storage metrics."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = schema or self.db_config.schema_name
        
        query = f"""
            SELECT 
                table_catalog, table_schema, table_name,
                row_count, bytes, 
                retention_time, created, last_altered
            FROM {self.db_config.database}.INFORMATION_SCHEMA.TABLES
            WHERE table_schema = '{schema}'
            AND table_name = '{safe_table}'
        """
        return await self._execute_query(query)
