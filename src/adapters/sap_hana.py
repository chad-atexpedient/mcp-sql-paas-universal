"""
SAP HANA Adapter for MCP
Provides SAP HANA-specific database operations.

Best Practices Implemented:
- Single-container and MDC (Multi-Database Container) support
- SSL/TLS encryption
- SAP HANA-specific optimizations
- Calculation view support
"""

import json
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..core.base_server import BaseMCPServer, BaseToolDefinitions, QueryResult, ServerConfig
from ..core.connection_pool import ConnectionPoolManager, PoolConfig
from ..core.security import SecurityManager


class SAPHanaConfig(BaseModel):
    """SAP HANA connection configuration."""
    
    # Connection type: "single", "mdc_system", "mdc_tenant"
    connection_type: str = Field(default="single")
    
    # Required for all connection types
    host: str = Field(..., description="HANA host")
    user: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    
    # Required for MDC types
    port: int = Field(default=30015, description="HANA port")
    instance_number: Optional[str] = Field(default=None, description="Instance number for MDC")
    
    # Required for MDC Tenant
    database_name: Optional[str] = Field(default=None, description="Tenant database name")
    
    # Optional settings
    schema_name: Optional[str] = Field(default=None, description="Default schema")
    
    # Security settings
    ssl_enabled: bool = Field(default=True)
    ssl_validate_cert: bool = Field(default=True)
    encrypt: bool = Field(default=True)
    
    # Connection settings
    connection_timeout: int = Field(default=30)
    query_timeout: int = Field(default=120)


class SAPHanaConnectionPool(ConnectionPoolManager):
    """Connection pool for SAP HANA."""
    
    def __init__(self, config: SAPHanaConfig, pool_config: PoolConfig):
        super().__init__(pool_config)
        self.db_config = config
    
    def _get_port(self) -> int:
        """Calculate the port based on connection type and instance."""
        if self.db_config.connection_type == "single":
            return self.db_config.port or 30015
        
        # MDC port calculation: 3<instance>13 for system, 3<instance>15 for tenant
        instance = int(self.db_config.instance_number or "00")
        if self.db_config.connection_type == "mdc_system":
            return 30013 + (instance * 100)
        else:  # mdc_tenant
            return 30015 + (instance * 100)
    
    async def _create_connection(self):
        """Create a new SAP HANA connection."""
        from hdbcli import dbapi
        
        conn_params = {
            "address": self.db_config.host,
            "port": self._get_port(),
            "user": self.db_config.user,
            "password": self.db_config.password,
            "encrypt": self.db_config.encrypt,
            "sslValidateCertificate": self.db_config.ssl_validate_cert,
        }
        
        # Add database name for MDC tenant connections
        if self.db_config.connection_type == "mdc_tenant" and self.db_config.database_name:
            conn_params["databaseName"] = self.db_config.database_name
        
        connection = dbapi.connect(**conn_params)
        
        # Set default schema if specified
        if self.db_config.schema_name:
            cursor = connection.cursor()
            cursor.execute(f"SET SCHEMA {self.db_config.schema_name}")
            cursor.close()
        
        return connection
    
    async def _close_connection(self, connection) -> None:
        """Close a SAP HANA connection."""
        try:
            connection.close()
        except Exception:
            pass
    
    async def _is_connection_healthy(self, connection) -> bool:
        """Check if connection is healthy."""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM DUMMY")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False


