# Step 3: Ask questions with citations (Nov 24)

**Goal:** answer a question using only the stored documents, with citations.

**Script:** `ask.py`

**Who does what**
- Local embedding model: turns the question into a vector (with the bge query prefix).
- Postgres/pgvector: finds the top 5 chunks by cosine distance. No LLM involved.
- Code: numbers the chunks `[1]` to `[5]` and builds the prompt (system rules plus passages plus the question).
- Gemini: writes the answer and the `[n]` citations. The system prompt says to answer only from the passages and otherwise reply exactly "I can't find that in the documents."
- Code again: shows sources with distances and logs the call.

**Reliability:** primary `gemini-3.5-flash`, fallback `gemini-3.5-flash-lite`. Retries on 429, 5xx and timeouts, 3 attempts with 1/2/4 second backoff, then falls back. 60 second timeout.

**Logging:** `logs/calls.jsonl` records latency, tokens, model used, attempts and notional cost at Claude Haiku 5.5 list rates (about $0.0001 to $0.00016 per question; actual cost on the free tier is $0).

**Findings:** relevant questions landed at distance 0.17 to 0.25 and the off-topic question at about 0.58, so a cutoff near 0.4 is worth testing. Latency on the free tier swings a lot.
