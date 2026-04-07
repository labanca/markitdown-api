FROM python:3.11-slim-bookworm

# LibreOffice is used to rasterize EMF/WMF images extracted from PPTX slides.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-draw \
    fonts-liberation \
    libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /app/temp && chmod 777 /app/temp

# LibreOffice headless needs a writable home for its user profile.
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV HOME=/home/appuser

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
