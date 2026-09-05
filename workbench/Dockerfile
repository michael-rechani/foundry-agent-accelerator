FROM node:24.20.0-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/src/ ./src/
COPY frontend/index.html frontend/tsconfig*.json frontend/vite.config.ts ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home workbench
COPY app.py history.py agents.json ./
COPY --from=frontend /build/static ./static
USER 10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]