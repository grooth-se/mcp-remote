FROM python:3.12-slim

WORKDIR /app

# System deps for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/new_projects data/generated data/templates data/vectordb

EXPOSE 5003

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5003/health')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
