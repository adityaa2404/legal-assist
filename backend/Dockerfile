FROM python:3.11-slim

WORKDIR /app

# Install runtime deps for PDF/report processing and compiled wheels.
RUN apt-get update && apt-get install -y \
    build-essential gcc \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
    curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spacy model for Presidio NER
RUN python -m spacy download en_core_web_lg

# Install a pinned Prometheus release for local scraping and remote_write.
ARG PROMETHEUS_VERSION=3.14.0
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) prom_arch="amd64" ;; \
      arm64) prom_arch="arm64" ;; \
      *) echo "Unsupported architecture: $arch"; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-${prom_arch}.tar.gz" -o /tmp/prometheus.tar.gz; \
    tar -xzf /tmp/prometheus.tar.gz -C /tmp; \
    install -m 0755 "/tmp/prometheus-${PROMETHEUS_VERSION}.linux-${prom_arch}/prometheus" /usr/local/bin/prometheus; \
    rm -rf /tmp/prometheus.tar.gz "/tmp/prometheus-${PROMETHEUS_VERSION}.linux-${prom_arch}"

COPY ./app ./app
COPY ./prometheus.yml.template ./prometheus.yml.template
COPY ./start.sh ./start.sh

# Add a non-root user for security
RUN useradd -m appuser \
    && chown -R appuser:appuser /app \
    && chmod 0755 /app/start.sh
USER appuser

ENV PORT=7860
ENV PROMETHEUS_RETENTION=24h
EXPOSE 7860

CMD ["/app/start.sh"]
