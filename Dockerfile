FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY entrypoint.sh /entrypoint.sh

# Install the package
RUN pip install --no-cache-dir .

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8998

# Volume for persistent data
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["webduck", "start", "--host", "0.0.0.0", "--port", "8998"]
