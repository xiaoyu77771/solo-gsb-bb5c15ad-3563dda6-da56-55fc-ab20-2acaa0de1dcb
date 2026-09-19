FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV APP_DB_PATH=/data/names.db
EXPOSE 8000

# 启动时初始化数据库（幂等）并启动服务
CMD ["sh", "-c", "python -m app.database && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
