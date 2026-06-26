# backend/Dockerfile
# Multi-stage Dockerfile for the FastAPI backend

# Stage 1: build (install deps)
FROM python:3.12-slim AS builder
WORKDIR /app
# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

# Create a non-root user and group
RUN addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 --gid 1001 appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY backend/app ./app

# Ensure local data directories exist with proper permissions (for FAISS)
RUN mkdir -p data/vector_store && chown -R appuser:appgroup data

# Run as non-root
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
