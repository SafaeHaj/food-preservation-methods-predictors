FROM python:3.13-slim

# libgomp1 is required at runtime by LightGBM/XGBoost's OpenMP-linked wheels.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the files    actually needed to serve predictions -- no training code,
# no notebooks, nothing that would let the container retrain anything.
COPY model_service.py app.py ./ 
COPY assets/ ./assets/
COPY artifacts/ ./artifacts/
COPY data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx ./data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

ENV TF_CPP_MIN_LOG_LEVEL=3 \
    TF_ENABLE_ONEDNN_OPTS=0 \
    PYTHONUNBUFFERED=1

EXPOSE 8050

# Render (and most PaaS Docker runners) inject $PORT and expect the process to
# bind to it; default to 8050 for local `docker run` where $PORT is unset.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8050} --workers 1 --threads 4 --timeout 120 app:server"]
