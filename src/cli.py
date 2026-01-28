#!/usr/bin/env python3
"""
MCP SQL Universal CLI
Command-line interface for launching MCP servers.

Usage:
    mcp-sql-server --type sqlserver --config config/sqlserver.yaml
    mcp-sql-server --type snowflake
    mcp-sql-server --type azure --host myserver.database.windows.net
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="MCP SQL Universal Server - Launch MCP servers for various SQL databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Launch SQL Server MCP with config file
    mcp-sql-server --type sqlserver --config config/sqlserver.yaml

    # Launch Snowflake MCP with environment variables
    mcp-sql-server --type snowflake

    # Launch Azure SQL with explicit host
    mcp-sql-server --type azure --host myserver.database.windows.net --database mydb

    # Launch with custom port
    mcp-sql-server --type postgres --port 8080

Supported database types:
    sqlserver   - Microsoft SQL Server
    azure       - Azure SQL Database
    snowflake   - Snowflake Data Cloud
    hana        - SAP HANA
    postgres    - PostgreSQL
    mysql       - MySQL
    oracle      - Oracle Database

ERP types (specialized configurations):
    dynamics365 - Microsoft Dynamics 365
    sap_s4hana  - SAP S/4HANA
    netsuite    - Oracle NetSuite
    workday     - Workday
        """
    )
    
    parser.add_argument(
        "--type", "-t",
        required=True,
        choices=["sqlserver", "azure", "snowflake", "hana", "postgres", "mysql", "oracle",
                 "dynamics365", "sap_s4hana", "netsuite", "workday"],
        help="Database or ERP type to launch"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=Path,
        help="Path to YAML configuration file"
    )
    
    parser.add_argument(
        "--host",
        help="Database host (overrides config/env)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        help="MCP server port (default: 8000)"
    )
    
    parser.add_argument(
        "--database", "--db",
        help="Database name (overrides config/env)"
    )
    
    parser.add_argument(
        "--user", "-u",
        help="Database username (overrides config/env)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Query timeout in seconds (default: 120)"
    )
    
    parser.add_argument(
        "--pool-size",
        type=int,
        default=10,
        help="Connection pool size (default: 10)"
    )
    
    parser.add_argument(
        "--read-only",
        action="store_true",
        default=True,
        help="Enforce read-only mode (default: True)"
    )
    
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file (default: .env)"
    )
    
    return parser


