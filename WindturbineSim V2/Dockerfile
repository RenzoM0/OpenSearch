FROM python:3.11-slim

WORKDIR /app

# deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code
COPY . .

EXPOSE 8000

# let op: host 0.0.0.0 is verplicht in Docker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
