# Gateway / BFF — the only publicly exposed service. Build context is pipeline/ so the
# `shared` package (db models, schemas, config, security) can be installed.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY shared /shared
RUN pip install --no-cache-dir -e /shared

COPY gateway/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ /app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
