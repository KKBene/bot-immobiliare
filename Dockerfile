# Container per il ciclo di scrape. Mira al minimo: serve solo Python + curl.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl_cffi richiede libcurl-impersonate (è inclusa nel wheel pacchettizzato per linux)
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: un ciclo singolo. Su Railway puoi usare cron, in alternativa
# usa lo schedule esterno (GitHub Actions, ecc.)
CMD ["python", "scripts/run_cycle.py", "--idealista", "1", "--immo", "1"]
