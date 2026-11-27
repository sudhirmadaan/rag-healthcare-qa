import os
import re
import unicodedata
import time
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

load_dotenv(override=True)

DATA_DIR = Path("data")
MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim embeddings, matches vector(384)
CHUNK_CHARS = 1200  # roughly 300 tokens
OVERLAP = 200

# Browser-print header/footer, e.g. "11/22/26, 6:02 PM <title> https://... 6/8"
PRINT_HEADER = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*[AP]M\s+.{0,200}?https?://\S+\s+\d+/\d+"
)
# NRCeS PDF page footer
NRCES_FOOTER = re.compile(
    r"National Resource Centre for EHR Standards \(NRCeS\).{0,80}?Page \d+ of \d+"
)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # expands fi/fl ligatures
    text = text.replace("\x00", " ")  # Postgres rejects NUL characters
    text = re.sub(r"\s+", " ", text).strip()
    text = PRINT_HEADER.sub(" ", text)
    text = NRCES_FOOTER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
    text = text.replace("\x00", " ")  # Postgres rejects NUL characters
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP) -> list[str]:
    text = clean(text)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)
            if space != -1:
                end = space
        # If only a short tail would remain (no longer than the overlap),
        # absorb it into this chunk instead of emitting a near-duplicate chunk.
        if end < len(text) and len(text) - end <= overlap:
            end = len(text)
        chunk = text[start:end].strip()
        if len(chunk) >= 50:  # skip tiny fragments
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks

def main():
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in data/")
        return

    print("Loading embedding model (first run downloads it)...")
    model = SentenceTransformer(MODEL_NAME)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)

        for pdf in pdfs:
            t0 = time.time()
            reader = PdfReader(str(pdf))
            rows = []  # (page, chunk_index, text)
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                for i, chunk in enumerate(chunk_text(text)):
                    rows.append((page_num, i, chunk))

            if not rows:
                print(f"SKIPPED {pdf.name}: no extractable text (scanned?)")
                continue

            embeddings = model.encode(
                [r[2] for r in rows],
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # Re-running replaces this file's chunks instead of duplicating them
            conn.execute("delete from documents where source = %s", (pdf.name,))
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into documents (source, page, chunk_index, content, embedding) "
                    "values (%s, %s, %s, %s, %s)",
                    [
                        (pdf.name, p, i, c, np.array(e))
                        for (p, i, c), e in zip(rows, embeddings)
                    ],
                )
            conn.commit()
            print(
                f"{pdf.name}: {len(reader.pages)} pages -> {len(rows)} chunks "
                f"({time.time() - t0:.1f}s)"
            )

        print("\nRows now in database:")
        for source, n in conn.execute(
            "select source, count(*) from documents group by source order by source"
        ):
            print(f"  {n:4d}  {source}")


if __name__ == "__main__":
    main()