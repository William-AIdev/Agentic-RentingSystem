# Rental Agent (Gradio + LangGraph)

面向衣物租赁场景的本地 Web 应用，支持订单管理、规则问答（RAG）、时间档期建议与可视化对话。

## 功能概览

- 订单全流程：创建/查询/更新/取消/支付/发货/完成
- 规则问答：基于本地规则文件检索回答
- 时间建议：基于库存占用推荐可租时间段
- 可配置时区：默认 Australia/Sydney
- Docker 一键启动：Postgres + Qdrant + App

## 快速开始（Docker）

1. 复制并配置环境变量：
   ```bash
   cp .env.example .env
   ```
   至少填写 `OPENAI_API_KEY`。

2. 启动服务：
   ```bash
   docker compose up --build
   ```

3. 打开浏览器：
   ```
   http://localhost:7860
   ```

## Happy Path（示例流程）

1. 规则查询（RAG）
   ```
   我想了解押金和清洗规则
   ```

2. 创建订单（本地时区默认 Sydney,sku代表商品颜色和型号，命名格式为[BLACK, WHITE]_[S,M,L]）
   ```
   创建订单，用户张三，微信 zhangsan，SKU black_l，开始 2026-01-29 08:00，结束 2026-01-30 20:00
   ```

3. 查询订单
   ```
   查询订单，订单号为 <order_id>
   ```

4. 标记已支付
   ```
   标记订单已支付，订单号为 <order_id>
   ```

5. 发货（需要 locker_code）
   ```
   发货，订单号为 <order_id>，取件码 LC123
   ```

6. 完成订单
   ```
   完成订单，订单号为 <order_id>
   ```

7. 取消订单（可选）
   ```
   取消订单，订单号为 <order_id>
   ```

## 目录结构

- `app/`：Gradio UI + LangGraph agent
- `services/`：订单服务层（SQLAlchemy ORM）
- `db/init/`：数据库初始化与约束
- `agent/rules/`：规则文档（RAG 语料）
- `scripts/`：脚本（如 LLM 延迟测试）

## 配置说明

所有配置集中在 `.env`，关键项：

- `OPENAI_API_KEY`：LLM 访问密钥
- `OPENAI_MODEL`：模型名（默认 `gpt-5-nano`）
- `OPENAI_TEMPERATURE`：采样温度（默认 `1`）
- `LOCAL_TIMEZONE`：用户输入/输出时区（默认 `Australia/Sydney`）
- `QDRANT_URL`：向量库地址
- `RULES_PATH`：规则文件路径

## 开发检查工具（可选）

- Ruff：
  ```bash
  ruff check .
  ```
- Black：
  ```bash
  black .
  ```
- mypy：
  ```bash
  mypy --explicit-package-bases .
  ```

## 常见问题

- **时区问题**：用户输入/输出默认 Sydney，可通过 `LOCAL_TIMEZONE` 调整。
- **RAG 未就绪**：规则文件缺失或初始化失败会返回提示。
