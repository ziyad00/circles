# Single-stage build for AWS deployment with correct platform
FROM --platform=$TARGETPLATFORM public.ecr.aws/docker/library/python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and use virtual environment with pip
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy dependency files and extract requirements
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv export --no-dev > requirements.txt

# Install dependencies with pip for proper platform handling
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create media directory for file uploads
RUN mkdir -p media

# Expose port
EXPOSE 8000

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["./start.sh"]

