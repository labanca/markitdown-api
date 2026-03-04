import os
import shutil
from uuid import uuid4
from fastapi import FastAPI, UploadFile, HTTPException, Body
from markitdown import MarkItDown
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, CouldNotRetrieveTranscript
from urllib.parse import urlparse, parse_qs
from openai import AzureOpenAI


app = FastAPI(title="MarkItDown API - Conversão para Markdown")


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

        llm_client = AzureOpenAI(
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),          
            api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
            api_version    = os.getenv("AZURE_OPENAI_API_VERSION") 
        )
        
        md = MarkItDown(
            llm_client=llm_client, 
            llm_model="gpt-4.1",
            llm_prompt="do not over describe the images, only extract the data from tables present in the images and return it in a markdown table format."

        )
        
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

def extract_video_id(url: str) -> str:
    """Extrai o video_id de várias formatos de URL YouTube (inclui shorts, youtu.be, embed, etc.)"""
    parsed = urlparse(url)
    if parsed.hostname == 'youtu.be':
        return parsed.path.lstrip('/')
    if parsed.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed.path == '/watch':
            return parse_qs(parsed.query).get('v', [None])[0]
        if parsed.path.startswith(('/embed/', '/v/')):
            return parsed.path.split('/')[2]
        if parsed.path.startswith('/shorts/'):
            return parsed.path.split('/')[2]
    raise ValueError("Não foi possível extrair video_id da URL")



@app.post("/youtube-transcription")
async def youtube_transcription(data: dict = Body(...)):
    """
    Transcreve vídeo do YouTube usando youtube-transcript-api v1.2+.
    Body: {"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
    """
    url = data.get("url")
    if not url:
        raise HTTPException(400, "Campo 'url' obrigatório no body JSON")

    try:
        video_id = extract_video_id(url)

        ytt = YouTubeTranscriptApi()  # Instancia o objeto (obrigatório na v1.2+)

        # Opção 1: Fetch direto (mais simples e recomendado)
        transcript_data = ytt.fetch(
            video_id=video_id,
            languages=['pt', 'pt-BR', 'en'],  # Prioridade: pt-BR > pt > en
            preserve_formatting=False  # Mude para True se quiser tags HTML como <i>
        )

        # Converte para Markdown com timestamps
        markdown_lines = []
        for entry in transcript_data:
            start = entry.get('start', 0)
            text = entry.get('text', '').strip()
            markdown_lines.append(f"[{int(start // 60):02d}:{int(start % 60):02d}] {text}")

        markdown = "\n".join(markdown_lines) or "Transcrição vazia ou não disponível."

        return {
            "markdown": markdown,
            "video_id": video_id,
            "source_url": url,
            "language": "Prioridade pt-BR/en (conforme disponível)",
            "note": "Usando youtube-transcript-api v1.2.4 – fetch direto. Funciona em vídeos com legendas manuais ou auto-geradas."
        }

    except (NoTranscriptFound, TranscriptsDisabled):
        raise HTTPException(404, "Nenhuma transcrição disponível (vídeo sem legendas manuais ou automáticas).")
    except CouldNotRetrieveTranscript as e:
        raise HTTPException(500, f"Erro ao recuperar transcrição: {str(e)} (pode ser bloqueio de IP, vídeo restrito ou sem legendas).")
    except Exception as e:
        raise HTTPException(500, f"Erro inesperado: {str(e)}")