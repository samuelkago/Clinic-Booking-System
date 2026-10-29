FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/start.sh

EXPOSE 8000

# Migrate + seed on boot (needed on Render free — no shell), then start API.
# Render injects $PORT; locally defaults to 8000.
CMD ["./scripts/start.sh"]
