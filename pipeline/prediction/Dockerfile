# Prediction microservice: survival/AFT engines (Weibull-AFT / RSF / GBS) + R shared-frailty.
# Python is standardized at 3.11 for this service (the numpy>=2.0 / scikit-survival --no-deps
# dance is a Python-3.14 artifact, not an algorithmic need; 3.11 has clean wheels for everything).
FROM python:3.11-slim

# System deps:
#   r-base / r-base-dev       -> Rscript + headers for the Weibull frailtypack stage 2
#   build-essential / gfortran -> compile frailtypack (Fortran/C) and osqp
#   libopenblas / liblapack    -> BLAS/LAPACK for numpy/scipy/R
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        r-base r-base-dev \
        build-essential gfortran \
        libopenblas-dev liblapack-dev \
        libcurl4-openssl-dev libssl-dev libxml2-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# R: frailtypack (Weibull shared-frailty, stage 2). Kept early so it caches across code changes.
# Rprofile.site points R at Posit Package Manager's Debian binaries -- frailtypack Imports shiny,
# whose bslib/sass chain fails to compile from source in a slim image. Fail loudly if unusable.
COPY Rprofile.site /usr/lib/R/etc/Rprofile.site
RUN Rscript -e 'install.packages("frailtypack")' \
    && Rscript -e 'library(frailtypack); cat("frailtypack OK\n")'

WORKDIR /app

# Python deps first (cache across code changes). scikit-survival WITHOUT its dependency
# resolution -- its only used modules (ensemble.RandomSurvivalForest, metrics) never touch `ecos`.
COPY requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt \
    && pip install --no-cache-dir --no-deps scikit-survival

COPY . .

# Production config (config/production.yaml is empty -> base.yaml applies, use_r_frailty=true).
ENV ENVIRONMENT=production \
    SURVIVAL_ARTIFACT_DIR=/artifacts \
    PYTHONUNBUFFERED=1
RUN mkdir -p /artifacts

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
