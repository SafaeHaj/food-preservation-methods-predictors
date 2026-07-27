# Processing service — canonical curation, kinetics, thresholds, exports, model lab.
# Internal only (reached via the gateway). Build context is pipeline/ for the `shared` package.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY shared /shared
RUN pip install --no-cache-dir -e /shared

COPY processing/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY processing/ /app/

# The Celery worker runs as 1000:1000 (see docker-compose.yml). The UID needs a real passwd
# entry: celery resolves os.getuid() through pwd, and on KeyError it assumes root and emits
# the superuser SecurityWarning even when the process is unprivileged.
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser

EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
