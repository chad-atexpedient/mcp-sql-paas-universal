# Contributing to MCP SQL PaaS Universal

Thank you for your interest in contributing! This project aims to provide a comprehensive MCP server framework for SQL databases and ERP systems.

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- uv (recommended) or pip
- Docker (for container testing)
- Access to at least one supported database for testing

### Development Setup

1. Clone the repository:
```bash
git clone https://github.com/chad-atexpedient/mcp-sql-paas-universal.git
cd mcp-sql-paas-universal
```

2. Create a virtual environment:
```bash
uv venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
uv pip install -r requirements.txt
uv pip install -e ".[dev]"
```

4. Set up pre-commit hooks:
```bash
pre-commit install
```

## 📝 Contribution Guidelines

### Code Style

- Follow PEP 8 guidelines
- Use type hints for all functions
- Maximum line length: 100 characters
- Use Black for formatting: `black src/`
- Use Ruff for linting: `ruff check src/`

### Adding a New Database Adapter

1. Create a new file in `src/adapters/`:
```python
# src/adapters/new_database.py
from ..core.base_server import BaseMCPServer, ServerConfig
from pydantic import BaseModel

class NewDatabaseConfig(BaseModel):
    """Configuration for New Database."""
    host: str
    port: int
    # ... other settings

class NewDatabaseAdapter(BaseMCPServer):
    """MCP Server adapter for New Database."""
    
    def get_tools(self) -> List[Tool]:
        # Implement required tools
        pass
    
    async def connect(self) -> None:
        # Implement connection logic
        pass
    
    # ... implement other abstract methods
```

2. Add configuration template in `config/`:
```yaml
# config/new_database.yaml
server:
  name: mcp-new-database
  timeout_seconds: 120
  pool_size: 10

connection:
  host: ${NEW_DB_HOST}
  port: ${NEW_DB_PORT}
  # ... other settings
```

3. Add Dockerfile in `docker/`:
```dockerfile
# docker/Dockerfile.new_database
FROM python:3.11-slim
# ... container setup
```

4. Update `docker-compose.yml` with the new service

5. Add tests in `tests/adapters/test_new_database.py`

### Adding ERP Support

1. Create ERP tools in `src/erp/`:
```python
# src/erp/new_erp.py
class NewERPTools:
    @staticmethod
    def get_tools() -> List[Tool]:
        # Define ERP-specific tools
        pass
```

2. Add configuration in `config/erp/new_erp.yaml`

3. Update CLI in `src/cli.py` to support the new ERP type

### Security Best Practices

All contributions must follow these security practices:

- ✅ Default to read-only access
- ✅ Use parameterized queries
- ✅ Implement query validation
- ✅ Mask sensitive data in logs
- ✅ Support connection encryption
- ✅ Use connection pooling
- ✅ Implement proper timeout handling

### Testing

Run tests before submitting:
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific adapter tests
pytest tests/adapters/test_sqlserver.py
```

### Documentation

- Update README.md for new features
- Add docstrings to all public functions
- Include usage examples
- Update configuration documentation

## 🔀 Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-database-support`
3. Make your changes
4. Run tests and linting
5. Commit with clear messages: `git commit -m "Add support for New Database"`
6. Push to your fork: `git push origin feature/new-database-support`
7. Open a Pull Request

### PR Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Security practices followed
- [ ] Changelog updated (if applicable)

## 🐛 Reporting Issues

When reporting issues, please include:

- Database type and version
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (with sensitive data removed)

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙏 Thank You!

Your contributions help make database interaction with AI safer and more accessible!
