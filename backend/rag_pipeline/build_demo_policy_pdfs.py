# pyright: reportMissingImports=false
import json
from pathlib import Path

DEMO_CHUNK_MARKER = "DEMO_POLICY_CHUNK_MARKER"

BASE_DIR = Path(__file__).resolve().parents[1]
DEMO_CHUNKS_PATH = BASE_DIR / "rag" / "data" / "demo_policy_chunks.json"
DEMO_POLICY_DIR = BASE_DIR / "demo_policies"


def _slugify(name: str) -> str:
    return "_".join(name.replace("/", " ").replace("-", " ").split()).lower()


def _draw_wrapped_text(pdf, text: str, x: float, y: float, max_width: float, line_height: float) -> float:
    words = text.split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if pdf.stringWidth(candidate, "Helvetica", 10) <= max_width:
            line = candidate
        else:
            pdf.drawString(x, y, line)
            y -= line_height
            line = word
    if line:
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def main() -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise ImportError("reportlab is required. Install in backend venv: pip install reportlab") from exc

    if not DEMO_CHUNKS_PATH.exists():
        raise FileNotFoundError(f"Missing demo chunks: {DEMO_CHUNKS_PATH}")

    with open(DEMO_CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if not isinstance(chunks, list) or not chunks:
        raise ValueError("demo_policy_chunks.json is empty or invalid")

    grouped = {}
    section_order = {}
    for item in chunks:
        section = str(item.get("section_title", "General")).strip() or "General"
        if section not in section_order:
            section_order[section] = len(section_order) + 1
        grouped.setdefault(section, []).append(item)

    DEMO_POLICY_DIR.mkdir(parents=True, exist_ok=True)
    for old_pdf in DEMO_POLICY_DIR.glob("*.pdf"):
        old_pdf.unlink()

    for section, section_chunks in grouped.items():
        order_prefix = section_order[section]
        out_path = DEMO_POLICY_DIR / f"{order_prefix:02d}_{_slugify(section)}.pdf"
        pdf = canvas.Canvas(str(out_path), pagesize=A4)
        width, height = A4

        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(50, height - 50, f"Demo Policy Section: {section}")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(50, height - 65, "Marker-delimited content for deterministic chunk reconstruction")

        y = height - 95
        for row in section_chunks:
            clause_id = str(row.get("clause_id", "")).strip()
            text = str(row.get("text", "")).strip()
            if not text:
                continue

            block = f"{DEMO_CHUNK_MARKER} {text}"
            pdf.setFont("Helvetica", 10)

            if y < 80:
                pdf.showPage()
                y = height - 50

            pdf.setFont("Helvetica", 10)
            y = _draw_wrapped_text(pdf, block, 50, y, width - 100, 13)
            y -= 8

        pdf.save()

    print(f"Generated {len(grouped)} demo policy PDFs in {DEMO_POLICY_DIR}")


if __name__ == "__main__":
    main()
