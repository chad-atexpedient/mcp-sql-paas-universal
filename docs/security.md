# Security Best Practices

This document outlines the security best practices implemented in the MCP SQL PaaS Universal framework.

## Overview

Security is a primary concern when enabling AI/LLM access to databases. This framework implements multiple layers of protection based on 2024 MCP best practices.

## Key Security Principles

### 1. Read-Only Access by Default

All MCP servers default to read-only mode:

```yaml
server:
  read_only: true  # Enforced by default
```

This prevents:
- Accidental data modification
- SQL injection attacks that attempt writes
- Unintended DDL operations

### 2. Query Validation

Every query is validated before execution:

```python
# Blocked patterns include:
- INSERT, UPDATE, DELETE, DROP
- EXEC, EXECUTE (stored procedures in read-only mode)
- xp_, sp_ (SQL Server extended procedures)
- SQL injection patterns (UNION SELECT, OR 1=1, etc.)
```

### 3. Database Isolation

**Best Practice**: Never connect MCP servers directly to production OLTP databases.

Recommended approaches:
- Use **read replicas** for real-time access
- Use **reporting databases** with nightly refreshes
- Use **views** instead of base tables

```yaml
security:
  use_read_replica: true
```

### 4. Least Privilege Access

Create dedicated database users with minimal permissions:

#### SQL Server
```sql
-- Create read-only user
CREATE LOGIN mcp_readonly WITH PASSWORD = 'secure_password';
CREATE USER mcp_readonly FOR LOGIN mcp_readonly;

-- Grant SELECT only on specific views
GRANT SELECT ON SCHEMA::reporting TO mcp_readonly;

-- Or grant EXECUTE on specific stored procedures
GRANT EXECUTE ON dbo.sp_GetSalesReport TO mcp_readonly;
```

#### PostgreSQL
```sql
CREATE ROLE mcp_readonly WITH LOGIN PASSWORD 'secure_password';
GRANT USAGE ON SCHEMA public TO mcp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
    GRANT SELECT ON TABLES TO mcp_readonly;
```

#### Snowflake
```sql
CREATE ROLE MCP_DEMO_ROLE;
GRANT USAGE ON DATABASE my_db TO ROLE MCP_DEMO_ROLE;
GRANT USAGE ON SCHEMA my_db.my_schema TO ROLE MCP_DEMO_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA my_db.my_schema TO ROLE MCP_DEMO_ROLE;

CREATE USER mcp_service_user PASSWORD = 'secure_password';
GRANT ROLE MCP_DEMO_ROLE TO USER mcp_service_user;
```

### 5. Sensitive Data Protection

Automatic masking of sensitive columns in query results:

```yaml
security:
  sensitive_columns:
    - password
    - pwd
    - secret
    - token
    - api_key
    - ssn
    - social_security
    - credit_card
```

Example output:
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "password": "****",  // Masked
  "ssn": "***-**-1234"  // Partially masked
}
```

### 6. Network Security

#### Azure SQL
```yaml
# Use private endpoints
security:
  encrypt: true
  min_tls_version: "1.2"
  
# Configure Azure firewall rules
# Only allow specific IPs
```

#### Snowflake
```sql
-- Create network policy
CREATE OR REPLACE NETWORK RULE mcp_access
    MODE = INGRESS
    TYPE = IPV4
    VALUE_LIST = ('10.0.0.0/24', '192.168.1.100');
```

### 7. Authentication Best Practices

#### SQL Authentication
- Use strong, unique passwords
- Rotate credentials regularly
- Store in environment variables or secrets management

#### Azure Entra ID (Recommended)
```yaml
connection:
  auth_method: entra_id_service_principal
  tenant_id: ${AZURE_TENANT_ID}
  client_id: ${AZURE_CLIENT_ID}
  # client_secret via environment variable
```

#### Snowflake PAT
```yaml
connection:
  auth_method: pat
  # token via environment variable
```

### 8. Query Auditing

All queries are logged for audit purposes:

```python
{
    "timestamp": "2024-01-15T10:30:45Z",
    "server_name": "mcp-sqlserver",
    "tool": "execute_query",
    "query_preview": "SELECT * FROM customers WHERE...",
    "query_type": "SELECT",
    "success": true,
    "rows_affected": 150,
    "user": "mcp_readonly"
}
```

Enable detailed auditing:
```yaml
logging:
  audit_queries: true
  file: /var/log/mcp/audit.log
```

### 9. Timeout Protection

Prevent long-running queries from impacting database performance:

```yaml
server:
  timeout_seconds: 120  # Maximum query duration
```

### 10. Connection Pooling

Limit database connections to prevent resource exhaustion:

```yaml
server:
  pool_size: 10  # Maximum concurrent connections
```

## Security Checklist

Before deploying to production:

- [ ] Read-only mode enabled
- [ ] Using read replica (not production database)
- [ ] Dedicated service account created
- [ ] Minimal permissions granted
- [ ] Network policies configured
- [ ] TLS/SSL encryption enabled
- [ ] Query auditing enabled
- [ ] Timeouts configured
- [ ] Connection pooling configured
- [ ] Sensitive columns defined
- [ ] Environment variables for secrets
- [ ] Firewall rules in place

## Incident Response

If suspicious activity is detected:

1. Review audit logs for anomalies
2. Revoke MCP service account access
3. Rotate all credentials
4. Review and restrict query patterns
5. Consider implementing additional query filtering

## Security Updates

This framework follows security best practices from:
- [Model Context Protocol Security](https://modelcontextprotocol.io/docs/concepts/security)
- [Microsoft Azure SQL Security](https://docs.microsoft.com/azure/azure-sql/database/security-overview)
- [Snowflake Security Best Practices](https://docs.snowflake.com/en/user-guide/security-best-practices)
- [SAP HANA Security Guide](https://help.sap.com/docs/SAP_HANA_PLATFORM/security)
