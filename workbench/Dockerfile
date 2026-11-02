FROM node:24.22.2-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/src/ ./src/
COPY frontend/index.html frontend/tsconfig*.json frontend/vite.config.ts ./
RUN npm run build

FROM python:3.14-slim-bookworm@sha256:516b51cb9db2ef061e465c803e50f64361b82cefd91e525b889b967b83e83527
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home workbench
COPY *.py *.json ./
COPY agent_runtime/ ./agent_runtime/
COPY agent_templates/ ./agent_templates/
COPY --from=frontend /build/static ./static
USER 10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "32", "--timeout-keep-alive", "5", "--no-access-log"]