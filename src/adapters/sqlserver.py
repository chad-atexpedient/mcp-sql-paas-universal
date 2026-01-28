"""
SQL Server Adapter for MCP
Provides SQL Server-specific database operations.

Best Practices Implemented:
- Read-only access with views/stored procedures
- Database Mode (single DB) and Server Mode (multi-DB)
- Connection pooling with configurable size
- Timeout management for long-running queries
- Query auditing via DMVs when available
"""

import json
import time
from typing import Any, Dict, List, Optional

import pyodbc
from pydantic import BaseModel, Field

from ..core.base_server import BaseMCPServer, BaseToolDefinitions, QueryResult, ServerConfig
from ..core.connection_pool import ConnectionPoolManager, PoolConfig
from ..core.security import SecurityManager


class SQLServerConfig(BaseModel):
    """SQL Server connection configuration."""
    
    host: str = Field(..., description="SQL Server hostname")
    port: int = Field(default=1433, description="SQL Server port")
    database: str = Field(..., description="Database name")
    user: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    
    # Server mode settings
    mode: str = Field(default="database", description="'database' or 'server' mode")
    
    # Security settings
    encrypt: bool = Field(default=True, description="Encrypt connection")
    trust_server_certificate: bool = Field(default=False)
    use_read_replica: bool = Field(default=False)
    
    # Connection settings
    connection_timeout: int = Field(default=30)
    query_timeout: int = Field(default=120)
    
    # Optional schema restriction
    default_schema: Optional[str] = None


class SQLServerConnectionPool(ConnectionPoolManager[pyodbc.Connection]):
    """Connection pool for SQL Server."""
    
    def __init__(self, config: SQLServerConfig, pool_config: PoolConfig):
        super().__init__(pool_config)
        self.db_config = config
    
    def _build_connection_string(self) -> str:
        """Build the ODBC connection string."""
        parts = [
            f"DRIVER={{ODBC Driver 18 for SQL Server}}",
            f"SERVER={self.db_config.host},{self.db_config.port}",
            f"DATABASE={self.db_config.database}",
            f"UID={self.db_config.user}",
            f"PWD={self.db_config.password}",
            f"Encrypt={'yes' if self.db_config.encrypt else 'no'}",
            f"TrustServerCertificate={'yes' if self.db_config.trust_server_certificate else 'no'}",
            f"Connection Timeout={self.db_config.connection_timeout}",
        ]
        return ";".join(parts)
    
    async def _create_connection(self) -> pyodbc.Connection:
        """Create a new SQL Server connection."""
        conn_str = self._build_connection_string()
        connection = pyodbc.connect(conn_str, timeout=self.db_config.connection_timeout)
        connection.timeout = self.db_config.query_timeout
        return connection
    
    async def _close_connection(self, connection: pyodbc.Connection) -> None:
        """Close a SQL Server connection."""
        try:
            connection.close()
        except Exception:
            pass
    
    async def _is_connection_healthy(self, connection: pyodbc.Connection) -> bool:
        """Check if connection is healthy."""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False


