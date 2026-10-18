# CLAUDE.md - InvoiceFlow Entry Point & Agent Instructions

See [AGENTS.md](file:///Users/tpmac/Python%20Projects/InvoiceFlow/AGENTS.md) for full agent operating instructions.

## Key Project Guidelines
- **Role**: Senior Python Engineer.
- **Workflow**: Check [05-TASKS.md](file:///Users/tpmac/Python%20Projects/InvoiceFlow/docs/05-TASKS.md) before starting any task. Update task status after completion.
- **Code Standards**: Follow [06-STANDARDS.md](file:///Users/tpmac/Python%20Projects/InvoiceFlow/docs/06-STANDARDS.md) strictly.
- **Testing**: Follow [07-TESTING.md](file:///Users/tpmac/Python%20Projects/InvoiceFlow/docs/07-TESTING.md). Maintain tests alongside all features.
- **Documentation**: Keep docs concise. Prefer tables and bullet lists over prose.

## Common Commands

| Command | Action |
| :--- | :--- |
| `pytest` | Run entire test suite |
| `pytest --cov=src/invoiceflow` | Run tests with coverage report |
| `ruff check .` | Run linter |
| `ruff format .` | Run code formatter |
| `mypy src/` | Run static type checking |
