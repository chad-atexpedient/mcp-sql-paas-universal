#!/bin/bash
# =============================================================================
# Railway Quick Deploy Script for MCP SQL PaaS Universal
# =============================================================================
# Usage: ./railway-deploy.sh [database-type]
# Example: ./railway-deploy.sh sqlserver
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    error "Railway CLI is not installed!"
    info "Install it with: npm i -g @railway/cli"
    info "Or visit: https://docs.railway.app/develop/cli"
    exit 1
fi

# Get database type from argument or prompt
DB_TYPE=${1:-""}
if [ -z "$DB_TYPE" ]; then
    echo ""
    info "Select database type:"
    echo "  1) SQL Server"
    echo "  2) Azure SQL"
    echo "  3) Snowflake"
    echo "  4) PostgreSQL"
    echo "  5) SAP HANA"
    echo "  6) MySQL"
    echo "  7) Oracle"
    echo ""
    read -p "Enter choice (1-7): " choice
    
    case $choice in
        1) DB_TYPE="sqlserver" ;;
        2) DB_TYPE="azure" ;;
        3) DB_TYPE="snowflake" ;;
        4) DB_TYPE="postgres" ;;
        5) DB_TYPE="hana" ;;
        6) DB_TYPE="mysql" ;;
        7) DB_TYPE="oracle" ;;
        *) error "Invalid choice"; exit 1 ;;
    esac
fi

success "Deploying MCP SQL Server for: $DB_TYPE"

# Login to Railway
info "Logging in to Railway..."
railway login

# Create new project or link existing
read -p "Do you want to create a new project? (y/n): " create_new
if [ "$create_new" = "y" ]; then
    info "Creating new Railway project..."
    PROJECT_NAME="mcp-sql-${DB_TYPE}-$(date +%s)"
    railway init --name "$PROJECT_NAME"
else
    info "Linking to existing project..."
    railway link
fi

# Set environment variables based on database type
info "Setting environment variables..."

# Common variables
railway variables set MCP_SERVER_NAME="mcp-${DB_TYPE}"
railway variables set MCP_LOG_LEVEL="INFO"
railway variables set MCP_TIMEOUT_SECONDS="120"
railway variables set MCP_CONNECTION_POOL_SIZE="10"
railway variables set PYTHONUNBUFFERED="1"

# Database-specific variables
case $DB_TYPE in
    sqlserver)
        warning "You'll need to set these variables manually in Railway dashboard:"
        echo "  - SQLSERVER_HOST"
        echo "  - SQLSERVER_DATABASE"
        echo "  - SQLSERVER_USER"
        echo "  - SQLSERVER_PASSWORD"
        ;;
    azure)
        warning "You'll need to set these variables manually in Railway dashboard:"
        echo "  - AZURE_SQL_SERVER"
        echo "  - AZURE_SQL_DATABASE"
        echo "  - AZURE_SQL_USER"
        echo "  - AZURE_SQL_PASSWORD"
        ;;
    snowflake)
        warning "You'll need to set these variables manually in Railway dashboard:"
        echo "  - SNOWFLAKE_ACCOUNT_URL"
        echo "  - SNOWFLAKE_USER"
        echo "  - SNOWFLAKE_PASSWORD"
        echo "  - SNOWFLAKE_WAREHOUSE"
        echo "  - SNOWFLAKE_DATABASE"
        ;;
    postgres)
        warning "You'll need to set these variables manually in Railway dashboard:"
        echo "  - POSTGRES_HOST"
        echo "  - POSTGRES_DATABASE"
        echo "  - POSTGRES_USER"
        echo "  - POSTGRES_PASSWORD"
        ;;
    hana)
        warning "You'll need to set these variables manually in Railway dashboard:"
        echo "  - HANA_HOST"
        echo "  - HANA_USER"
        echo "  - HANA_PASSWORD"
        ;;
esac

# Deploy to Railway
info "Deploying to Railway..."
railway up

success "Deployment initiated!"
info "Monitor your deployment at: https://railway.app/dashboard"
info "View logs with: railway logs"
info "Open in browser: railway open"

echo ""
success "🎉 Deployment complete!"
warning "Don't forget to set your database credentials in the Railway dashboard!"
info "Run 'railway logs' to see deployment progress"
