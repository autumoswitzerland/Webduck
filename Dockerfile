FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY entrypoint.sh /entrypoint.sh

# Install the package
RUN pip install --no-cache-dir .

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Create application data directory
RUN mkdir -p /app/data

# Persistent data directory
VOLUME ["/app/data"]

# Expose port
EXPOSE 8998

ENTRYPOINT ["/entrypoint.sh"]

CMD ["webduck", "start", "--host", "0.0.0.0", "--port", "8998"]
