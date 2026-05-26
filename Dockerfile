# --- builder ---
FROM python:3.11-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels .

# --- runtime ---
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN groupadd -r orbyn && useradd -r -g orbyn -d /app orbyn
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY app ./app
RUN mkdir -p /data && chown -R orbyn:orbyn /app /data
USER orbyn

# leads.db vive en un volumen para no perderlo entre redeploys
ENV ORBYN_DB_DIR=/data
VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
