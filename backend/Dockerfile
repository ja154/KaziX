# Build stage
FROM python:3.11-slim-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim-alpine

# Install runtime dependencies only
RUN apk add --no-cache libffi openssl

# Create non-root user for security
RUN addgroup -g 1000 kazix && adduser -D -u 1000 -G kazix kazix

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=kazix:kazix /opt/venv /opt/venv

# Copy application code
COPY --chown=kazix:kazix . .

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER kazix

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
