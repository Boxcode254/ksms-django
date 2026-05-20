# KSMS Production Dockerfile v15 - collectstatic first
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt --no-cache-dir

COPY . .

RUN mkdir -p /app/logs /app/media /app/staticfiles

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
