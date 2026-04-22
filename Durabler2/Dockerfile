FROM python:3.11-slim

# System dependencies for scientific packages, PDF conversion, and image handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libreoffice-writer \
    libffi-dev \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install metric-compatible fonts for Word documents (Calibri→Carlito, Cambria→Caladea)
# Plus Liberation fonts (Arial→Liberation Sans, Times→Liberation Serif)
# Required for LibreOffice Word-to-PDF conversion to match original layout
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-liberation \
    fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for persistent data
RUN mkdir -p /app/reports /app/certs /app/app/static/uploads /app/instance

# Entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 5005

ENTRYPOINT ["/docker-entrypoint.sh"]
