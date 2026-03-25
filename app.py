import os
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4

from fastapi import FastAPI, UploadFile, HTTPException
from markitdown import MarkItDown
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput
from azure.core.credentials import AzureKeyCredential

app = FastAPI(title="MarkItDown API - Conversão para Markdown")


# ---------------------------------------------------------------------------
# Azure Content Understanding client
# ---------------------------------------------------------------------------

def get_cu_client() -> ContentUnderstandingClient:
    endpoint = os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT")
    key = os.getenv("AZURE_FOUNDRY_API_KEY")
    return ContentUnderstandingClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
        api_version="2025-11-01",
    )


# ---------------------------------------------------------------------------
# Vector image rasterization: EMF/WMF -> PNG via LibreOffice
# ---------------------------------------------------------------------------

_VECTOR_FORMATS = {"wmf", "emf", "svg"}

_EXT_TO_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "bmp": "image/bmp",
    "tif": "image/tiff", "tiff": "image/tiff",
}


def convert_to_pdf(image_bytes: bytes, ext: str) -> bytes:
    """Convert a vector image (EMF, WMF, SVG) to PDF using LibreOffice headless.

    LibreOffice preserves vector information when converting to PDF, so the
    Content Understanding service receives a high-fidelity document rather than
    a rasterized bitmap — no resolution loss, no interpolation artifacts.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        src = os.path.join(tmp_dir, f"input.{ext}")
        with open(src, "wb") as f:
            f.write(image_bytes)

        result = subprocess.run(
            [
                "libreoffice", "--headless", "--norestore",
                "--convert-to", "pdf",
                "--outdir", tmp_dir,
                src,
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice PDF conversion failed: {result.stderr.decode(errors='replace')}"
            )

        dst = os.path.join(tmp_dir, "input.pdf")
        if not os.path.exists(dst):
            raise RuntimeError(
                f"LibreOffice produced no PDF output. "
                f"stdout: {result.stdout.decode(errors='replace')}"
            )

        with open(dst, "rb") as f:
            return f.read()


def get_base_temp_dir() -> str:
    """Retorna um diretório temporario portavel (Windows local vs Docker).

    O codigo historicamente usava '/app/temp' (Linux container). Para debug
    local no Windows, ajustamos para um diretorio writeable.
    """
    env_dir = os.getenv("MARKITDOWN_TEMP_DIR")
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir

    default_dir = "/app/temp"
    try:
        os.makedirs(default_dir, exist_ok=True)
        # Probe de escrita para evitar surprisas com permissao.
        probe = os.path.join(default_dir, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return default_dir
    except Exception:
        # Usa o diretorio temporario do SO como fallback.
        return os.path.join(tempfile.gettempdir(), "markitdown-api", "temp")


# ---------------------------------------------------------------------------
# Table extraction via Azure Content Understanding Layout
# ---------------------------------------------------------------------------

def _tables_to_markdown(tables: list) -> str:
    """Convert Content Understanding table objects to markdown tables.

    Uses the structured cells array (rowIndex, columnIndex, content) to build
    markdown directly — no HTML parsing needed.
    """
    md_tables = []
    for table in tables:
        cells = table.get("cells", [])
        if not cells:
            continue

        row_count = table.get("rowCount", 0)
        col_count = table.get("columnCount", 0)

        # Build a 2D grid filled with empty strings
        grid = [[""] * col_count for _ in range(row_count)]
        header_row = set()

        for cell in cells:
            r = cell.get("rowIndex", 0)
            c = cell.get("columnIndex", 0)
            content = cell.get("content", "").replace("\n", " ").strip()
            if r < row_count and c < col_count:
                grid[r][c] = content
            if cell.get("kind") == "columnHeader":
                header_row.add(r)

        lines = []
        for r_idx, row in enumerate(grid):
            line = "| " + " | ".join(row) + " |"
            lines.append(line)
            # Add separator after the last header row
            if r_idx in header_row and (r_idx + 1) not in header_row:
                sep = "| " + " | ".join(["---"] * col_count) + " |"
                lines.append(sep)

        md_tables.append("\n".join(lines))

    return "\n\n".join(md_tables)


def extract_tables_from_image(
    image_bytes: bytes,
    mime_type: str,
    image_name: str,
) -> str | None:
    """Send image bytes to Azure Content Understanding Layout and return markdown.

    Returns a markdown string with the extracted tables, or None if no tables
    were found. Raises on API errors (caller handles retry if needed).
    """
    client = get_cu_client()

    poller = client.begin_analyze(
        analyzer_id="prebuilt-layout",
        inputs=[AnalysisInput(data=image_bytes, mime_type=mime_type)],
    )
    result = poller.result()
    result_dict = result.as_dict()

    contents = result_dict.get("contents", [])
    if not contents:
        return None

    content = contents[0]
    tables = content.get("tables", [])

    if not tables:
        return None

    return _tables_to_markdown(tables)


# ---------------------------------------------------------------------------
# Per-image processing: detect format, rasterize if needed, extract tables
# ---------------------------------------------------------------------------

def process_image(
    image_bytes: bytes,
    ext: str,
    image_name: str,
    max_retries: int = 3,
) -> str | None:
    """Process a single image extracted from a PPTX slide.

    - Vector formats (EMF/WMF): rasterize with LibreOffice first.
    - Raster formats (PNG/JPG): send directly.
    Returns extracted markdown or None if no table found.
    """
    ext = ext.lower()

    if ext in _VECTOR_FORMATS:
        try:
            image_bytes = convert_to_pdf(image_bytes, ext)
            ext = "pdf"
            print(f"[INFO] Converted to PDF: {image_name}")
        except Exception as exc:
            print(f"[ERROR] Could not rasterize {image_name}: {exc}")
            return f"[Não foi possível rasterizar {image_name}: {exc}]"

    mime_type = "application/pdf" if ext == "pdf" else _EXT_TO_MIME.get(ext, "image/png")

    for attempt in range(max_retries):
        try:
            result = extract_tables_from_image(image_bytes, mime_type, image_name)
            print(
                f"[INFO] {'Tables found' if result else 'No table'} in {image_name}"
            )
            return result  # None = no table, string = extracted markdown
        except Exception as exc:
            print(
                f"[ERROR] Content Understanding failed for {image_name} "
                f"(attempt {attempt + 1}): {exc}"
            )

    return f"[Não foi possível extrair dados de {image_name} após {max_retries} tentativas]"


# ---------------------------------------------------------------------------
# PPTX processing: MarkItDown text + per-image Content Understanding
# ---------------------------------------------------------------------------

def _extract_slide_images(pptx_path: str) -> list[list[tuple[str, bytes, str]]]:
    """Return a list (one per slide) of [(shape_name, image_bytes, ext), ...].

    Uses python-pptx directly to avoid shape name collisions across slides.
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(pptx_path)
    result = []
    for slide in prs.slides:
        slide_images: list[tuple[str, bytes, str]] = []
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    slide_images.append(
                        (shape.name, shape.image.blob, shape.image.ext or "png")
                    )
                except Exception as exc:
                    print(f"[WARN] Could not read image from shape '{shape.name}': {exc}")
        result.append(slide_images)
    return result


