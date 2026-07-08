FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PUBLIC_BASE_URL=http://127.0.0.1:6397

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libxcb1 libxkbcommon0 libasound2 libexpat1 \
    libdrm2 libgtk-3-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

COPY . /app/

VOLUME ["/app/database"]
VOLUME ["/app/env"]
VOLUME ["/app/static/uploads"]

EXPOSE 6397

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6397/cache_status', timeout=5)"

# -w 1 is required: the in-process scheduler thread must be a singleton.
# gthread provides request concurrency (chart capture calls back into the app).
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", "--timeout", "180", "-b", "0.0.0.0:6397", "newsletterr:app"]
