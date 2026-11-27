# Step 2: Ingest documents (Nov 22)

**Goal:** turn PDFs into searchable chunks in Postgres.

**Script:** `ingest.py`

**What it does**
1. Reads every PDF in `data/` with pypdf, page by page.
2. Cleans the text (strips NUL characters, collapses whitespace).
3. Splits into chunks of about 1,200 characters with 200 overlap, breaking at a space and skipping chunks under 50 characters.
4. Embeds each chunk locally with `BAAI/bge-small-en-v1.5` (384 dimensions, normalised).
5. Deletes the old rows for that source and inserts the new ones.

**Result:** 5 documents became 120 chunks (52, 20, 15, 12, 21).

**Sources:** NRCeS FHIR adoption PDF, two NRCeS FHIR Implementation Guide pages, two ABDM sandbox pages. The official abdm.gov.in:8081 PDFs would not load, and the sandbox pages come from a community site.

**Known issue:** overlap creates near-duplicate chunks that can fill the top 5 with the same text.
