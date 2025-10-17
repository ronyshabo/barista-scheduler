# Use official Python image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps (for google auth, tzdata)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better caching
COPY barista-pay/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy app
COPY barista-pay /app

# Ensure templates are in place
ENV FLASK_APP=app.py

# Create a non-root user
RUN useradd -m appuser
USER appuser

# Expose the port Cloud Run/Render use
EXPOSE 8080

# Start with gunicorn; bind to $PORT for Cloud Run
# Note: Flask app is in app.py and variable `app`
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "app:app"]
