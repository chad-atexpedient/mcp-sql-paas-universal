"""
Logging Configuration for MCP SQL Servers
Provides structured logging with audit capabilities.

Best practices:
- Log all MCP interactions for audit
- Use structured logging for easy parsing
- Configurable log levels
- Support for file and console output
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console_logging: bool = True
) -> structlog.BoundLogger:
    """
    Configure structured logging for MCP servers.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
        console_logging: Whether to log to console
        
    Returns:
        Configured structlog logger
    """
    # Parse log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure handlers
    handlers = []
    
    if console_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        ))
        handlers.append(console_handler)
    
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if log_file else structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()


class AuditLogger:
    """
    Specialized logger for MCP audit events.
    
    Records all database interactions for compliance and security review.
    """
    
    def __init__(
        self,
        audit_file: Optional[str] = None,
        server_name: str = "mcp-sql"
    ):
        self.server_name = server_name
        self.logger = structlog.get_logger("mcp.audit")
        
        # Set up dedicated audit file if specified
        if audit_file:
            self._setup_audit_file(audit_file)
    
    def _setup_audit_file(self, audit_file: str) -> None:
        """Set up dedicated audit log file."""
        audit_path = Path(audit_file)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        
        audit_handler = logging.FileHandler(audit_file)
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","event":%(message)s}'
        ))
        
        audit_logger = logging.getLogger("mcp.audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(logging.INFO)
    
    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """Log a tool invocation."""
        self.logger.info(
            "tool_called",
            server=self.server_name,
            tool=tool_name,
            arguments=self._sanitize(arguments),
            user=user,
            session_id=session_id,
            event_type="tool_call"
        )
    
    def log_tool_result(
        self,
        tool_name: str,
        success: bool,
        execution_time_ms: float,
        rows_returned: int = 0,
        error: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """Log tool execution result."""
        self.logger.info(
            "tool_completed",
            server=self.server_name,
            tool=tool_name,
            success=success,
            execution_time_ms=execution_time_ms,
            rows_returned=rows_returned,
            error=error,
            session_id=session_id,
            event_type="tool_result"
        )
    
    def log_query(
        self,
        query: str,
        query_type: str,
        execution_time_ms: float,
        rows_affected: int = 0,
        success: bool = True,
        error: Optional[str] = None,
        user: Optional[str] = None
    ) -> None:
        """Log a database query execution."""
        # Truncate long queries for logging
        query_preview = query[:200] + "..." if len(query) > 200 else query
        
        self.logger.info(
            "query_executed",
            server=self.server_name,
            query_preview=query_preview,
            query_type=query_type,
            execution_time_ms=execution_time_ms,
            rows_affected=rows_affected,
            success=success,
            error=error,
            user=user,
            event_type="query"
        )
    
    def log_connection_event(
        self,
        event: str,  # "connect", "disconnect", "reconnect", "health_check"
        success: bool = True,
        error: Optional[str] = None,
        connection_id: Optional[str] = None
    ) -> None:
        """Log connection-related events."""
        self.logger.info(
            f"connection_{event}",
            server=self.server_name,
            event=event,
            success=success,
            error=error,
            connection_id=connection_id,
            event_type="connection"
        )
    
    def log_security_event(
        self,
        event: str,  # "query_blocked", "access_denied", "injection_attempt"
        details: Dict[str, Any],
        severity: str = "warning"  # "info", "warning", "critical"
    ) -> None:
        """Log security-related events."""
        log_method = getattr(self.logger, severity, self.logger.warning)
        log_method(
            f"security_{event}",
            server=self.server_name,
            event=event,
            details=self._sanitize(details),
            event_type="security"
        )
    
    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from log entries."""
        sensitive_keys = {"password", "secret", "token", "key", "credential", "api_key"}
        
        sanitized = {}
        for k, v in data.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize(v)
            else:
                sanitized[k] = v
        
        return sanitized


class QueryMetrics:
    """
    Collects and reports query execution metrics.
    
    Useful for monitoring MCP server performance.
    """
    
    def __init__(self):
        self._query_count = 0
        self._total_execution_time_ms = 0.0
        self._error_count = 0
        self._rows_returned = 0
        self._query_types: Dict[str, int] = {}
    
    def record_query(
        self,
        query_type: str,
        execution_time_ms: float,
        rows: int = 0,
        success: bool = True
    ) -> None:
        """Record metrics for a query execution."""
        self._query_count += 1
        self._total_execution_time_ms += execution_time_ms
        self._rows_returned += rows
        
        if not success:
            self._error_count += 1
        
        self._query_types[query_type] = self._query_types.get(query_type, 0) + 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        avg_time = (
            self._total_execution_time_ms / self._query_count 
            if self._query_count > 0 else 0
        )
        
        return {
            "total_queries": self._query_count,
            "total_execution_time_ms": self._total_execution_time_ms,
            "average_execution_time_ms": avg_time,
            "total_rows_returned": self._rows_returned,
            "error_count": self._error_count,
            "error_rate": self._error_count / self._query_count if self._query_count > 0 else 0,
            "queries_by_type": self._query_types,
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._query_count = 0
        self._total_execution_time_ms = 0.0
        self._error_count = 0
        self._rows_returned = 0
        self._query_types = {}
