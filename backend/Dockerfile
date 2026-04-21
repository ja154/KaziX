# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS builder

# Build deps: gcc for C extensions, musl-dev for libc, libffi/openssl for cryptography
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev curl

WORKDIR /app

COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ───────────────────────────────────────────────────────────────
FROM python:3.11-alpine

# Runtime libs + curl (required by HEALTHCHECK)
RUN apk add --no-cache libffi openssl curl

# Non-root user
RUN addgroup -g 1000 kazix \
 && adduser -D -u 1000 -G kazix kazix

WORKDIR /app

# Copy venv from builder
COPY --from=builder --chown=kazix:kazix /opt/venv /opt/venv

# Copy application source
COPY --chown=kazix:kazix . .

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER kazix

# grace_period gives uvicorn time to fully boot before first probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD sh -c 'curl -f "http://localhost:${PORT:-8000}/health" || exit 1'

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
