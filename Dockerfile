FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt requirements-prod.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev libmagic1 && rm -rf /var/lib/apt/lists/*
RUN pip install -r requirements-prod.txt --no-cache-dir
COPY . .
RUN mkdir -p /app/logs /app/media /app/staticfiles

EXPOSE 8000

# TEMP: Test server to verify container works
CMD ["python", "test_server.py"]