class SQLServerAdapter(BaseMCPServer):
    """
    MCP Server adapter for SQL Server.
    
    Supports both Database Mode (single database) and
    Server Mode (multi-database operations).
    """
    
    def __init__(self, server_config: ServerConfig, db_config: SQLServerConfig):
        super().__init__(server_config)
        self.db_config = db_config
        self._connection: Optional[pyodbc.Connection] = None
        self._pool: Optional[SQLServerConnectionPool] = None
    
    def get_tools(self) -> List:
        """Return SQL Server-specific tools."""
        from mcp.types import Tool
        
        tools = [
            BaseToolDefinitions.query_tool(),
            BaseToolDefinitions.list_tables_tool(),
            BaseToolDefinitions.describe_table_tool(),
            BaseToolDefinitions.sample_data_tool(),
            BaseToolDefinitions.count_rows_tool(),
            BaseToolDefinitions.test_connection_tool(),
        ]
        
        # Add server mode tools
        if self.db_config.mode == "server":
            tools.append(Tool(
                name="list_databases",
                description="List all databases on the server (Server Mode only)",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ))
            tools.append(Tool(
                name="switch_database",
                description="Switch to a different database (Server Mode only)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "database_name": {
                            "type": "string",
                            "description": "Name of the database to switch to"
                        }
                    },
                    "required": ["database_name"]
                }
            ))
        
        # Add SQL Server specific tools
        tools.append(Tool(
            name="get_query_stats",
            description="Get query execution statistics from DMVs (requires VIEW SERVER STATE)",
            inputSchema={
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "default": 10,
                        "description": "Number of top queries to return"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="execute_stored_procedure",
            description="Execute a stored procedure with parameters",
            inputSchema={
                "type": "object",
                "properties": {
                    "procedure_name": {
                        "type": "string",
                        "description": "Name of the stored procedure"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Procedure parameters as key-value pairs"
                    },
                    "schema": {
                        "type": "string",
                        "default": "dbo",
                        "description": "Schema containing the procedure"
                    }
                },
                "required": ["procedure_name"]
            }
        ))
        
        return tools
    
    async def connect(self) -> None:
        """Establish connection to SQL Server."""
        pool_config = PoolConfig(
            min_size=2,
            max_size=self.config.pool_size,
            connection_timeout_seconds=self.db_config.connection_timeout
        )
        
        self._pool = SQLServerConnectionPool(self.db_config, pool_config)
        await self._pool.initialize()
        
        self.logger.info(
            "Connected to SQL Server",
            host=self.db_config.host,
            database=self.db_config.database,
            mode=self.db_config.mode
        )
    
    async def disconnect(self) -> None:
        """Close SQL Server connection."""
        if self._pool:
            await self._pool.close()
        self.logger.info("Disconnected from SQL Server")
    
    async def test_connection(self) -> bool:
        """Test SQL Server connectivity."""
        try:
            async with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT @@VERSION, DB_NAME(), SUSER_SNAME()")
                row = cursor.fetchone()
                cursor.close()
                
                self.logger.info(
                    "Connection test successful",
                    version=row[0][:50] if row else "unknown",
                    database=row[1] if row else "unknown",
                    user=row[2] if row else "unknown"
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
        
        elif tool_name == "list_databases":
            return await self._list_databases()
        
        elif tool_name == "get_query_stats":
            return await self._get_query_stats(arguments.get("top_n", 10))
        
        elif tool_name == "execute_stored_procedure":
            return await self._execute_procedure(
                arguments["procedure_name"],
                arguments.get("parameters", {}),
                arguments.get("schema", "dbo")
            )
        
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def _execute_query(
        self,
        query: str,
        parameters: Optional[List] = None,
        max_rows: int = 1000
    ) -> str:
        """Execute a SQL query with security validation."""
        # Validate query
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
                
                # Get column names
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                
                # Fetch results
                rows = cursor.fetchmany(max_rows)
                truncated = len(rows) == max_rows
                
                # Convert to list of dicts
                result_rows = []
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    # Apply sensitive data masking
                    row_dict = self.security.mask_sensitive_data(row_dict)
                    result_rows.append(row_dict)
                
                execution_time = (time.time() - start_time) * 1000
                
                result = QueryResult(
                    columns=columns,
                    rows=result_rows,
                    row_count=len(result_rows),
                    execution_time_ms=execution_time,
                    truncated=truncated,
                    message=f"Returned {len(result_rows)} rows" + 
                            (" (truncated)" if truncated else "")
                )
                
                return result.model_dump_json()
                
            finally:
                cursor.close()
    
    async def _list_tables(
        self,
        schema: Optional[str] = None,
        pattern: Optional[str] = None
    ) -> str:
        """List available tables."""
        query = """
            SELECT 
                TABLE_SCHEMA as schema_name,
                TABLE_NAME as table_name,
                TABLE_TYPE as table_type
            FROM INFORMATION_SCHEMA.TABLES
            WHERE 1=1
        """
        params = []
        
        if schema:
            query += " AND TABLE_SCHEMA = ?"
            params.append(schema)
        
        if pattern:
            query += " AND TABLE_NAME LIKE ?"
            params.append(f"%{pattern}%")
        
        query += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
        
        return await self._execute_query(query, params if params else None)
    
    async def _describe_table(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> str:
        """Get table column information."""
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                COLUMN_NAME as column_name,
                DATA_TYPE as data_type,
                CHARACTER_MAXIMUM_LENGTH as max_length,
                IS_NULLABLE as is_nullable,
                COLUMN_DEFAULT as default_value
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
        """
        params = [safe_table]
        
        if schema:
            safe_schema = self.security.sanitize_identifier(schema)
            query += " AND TABLE_SCHEMA = ?"
            params.append(safe_schema)
        
        query += " ORDER BY ORDINAL_POSITION"
        
        return await self._execute_query(query, params)
    
    async def _get_sample_data(self, table_name: str, limit: int = 10) -> str:
        """Get sample rows from a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.default_schema or "dbo"
        
        query = f"SELECT TOP {int(limit)} * FROM [{schema}].[{safe_table}]"
        return await self._execute_query(query)
    
    async def _count_rows(
        self,
        table_name: str,
        where_clause: Optional[str] = None
    ) -> str:
        """Count rows in a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.default_schema or "dbo"
        
        query = f"SELECT COUNT(*) as row_count FROM [{schema}].[{safe_table}]"
        
        if where_clause:
            # Validate where clause
            is_valid, error = self.security.validate_query(f"SELECT * FROM t WHERE {where_clause}")
            if not is_valid:
                return json.dumps({"error": f"Invalid WHERE clause: {error}"})
            query += f" WHERE {where_clause}"
        
        return await self._execute_query(query)
    
    async def _list_databases(self) -> str:
        """List all databases (Server Mode)."""
        if self.db_config.mode != "server":
            return json.dumps({"error": "This operation requires Server Mode"})
        
        query = """
            SELECT 
                name as database_name,
                state_desc as state,
                recovery_model_desc as recovery_model,
                create_date
            FROM sys.databases
            WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
            ORDER BY name
        """
        return await self._execute_query(query)
    
    async def _get_query_stats(self, top_n: int = 10) -> str:
        """Get query execution statistics from DMVs."""
        query = f"""
            SELECT TOP {int(top_n)}
                qs.total_elapsed_time / qs.execution_count as avg_elapsed_time_ms,
                qs.execution_count,
                qs.total_logical_reads / qs.execution_count as avg_logical_reads,
                SUBSTRING(qt.text, 1, 200) as query_text
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            ORDER BY qs.total_elapsed_time / qs.execution_count DESC
        """
        return await self._execute_query(query)
    
    async def _execute_procedure(
        self,
        procedure_name: str,
        parameters: Dict[str, Any],
        schema: str = "dbo"
    ) -> str:
        """Execute a stored procedure."""
        safe_proc = self.security.sanitize_identifier(procedure_name)
        safe_schema = self.security.sanitize_identifier(schema)
        
        # Build parameter list
        param_placeholders = ", ".join([f"@{k} = ?" for k in parameters.keys()])
        query = f"EXEC [{safe_schema}].[{safe_proc}] {param_placeholders}"
        
        return await self._execute_query(query, list(parameters.values()))
