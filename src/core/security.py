"""
Security Manager for MCP SQL Servers
Implements security best practices for MCP database access.

Key practices implemented:
- Query validation (read-only enforcement)
- SQL injection prevention
- Sensitive data masking
- Access control verification
"""

import re
import logging
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class SecurityConfig(BaseModel):
    """Security configuration settings."""
    
    read_only: bool = Field(default=True)
    allow_ddl: bool = Field(default=False)
    allow_dml: bool = Field(default=False)
    blocked_keywords: List[str] = Field(default_factory=lambda: [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE",
        "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
        "xp_", "sp_", "--", ";--", "/*", "*/"
    ])
    allowed_schemas: Optional[List[str]] = None
    blocked_tables: List[str] = Field(default_factory=list)
    sensitive_columns: List[str] = Field(default_factory=lambda: [
        "password", "pwd", "secret", "token", "api_key",
        "ssn", "social_security", "credit_card", "card_number"
    ])
    max_query_length: int = Field(default=10000)
    max_rows_returned: int = Field(default=10000)


class SecurityManager:
    """
    Manages security for MCP database operations.
    
    Implements best practices:
    - Read-only enforcement
    - SQL injection prevention  
    - Query validation
    - Sensitive data protection
    """
    
    # Patterns that indicate write operations
    WRITE_PATTERNS = [
        r"\bINSERT\s+INTO\b",
        r"\bUPDATE\s+\w+\s+SET\b",
        r"\bDELETE\s+FROM\b",
        r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA)\b",
        r"\bTRUNCATE\s+TABLE\b",
        r"\bALTER\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA)\b",
        r"\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA)\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bEXEC(UTE)?\s+",
    ]
    
    # Patterns that indicate potential SQL injection
    INJECTION_PATTERNS = [
        r";\s*--",           # Comment after semicolon
        r"'\s*OR\s+'",       # OR injection
        r"'\s*OR\s+1\s*=\s*1",  # Classic OR 1=1
        r"UNION\s+SELECT",   # UNION injection
        r"INTO\s+OUTFILE",   # File write attempt
        r"LOAD_FILE",        # File read attempt
        r"BENCHMARK\s*\(",   # Timing attack
        r"SLEEP\s*\(",       # Timing attack
        r"WAITFOR\s+DELAY",  # SQL Server timing
        r"xp_cmdshell",      # SQL Server command execution
        r"sp_executesql",    # Dynamic SQL
    ]
    
    def __init__(self, config: Optional[SecurityConfig] = None, read_only: bool = True):
        self.config = config or SecurityConfig(read_only=read_only)
        self.logger = logging.getLogger(__name__)
        
        # Compile regex patterns for efficiency
        self._write_patterns = [re.compile(p, re.IGNORECASE) for p in self.WRITE_PATTERNS]
        self._injection_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
    
    def validate_query(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Validate a SQL query for security issues.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Empty query provided"
        
        # Check query length
        if len(query) > self.config.max_query_length:
            return False, f"Query exceeds maximum length of {self.config.max_query_length}"
        
        # Check for write operations in read-only mode
        if self.config.read_only:
            for pattern in self._write_patterns:
                if pattern.search(query):
                    return False, "Write operations are not allowed in read-only mode"
        
        # Check for SQL injection patterns
        for pattern in self._injection_patterns:
            if pattern.search(query):
                self.logger.warning(f"Potential SQL injection detected: {pattern.pattern}")
                return False, "Query contains potentially dangerous patterns"
        
        # Check for blocked keywords
        query_upper = query.upper()
        for keyword in self.config.blocked_keywords:
            if keyword.upper() in query_upper:
                return False, f"Query contains blocked keyword: {keyword}"
        
        # Check for blocked tables
        for table in self.config.blocked_tables:
            if re.search(rf"\b{re.escape(table)}\b", query, re.IGNORECASE):
                return False, f"Access to table '{table}' is not allowed"
        
        return True, None
    
    def sanitize_identifier(self, identifier: str) -> str:
        """
        Sanitize a database identifier (table/column name).
        
        Removes any characters that could be used for injection.
        """
        # Only allow alphanumeric, underscore, and period (for schema.table)
        sanitized = re.sub(r'[^a-zA-Z0-9_.]', '', identifier)
        
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        
        return sanitized
    
    def mask_sensitive_data(
        self,
        data: Dict[str, Any],
        columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Mask sensitive data in query results.
        
        Args:
            data: Dictionary of column name to value
            columns: Optional list of column names in the result
            
        Returns:
            Data with sensitive columns masked
        """
        sensitive_cols = set(col.lower() for col in self.config.sensitive_columns)
        
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            
            # Check if column contains sensitive data
            should_mask = any(
                sensitive in key_lower 
                for sensitive in sensitive_cols
            )
            
            if should_mask and value is not None:
                # Mask the value
                if isinstance(value, str):
                    if len(value) > 4:
                        masked[key] = value[:2] + '*' * (len(value) - 4) + value[-2:]
                    else:
                        masked[key] = '****'
                else:
                    masked[key] = '****'
            else:
                masked[key] = value
        
        return masked
    
    def check_schema_access(self, schema: str) -> bool:
        """Check if access to a schema is allowed."""
        if self.config.allowed_schemas is None:
            return True
        return schema.lower() in [s.lower() for s in self.config.allowed_schemas]
    
    def get_query_type(self, query: str) -> str:
        """
        Determine the type of SQL query.
        
        Returns one of: SELECT, INSERT, UPDATE, DELETE, DDL, OTHER
        """
        query_stripped = query.strip().upper()
        
        if query_stripped.startswith("SELECT"):
            return "SELECT"
        elif query_stripped.startswith("INSERT"):
            return "INSERT"
        elif query_stripped.startswith("UPDATE"):
            return "UPDATE"
        elif query_stripped.startswith("DELETE"):
            return "DELETE"
        elif any(query_stripped.startswith(ddl) for ddl in 
                 ["CREATE", "ALTER", "DROP", "TRUNCATE"]):
            return "DDL"
        else:
            return "OTHER"
    
    def create_audit_record(
        self,
        query: str,
        user: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        rows_affected: int = 0
    ) -> Dict[str, Any]:
        """
        Create an audit record for a query execution.
        
        Returns a dictionary suitable for logging or storage.
        """
        import hashlib
        from datetime import datetime
        
        # Create a hash of the query for tracking
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "user": user or "unknown",
            "query_hash": query_hash,
            "query_type": self.get_query_type(query),
            "query_preview": query[:100] + "..." if len(query) > 100 else query,
            "success": success,
            "error": error,
            "rows_affected": rows_affected,
        }


class QueryBuilder:
    """
    Safe query builder to help construct parameterized queries.
    
    Prevents SQL injection by using parameterized queries.
    """
    
    def __init__(self, security_manager: SecurityManager):
        self.security = security_manager
    
    def build_select(
        self,
        table: str,
        columns: List[str] = None,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        limit: int = 1000,
        schema: Optional[str] = None
    ) -> tuple[str, List[Any]]:
        """
        Build a safe SELECT query with parameters.
        
        Returns:
            Tuple of (query_string, parameters_list)
        """
        # Sanitize table name
        safe_table = self.security.sanitize_identifier(table)
        if schema:
            safe_schema = self.security.sanitize_identifier(schema)
            full_table = f"{safe_schema}.{safe_table}"
        else:
            full_table = safe_table
        
        # Sanitize column names
        if columns:
            safe_columns = [self.security.sanitize_identifier(c) for c in columns]
            col_str = ", ".join(safe_columns)
        else:
            col_str = "*"
        
        query = f"SELECT {col_str} FROM {full_table}"
        params: List[Any] = []
        
        # Add WHERE clause
        if where:
            conditions = []
            for col, value in where.items():
                safe_col = self.security.sanitize_identifier(col)
                conditions.append(f"{safe_col} = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)
        
        # Add ORDER BY
        if order_by:
            safe_order = [self.security.sanitize_identifier(c) for c in order_by]
            query += " ORDER BY " + ", ".join(safe_order)
        
        # Add LIMIT
        query += f" LIMIT {int(limit)}"
        
        return query, params
    
    def build_count(
        self,
        table: str,
        where: Optional[Dict[str, Any]] = None,
        schema: Optional[str] = None
    ) -> tuple[str, List[Any]]:
        """Build a safe COUNT query."""
        safe_table = self.security.sanitize_identifier(table)
        if schema:
            safe_schema = self.security.sanitize_identifier(schema)
            full_table = f"{safe_schema}.{safe_table}"
        else:
            full_table = safe_table
        
        query = f"SELECT COUNT(*) as row_count FROM {full_table}"
        params: List[Any] = []
        
        if where:
            conditions = []
            for col, value in where.items():
                safe_col = self.security.sanitize_identifier(col)
                conditions.append(f"{safe_col} = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)
        
        return query, params
