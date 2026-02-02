# 🚂 Railway Deployment Guide

This guide walks you through deploying the MCP SQL PaaS Universal framework to Railway.

## 🚀 Quick Deploy

### Option 1: Deploy from GitHub (Recommended)

1. **Connect Repository to Railway**
   - Go to [Railway Dashboard](https://railway.app/dashboard)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select `chad-atexpedient/mcp-sql-paas-universal`
   - Railway will auto-detect the Dockerfile

2. **Configure Environment Variables**
   
   Navigate to your service settings and add these variables based on your database:

   #### For SQL Server:
   ```
   MCP_SERVER_NAME=mcp-sqlserver
   MCP_LOG_LEVEL=INFO
   SQLSERVER_HOST=your-host.database.windows.net
   SQLSERVER_PORT=1433
   SQLSERVER_DATABASE=your-database
   SQLSERVER_USER=mcp_readonly
   SQLSERVER_PASSWORD=your-password
   SQLSERVER_ENCRYPT=true
   ```

   #### For Azure SQL:
   ```
   MCP_SERVER_NAME=mcp-azure-sql
   AZURE_SQL_SERVER=your-server.database.windows.net
   AZURE_SQL_DATABASE=your-database
   AZURE_SQL_AUTH_METHOD=sql
   AZURE_SQL_USER=your-user
   AZURE_SQL_PASSWORD=your-password
   ```

   #### For Snowflake:
   ```
   MCP_SERVER_NAME=mcp-snowflake
   SNOWFLAKE_ACCOUNT_URL=https://your-account.snowflakecomputing.com
   SNOWFLAKE_USER=your-user
   SNOWFLAKE_PASSWORD=your-password
   SNOWFLAKE_WAREHOUSE=MCP_WAREHOUSE
   SNOWFLAKE_DATABASE=your-database
   SNOWFLAKE_SCHEMA=PUBLIC
   ```

   #### For PostgreSQL:
   ```
   MCP_SERVER_NAME=mcp-postgres
   POSTGRES_HOST=your-host
   POSTGRES_PORT=5432
   POSTGRES_DATABASE=your-database
   POSTGRES_USER=your-user
   POSTGRES_PASSWORD=your-password
   POSTGRES_SSLMODE=require
   ```

3. **Deploy**
   - Railway will automatically build and deploy
   - Monitor logs in the Railway dashboard
   - Your service will be available at: `https://your-service.up.railway.app`

### Option 2: Deploy with Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login to Railway
railway login

# Link to existing project or create new one
railway link

# Set environment variables
railway variables set SQLSERVER_HOST=your-host
railway variables set SQLSERVER_USER=your-user
railway variables set SQLSERVER_PASSWORD=your-password
# ... add other variables

# Deploy
railway up
```

## 🔧 Configuration

### Multi-Database Deployment

You can deploy multiple instances for different databases:

1. **Create multiple services in Railway**
   - Each service can use the same GitHub repo
   - Configure different environment variables per service
   - Use different `MCP_SERVER_NAME` values

2. **Example: SQL Server + Snowflake**
   - Service 1: `mcp-sqlserver` with SQL Server env vars
   - Service 2: `mcp-snowflake` with Snowflake env vars

### Custom Dockerfile Selection

To deploy a specific database adapter:

1. Edit `railway.toml` or `railway.json`
2. Change `dockerfilePath`:
   ```toml
   [build]
   dockerfilePath = "docker/Dockerfile.snowflake"
   ```

## 🔐 Security Best Practices

1. **Use Railway Environment Variables**
   - Never commit secrets to GitHub
   - Use Railway's encrypted variable storage
   - Reference: `.env.template` for all available variables

2. **Network Security**
   - Enable SSL/TLS for database connections
   - Use VPN or Private networking for production
   - Whitelist Railway's IP addresses in your database firewall

3. **Database Access**
   - Create read-only database users
   - Use minimal privilege grants
   - Enable query auditing

## 📊 Monitoring

Railway provides built-in monitoring:

- **Metrics**: CPU, Memory, Network usage
- **Logs**: Real-time application logs
- **Deployments**: Track deployment history
- **Health Checks**: Automatic service health monitoring

## 🔄 CI/CD

Railway automatically redeploys when you push to GitHub:

1. Make changes to your code
2. Push to `main` branch
3. Railway detects changes and redeploys

To disable auto-deploy:
- Go to Service Settings → Deploy
- Toggle "Auto Deploy" off

## 🆘 Troubleshooting

### Build Failures

**Issue**: Dockerfile build fails
```bash
# Check Railway logs for specific error
railway logs
```

**Common fixes**:
- Verify `requirements.txt` has all dependencies
- Check Docker build logs for missing system packages
- Ensure Python version matches (3.11+)

### Connection Issues

**Issue**: Can't connect to database
- Verify environment variables are set correctly
- Check database firewall allows Railway IPs
- Test connection with `railway run python -c "import pyodbc"`

### Port Issues

**Issue**: Service not responding
- Railway automatically assigns PORT variable
- Ensure your app listens on `$PORT`
- Check health check endpoint: `/health`

## 💰 Pricing

Railway offers:
- **Free Tier**: $5 credit/month (suitable for testing)
- **Pro Plan**: $20/month + usage
- **Database costs**: Separate if using Railway databases

Estimated costs for this MCP server:
- Light usage: ~$5-10/month
- Medium usage: ~$20-30/month
- Heavy usage: $50+/month

## 📚 Additional Resources

- [Railway Documentation](https://docs.railway.app/)
- [Railway Discord](https://discord.gg/railway)
- [MCP Protocol Docs](https://modelcontextprotocol.io/)
- [Project Repository](https://github.com/chad-atexpedient/mcp-sql-paas-universal)

## 🎯 Next Steps

1. ✅ Deploy to Railway
2. ✅ Configure environment variables
3. ✅ Test database connection
4. ✅ Integrate with MCP client (Claude, etc.)
5. ✅ Set up monitoring and alerts
6. ✅ Configure auto-scaling (if needed)

---

**Need Help?** Open an issue on GitHub or reach out to the team!
