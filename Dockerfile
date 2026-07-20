FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY locales/ locales/
COPY scripts/ scripts/

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 9000

# Volume for persistent data
VOLUME ["/data"]

# Default command
CMD ["webduck", "start", "--host", "0.0.0.0", "--port", "8998"]
