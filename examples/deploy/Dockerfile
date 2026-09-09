# Production-shaped image for an Almasix application directory.
# Build from the app root (sibling of bootstrap/, smith, pyproject.toml).

FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_DEBUG=false

COPY pyproject.toml README.md ./
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["smith", "serve", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-reload", "--proxy-headers"]
