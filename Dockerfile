# Use a lightweight Python base image
FROM python:3.9-slim

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Upgrade pip to the latest version
RUN pip install --upgrade pip

# Copy the requirements file first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code from app/ to /app/
COPY app/ /app/

# test
RUN echo "DEBUG: Listing /app" && ls -R /app

# Expose port 3000 for the application
EXPOSE 3000

# Environment variables
ENV PORT=3000

# Start the application
CMD ["python", "-u", "core/main.py"]
