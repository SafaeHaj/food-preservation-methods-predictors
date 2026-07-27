# Extraction service — PDF/LLM + Docling/PaddleOCR. Internal only (reached via the gateway).
# Build context is pipeline/ so the `shared` package can be installed.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Native libs needed by Docling / PaddleOCR / OpenCV and PyMuPDF rendering.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY shared /shared
RUN pip install --no-cache-dir -e /shared

COPY extraction/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY extraction/ /app/

# The Celery worker runs as 1000:1000 (see docker-compose.yml). The UID needs a real passwd
# entry: celery resolves os.getuid() through pwd, and on KeyError it assumes root and emits
# the superuser SecurityWarning even when the process is unprivileged. --create-home also
# gives Docling's HuggingFace downloads a writable ~/.cache.
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser \
    # RapidOCR (via Docling) downloads detector/recogniser weights into its own package
    # directory on first use rather than a cache dir, so an unprivileged worker cannot
    # start without this. Owned, not world-writable.
    && chown -R appuser:appuser /usr/local/lib/python3.11/site-packages/rapidocr

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