_SLIDE_HEADER = re.compile(r"(<!-- Slide number: (\d+) -->)")
_IMG_PLACEHOLDER = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def process_pptx(file_path: str) -> str:
    """Process a PPTX file and return clean markdown with tables extracted from images.

    Strategy:
    1. MarkItDown without LLM -> reliable text/structure extraction.
    2. python-pptx -> extract image bytes per slide (avoids shape name collisions).
    3. For each empty image placeholder:
       - Rasterize if EMF/WMF (LibreOffice).
       - Send to Azure Content Understanding Layout.
       - Replace placeholder with structured markdown table.
    """
    # Step 1: base markdown (text only, no LLM)
    base_markdown = MarkItDown().convert(file_path).text_content

    # Step 2: extract images per slide
    slide_images = _extract_slide_images(file_path)

    # Step 3: walk slide by slide and replace placeholders
    parts = _SLIDE_HEADER.split(base_markdown)
    # layout: [pre, full_header, slide_num, content, ...]

    output: list[str] = []
    i = 0

    if parts:
        output.append(parts[0])
        i = 1

    while i < len(parts):
        full_header   = parts[i]
        slide_num_str = parts[i + 1]
        content       = parts[i + 2] if i + 2 < len(parts) else ""
        i += 3

        output.append(full_header)

        slide_idx = int(slide_num_str) - 1  # 0-based
        images_for_slide = slide_images[slide_idx] if slide_idx < len(slide_images) else []
        img_counter = [0]

        def replace_placeholder(match: re.Match) -> str:
            alt_text = match.group(1).strip()

            # MarkItDown already extracted something here — keep it
            if alt_text:
                return match.group(0)

            pos = img_counter[0]
            img_counter[0] += 1

            if pos >= len(images_for_slide):
                return ""  # no image data — remove placeholder

            shape_name, img_bytes, ext = images_for_slide[pos]
            label = f"slide{slide_idx + 1}_{shape_name}.{ext}"
            print(f"[INFO] Processing image: {label}")

            extracted = process_image(img_bytes, ext, label)

            if extracted is None:
                return ""  # no table in this image — remove placeholder cleanly
            return f"\n{extracted}\n"

        content = _IMG_PLACEHOLDER.sub(replace_placeholder, content)
        output.append(content)

    return "".join(output)


# ---------------------------------------------------------------------------
# Main /convert endpoint
# ---------------------------------------------------------------------------

@app.post("/convert")
async def convert_to_markdown(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    unique_id = uuid4().hex
    base_temp_dir = get_base_temp_dir()
    temp_dir = os.path.join(base_temp_dir, unique_id)
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ext = file.filename.rsplit(".", 1)[-1].lower()

        if ext in ("pptx", "ppt"):
            markdown_content = process_pptx(file_path)
        else:
            # All other formats: standard MarkItDown (no LLM needed for text docs)
            markdown_content = MarkItDown().convert(file_path).text_content

        return {"markdown": markdown_content}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na conversão: {str(e)}")

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Debug endpoint: convert EMF/WMF to PDF and return as download
# ---------------------------------------------------------------------------

@app.post("/debug-to-pdf")
async def debug_to_pdf(file: UploadFile):
    """Recebe um arquivo EMF/WMF e devolve o PDF gerado pelo LibreOffice.

    Util para inspecionar visualmente o que o LibreOffice esta gerando
    antes de enviar ao Content Understanding.

    Exemplo de uso:
        curl -X POST http://localhost:8000/debug-to-pdf \
             -F "file=@imagem.wmf" \
             --output resultado.pdf
    """
    from fastapi.responses import Response

    if not file.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in _VECTOR_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato nao suportado: .{ext}. Envie um arquivo EMF, WMF ou SVG.",
        )

    image_bytes = await file.read()

    try:
        pdf_bytes = convert_to_pdf(image_bytes, ext)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na conversao: {str(e)}")

    filename = file.filename.rsplit(".", 1)[0] + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )