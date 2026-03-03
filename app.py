import os
import shutil
from uuid import uuid4
from fastapi import FastAPI, UploadFile, HTTPException, Body
from markitdown import MarkItDown


app = FastAPI(title="MarkItDown API - Conversão para Markdown")

# Instancia o MarkItDown (pode receber configs via env se precisar de LLM)
md = MarkItDown()  # Adicione parâmetros se quiser customizar (ex: llm_provider)

@app.post("/convert")
async def convert_to_markdown(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    unique_id = uuid4().hex
    temp_dir = f"/app/temp/{unique_id}"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = md.convert(file_path)
        markdown_content = result.text_content

        return {"markdown": markdown_content}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na conversão: {str(e)}")

    finally:
        # Sempre limpa a pasta temporária
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/youtube-transcription")
async def youtube_transcription(data: dict = Body(...)):
    """
    Transcreve um vídeo do YouTube para Markdown usando MarkItDown.
    Envie no body: {"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
    """
    url = data.get("url")
    if not url or not isinstance(url, str) or "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(status_code=400, detail="Envie uma URL válida do YouTube no campo 'url'")

    try:
        # MarkItDown suporta URL diretamente!
        result = md.convert(url)
        markdown_content = result.text_content

        return {
            "markdown": markdown_content,
            "source_url": url,
            "note": "Transcrição automática via MarkItDown (pode incluir timestamps se disponíveis)"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao transcrever YouTube: {str(e)}")