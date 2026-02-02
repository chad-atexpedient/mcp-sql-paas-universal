# 🚀 MCP SQL PaaS Universal Framework

A comprehensive **Model Context Protocol (MCP)** server framework supporting multiple SQL databases and ERP systems with containerized deployment options.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/mcp-sql-universal?referralCode=expedient)

## 📋 Overview

This framework provides launchable MCP servers for various SQL databases and ERP systems, following 2024 industry best practices for security, performance, and operational efficiency.

### Supported SQL Databases

| Database | Status | Container | SDK Ready |
|----------|--------|-----------|-----------|
| **SQL Server** | ✅ Ready | ✅ | ✅ |
| **Azure SQL** | ✅ Ready | ✅ | ✅ |
| **Snowflake** | ✅ Ready | ✅ | ✅ |
| **PostgreSQL** | ✅ Ready | ✅ | ✅ |
| **SAP HANA** | ✅ Ready | ✅ | ✅ |
| **MySQL** | ✅ Ready | ✅ | ✅ |
| **Oracle DB** | ✅ Ready | ✅ | ✅ |

### Supported ERP Systems

| ERP System | Database Backend | Status |
|------------|-----------------|--------|
| **SAP S/4HANA** | SAP HANA | ✅ Ready |
| **SAP ECC** | SQL Server/Oracle | ✅ Ready |
| **Oracle ERP Cloud** | Oracle DB | ✅ Ready |
| **Microsoft Dynamics 365** | Azure SQL | ✅ Ready |
| **NetSuite** | Oracle DB | ✅ Ready |
| **Workday** | PostgreSQL | ✅ Ready |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (Claude, etc.)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP Protocol
┌─────────────────────────▼───────────────────────────────────┐
│                  MCP Server Factory                          │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
│  │ SQL Srv │ Azure   │Snowflake│ SAP     │ Postgre │       │
│  │ Adapter │ Adapter │ Adapter │ Adapter │ Adapter │       │
│  └────┬────┴────┬────┴────┬────┴────┬────┴────┬────┘       │
└───────┼─────────┼─────────┼─────────┼─────────┼─────────────┘
        │         │         │         │         │
   ┌────▼────┐┌───▼────┐┌───▼────┐┌───▼────┐┌───▼────┐
   │SQL Srv  ││Azure   ││Snowflake││SAP HANA││ PostgreSQL│
   │Database ││SQL DB  ││Warehouse││Database││ Database  │
   └─────────┘└────────┘└─────────┘└─────────┘└───────────┘
```

## 🚀 Quick Start

### 🚂 Deploy to Railway (Fastest)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/mcp-sql-universal)

1. Click the button above
2. Configure your database credentials as environment variables
3. Deploy! 🎉

**See:** [Railway Deployment Guide](RAILWAY_DEPLOYMENT.md) for detailed instructions.

### Using Docker (Recommended for Local Development)

```bash
# Clone the repository
git clone https://github.com/chad-atexpedient/mcp-sql-paas-universal.git
cd mcp-sql-paas-universal

# Copy environment template
cp .env.template .env

# Edit .env with your database credentials
nano .env

# Launch with Docker Compose
docker-compose up -d mcp-sqlserver  # For SQL Server
docker-compose up -d mcp-azure      # For Azure SQL
docker-compose up -d mcp-snowflake  # For Snowflake
docker-compose up -d mcp-hana       # For SAP HANA
docker-compose up -d mcp-postgres   # For PostgreSQL
```

### Using Python SDK

```bash
# Install the package
pip install mcp-sql-universal

# Or with uv (recommended)
uv add mcp-sql-universal

# Launch server
mcp-sql-server --type sqlserver --config config/sqlserver.yaml
```

### Direct Python Execution

```bash
# Install dependencies
uv pip install -r requirements.txt

