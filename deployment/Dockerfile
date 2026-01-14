# IT Infrastructure Monitoring System - Docker Image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY deployment/requirements.txt /app/deployment/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r deployment/requirements.txt

# Copy application code
COPY src/ /app/src/
COPY config/config.example.yaml /app/config/config.example.yaml

# Copy entrypoint script
COPY deployment/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create directories for runtime data
RUN mkdir -p /app/config /app/secrets /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Health check - verify the application can start
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app'); from src.config.loader import ConfigLoader; ConfigLoader.load_from_file('/app/config/config.yaml')" || exit 1

# Run as non-root user for security
RUN useradd -m -u 1000 monitoring && \
    chown -R monitoring:monitoring /app
USER monitoring

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command - run with scheduler
CMD []
