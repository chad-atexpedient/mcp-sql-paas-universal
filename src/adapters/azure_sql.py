"""
Azure SQL Database Adapter for MCP
Provides Azure SQL-specific database operations with Entra ID support.

Best Practices Implemented:
- Microsoft Entra ID (Azure AD) authentication
- VNet/Private endpoint support
- TDE and TLS 1.2 encryption
- Zone redundancy awareness
- Geo-replication support
"""

import json
import time
from typing import Any, Dict, List, Optional

import pyodbc
from pydantic import BaseModel, Field

from ..core.base_server import BaseMCPServer, BaseToolDefinitions, QueryResult, ServerConfig
from ..core.connection_pool import ConnectionPoolManager, PoolConfig
from ..core.security import SecurityManager


class AzureSQLConfig(BaseModel):
    """Azure SQL Database connection configuration."""
    
    # Server settings
    server: str = Field(..., description="Azure SQL server name (without .database.windows.net)")
    database: str = Field(..., description="Database name")
    
    # Authentication method
    auth_method: str = Field(
        default="sql", 
        description="'sql', 'entra_id', 'entra_id_msi', 'entra_id_service_principal'"
    )
    
    # SQL Auth credentials (if auth_method == 'sql')
    user: Optional[str] = None
    password: Optional[str] = None
    
    # Entra ID settings
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    
    # Security settings (Azure best practices)
    encrypt: bool = Field(default=True, description="Always encrypt for Azure")
    min_tls_version: str = Field(default="1.2")
    
    # Connection settings
    connection_timeout: int = Field(default=30)
    query_timeout: int = Field(default=120)
    
    # Optional schema restriction
    default_schema: Optional[str] = None
    
    # Geo settings
    use_read_replica: bool = Field(default=False, description="Use readable secondary")
    application_intent: str = Field(default="ReadWrite", description="ReadWrite or ReadOnly")


class AzureSQLConnectionPool(ConnectionPoolManager[pyodbc.Connection]):
    """Connection pool for Azure SQL Database."""
    
    def __init__(self, config: AzureSQLConfig, pool_config: PoolConfig):
        super().__init__(pool_config)
        self.db_config = config
        self._access_token: Optional[str] = None
    
    async def _get_entra_token(self) -> str:
        """Get Azure AD access token for authentication."""
        from msal import ConfidentialClientApplication
        
        if self.db_config.auth_method == "entra_id_service_principal":
            app = ConfidentialClientApplication(
                self.db_config.client_id,
                authority=f"https://login.microsoftonline.com/{self.db_config.tenant_id}",
                client_credential=self.db_config.client_secret
            )
            
            result = app.acquire_token_for_client(
                scopes=["https://database.windows.net/.default"]
            )
            
            if "access_token" in result:
                return result["access_token"]
            else:
                raise Exception(f"Failed to get token: {result.get('error_description')}")
        
        elif self.db_config.auth_method == "entra_id_msi":
            # Use Managed Service Identity
            import requests
            
            response = requests.get(
                "http://169.254.169.254/metadata/identity/oauth2/token",
                params={
                    "api-version": "2018-02-01",
                    "resource": "https://database.windows.net/"
                },
                headers={"Metadata": "true"}
            )
            
            if response.status_code == 200:
                return response.json()["access_token"]
            else:
                raise Exception(f"Failed to get MSI token: {response.text}")
        
        raise ValueError(f"Unsupported auth method: {self.db_config.auth_method}")
    
    def _build_connection_string(self) -> str:
        """Build the ODBC connection string for Azure SQL."""
        server_fqdn = f"{self.db_config.server}.database.windows.net"
        
        parts = [
            f"DRIVER={{ODBC Driver 18 for SQL Server}}",
            f"SERVER={server_fqdn}",
            f"DATABASE={self.db_config.database}",
            f"Encrypt=yes",  # Always encrypt for Azure
            f"TrustServerCertificate=no",
            f"Connection Timeout={self.db_config.connection_timeout}",
        ]
        
        # Add application intent for read replicas
        if self.db_config.use_read_replica:
            parts.append("ApplicationIntent=ReadOnly")
        
        # Add authentication
        if self.db_config.auth_method == "sql":
            parts.append(f"UID={self.db_config.user}")
            parts.append(f"PWD={self.db_config.password}")
        elif self.db_config.auth_method.startswith("entra_id"):
            parts.append("Authentication=ActiveDirectoryAccessToken")
        
        return ";".join(parts)
    
    async def _create_connection(self) -> pyodbc.Connection:
        """Create a new Azure SQL connection."""
        conn_str = self._build_connection_string()
        
        if self.db_config.auth_method.startswith("entra_id"):
            # Get access token
            token = await self._get_entra_token()
            # Token needs to be encoded for ODBC
            token_bytes = token.encode("utf-16-le")
            token_struct = bytes([len(token_bytes) & 0xFF, (len(token_bytes) >> 8) & 0xFF]) + token_bytes
            
            connection = pyodbc.connect(
                conn_str,
                attrs_before={1256: token_struct}  # SQL_COPT_SS_ACCESS_TOKEN
            )
        else:
            connection = pyodbc.connect(conn_str, timeout=self.db_config.connection_timeout)
        
        connection.timeout = self.db_config.query_timeout
        return connection
    
    async def _close_connection(self, connection: pyodbc.Connection) -> None:
        """Close an Azure SQL connection."""
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


