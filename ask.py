import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv(override=True)

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TOP_K = 5

# Primary model first, fallback second. Override in .env if needed.
MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
    os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
]
MODELS = list(dict.fromkeys(MODELS))  # drop duplicates, keep order

# Notional paid rates (USD per million tokens), Claude Haiku 5.5 list price,
# used only to estimate what this call would cost at scale. The free tier costs $0.
PRICE_IN, PRICE_OUT = 0.10, 0.50

LOG_PATH = Path("logs/calls.jsonl")

SYSTEM_PROMPT = (
    "You answer questions about ABDM and FHIR using ONLY the numbered context "
    "passages provided. After each claim, cite the passage number in square "
    "brackets, like [1] or [2][3]. If the passages do not contain the answer, "
    "reply exactly: I can't find that in the documents. "
    "Do not use outside knowledge."
)

client = OpenAI(
    api_key=os.environ["GEMINI_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    timeout=60,
    max_retries=0,  # we do our own retries below so we can log them
)

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def retrieve(conn, question: str):
    q = get_embedder().encode(QUERY_PREFIX + question, normalize_embeddings=True)
    q = np.array(q)
    rows = conn.execute(
        "select source, page, content, embedding <=> %s as distance "
        "from documents order by embedding <=> %s limit %s",
        (q, q, TOP_K),
    ).fetchall()
    return [
        {"source": r[0], "page": r[1], "content": r[2], "distance": float(r[3])}
        for r in rows
    ]


def build_messages(question: str, chunks: list[dict]):
    context = "\n\n".join(
        f"[{i}] ({c['source']}, p.{c['page']})\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )
    user = f"Context passages:\n\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def generate(messages):
    """Try each model in order, with retry and backoff on transient errors."""
    last_error = None
    attempts = 0
    for model in MODELS:
        for attempt in range(3):
            attempts += 1
            try:
                resp = client.chat.completions.create(model=model, messages=messages)
                usage = resp.usage
                return {
                    "text": resp.choices[0].message.content or "",
                    "model": model,
                    "attempts": attempts,
                    "tokens_in": getattr(usage, "prompt_tokens", 0) or 0,
                    "tokens_out": getattr(usage, "completion_tokens", 0) or 0,
                }
            except (APIStatusError, APITimeoutError, APIConnectionError) as e:
                status = getattr(e, "status_code", None)
                transient = status in (429, 500, 502, 503, 504) or status is None
                last_error = f"{model}: {type(e).__name__} {status}"
                print(f"  ! {last_error} (attempt {attempt + 1}/3)")
                if not transient:
                    break  # permanent error for this model, try the next one
                time.sleep(2**attempt)
    raise RuntimeError(f"All models failed. Last error: {last_error}")


def ask(conn, question: str) -> dict:
    t0 = time.time()
    chunks = retrieve(conn, question)
    t_retrieve = time.time() - t0

    t1 = time.time()
    result = generate(build_messages(question, chunks))
    t_generate = time.time() - t1

    cost = (
        result["tokens_in"] * PRICE_IN + result["tokens_out"] * PRICE_OUT
    ) / 1_000_000

    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": result["text"],
        "model": result["model"],
        "attempts": result["attempts"],
        "retrieve_s": round(t_retrieve, 3),
        "generate_s": round(t_generate, 3),
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "notional_cost_usd": round(cost, 6),
        "sources": [
            {"source": c["source"], "page": c["page"], "distance": round(c["distance"], 4)}
            for c in chunks
        ],
    }
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def show(record: dict):
    print("\nANSWER\n" + record["answer"])
    print("\nSOURCES (closest first; smaller distance = closer)")
    for i, s in enumerate(record["sources"], start=1):
        print(f"  [{i}] {s['source']}, p.{s['page']}  (distance {s['distance']})")
    print(
        f"\nmodel={record['model']}  attempts={record['attempts']}  "
        f"retrieve={record['retrieve_s']}s  generate={record['generate_s']}s  "
        f"tokens={record['tokens_in']} in / {record['tokens_out']} out  "
        f"notional cost=${record['notional_cost_usd']}"
    )


def main():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        if len(sys.argv) > 1:
            show(ask(conn, " ".join(sys.argv[1:])))
            return
        print("Ask a question (blank line to quit).")
        while True:
            q = input("\n> ").strip()
            if not q:
                break
            show(ask(conn, q))


if __name__ == "__main__":
    main()