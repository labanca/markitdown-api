import os
import shutil
from uuid import uuid4
from fastapi import FastAPI, UploadFile, HTTPException
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