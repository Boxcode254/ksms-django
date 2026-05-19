# KSMS Production Dockerfile v3
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements-prod.txt --no-cache-dir

# Copy application code
COPY . .

# Create runtime directories and make entrypoint executable
RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chmod +x entrypoint.sh

EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
