# todo list

## tool
1. 默认输入时间的格式 时区？
2. 订单操作时，所需字段太多，或者agent不懂如何提取关键词

## RAG
1. RAG现在不能正常工作
2. 第一次调用RAG会特别久？是qdrant的缘故吗？

## frontend
1. 需要立刻显示用户消息
2. 可以考虑流式输出

## 测试
1. 需要单元测试

## log
1. docker日志需要有时间戳

## 其他
1. 不要用load_dotenv，应该在docker环境变量中设置
2. 模型应该保存在huggingface文件夹里面，而不是cache？
3. LangChain 的 embedding deprecation 不是致命，但建议顺手修
    你现在用的 HuggingFaceBgeEmbeddings 已 deprecated。建议换到新包，避免未来突然崩：
    安装：pip install -U langchain-huggingface
    替换 import：from langchain_huggingface import HuggingFaceEmbeddings
4. 数据库操作，不要直接用SQL？

----log----
