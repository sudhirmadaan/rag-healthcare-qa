# rag-healthcare-qa

A small retrieval-augmented question-answering system over public ABDM (Ayushman Bharat Digital Mission) and FHIR documentation. Ask a question, get an answer with numbered citations back to the source page, or an explicit refusal when the documents don't contain the answer.

Built as a hands-on project to show end-to-end ownership of an AI feature: ingestion, retrieval, generation, and, most importantly, a way to measure whether it works.

> Status: proof of concept. Web UI and cloud deployment: _TODO (link when live)_. Demo: _TODO_.

## What it does

- Answers questions from five public PDFs (see `data/README.md` for source URLs): ABDM Sandbox docs (PHR Framework, Requesting Consent), the FHIR Implementation Guide for ABDM v6.5.0 (Home, Profiles), and the NRCeS FHIR adoption guide.
- Cites sources as `[n]`, mapped to document and page.
- Replies "I can't find that in the documents." when retrieval doesn't support an answer.

## Architecture

```
PDFs -> clean -> chunk (1,200 chars, 200 overlap, per page)
     -> embed locally (BAAI/bge-small-en-v1.5, 384-dim, normalized)
     -> Postgres + pgvector (Supabase), HNSW index, cosine distance

question -> embed (query prefix) -> top-8 chunks by cosine distance
         -> Gemini (OpenAI-compatible endpoint) answers from those chunks only, with [n] citations
         -> retry 3x with backoff, then fall back to a lighter model
```

| Piece | Choice | Why |
|---|---|---|
| Embeddings | bge-small-en-v1.5, local | Free, fast, no data leaves the machine at ingest/query embedding time |
| Vector store | Postgres + pgvector (HNSW, cosine) | One boring database instead of a separate vector service |
| Generation | Gemini via OpenAI-compatible API, with fallback model | Provider swappable by config; fallback handles 429/503 |
| Retrieval | top_k = 8 | See "What the evaluation found" |

_TODO: add architecture diagram image here._

## Evaluation

Quality is measured with a golden set of 12 questions (`eval/questions.json`): 10 answerable, 2 deliberately unanswerable (one out-of-domain, one in-domain but not in the documents).

Run it with `python run_eval.py`. Each run writes a Markdown and JSON report to `eval/`.

For each question the harness records:

- **Retrieval hit and gold rank.** Gold chunks are found offline by searching the database for a short phrase that must appear in the right passage. This labels retrieval only. It is not used in the live pipeline.
- **Citation checks.** Whether the answer cites a gold chunk, and whether every `[n]` points to a real retrieved chunk.
- **Refusal.** Whether unanswerable questions are refused.
- **LLM judge.** SUPPORTED / PARTIAL / UNSUPPORTED against the cited text. Same model family as the generator, so it is lenient and noisy; treat it as a flag, not ground truth.
- **Warnings.** For example, gold phrases that match too many chunks (labels too loose).

### What the evaluation found

| Run | Auto-pass | What happened |
|---|---|---|
| Baseline | 9/12 | Failures on Q7, Q8, Q10 |
| After ingestion fix | 11/12 | Q7 and Q8 fixed |
| After `top_k` 5 -> 8 and chunker dedupe | 11/12 | Q10 now retrieved; remaining failure is a judge PARTIAL |

1. **Data cleaning beat retrieval tuning.** Print headers and page footers from the PDFs (timestamps, URLs, "Page x of y") had been chunked as content and were outranking real passages. Stripping them at ingestion fixed two failing questions with no change to the model or the search. Chunks: 120 -> 110.
2. **"Supported" is not "complete".** Q10 ("What is the HIE-CM for?") was judged SUPPORTED while missing the headline function, because the defining chunk mixed two topics (ABHA numbers and the HIE-CM definition), diluting its embedding, and it wasn't in the top 5. The judge checks faithfulness, not coverage. Raising `top_k` to 8 pulled the chunk in (rank 6) and the answer became complete.
3. **Chunker fix.** The last chunk of a page could be a near-duplicate of the previous one. A short tail is now absorbed into the final chunk. Chunks: 110 -> 103.

## Known limitations

- **Q10 still flagged PARTIAL.** The model adds one unsupported detail (revocation notification) beyond the cited text. Fix options: stricter prompt, or a post-generation faithfulness check.
- **Loose gold labels** for Q4 to Q9 (phrases match 4 to 11 chunks). Retrieval hit rate for these questions is therefore optimistic.
- **Small, easy golden set.** 12 questions is enough to catch regressions, not to claim accuracy. Next: add harder cases (multi-chunk answers, near-miss unanswerable, numeric details, paraphrased wording) and an `expected_points` completeness check.
- **No relevance cutoff yet.** On this set, top-1 distance separates answerable (about 0.30 or lower) from the in-domain unanswerable question (0.374), but the sample is too small to set a threshold.
- **Pure vector search.** Questions that quote a heading would likely benefit from hybrid keyword + vector search.

## Setup

_TODO: fill in against your actual repo._

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # DATABASE_URL, GEMINI_API_KEY, optional GEMINI_MODEL / GEMINI_FALLBACK_MODEL
python ingest.py          # clean, chunk, embed, load into pgvector
python ask.py "What is a Health Information Provider (HIP) in ABDM?"
python run_eval.py        # writes eval/results-<timestamp>.md and .json
```

## Repo layout

_TODO: confirm against actual tree._

```
ingest.py          clean, chunk, embed, load
ask.py             retrieve and generate with citations, timing and retry logic
run_eval.py        golden-set evaluation
eval/              questions.json, run reports, diagnostic scripts
data/              source PDFs and data/README.md (URLs)
docs/steps/        build notes, step by step
```

## Roadmap

- Web UI and cloud deployment
- Hybrid (keyword + vector) retrieval
- Larger golden set with completeness checks
- Agent step with tracing; model routing and per-request cost caps