class SAPHanaAdapter(BaseMCPServer):
    """
    MCP Server adapter for SAP HANA.
    
    Supports:
    - Single-container databases
    - Multi-Database Container (MDC) system databases
    - MDC tenant databases
    - Calculation views
    - SAP-specific metadata
    """
    
    def __init__(self, server_config: ServerConfig, db_config: SAPHanaConfig):
        super().__init__(server_config)
        self.db_config = db_config
        self._pool: Optional[SAPHanaConnectionPool] = None
    
    def get_tools(self) -> List:
        """Return SAP HANA-specific tools."""
        from mcp.types import Tool
        
        tools = [
            BaseToolDefinitions.query_tool(),
            BaseToolDefinitions.list_tables_tool(),
            BaseToolDefinitions.describe_table_tool(),
            BaseToolDefinitions.sample_data_tool(),
            BaseToolDefinitions.count_rows_tool(),
            BaseToolDefinitions.test_connection_tool(),
        ]
        
        # SAP HANA-specific tools
        tools.append(Tool(
            name="list_schemas",
            description="List all schemas in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_system": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include system schemas"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="list_calculation_views",
            description="List calculation views in a schema",
            inputSchema={
                "type": "object",
                "properties": {
                    "schema": {
                        "type": "string",
                        "description": "Schema name"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Name pattern filter"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_table_partitions",
            description="Get partition information for a table",
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
        
        tools.append(Tool(
            name="get_memory_usage",
            description="Get HANA memory usage statistics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        tools.append(Tool(
            name="get_expensive_statements",
            description="Get expensive statements from statement history",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Number of statements to return"
                    },
                    "order_by": {
                        "type": "string",
                        "default": "total_execution_time",
                        "description": "Order by: total_execution_time, avg_execution_time, execution_count"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_index_info",
            description="Get index information for a table",
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
        
        # MDC-specific tools
        if self.db_config.connection_type == "mdc_system":
            tools.append(Tool(
                name="list_tenants",
                description="List tenant databases (MDC System only)",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ))
        
        return tools
    
    async def connect(self) -> None:
        """Establish connection to SAP HANA."""
        pool_config = PoolConfig(
            min_size=2,
            max_size=self.config.pool_size,
            connection_timeout_seconds=self.db_config.connection_timeout
        )
        
        self._pool = SAPHanaConnectionPool(self.db_config, pool_config)
        await self._pool.initialize()
        
        self.logger.info(
            "Connected to SAP HANA",
            host=self.db_config.host,
            connection_type=self.db_config.connection_type,
            database=self.db_config.database_name
        )
    
    async def disconnect(self) -> None:
        """Close SAP HANA connection."""
        if self._pool:
            await self._pool.close()
        self.logger.info("Disconnected from SAP HANA")
    
    async def test_connection(self) -> bool:
        """Test SAP HANA connectivity."""
        try:
            async with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        SYSTEM_ID,
                        DATABASE_NAME,
                        HOST,
                        VERSION,
                        CURRENT_USER
                    FROM M_DATABASE
                """)
                row = cursor.fetchone()
                cursor.close()
                
                self.logger.info(
                    "Connection test successful",
                    system_id=row[0] if row else "unknown",
                    database=row[1] if row else "unknown",
                    version=row[3] if row else "unknown"
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
        
        elif tool_name == "list_schemas":
            return await self._list_schemas(arguments.get("include_system", False))
        
        elif tool_name == "list_calculation_views":
            return await self._list_calculation_views(
                arguments.get("schema"),
                arguments.get("pattern")
            )
        
        elif tool_name == "get_table_partitions":
            return await self._get_table_partitions(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        elif tool_name == "get_memory_usage":
            return await self._get_memory_usage()
        
        elif tool_name == "get_expensive_statements":
            return await self._get_expensive_statements(
                arguments.get("limit", 20),
                arguments.get("order_by", "total_execution_time")
            )
        
        elif tool_name == "get_index_info":
            return await self._get_index_info(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        elif tool_name == "list_tenants":
            return await self._list_tenants()
        
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
        query = """
            SELECT 
                SCHEMA_NAME,
                TABLE_NAME,
                TABLE_TYPE,
                RECORD_COUNT,
                IS_COLUMN_TABLE
            FROM TABLES
            WHERE IS_SYSTEM_TABLE = 'FALSE'
        """
        params = []
        
        if schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(schema)
        
        if pattern:
            query += " AND TABLE_NAME LIKE ?"
            params.append(f"%{pattern}%")
        
        query += " ORDER BY SCHEMA_NAME, TABLE_NAME"
        
        return await self._execute_query(query, params if params else None)
    
    async def _describe_table(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table column information."""
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                COLUMN_NAME,
                DATA_TYPE_NAME,
                LENGTH,
                SCALE,
                IS_NULLABLE,
                DEFAULT_VALUE,
                COMMENTS
            FROM TABLE_COLUMNS
            WHERE TABLE_NAME = ?
        """
        params = [safe_table]
        
        if schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(self.security.sanitize_identifier(schema))
        
        query += " ORDER BY POSITION"
        
        return await self._execute_query(query, params)
    
    async def _get_sample_data(self, table_name: str, limit: int = 10) -> str:
        """Get sample rows from a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name or "SYSTEM"
        query = f'SELECT TOP {int(limit)} * FROM "{schema}"."{safe_table}"'
        return await self._execute_query(query)
    
    async def _count_rows(self, table_name: str, where_clause: Optional[str] = None) -> str:
        """Count rows in a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name or "SYSTEM"
        query = f'SELECT COUNT(*) as row_count FROM "{schema}"."{safe_table}"'
        
        if where_clause:
            is_valid, error = self.security.validate_query(f"SELECT * FROM t WHERE {where_clause}")
            if not is_valid:
                return json.dumps({"error": f"Invalid WHERE clause: {error}"})
            query += f" WHERE {where_clause}"
        
        return await self._execute_query(query)
    
    async def _list_schemas(self, include_system: bool = False) -> str:
        """List all schemas."""
        query = """
            SELECT 
                SCHEMA_NAME,
                SCHEMA_OWNER,
                CREATE_TIME,
                HAS_PRIVILEGES
            FROM SCHEMAS
        """
        if not include_system:
            query += " WHERE IS_SYSTEM_SCHEMA = 'FALSE'"
        query += " ORDER BY SCHEMA_NAME"
        return await self._execute_query(query)
    
    async def _list_calculation_views(self, schema: Optional[str] = None, pattern: Optional[str] = None) -> str:
        """List calculation views."""
        query = """
            SELECT 
                SCHEMA_NAME,
                VIEW_NAME,
                VIEW_TYPE,
                IS_VALID,
                CREATE_TIME
            FROM VIEWS
            WHERE VIEW_TYPE = 'CALC'
        """
        params = []
        
        if schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(schema)
        
        if pattern:
            query += " AND VIEW_NAME LIKE ?"
            params.append(f"%{pattern}%")
        
        query += " ORDER BY SCHEMA_NAME, VIEW_NAME"
        return await self._execute_query(query, params if params else None)
    
    async def _get_table_partitions(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table partition information."""
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                SCHEMA_NAME,
                TABLE_NAME,
                PART_ID,
                PARTITION_SPEC,
                RECORD_COUNT,
                DISK_SIZE
            FROM M_TABLE_PARTITIONS
            WHERE TABLE_NAME = ?
        """
        params = [safe_table]
        
        if schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(self.security.sanitize_identifier(schema))
        
        return await self._execute_query(query, params)
    
    async def _get_memory_usage(self) -> str:
        """Get HANA memory usage statistics."""
        query = """
            SELECT 
                HOST,
                ROUND(FREE_PHYSICAL_MEMORY/1024/1024/1024, 2) as free_memory_gb,
                ROUND(USED_PHYSICAL_MEMORY/1024/1024/1024, 2) as used_memory_gb,
                ROUND(ALLOCATION_LIMIT/1024/1024/1024, 2) as allocation_limit_gb,
                ROUND(INSTANCE_TOTAL_MEMORY_USED_SIZE/1024/1024/1024, 2) as instance_used_gb,
                ROUND(INSTANCE_TOTAL_MEMORY_PEAK_USED_SIZE/1024/1024/1024, 2) as peak_used_gb
            FROM M_HOST_RESOURCE_UTILIZATION
        """
        return await self._execute_query(query)
    
    async def _get_expensive_statements(self, limit: int = 20, order_by: str = "total_execution_time") -> str:
        """Get expensive statements from history."""
        order_column = {
            "total_execution_time": "TOTAL_EXECUTION_TIME",
            "avg_execution_time": "AVG_EXECUTION_TIME",
            "execution_count": "EXECUTION_COUNT"
        }.get(order_by, "TOTAL_EXECUTION_TIME")
        
        query = f"""
            SELECT 
                STATEMENT_HASH,
                SUBSTR(STATEMENT_STRING, 1, 200) as statement_preview,
                USER_NAME,
                EXECUTION_COUNT,
                TOTAL_EXECUTION_TIME,
                AVG_EXECUTION_TIME,
                TOTAL_RESULT_RECORD_COUNT,
                LAST_EXECUTION_TIMESTAMP
            FROM M_SQL_PLAN_CACHE
            ORDER BY {order_column} DESC
            LIMIT {int(limit)}
        """
        return await self._execute_query(query)
    
    async def _get_index_info(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get index information for a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                SCHEMA_NAME,
                TABLE_NAME,
                INDEX_NAME,
                INDEX_TYPE,
                CONSTRAINT,
                COLUMN_NAME
            FROM INDEX_COLUMNS
            WHERE TABLE_NAME = ?
        """
        params = [safe_table]
        
        if schema:
            query += " AND SCHEMA_NAME = ?"
            params.append(self.security.sanitize_identifier(schema))
        
        query += " ORDER BY INDEX_NAME, POSITION"
        return await self._execute_query(query, params)
    
    async def _list_tenants(self) -> str:
        """List tenant databases (MDC System only)."""
        if self.db_config.connection_type != "mdc_system":
            return json.dumps({"error": "This operation requires MDC System connection"})
        
        query = """
            SELECT 
                DATABASE_NAME,
                ACTIVE_STATUS,
                ACTIVE_STATUS_DETAILS,
                OS_USER,
                OS_GROUP,
                RESTART_MODE
            FROM M_DATABASES
            ORDER BY DATABASE_NAME
        """
        return await self._execute_query(query)