async def run_server(db_type: str, args: argparse.Namespace) -> None:
    """Run the appropriate MCP server based on type."""
    
    # Set environment variables from CLI args
    if args.host:
        os.environ[f"{db_type.upper()}_HOST"] = args.host
    if args.database:
        os.environ[f"{db_type.upper()}_DATABASE"] = args.database
    if args.user:
        os.environ[f"{db_type.upper()}_USER"] = args.user
    
    os.environ["MCP_LOG_LEVEL"] = args.log_level
    os.environ["MCP_TIMEOUT_SECONDS"] = str(args.timeout)
    os.environ["MCP_CONNECTION_POOL_SIZE"] = str(args.pool_size)
    
    if args.config:
        os.environ["MCP_CONFIG_PATH"] = str(args.config)
    
    # Import and run the appropriate server
    if db_type == "sqlserver":
        from src.servers.sqlserver_server import main
        await main()
    
    elif db_type == "azure":
        from src.adapters.azure_sql import AzureSQLAdapter, AzureSQLConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-azure-sql",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=args.read_only,
        )
        
        db_config = AzureSQLConfig(
            server=os.getenv("AZURE_SQL_SERVER", args.host or ""),
            database=os.getenv("AZURE_SQL_DATABASE", args.database or ""),
            auth_method=os.getenv("AZURE_SQL_AUTH_METHOD", "sql"),
            user=os.getenv("AZURE_SQL_USER", args.user),
            password=os.getenv("AZURE_SQL_PASSWORD", ""),
        )
        
        server = AzureSQLAdapter(server_config, db_config)
        await server.run()
    
    elif db_type == "snowflake":
        from src.adapters.snowflake import SnowflakeAdapter, SnowflakeConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-snowflake",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=args.read_only,
        )
        
        db_config = SnowflakeConfig(
            account_url=os.getenv("SNOWFLAKE_ACCOUNT_URL", ""),
            account=os.getenv("SNOWFLAKE_ACCOUNT", ""),
            user=os.getenv("SNOWFLAKE_USER", args.user or ""),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", ""),
            database=os.getenv("SNOWFLAKE_DATABASE", args.database or ""),
            schema_name=os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
            role=os.getenv("SNOWFLAKE_ROLE", "PUBLIC"),
        )
        
        server = SnowflakeAdapter(server_config, db_config)
        await server.run()
    
    elif db_type == "hana":
        from src.adapters.sap_hana import SAPHanaAdapter, SAPHanaConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-sap-hana",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=args.read_only,
        )
        
        db_config = SAPHanaConfig(
            connection_type=os.getenv("HANA_CONNECTION_TYPE", "single"),
            host=os.getenv("HANA_HOST", args.host or ""),
            port=int(os.getenv("HANA_PORT", "30015")),
            user=os.getenv("HANA_USER", args.user or ""),
            password=os.getenv("HANA_PASSWORD", ""),
            database_name=os.getenv("HANA_DATABASE_NAME", args.database),
        )
        
        server = SAPHanaAdapter(server_config, db_config)
        await server.run()
    
    elif db_type == "postgres":
        from src.adapters.postgresql import PostgreSQLAdapter, PostgreSQLConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-postgres",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=args.read_only,
        )
        
        db_config = PostgreSQLConfig(
            host=os.getenv("POSTGRES_HOST", args.host or "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DATABASE", args.database or ""),
            user=os.getenv("POSTGRES_USER", args.user or ""),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            schema_name=os.getenv("POSTGRES_SCHEMA", "public"),
        )
        
        server = PostgreSQLAdapter(server_config, db_config)
        await server.run()
    
    # ERP types
    elif db_type == "dynamics365":
        print("Dynamics 365 uses Azure SQL backend - launching with ERP extensions...")
        os.environ["ERP_TYPE"] = "dynamics365"
        os.environ["MCP_CONFIG_PATH"] = str(args.config or "config/erp/dynamics365.yaml")
        
        from src.adapters.azure_sql import AzureSQLAdapter, AzureSQLConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-dynamics365",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=True,
        )
        
        db_config = AzureSQLConfig(
            server=os.getenv("DYNAMICS365_SQL_SERVER", args.host or ""),
            database=os.getenv("DYNAMICS365_SQL_DATABASE", args.database or ""),
            auth_method="entra_id_service_principal",
            tenant_id=os.getenv("DYNAMICS365_TENANT_ID"),
            client_id=os.getenv("DYNAMICS365_CLIENT_ID"),
            client_secret=os.getenv("DYNAMICS365_CLIENT_SECRET"),
        )
        
        server = AzureSQLAdapter(server_config, db_config)
        await server.run()
    
    elif db_type == "sap_s4hana":
        print("SAP S/4HANA uses HANA backend - launching with ERP extensions...")
        os.environ["ERP_TYPE"] = "sap_s4hana"
        os.environ["MCP_CONFIG_PATH"] = str(args.config or "config/erp/sap_s4hana.yaml")
        
        from src.adapters.sap_hana import SAPHanaAdapter, SAPHanaConfig
        from src.core.base_server import ServerConfig
        
        server_config = ServerConfig(
            server_name="mcp-sap-s4hana",
            timeout_seconds=args.timeout,
            pool_size=args.pool_size,
            log_level=args.log_level,
            read_only=True,
        )
        
        db_config = SAPHanaConfig(
            connection_type="mdc_tenant",
            host=os.getenv("SAP_S4HANA_HOST", args.host or ""),
            port=int(os.getenv("SAP_S4HANA_PORT", "30015")),
            user=os.getenv("SAP_S4HANA_USER", args.user or ""),
            password=os.getenv("SAP_S4HANA_PASSWORD", ""),
            database_name=os.getenv("SAP_S4HANA_DATABASE", args.database),
            instance_number=os.getenv("SAP_S4HANA_INSTANCE", "00"),
        )
        
        server = SAPHanaAdapter(server_config, db_config)
        await server.run()
    
    else:
        print(f"Server type '{db_type}' not yet implemented")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load environment file
    if args.env_file.exists():
        load_dotenv(args.env_file)
    
    print("=" * 60)
    print("MCP SQL Universal Server")
    print("=" * 60)
    print(f"Type: {args.type}")
    print(f"Log Level: {args.log_level}")
    print(f"Pool Size: {args.pool_size}")
    print(f"Timeout: {args.timeout}s")
    print("=" * 60)
    
    try:
        asyncio.run(run_server(args.type, args))
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
