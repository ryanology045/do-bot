# Use a lightweight Python base image
FROM python:3.9-slim

# Working directory inside the container
WORKDIR /app

# Copy requirement file and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source code into /app
COPY . /app

# Expose port 3000 for HTTP server
EXPOSE 3000

# Environment variables can be overridden by ECS task definition
ENV PORT=3000

# Start the bot
CMD ["python", "-u", "core/main.py"]
