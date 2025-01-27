# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip, setuptools, and wheel
RUN pip install --upgrade pip setuptools wheel

# Set work directory
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Install Python dependencies with retry mechanism and explicit PyPI index
RUN pip install --no-cache-dir -r requirements.txt --retries 5 --timeout 30 --index-url https://pypi.org/simple -v

# Copy the rest of the application code
COPY . /app/

ENV PYTHONPATH=/app

# Define the default command
CMD ["python", "core/main.py"]
