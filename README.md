# MarkItDown API

A FastAPI service that converts documents to Markdown. Designed for RAG pipelines that need clean, structured text — including tables embedded as images inside PowerPoint presentations.

## Features

- Converts PPTX, DOCX, PDF, XLSX and other formats to Markdown
- **PPTX image intelligence**: extracts images slide-by-slide via `python-pptx`, calls GPT-4.1 vision directly with retry logic to reliably turn image-tables into Markdown tables
- Automatic retry with exponential back-off (up to 3 attempts per image)
- Isolated temp directories per request — no file collisions under concurrent load

## Endpoints

### `POST /convert`

Converts an uploaded file to Markdown.

**Request:** `multipart/form-data` with a `file` field.

**Response:**
```json
{
  "markdown": "# Slide title\n\n| Col A | Col B |\n|-------|-------|\n| 1     | 2     |\n"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/convert \
  -F "file=@presentation.pptx"
```

### `GET /health`

Returns `{"status": "healthy"}`. Use for container health checks and load balancer probes.

## PPTX Image Extraction — How It Works

Standard MarkItDown passes images to the LLM internally and silently drops failures, producing empty `![]()` placeholders. This API replaces that behaviour for PPTX files:

1. **MarkItDown without LLM** extracts all text and slide structure.
2. **`python-pptx`** extracts image bytes directly from each slide, keyed by slide index and shape position — not by shape name. This avoids the name collision where PowerPoint reuses names like `Imagem1` across multiple slides pointing to different images.
3. **GPT-4.1 vision** is called directly per image with up to 3 retries and empty-response detection.
4. The image placeholder in the Markdown is replaced with the extracted table or a one-sentence fallback description.

All other file formats (DOCX, PDF, XLSX, etc.) are handled by the standard MarkItDown + LLM path.

## Setup

### Environment variables

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | API key |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |

### Running with Docker

```bash
docker build -t markitdown-api .

docker run -p 8000:8000 \
  -e AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/ \
  -e AZURE_OPENAI_API_KEY=your-key \
  -e AZURE_OPENAI_API_VERSION=2024-02-01 \
  markitdown-api
```

### Running locally

```bash
pip install -r requirements.txt

AZURE_OPENAI_ENDPOINT=... \
AZURE_OPENAI_API_KEY=... \
AZURE_OPENAI_API_VERSION=... \
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Project Structure

```
.
├── app.py            # FastAPI application
├── requirements.txt  # Python dependencies
├── Dockerfile        # Container definition
└── README.md
```

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | HTTP server |
| `markitdown` | Text and structure extraction from documents |
| `python-pptx` | Slide-level image extraction for PPTX |
| `openai` | Azure OpenAI client for GPT-4.1 vision |
| `python-multipart` | File upload support |

System dependencies installed in the Docker image: `tesseract-ocr`, `poppler-utils`, `ffmpeg`, `libmagic`.
