#!/usr/bin/env python3
"""
SQL Server MCP Server Entry Point
Launches the SQL Server MCP server with configuration from environment/files.
"""

import asyncio
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.adapters.sqlserver import SQLServerAdapter, SQLServerConfig
from src.core.base_server import ServerConfig


def load_config() -> tuple[ServerConfig, SQLServerConfig]:
    """Load configuration from environment and config files."""
    
    # Load .env file if present
    load_dotenv()
    
    # Load YAML config if present
    config_path = Path(os.getenv("MCP_CONFIG_PATH", "config/sqlserver.yaml"))
    yaml_config = {}
    if config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f)
    
    # Server configuration
    server_config = ServerConfig(
        server_name=os.getenv("MCP_SERVER_NAME", yaml_config.get("server", {}).get("name", "mcp-sqlserver")),
        server_mode=os.getenv("SQLSERVER_MODE", yaml_config.get("server", {}).get("mode", "database")),
        timeout_seconds=int(os.getenv("MCP_TIMEOUT_SECONDS", yaml_config.get("server", {}).get("timeout_seconds", 120))),
        pool_size=int(os.getenv("MCP_CONNECTION_POOL_SIZE", yaml_config.get("server", {}).get("pool_size", 10))),
        log_level=os.getenv("MCP_LOG_LEVEL", yaml_config.get("logging", {}).get("level", "INFO")),
        log_file=os.getenv("MCP_LOG_FILE", yaml_config.get("logging", {}).get("file")),
        console_logging=os.getenv("MCP_CONSOLE_LOGGING", str(yaml_config.get("logging", {}).get("console", True))).lower() == "true",
        read_only=os.getenv("MCP_READ_ONLY", str(yaml_config.get("server", {}).get("read_only", True))).lower() == "true",
        audit_queries=os.getenv("MCP_AUDIT_QUERIES", str(yaml_config.get("logging", {}).get("audit_queries", True))).lower() == "true",
    )
    
    # Database configuration
    db_config = SQLServerConfig(
        host=os.getenv("SQLSERVER_HOST", yaml_config.get("connection", {}).get("host", "localhost")),
        port=int(os.getenv("SQLSERVER_PORT", yaml_config.get("connection", {}).get("port", 1433))),
        database=os.getenv("SQLSERVER_DATABASE", yaml_config.get("connection", {}).get("database", "master")),
        user=os.getenv("SQLSERVER_USER", yaml_config.get("connection", {}).get("user", "")),
        password=os.getenv("SQLSERVER_PASSWORD", ""),
        mode=os.getenv("SQLSERVER_MODE", yaml_config.get("server", {}).get("mode", "database")),
        encrypt=os.getenv("SQLSERVER_ENCRYPT", str(yaml_config.get("security", {}).get("encrypt", True))).lower() == "true",
        trust_server_certificate=os.getenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", str(yaml_config.get("security", {}).get("trust_server_certificate", False))).lower() == "true",
        use_read_replica=os.getenv("SQLSERVER_USE_READ_REPLICA", str(yaml_config.get("security", {}).get("use_read_replica", False))).lower() == "true",
        connection_timeout=int(os.getenv("SQLSERVER_CONNECTION_TIMEOUT", 30)),
        query_timeout=int(os.getenv("SQLSERVER_QUERY_TIMEOUT", server_config.timeout_seconds)),
        default_schema=os.getenv("SQLSERVER_SCHEMA", yaml_config.get("connection", {}).get("default_schema")),
    )
    
    return server_config, db_config


async def main():
    """Main entry point."""
    print("=" * 60)
    print("SQL Server MCP Server")
    print("=" * 60)
    
    try:
        server_config, db_config = load_config()
        
        print(f"Server Name: {server_config.server_name}")
        print(f"Mode: {db_config.mode}")
        print(f"Host: {db_config.host}:{db_config.port}")
        print(f"Database: {db_config.database}")
        print(f"Pool Size: {server_config.pool_size}")
        print(f"Read-Only: {server_config.read_only}")
        print("=" * 60)
        
        # Create and run server
        server = SQLServerAdapter(server_config, db_config)
        await server.run()
        
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
