# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Set environment flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVOICEFLOW_DATA_DIR="/app/data" \
    INVOICEFLOW_RAW_DIR="/app/data/raw" \
    INVOICEFLOW_EXPORT_DIR="/app/data/exports" \
    PATH="/home/appuser/.local/bin:${PATH}"

# Install system dependencies including Tesseract OCR and Poppler utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Create application data directories
RUN mkdir -p /app/data/raw /app/data/exports && \
    chown -R appuser:appuser /app

# Switch to appuser for dependency installation and execution
USER appuser

# Copy dependency specifications first for layer caching
COPY --chown=appuser:appuser pyproject.toml README.md* /app/

# Copy source code and extraction rules
COPY --chown=appuser:appuser src/ /app/src/

# Install the invoiceflow package into user site
RUN pip install --no-cache-dir --user .

# Default container entrypoint
ENTRYPOINT ["invoiceflow"]
CMD ["--help"]
