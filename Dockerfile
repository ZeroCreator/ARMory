FROM python:3.13-slim

LABEL maintainer="Shkola Olga"

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (production only)
RUN uv sync --no-dev

# Copy application code
COPY app/ ./app/

# Create data directories for persistent storage
RUN mkdir -p /app/data/uploads

EXPOSE 8088

ENV PORT=8088
CMD uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
