FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY backend /app/backend
COPY data /app/data
RUN pip install --no-cache-dir -c /app/backend/requirements-gcp.lock '/app/backend[gcp]' \
    && useradd --create-home --uid 10001 regimpact \
    && mkdir -p /app/.local && chown regimpact:regimpact /app/.local
USER regimpact
EXPOSE 8080
# GCP mode uses explicitly configured real stores; import the corpus before deployment.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
