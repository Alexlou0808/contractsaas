import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

OCR_DPI = 200
TESS_LANG = "chi_sim"


def run_tesseract(image_path: str, psm: int = 4, work_dir: Optional[str] = None) -> str:
    work_dir = work_dir or tempfile.mkdtemp()
    # Resolve macOS /tmp → /private/tmp symlink (Leptonica bug on macOS)
    real_image = os.path.realpath(image_path)
    out_stem = os.path.join(work_dir, Path(real_image).stem)
    result = subprocess.run(
        ["tesseract", real_image, out_stem, "-l", TESS_LANG, "--psm", str(psm)],
        capture_output=True, timeout=120,
    )
    txt_path = out_stem + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return ""


def pdf_to_ocr(pdf_path: str, work_dir: Optional[str] = None,
               page_numbers: Optional[list[int]] = None,
               all_pages: bool = False) -> dict[int, str]:
    """Render PDF pages to images, OCR them, return {page_num: text}."""
    work_dir = work_dir or tempfile.mkdtemp()
    os.makedirs(work_dir, exist_ok=True)

    result = subprocess.run(
        ["pdfinfo", pdf_path], capture_output=True, timeout=30,
    )
    total_pages = 0
    for line in result.stdout.decode("utf-8", errors="replace").split("\n"):
        if line.strip().startswith("Pages:"):
            total_pages = int(line.split(":")[1].strip())
            break
    if total_pages == 0:
        return {}

    if page_numbers:
        pages = [p for p in page_numbers if 1 <= p <= total_pages]
    elif all_pages:
        pages = list(range(1, total_pages + 1))
    else:
        pages = list(range(1, total_pages + 1))

    pdf_stem = Path(pdf_path).stem
    results = {}
    for pg in pages:
        prefix = os.path.join(work_dir, f"pg_{pdf_stem}_{pg}")
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(OCR_DPI), "-f", str(pg), "-l", str(pg),
             pdf_path, prefix],
            capture_output=True, timeout=120,
        )
        img_path = f"{prefix}-{pg}.png"
        if os.path.exists(img_path):
            text = run_tesseract(img_path, work_dir=work_dir)
            results[pg] = text
            try:
                os.remove(img_path)
            except OSError:
                pass
    return results


def normalize_ocr_text(text: str) -> str:
    """Clean OCR artifacts."""
    text = re.sub(r'\.\s+(\d)', r'.\1', text)
    text = re.sub(r'(?<=\d)\. (?=\d)', '.', text)
    text = re.sub(r'(?<=\d),(?=\d)', '.', text)
    text = re.sub(r'(?<=[一-鿿])\s+(?=[一-鿿])', '', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()
