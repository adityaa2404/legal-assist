FROM python:3.11-slim

WORKDIR /app

# Install system deps for PDF processing
RUN apt-get update && apt-get install -y \
    libmupdf-dev gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spacy model for Presidio NER
RUN python -m spacy download en_core_web_lg

COPY ./app ./app

# Add a non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
