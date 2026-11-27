# Step 4: Automated eval (Nov 26, updated Nov 27)

**Goal:** replace manual answer-checking with a repeatable score, and understand how this scales beyond a proof of concept.

## What was built

- `eval/questions.json`: 12 questions (10 answerable, each with gold phrases; 2 unanswerable).
- `run_eval.py`: runs each question through the real pipeline (`ask()`), scores it, and writes `eval/results-<timestamp>.json` and `.md`.

## What a gold phrase is

A gold phrase is a short piece of text that must appear in the chunk that really answers a question (for example "Composition resource"). It is a way to say which chunks are the right ones without hard-coding chunk IDs, which change every time you re-ingest or change the chunk size.

- **How it is used:** before scoring a question, `run_eval.py` looks up the gold chunks with `content ILIKE '%phrase%'` in Postgres. ILIKE returns every chunk containing the phrase, so a question has a **list** of gold chunk IDs, not one.
- **What it measures:** retrieval, not answer accuracy. It tests whether the embedding model plus cosine ranking (plus your chunking) put the right chunk in the top 5.
- **What it is not:** it is not part of the live pipeline. The lookup only labels the right sources for the eval. The normal flow (embed, cosine search, prompt, Gemini) never sees gold phrases.
- **Open check:** when a question has several phrases, confirm in `run_eval.py` whether they are joined with OR or AND.

## Per-question checks

- **Retrieval hit:** any gold chunk in the top 5.
- **Gold rank:** position of the first gold chunk in the top 5.
- **Cited gold chunk:** the answer cites a passage that is a gold chunk.
- **Refusal:** correct refusal for unanswerable questions, no refusal for answerable ones.
- **Citation validity:** no citation numbers outside the passages shown.
- **Missing details:** numbers or acronyms in the answer that are absent from the cited text.
- **LLM judge:** SUPPORTED, PARTIAL or UNSUPPORTED against the retrieved passages.
- **Auto-pass:** answerable = retrieved a gold chunk and cited one and judged SUPPORTED; unanswerable = refused.

Separating the checks tells you where a failure comes from: no gold chunk retrieved means retrieval (chunking, embeddings, top_k); gold chunk retrieved but not cited or wrong means prompt or model.

## Baseline (Nov 26): 9 of 12 pass

- Retrieval hit 8/10, cited gold chunk 7/10, judge SUPPORTED 9/10, correct refusals 2/2, average generate time 2.3 s.
- Q7 (create a consent request): gold chunk ranked 5th and was not cited.
- Q8 (what a patient can do with a consent request) and Q10 (HIE-CM purpose): no gold chunk retrieved, yet judged supported.

## Weaknesses of gold phrases

- **Too loose:** Q4 to Q6 matched 8 to 12 chunks each. If many chunks count as gold, almost any retrieval "hits". A good phrase matches one to three chunks.
- **Too tight:** a phrase that differs from the PDF text (wording, line breaks) matches nothing, leaving no gold chunk.
- **Presence, not truth:** a chunk can contain the phrase without containing the answer.
- **Same author, same documents:** the labels are written by the same person who built the system, so they are not independent ground truth.
- **Judge bias:** the judge is the same model family as the answerer, so it is lenient. "Supported" does not mean complete or correct.
- **Small sample:** 12 questions demonstrates a method, not quality.

**Guard to add:** print the gold-chunk match count per question and flag any answerable question that matches more than 3 chunks or none.

## How this works in production (the key point)

The gold lookup running before each question is a convenience of the proof of concept. At scale you cannot list every question upfront, so the golden set is an **offline regression suite**, not a production monitor. It covers the important and tricky cases and is re-run before every change.

### Offline: the golden set

- Re-run on every change to chunking, embedding model, prompt or LLM version.
- Compare to the saved baseline: what improved, and what regressed.
- Example: a chunking change fixes Q7 but breaks Q3. Without the suite you would ship it unnoticed.
- At larger scale the gold labels are stored as passage text or document and page references, pinned chunk IDs per corpus version, or human or LLM relevance labels, instead of a phrase lookup at run time.

### Online: label-free checks on real traffic

Real users ask questions with no gold labels, so monitor signals that need none:

- citation validity (no citation to a passage that does not exist)
- refusal rate (a spike means retrieval or the corpus broke, or users ask new things)
- top-1 distance trend (drift away from the corpus)
- LLM faithfulness check of each answer against its cited passages
- latency, cost and error rates; user thumbs up or down if the UI has them

These are alarms, not accuracy scores.

### The loop: online failures become golden questions

1. Sample about 30 real queries a week: all thumbs-down, all UNSUPPORTED, all refusals, plus some random ones.
2. Label by hand: is it in scope, which passage answers it (copy a distinctive 2 to 4 word phrase), and what a correct answer says.
3. Add failures to the golden set, fix the cause, and prove the fix: the new question fails before and passes after, and all earlier questions still pass.
4. The set grows from what users actually ask.

```
real queries -> online checks (no labels) -> alarms
      |                                          |
      +-> weekly sample -> human labels -> new golden questions
                                                 |
change (chunking, model, prompt) -> offline run on golden set -> ship or fix
```

## What to say in the README and leadership note

"The golden set is a 12-question regression suite tied to specific passages through gold phrases. Online, label-free checks run on every query. The set grows from sampled production failures, and every fix is verified against it."

## Next

See step 5: diagnose Q7, Q8 and Q10, then test one retrieval fix at a time against this baseline.