# Run specific adapter
uv run src/servers/sqlserver_server.py
```

## 🌐 Deployment Options

| Platform | Status | Guide | Est. Cost |
|----------|--------|-------|-----------|
| **Railway** | ✅ Ready | [Guide](RAILWAY_DEPLOYMENT.md) | $5-20/mo |
| **Docker** | ✅ Ready | [docker-compose.yml](docker-compose.yml) | Free (local) |
| **Azure Container Instances** | 🔄 Coming Soon | - | $10-30/mo |
| **AWS ECS** | 🔄 Coming Soon | - | $15-40/mo |
| **Google Cloud Run** | 🔄 Coming Soon | - | $5-25/mo |

## 📁 Project Structure

```
mcp-sql-paas-universal/
├── src/
│   ├── core/                    # Core MCP functionality
│   │   ├── base_server.py       # Base MCP server class
│   │   ├── connection_pool.py   # Connection pooling
│   │   ├── security.py          # Security utilities
│   │   └── logging_config.py    # Logging configuration
│   ├── adapters/                # Database adapters
│   │   ├── sqlserver.py
│   │   ├── azure_sql.py
│   │   ├── snowflake.py
│   │   ├── sap_hana.py
│   │   ├── postgresql.py
│   │   ├── mysql.py
│   │   └── oracle.py
│   ├── erp/                     # ERP-specific configurations
│   │   ├── sap_s4hana.py
│   │   ├── dynamics365.py
│   │   ├── oracle_erp.py
│   │   ├── netsuite.py
│   │   └── workday.py
│   └── servers/                 # MCP server implementations
│       ├── sqlserver_server.py
│       ├── azure_server.py
│       ├── snowflake_server.py
│       ├── hana_server.py
│       └── postgres_server.py
├── config/                      # Configuration templates
│   ├── sqlserver.yaml
│   ├── azure_sql.yaml
│   ├── snowflake.yaml
│   ├── sap_hana.yaml
│   ├── postgresql.yaml
│   └── erp/
│       ├── dynamics365.yaml
│       ├── sap_s4hana.yaml
│       └── netsuite.yaml
├── docker/                      # Docker configurations
│   ├── Dockerfile.sqlserver
│   ├── Dockerfile.azure
│   ├── Dockerfile.snowflake
│   ├── Dockerfile.hana
│   └── Dockerfile.postgres
├── Dockerfile                   # Railway deployment
├── railway.toml                 # Railway configuration
├── docker-compose.yml
├── .env.template
├── requirements.txt
└── pyproject.toml
```

## 🔒 Security Best Practices (Built-in)

This framework implements industry best practices for MCP security:

- **Read-only accounts with views/stored procedures** - Limits AI access to prevent data modification
- **Database isolation** - Uses read replicas instead of production databases
- **Least privilege connections** - Dedicated accounts with minimal permissions
- **Explicit permission enforcement** - User approval required for all tools/resources
- **Query auditing** - All interactions logged for security review
- **Connection pooling** - Configurable pool sizes (5-20 connections)
- **Timeout management** - Configurable timeouts (90-120 seconds default)

## 📖 Documentation

- [🚂 Railway Deployment](RAILWAY_DEPLOYMENT.md) - **Deploy in 5 minutes**
- [SQL Server Configuration](docs/sqlserver.md)
- [Azure SQL Configuration](docs/azure-sql.md)
- [Snowflake Configuration](docs/snowflake.md)
- [SAP HANA Configuration](docs/sap-hana.md)
- [ERP Integration Guide](docs/erp-integration.md)
- [Container Deployment](docs/container-deployment.md)
- [Security Hardening](docs/security.md)

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) by Anthropic
- [mssqlclient-mcp-server](https://github.com/aadversteeg/mssqlclient-mcp-server)
- [SAP HANA MCP Server](https://github.com/HatriGt/hana-mcp-server)

---

**🚀 Ready to deploy?** [Click here to deploy to Railway now!](https://railway.app/template/mcp-sql-universal)
