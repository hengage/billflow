FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files (ignore errors on first build)
RUN python manage.py collectstatic --noinput || true

# Default command — overridden by docker-compose
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "billflow.asgi:application"]