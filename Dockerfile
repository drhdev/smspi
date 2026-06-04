FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        modemmanager \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src
ENV SMSPI_CONFIG=/app/config/config.yaml

RUN useradd --create-home --uid 1000 smspi \
    && mkdir -p /app/config /app/data /app/logs \
    && chown -R smspi:smspi /app

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER smspi

HEALTHCHECK --interval=2m --timeout=10s --start-period=3m \
    CMD test -f /app/data/.health_ok

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "smspi"]
