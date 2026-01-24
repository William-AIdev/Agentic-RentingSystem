# Rental Agent (Gradio + LangGraph)

本项目已从教学 Notebook 重构为生产可部署的本地 Web 应用。所有配置都集中在 `.env` 中。

## 快速开始（Docker 一键部署）

1. 复制配置模板并填写必要字段：
   ```bash
   cp .env.example .env
   ```
   至少填写 `OPENAI_API_KEY`。

2. 启动：
   ```bash
   docker compose up --build
   ```

3. 打开浏览器访问：
   ```
   http://localhost:7860
   ```


## 目录结构

- `app/`：Gradio UI + LangGraph agent
- `services/`：订单服务层（Postgres）
- `db/init.sql`：数据库初始化与约束
- `agent/rules/`：规则文档（RAG 语料）

## 说明

- Postgres 与 Qdrant 均由 docker compose 启动。
- 配置项全部位于 `.env`，满足“单文件配置”的要求。
