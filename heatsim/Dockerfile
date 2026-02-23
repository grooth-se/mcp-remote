# Subseatec Materials Simulation Platform
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cadquery needs native OCP - skip if unavailable)
COPY requirements.txt .
RUN grep -v cadquery requirements.txt > requirements-docker.txt && \
    pip install --no-cache-dir -r requirements-docker.txt && \
    pip install --no-cache-dir cadquery 2>/dev/null || echo "cadquery skipped (optional, needs native OCP)"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p instance data/uploads data/geometries data/results

# Set environment variables
ENV FLASK_CONFIG=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "--workers", "1", "--threads", "4", "run:app"]
