FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend/ ./
COPY demo/ /app/demo/
COPY evaluation/ /app/evaluation/
COPY --from=frontend /build/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 legallens && mkdir -p /var/lib/legallens/files && chown -R legallens:legallens /var/lib/legallens
USER legallens
ENV LEGALLENS_STORAGE_DIR=/var/lib/legallens/files LEGALLENS_DATABASE_URL=sqlite:////var/lib/legallens/legallens.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
