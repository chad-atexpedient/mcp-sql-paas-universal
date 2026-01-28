"""
Database Adapters for MCP SQL Servers.

Each adapter provides database-specific implementation
for the common MCP server interface.
"""

from .sqlserver import SQLServerAdapter
from .azure_sql import AzureSQLAdapter
from .snowflake import SnowflakeAdapter
from .sap_hana import SAPHanaAdapter
from .postgresql import PostgreSQLAdapter

__all__ = [
    "SQLServerAdapter",
    "AzureSQLAdapter", 
    "SnowflakeAdapter",
    "SAPHanaAdapter",
    "PostgreSQLAdapter",
]
