"""
PostgreSQL Adapter for MCP
Provides PostgreSQL-specific database operations.

Best Practices Implemented:
- SSL/TLS encryption support
- Connection pooling with asyncpg
- Schema-based access control
- Azure PostgreSQL Entra ID support
"""

import json
import time
from typing import Any, Dict, List, Optional

import asyncpg
from pydantic import BaseModel, Field

from ..core.base_server import BaseMCPServer, BaseToolDefinitions, QueryResult, ServerConfig
from ..core.connection_pool import ConnectionPoolManager, PoolConfig
from ..core.security import SecurityManager


class PostgreSQLConfig(BaseModel):
    """PostgreSQL connection configuration."""
    
    host: str = Field(..., description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    database: str = Field(..., description="Database name")
    user: str = Field(..., description="Username")
    password: Optional[str] = None
    
    # Schema settings
    schema_name: str = Field(default="public", description="Default schema")
    search_path: Optional[List[str]] = None
    
    # SSL settings
    ssl_mode: str = Field(
        default="prefer",
        description="disable, allow, prefer, require, verify-ca, verify-full"
    )
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    ssl_root_cert: Optional[str] = None
    
    # Azure PostgreSQL specific
    azure_entra_id: bool = Field(default=False)
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    
    # Connection settings
    connection_timeout: int = Field(default=30)
    query_timeout: int = Field(default=120)


class PostgreSQLConnectionPool(ConnectionPoolManager[asyncpg.Connection]):
    """Connection pool for PostgreSQL using asyncpg."""
    
    def __init__(self, config: PostgreSQLConfig, pool_config: PoolConfig):
        super().__init__(pool_config)
        self.db_config = config
        self._asyncpg_pool: Optional[asyncpg.Pool] = None
    
    async def _get_azure_token(self) -> str:
        """Get Azure AD token for PostgreSQL authentication."""
        from msal import ConfidentialClientApplication
        
        app = ConfidentialClientApplication(
            self.db_config.azure_client_id,
            authority=f"https://login.microsoftonline.com/{self.db_config.azure_tenant_id}",
            client_credential=self.db_config.azure_client_secret
        )
        
        result = app.acquire_token_for_client(
            scopes=["https://ossrdbms-aad.database.windows.net/.default"]
        )
        
        if "access_token" in result:
            return result["access_token"]
        else:
            raise Exception(f"Failed to get token: {result.get('error_description')}")
    
    async def _create_connection(self) -> asyncpg.Connection:
        """Create a new PostgreSQL connection."""
        ssl_context = None
        
        if self.db_config.ssl_mode not in ("disable", "allow"):
            import ssl
            ssl_context = ssl.create_default_context()
            
            if self.db_config.ssl_root_cert:
                ssl_context.load_verify_locations(self.db_config.ssl_root_cert)
            
            if self.db_config.ssl_cert and self.db_config.ssl_key:
                ssl_context.load_cert_chain(
                    self.db_config.ssl_cert,
                    self.db_config.ssl_key
                )
            
            if self.db_config.ssl_mode == "verify-full":
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
            elif self.db_config.ssl_mode == "verify-ca":
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_REQUIRED
            else:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        
        password = self.db_config.password
        if self.db_config.azure_entra_id:
            password = await self._get_azure_token()
        
        connection = await asyncpg.connect(
            host=self.db_config.host,
            port=self.db_config.port,
            database=self.db_config.database,
            user=self.db_config.user,
            password=password,
            ssl=ssl_context,
            timeout=self.db_config.connection_timeout
        )
        
        # Set search path
        if self.db_config.search_path:
            search_path = ", ".join(self.db_config.search_path)
            await connection.execute(f"SET search_path TO {search_path}")
        
        return connection
    
    async def _close_connection(self, connection: asyncpg.Connection) -> None:
        """Close a PostgreSQL connection."""
        try:
            await connection.close()
        except Exception:
            pass
    
    async def _is_connection_healthy(self, connection: asyncpg.Connection) -> bool:
        """Check if connection is healthy."""
        try:
            await connection.fetchval("SELECT 1")
            return True
        except Exception:
            return False


class PostgreSQLAdapter(BaseMCPServer):
    """
    MCP Server adapter for PostgreSQL.
    
    Supports:
    - Standard PostgreSQL
    - Azure Database for PostgreSQL
    - Amazon RDS PostgreSQL
    - Schema-based access control
    """
    
    def __init__(self, server_config: ServerConfig, db_config: PostgreSQLConfig):
        super().__init__(server_config)
        self.db_config = db_config
        self._pool: Optional[PostgreSQLConnectionPool] = None
    
    def get_tools(self) -> List:
        """Return PostgreSQL-specific tools."""
        from mcp.types import Tool
        
        tools = [
            BaseToolDefinitions.query_tool(),
            BaseToolDefinitions.list_tables_tool(),
            BaseToolDefinitions.describe_table_tool(),
            BaseToolDefinitions.sample_data_tool(),
            BaseToolDefinitions.count_rows_tool(),
            BaseToolDefinitions.test_connection_tool(),
        ]
        
        # PostgreSQL-specific tools
        tools.append(Tool(
            name="list_schemas",
            description="List all schemas in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_system": {
                        "type": "boolean",
                        "default": False
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="list_indexes",
            description="List indexes for a table",
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
            name="explain_query",
            description="Get query execution plan",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query to explain"
                    },
                    "analyze": {
                        "type": "boolean",
                        "default": False,
                        "description": "Run EXPLAIN ANALYZE (executes the query)"
                    },
                    "format": {
                        "type": "string",
                        "default": "text",
                        "description": "Output format: text, json, yaml"
                    }
                },
                "required": ["query"]
            }
        ))
        
        tools.append(Tool(
            name="get_table_statistics",
            description="Get table statistics (pg_stat_user_tables)",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Table name (optional, all tables if not specified)"
                    },
                    "schema": {
                        "type": "string",
                        "description": "Schema name"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_active_queries",
            description="Get currently running queries",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_idle": {
                        "type": "boolean",
                        "default": False
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_table_size",
            description="Get table and index sizes",
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
            name="list_extensions",
            description="List installed PostgreSQL extensions",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        return tools
    
    async def connect(self) -> None:
        """Establish connection to PostgreSQL."""
        pool_config = PoolConfig(
            min_size=2,
            max_size=self.config.pool_size,
            connection_timeout_seconds=self.db_config.connection_timeout
        )
        
        self._pool = PostgreSQLConnectionPool(self.db_config, pool_config)
        await self._pool.initialize()
        
        self.logger.info(
            "Connected to PostgreSQL",
            host=self.db_config.host,
            database=self.db_config.database,
            schema=self.db_config.schema_name
        )
    
    async def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self._pool:
            await self._pool.close()
        self.logger.info("Disconnected from PostgreSQL")
    
    async def test_connection(self) -> bool:
        """Test PostgreSQL connectivity."""
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT 
                        version(),
                        current_database(),
                        current_schema(),
                        current_user
                """)
                
                self.logger.info(
                    "Connection test successful",
                    version=row[0][:50] if row else "unknown",
                    database=row[1] if row else "unknown",
                    schema=row[2] if row else "unknown"
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
        
        elif tool_name == "list_indexes":
            return await self._list_indexes(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        elif tool_name == "explain_query":
            return await self._explain_query(
                arguments["query"],
                arguments.get("analyze", False),
                arguments.get("format", "text")
            )
        
        elif tool_name == "get_table_statistics":
            return await self._get_table_statistics(
                arguments.get("table_name"),
                arguments.get("schema")
            )
        
        elif tool_name == "get_active_queries":
            return await self._get_active_queries(arguments.get("include_idle", False))
        
        elif tool_name == "get_table_size":
            return await self._get_table_size(
                arguments["table_name"],
                arguments.get("schema")
            )
        
        elif tool_name == "list_extensions":
            return await self._list_extensions()
        
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
            try:
                # Add LIMIT if not present and it's a SELECT
                if query.strip().upper().startswith("SELECT") and "LIMIT" not in query.upper():
                    query = f"{query} LIMIT {max_rows}"
                
                if parameters:
                    rows = await conn.fetch(query, *parameters)
                else:
                    rows = await conn.fetch(query)
                
                columns = list(rows[0].keys()) if rows else []
                truncated = len(rows) == max_rows
                
                result_rows = []
                for row in rows:
                    row_dict = dict(row)
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
                
            except Exception as e:
                return json.dumps({"error": str(e)})
    
    async def _list_tables(self, schema: Optional[str] = None, pattern: Optional[str] = None) -> str:
        """List available tables."""
        schema = schema or self.db_config.schema_name
        
        query = """
            SELECT 
                table_schema,
                table_name,
                table_type
            FROM information_schema.tables
            WHERE table_schema = $1
        """
        params = [schema]
        
        if pattern:
            query += " AND table_name LIKE $2"
            params.append(f"%{pattern}%")
        
        query += " ORDER BY table_schema, table_name"
        
        return await self._execute_query(query, params)
    
    async def _describe_table(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table column information."""
        schema = schema or self.db_config.schema_name
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
        """
        return await self._execute_query(query, [schema, safe_table])
    
    async def _get_sample_data(self, table_name: str, limit: int = 10) -> str:
        """Get sample rows from a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name
        query = f'SELECT * FROM "{schema}"."{safe_table}" LIMIT {int(limit)}'
        return await self._execute_query(query)
    
    async def _count_rows(self, table_name: str, where_clause: Optional[str] = None) -> str:
        """Count rows in a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.schema_name
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
                schema_name,
                schema_owner
            FROM information_schema.schemata
        """
        if not include_system:
            query += " WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"
        query += " ORDER BY schema_name"
        return await self._execute_query(query)
    
    async def _list_indexes(self, table_name: str, schema: Optional[str] = None) -> str:
        """List indexes for a table."""
        schema = schema or self.db_config.schema_name
        safe_table = self.security.sanitize_identifier(table_name)
        
        query = """
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = $1 AND tablename = $2
            ORDER BY indexname
        """
        return await self._execute_query(query, [schema, safe_table])
    
    async def _explain_query(
        self,
        query: str,
        analyze: bool = False,
        format: str = "text"
    ) -> str:
        """Get query execution plan."""
        is_valid, error = self.security.validate_query(query)
        if not is_valid:
            return json.dumps({"error": error})
        
        explain_query = f"EXPLAIN (FORMAT {format.upper()}"
        if analyze:
            explain_query += ", ANALYZE"
        explain_query += f") {query}"
        
        return await self._execute_query(explain_query)
    
    async def _get_table_statistics(
        self,
        table_name: Optional[str] = None,
        schema: Optional[str] = None
    ) -> str:
        """Get table statistics."""
        query = """
            SELECT 
                schemaname,
                relname as table_name,
                seq_scan,
                seq_tup_read,
                idx_scan,
                idx_tup_fetch,
                n_tup_ins,
                n_tup_upd,
                n_tup_del,
                n_live_tup,
                n_dead_tup,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE 1=1
        """
        params = []
        
        if schema:
            query += f" AND schemaname = ${len(params) + 1}"
            params.append(schema)
        
        if table_name:
            query += f" AND relname = ${len(params) + 1}"
            params.append(self.security.sanitize_identifier(table_name))
        
        query += " ORDER BY schemaname, relname"
        
        return await self._execute_query(query, params if params else None)
    
    async def _get_active_queries(self, include_idle: bool = False) -> str:
        """Get currently running queries."""
        query = """
            SELECT 
                pid,
                usename,
                datname,
                state,
                query_start,
                now() - query_start as duration,
                query
            FROM pg_stat_activity
            WHERE datname = current_database()
        """
        
        if not include_idle:
            query += " AND state != 'idle'"
        
        query += " ORDER BY query_start"
        return await self._execute_query(query)
    
    async def _get_table_size(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table and index sizes."""
        schema = schema or self.db_config.schema_name
        safe_table = self.security.sanitize_identifier(table_name)
        full_name = f'"{schema}"."{safe_table}"'
        
        query = f"""
            SELECT 
                pg_size_pretty(pg_total_relation_size('{full_name}')) as total_size,
                pg_size_pretty(pg_table_size('{full_name}')) as table_size,
                pg_size_pretty(pg_indexes_size('{full_name}')) as indexes_size,
                (SELECT reltuples FROM pg_class WHERE oid = '{full_name}'::regclass) as estimated_rows
        """
        return await self._execute_query(query)
    
    async def _list_extensions(self) -> str:
        """List installed extensions."""
        query = """
            SELECT 
                extname,
                extversion,
                extrelocatable
            FROM pg_extension
            ORDER BY extname
        """
        return await self._execute_query(query)