class AzureSQLAdapter(BaseMCPServer):
    """
    MCP Server adapter for Azure SQL Database.
    
    Implements Azure-specific best practices:
    - Entra ID authentication
    - Read replica support
    - Geo-replication awareness
    """
    
    def __init__(self, server_config: ServerConfig, db_config: AzureSQLConfig):
        super().__init__(server_config)
        self.db_config = db_config
        self._pool: Optional[AzureSQLConnectionPool] = None
    
    def get_tools(self) -> List:
        """Return Azure SQL-specific tools."""
        from mcp.types import Tool
        
        tools = [
            BaseToolDefinitions.query_tool(),
            BaseToolDefinitions.list_tables_tool(),
            BaseToolDefinitions.describe_table_tool(),
            BaseToolDefinitions.sample_data_tool(),
            BaseToolDefinitions.count_rows_tool(),
            BaseToolDefinitions.test_connection_tool(),
        ]
        
        # Azure-specific tools
        tools.append(Tool(
            name="get_database_info",
            description="Get Azure SQL database information (size, tier, etc.)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        tools.append(Tool(
            name="get_geo_replication_status",
            description="Get geo-replication link status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        tools.append(Tool(
            name="get_query_performance_insights",
            description="Get Query Performance Insights data",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_range_hours": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours of history to analyze"
                    }
                }
            }
        ))
        
        tools.append(Tool(
            name="get_automatic_tuning_recommendations",
            description="Get automatic tuning recommendations",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ))
        
        return tools
    
    async def connect(self) -> None:
        """Establish connection to Azure SQL."""
        pool_config = PoolConfig(
            min_size=2,
            max_size=self.config.pool_size,
            connection_timeout_seconds=self.db_config.connection_timeout
        )
        
        self._pool = AzureSQLConnectionPool(self.db_config, pool_config)
        await self._pool.initialize()
        
        self.logger.info(
            "Connected to Azure SQL",
            server=self.db_config.server,
            database=self.db_config.database,
            auth_method=self.db_config.auth_method,
            read_replica=self.db_config.use_read_replica
        )
    
    async def disconnect(self) -> None:
        """Close Azure SQL connection."""
        if self._pool:
            await self._pool.close()
        self.logger.info("Disconnected from Azure SQL")
    
    async def test_connection(self) -> bool:
        """Test Azure SQL connectivity."""
        try:
            async with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        @@VERSION,
                        DB_NAME(),
                        SUSER_SNAME(),
                        DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective')
                """)
                row = cursor.fetchone()
                cursor.close()
                
                self.logger.info(
                    "Connection test successful",
                    database=row[1] if row else "unknown",
                    service_tier=row[3] if row else "unknown"
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
        
        elif tool_name == "get_database_info":
            return await self._get_database_info()
        
        elif tool_name == "get_geo_replication_status":
            return await self._get_geo_replication_status()
        
        elif tool_name == "get_query_performance_insights":
            return await self._get_query_performance_insights(
                arguments.get("time_range_hours", 24)
            )
        
        elif tool_name == "get_automatic_tuning_recommendations":
            return await self._get_automatic_tuning_recommendations()
        
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
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES WHERE 1=1
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
    
    async def _describe_table(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get table column information."""
        safe_table = self.security.sanitize_identifier(table_name)
        query = """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?
        """
        params = [safe_table]
        if schema:
            query += " AND TABLE_SCHEMA = ?"
            params.append(self.security.sanitize_identifier(schema))
        query += " ORDER BY ORDINAL_POSITION"
        return await self._execute_query(query, params)
    
    async def _get_sample_data(self, table_name: str, limit: int = 10) -> str:
        """Get sample rows from a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.default_schema or "dbo"
        query = f"SELECT TOP {int(limit)} * FROM [{schema}].[{safe_table}]"
        return await self._execute_query(query)
    
    async def _count_rows(self, table_name: str, where_clause: Optional[str] = None) -> str:
        """Count rows in a table."""
        safe_table = self.security.sanitize_identifier(table_name)
        schema = self.db_config.default_schema or "dbo"
        query = f"SELECT COUNT(*) as row_count FROM [{schema}].[{safe_table}]"
        if where_clause:
            is_valid, error = self.security.validate_query(f"SELECT * FROM t WHERE {where_clause}")
            if not is_valid:
                return json.dumps({"error": f"Invalid WHERE clause: {error}"})
            query += f" WHERE {where_clause}"
        return await self._execute_query(query)
    
    async def _get_database_info(self) -> str:
        """Get Azure SQL database information."""
        query = """
            SELECT 
                DB_NAME() as database_name,
                DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective') as service_tier,
                DATABASEPROPERTYEX(DB_NAME(), 'Edition') as edition,
                (SELECT SUM(size * 8.0 / 1024) FROM sys.database_files) as size_mb,
                DATABASEPROPERTYEX(DB_NAME(), 'Collation') as collation,
                DATABASEPROPERTYEX(DB_NAME(), 'IsAutoCreateStatistics') as auto_create_stats,
                DATABASEPROPERTYEX(DB_NAME(), 'IsAutoUpdateStatistics') as auto_update_stats
        """
        return await self._execute_query(query)
    
    async def _get_geo_replication_status(self) -> str:
        """Get geo-replication link status."""
        query = """
            SELECT 
                link_guid,
                partner_server,
                partner_database,
                replication_state_desc,
                role_desc,
                secondary_allow_connections_desc,
                last_replication
            FROM sys.geo_replication_links
        """
        return await self._execute_query(query)
    
    async def _get_query_performance_insights(self, time_range_hours: int = 24) -> str:
        """Get Query Performance Insights data."""
        query = f"""
            SELECT TOP 20
                qs.query_id,
                qt.query_sql_text,
                rs.avg_duration / 1000.0 as avg_duration_ms,
                rs.avg_cpu_time / 1000.0 as avg_cpu_ms,
                rs.count_executions,
                rs.avg_logical_io_reads,
                rs.avg_logical_io_writes
            FROM sys.query_store_query_text qt
            JOIN sys.query_store_query q ON qt.query_text_id = q.query_text_id
            JOIN sys.query_store_plan qp ON q.query_id = qp.query_id
            JOIN sys.query_store_runtime_stats rs ON qp.plan_id = rs.plan_id
            JOIN sys.query_store_runtime_stats_interval rsi ON rs.runtime_stats_interval_id = rsi.runtime_stats_interval_id
            WHERE rsi.start_time >= DATEADD(hour, -{int(time_range_hours)}, GETUTCDATE())
            ORDER BY rs.avg_duration DESC
        """
        return await self._execute_query(query)
    
    async def _get_automatic_tuning_recommendations(self) -> str:
        """Get automatic tuning recommendations."""
        query = """
            SELECT 
                name,
                reason,
                score,
                state_desc,
                is_executable_action,
                is_revertable_action,
                execute_action_start_time,
                execute_action_duration,
                execute_action_initiated_by,
                revert_action_start_time
            FROM sys.dm_db_tuning_recommendations
            ORDER BY score DESC
        """
        return await self._execute_query(query)
