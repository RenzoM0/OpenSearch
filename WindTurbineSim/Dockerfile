# Use a slim Python image
FROM python:3.11-slim

# Avoid creating .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory inside the container
WORKDIR /app

# Copy and install dependencies first (better build cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, config package, data, and env file
COPY app ./app
COPY config ./config
COPY data ./data
COPY .env ./.env

# Expose FastAPI port
EXPOSE 8000

# Start the FastAPI app with Uvicorn
CMD ["uvicorn", "app.web.main_app:app", "--host", "0.0.0.0", "--port", "8000"]
