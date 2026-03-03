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


from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, CouldNotRetrieveTranscript
from urllib.parse import urlparse, parse_qs
from fastapi import Body, HTTPException

def extract_video_id(url: str) -> str:
    """Extrai video_id de URL YouTube (inclui shorts, youtu.be, etc.)"""
    parsed = urlparse(url)
    if parsed.hostname == 'youtu.be':
        return parsed.path[1:]
    if parsed.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed.path == '/watch':
            params = parse_qs(parsed.query)
            return params['v'][0]
        if parsed.path[:7] == '/embed/':
            return parsed.path.split('/')[2]
        if parsed.path[:3] == '/v/':
            return parsed.path.split('/')[2]
        if parsed.path[:9] == '/shorts/':
            return parsed.path.split('/')[2]
    raise ValueError("URL inválida do YouTube")

@app.post("/youtube-transcription")
async def youtube_transcription(data: dict = Body(...)):
    url = data.get("url")
    if not url:
        raise HTTPException(400, "Envie 'url' no body JSON")

    try:
        video_id = extract_video_id(url)
        # Tenta transcrições em pt-BR primeiro, fallback para en ou auto
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['pt', 'pt-BR'])
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_transcript(['en'])
            except NoTranscriptFound:
                transcript = transcript_list.find_generated_transcript(['en'])  # auto-gerada

        transcript_data = transcript.fetch()
        markdown = "\n".join([f"[{entry['start']:.0f}s] {entry['text']}" for entry in transcript_data])

        return {
            "markdown": markdown or "Transcrição vazia (vídeo sem legendas).",
            "video_id": video_id,
            "source_url": url,
            "language": transcript.language_code
        }

    except (NoTranscriptFound, TranscriptsDisabled):
        raise HTTPException(404, "Transcrição não disponível para este vídeo (sem legendas manuais ou auto-geradas).")
    except CouldNotRetrieveTranscript as e:
        raise HTTPException(500, f"Erro ao recuperar transcrição: {str(e)} (pode ser IP bloqueado ou vídeo restrito).")
    except Exception as e:
        raise HTTPException(500, f"Erro inesperado: {str(e)}")