# Base image with Python and system dependencies
FROM python:3.11-slim

# Install system packages for OpenCV, Tesseract, and fonts
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment variables (override in docker-compose.yml or runtime)
ENV BOT_TOKEN=""
ENV CHANNEL_ID=0

# Expose nothing (Discord bot is outbound only)
# Default command
CMD ["python", "app.py"]
