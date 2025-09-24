FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies for packages that may require compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY web/requirements.txt ./web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt

# Copy application source
COPY web ./web

# Expose the FastAPI port
EXPOSE 8000

ENV MODULE_NAME=web.app.main \
    APP_NAME=app \
    HOST=0.0.0.0 \
    PORT=8000

CMD ["uvicorn", "web.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
