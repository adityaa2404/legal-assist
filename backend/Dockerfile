FROM python:3.11-slim

WORKDIR /app

# Install runtime deps for PDF/report processing and compiled wheels.
RUN apt-get update && apt-get install -y \
    build-essential gcc \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spacy model for Presidio NER
RUN python -m spacy download en_core_web_lg

COPY ./app ./app

# Add a non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
