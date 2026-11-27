# Step 1: Setup (Nov 19 to Nov 24)

**Goal:** a working local environment that can reach the database and the model.

**Done**
- GitHub repo `rag-healthcare-qa`, Python venv, VS Code with Cline.
- Supabase project with the pgvector extension; table `documents` (source, page, chunk_index, content, embedding vector(384), created_at) with an HNSW cosine index and row-level security on.
- Gemini API key on the free tier, used through Google's OpenAI-compatible endpoint.
- `.env` (secrets), `.gitignore` and `.clineignore` so secrets never reach git or the AI assistant.
- `smoke_test.py` checks the database connection, that pgvector is enabled, and one model call.

**Problems hit and fixes**
- `KeyError: DATABASE_URL`: `.env` was in the wrong folder. Keep project files in the repo root.
- Do not move `pyvenv.cfg` out of `.venv`.
- Connection failures: brackets left around the password, and special characters (`#`, `$`, `@`) in it. Use letters and numbers only. The pooler username is `postgres.<project-ref>`.
- Stale system environment variable overriding `.env`: use `load_dotenv(override=True)`.
- Gemini 503 errors: handled in step 3 with retry and fallback.

**Lesson:** never print secrets while debugging; print yes/no checks instead.
