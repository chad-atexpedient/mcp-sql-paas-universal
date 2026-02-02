# =============================================================================
# MCP SQL PaaS Universal - Railway Deployment Dockerfile
# =============================================================================
# Optimized for Railway deployment with dynamic port assignment
# Supports all database adapters in a single container
# =============================================================================

FROM python:3.11-slim

# Install system dependencies for all database drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gnupg2 \
    unixodbc-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver for SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create non-root user
RUN groupadd -r mcp && useradd -r -g mcp mcp \
    && mkdir -p /var/log/mcp \
    && chown -R mcp:mcp /app /var/log/mcp

# Switch to non-root user
USER mcp

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_LOG_LEVEL=INFO \
    PORT=8000

# Railway will set PORT automatically, expose it
EXPOSE $PORT

# Start script that adapts to Railway's dynamic port
CMD python -c "import os; port = os.environ.get('PORT', '8000'); print(f'Starting MCP server on port {port}')" && \
    python -m src.servers.sqlserver_server
