FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ENV HF_HOME=/app/.cache/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Pre-download embedding model for RAG at build time
RUN python -c "from langchain_community.embeddings import HuggingFaceBgeEmbeddings; from app.config import settings; print('Pre downloading RAG models...'); emb = HuggingFaceBgeEmbeddings(model_name=settings.embedding_model, model_kwargs={'device': 'cpu'}, encode_kwargs={'normalize_embeddings': settings.embedding_normalize}, query_instruction=''); emb.embed_query('warmup')"

EXPOSE 7860

CMD ["python", "-m", "app.main"]
