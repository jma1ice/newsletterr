FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget gosu \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libxcb1 libxkbcommon0 libasound2 libexpat1 \
    libdrm2 libgtk-3-0 fonts-liberation \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libcairo2 \
    libharfbuzz0b libharfbuzz-subset0 libfontconfig1 libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime account (NEWS-7). uid/gid 1000 is the linuxserver.io
# default and can be remapped at runtime via PUID/PGID (see entrypoint).
RUN groupadd -g 1000 app && useradd -u 1000 -g app -d /app -s /usr/sbin/nologin app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Playwright browsers install to /root by default; put them somewhere the app
# user can read and point the runtime at it.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN python -m playwright install chromium

COPY . /app/

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Runtime dirs owned by the app user so writes work whether started as the
# baked-in user or dropped into via gosu.
RUN mkdir -p /app/database /app/env /app/static/uploads \
    && chown -R app:app /app /opt/playwright

VOLUME ["/app/database"]
VOLUME ["/app/env"]
VOLUME ["/app/static/uploads"]

EXPOSE 6397

# Default to the non-root user. Starting the container as root (with PUID/PGID)
# still works: the entrypoint chowns the volumes and drops privileges via gosu.
USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6397/cache_status', timeout=5)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# -w 1 is required: the in-process scheduler thread must be a singleton.
# gthread provides request concurrency (chart capture calls back into the app).
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", "--timeout", "180", "-b", "0.0.0.0:6397", "newsletterr:app"]
