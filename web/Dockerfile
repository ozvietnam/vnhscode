FROM python:3.11-slim

WORKDIR /app

# System deps (gmssl needs build tools for any C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.flask.txt ./
RUN pip install --no-cache-dir -r requirements.flask.txt

# Copy application
COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
