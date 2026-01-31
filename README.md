# Rental Agent (LangGraph + RAG)
<!-- 构建 / CI 状态 -->
![Build Status](https://img.shields.io/github/actions/workflow/status/William-AIdev/Agentic-RentingSystem/ci.yml?branch=main&style=flat-square)
<!-- Tech Stacks -->
![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&style=flat-square)
![LangChain](https://img.shields.io/badge/LangChain-RAG_Framework-0FA958?style=flat-square)
![OpenAI](https://img.shields.io/badge/OpenAI-LLM-412991?logo=openai&style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-DB-336791?logo=postgresql&style=flat-square)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-red?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?logo=docker&style=flat-square)



A production-minded rental-agent, based on real personal rental business.
User can interact with the agent to speed up rental order processing, 
including creating, querying, updating, canceling, paying, shipping, and completing orders. 

The agent can also answer questions about rental rules using Retrieval-Augmented Generation (RAG) over documents.

Tech Stack:
- Frontend: [Gradio](https://gradio.ai/)
- Agent framework: [LangGraph + LangSmith](https://langgraph.com/)
- Vector store: [Qdrant](https://qdrant.io/)
- Database: [PostgreSQL](https://www.postgresql.org/)
- LLM: [OpenAI GPT-5 Nano](https://openai.com/)

## Features

- Full order flow: create / query / update / cancel / pay / ship / complete / suggest time slots
- Rules Q&A: retrieval over local rules file
- Agent tracking: use LangSmith to track agent and fine-tune the workflow and token cost
- One-command Docker startup: Postgres + Qdrant + App
- Unit tests, auto-lint bash script and GitHub Actions CI are included.
- Can be easily deployed to cloud (e.g., AWS, Supabase, Qdrant Cloud)
- Future: Personalized frontend with ReactJS, multi-user support, email notifications

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

7. Try a conflicting Order

   Enter a order that overlaps with an existing order's time
   ```
   Create order, user Alice, wechat alicechat, SKU black_l, start 2026-01-29 10:00, end 2026-01-30 18:00
   ```
   Then the agent will suggest alternative available time slots.
   ```
   The requested SKU black_l is already booked for 2026-01-29 10:00 to 2026-01-30 18:00.

   Next available window for black_l is:

   ...
   ```
   Then you can choose another time slot to order. 
   
   You don't need to specify other details again if in the same chat session.

8. Cancel order (optional)
   ```
   Cancel order <order_id>
   ```

9. Update order (optional)
   ```
   I want to update order <order_id>, the new end time is 2026-01-31 20:00
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
## LangSmith (Optional)

Set the LangSmith key in .env to enable agent tracking, or deploy it locally (not included).

You could see the workflow and token cost through the panel:

<img width="1407" height="1226" alt="image" src="https://github.com/user-attachments/assets/0d61b769-f836-4c74-840e-99d40ddcb737" />


## FAQ

- **Timezone**: user input/output defaults to Sydney; change with `LOCAL_TIMEZONE`.
- **RAG not ready**: missing rules file or initialization failure returns a warning.
- **RAG init**: ensure you deleted previous Qdrant collection if rules file changed.
Use `docker compose down -v` to remove volumes or only delete qdrant_data volume and qdrant-1 container(faster).
