FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIZIO_DATA_DIR=/app/data \
    VIZIO_MEDIA_DIR=/app/media

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 vizio \
    && useradd --uid 10001 --gid vizio --no-create-home --shell /usr/sbin/nologin vizio \
    && mkdir -p /app/data /app/media \
    && chown vizio:vizio /app/data /app/media

COPY --chown=vizio:vizio app/ ./app/
COPY --chown=vizio:vizio web/ ./web/
COPY --chown=vizio:vizio coco_worker/ ./coco_worker/
COPY --chown=vizio:vizio vendor/ ./vendor/
COPY --chown=vizio:vizio LICENSE THIRD_PARTY_NOTICES.md ./
COPY --chown=vizio:vizio run.py ./
COPY --chown=vizio:vizio scripts/download_sample.py scripts/container_health.py ./scripts/
COPY --chown=vizio:vizio media/ATTRIBUTION.md ./media/

USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "scripts/container_health.py"]
CMD ["python", "run.py"]
