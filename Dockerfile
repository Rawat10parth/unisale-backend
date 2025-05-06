# Use a more compatible Python image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV PORT=8080

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Firebase Admin SDK credentials
COPY firebase-adminsdk.json /app/firebase-adminsdk.json
COPY tactile-rigging-451008-a0-f0a39bd91c95.json /app/tactile-rigging-451008-a0-f0a39bd91c95.json

# Note: GOOGLE_APPLICATION_CREDENTIALS should be set at runtime, not in the Dockerfile
# For example: docker run -e GOOGLE_APPLICATION_CREDENTIALS=/app/tactile-rigging-451008-a0-f0a39bd91c95.json ...

# Copy application code
COPY . .

# Command to run the application
# Note: Using environment variable with JSON array format
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app"]