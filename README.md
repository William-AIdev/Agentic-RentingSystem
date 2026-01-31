# Rental Agent (Gradio + LangGraph)

A local web app for a clothing rental scenario. It supports order management, rules Q&A (RAG), time-slot suggestions, and a visual chat interface.

## Features

- Full order flow: create / query / update / cancel / pay / ship / complete
- Rules Q&A: retrieval over local rules file
- Time suggestions: recommend available rental slots based on inventory occupancy
- Configurable timezone: default `Australia/Sydney`
- One-command Docker startup: Postgres + Qdrant + App

## Quick Start (Docker)

1. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Fill at least `OPENAI_API_KEY`.

2. Start services:

   For production:
   ```bash
   docker compose up --build
   ```
   (First build may take a few minutes because it downloads ~4GB of models and dependencies.)

   For development:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
   ```

3. Open in browser:
   ```
   http://localhost:7860
   ```

## Happy Path (Sample Flow)

1. Rules query (RAG)
   Examples:
   - I want to know the deposit and cleaning rules
   - How do I rent clothes
   - How do I return clothes

2. Create an order (local timezone defaults to Sydney; SKU is color + size, format `[BLACK, WHITE]_[S,M,L]`)
   ```
   Create order, user William, wechat willychat, SKU black_l, start 2026-01-29 08:00, end 2026-01-30 20:00
   ```

3. Query an order
   ```
   Query order <order_id>
   ```

4. Mark as paid
   ```
   Mark order paid <order_id>
   ```

5. Ship (locker_code required)
   ```
   Ship order <order_id>, locker code is LC123 (can be any)
   ```

6. Complete order
   ```
   Complete order <order_id>
   ```

7. Cancel order (optional)
   ```
   Cancel order <order_id>
   ```

## Project Structure

- `app/`: Gradio UI + RAG logic + LangGraph agent (graph and node initialization, tool definition)
- `services/`: order service layer (SQLAlchemy ORM, business logic)
- `db/init/`: database initialization and constraints
- `agent/rules/`: rule documents (RAG text)
- `scripts/`: scripts (e.g., auto_lint tool)
- `tests/`: unit tests
- `workflows/`: GitHub Actions workflows
- 

## Configuration

All configuration is in `.env`. Key variables:

- `OPENAI_API_KEY`: LLM access key
- `OPENAI_MODEL`: model name (default `gpt-5-nano`)
- `OPENAI_TEMPERATURE`: sampling temperature (default `1`)
- `LOCAL_TIMEZONE`: user input/output timezone (default `Australia/Sydney`)
- `QDRANT_URL`: vector store URL
- `RULES_PATH`: rules file path

## Dev Tools (Optional)

- Black:
  ```bash
  black .
  ```
- mypy:
  ```bash
  mypy --explicit-package-bases .
  ```
- Ruff:
  ```bash
  ruff check .
  ```

## FAQ

- **Timezone**: user input/output defaults to Sydney; change with `LOCAL_TIMEZONE`.
- **RAG not ready**: missing rules file or initialization failure returns a warning.
- **RAG init**: ensure you deleted previous Qdrant collection if rules file changed.
Use `docker compose down -v` to remove volumes or only delete qdrant_data volume and qdrant-1 container(faster).
