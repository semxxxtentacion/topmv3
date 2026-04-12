FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    xvfb \
    libxi6 \
    libgles2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir PyVirtualDisplay==3.0 \
    && playwright install --with-deps chromium

COPY . .

EXPOSE 8082

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8082"]
