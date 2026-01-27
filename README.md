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

## Happy Path（示例流程）

以下是常见的顺利使用路径，便于快速验证功能是否正常：

1. 规则查询（RAG）
   ```
   我想了解押金和清洗规则
   ```
   预期：助手会给出规则摘要。

2. 创建订单
   ```
   创建订单，用户张三，微信 zhangsan，SKU black_l，开始 2026-01-29 08：00，结束 2026-01-30 20:00
   ```
   预期：返回订单详情与 order_id。

3. 查询订单
   ```
   查询订单，订单号为 <order_id>
   ```
   预期：返回订单信息。

4. 标记已支付
   ```
   标记订单已支付，订单号为 <order_id>
   ```
   预期：订单状态变为 paid。

5. 发货（需要 locker_code）
   ```
   发货，订单号为 <order_id>，取件码 LC123
   ```
   预期：订单状态变为 shipped。

6. 完成订单
   ```
   完成订单，订单号为 <order_id>
   ```
   预期：订单状态变为 successful。

7. 取消订单（可选）
   ```
   取消订单，订单号为 <order_id>
   ```
   预期：订单状态变为 canceled（软取消）。


## 目录结构

- `app/`：Gradio UI + LangGraph agent
- `services/`：订单服务层（Postgres）
- `db/init.sql`：数据库初始化与约束
- `agent/rules/`：规则文档（RAG 语料）

## 说明

- Postgres 与 Qdrant 均由 docker compose 启动。
- 配置项全部位于 `.env`，满足“单文件配置”的要求。
