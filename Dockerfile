# Usa uma base Debian com Python (melhor compatibilidade com libs nativas)
FROM python:3.11-slim-bookworm

# Instala dependências do sistema necessárias para MarkItDown funcionar bem
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    ffmpeg \
    libmagic1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia e instala Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY app.py .

# Cria pasta temp com permissão
RUN mkdir -p /app/temp && chmod 777 /app/temp

# Expõe a porta
EXPOSE 8000

# Comando para rodar (use --workers para produção se quiser)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]