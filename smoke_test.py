import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

# 1. Database check
import psycopg

try:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "select extname from pg_extension where extname = 'vector'"
        ).fetchone()
        print("DB connected. pgvector enabled:", bool(row))
except Exception as e:
    print("DB check FAILED:", type(e).__name__, str(e)[:200])
    sys.exit(1)

# 2. Gemini check (OpenAI-compatible endpoint)
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GEMINI_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    timeout=30,
    max_retries=0,
)

model = os.environ.get("GEMINI_MODEL")
print("GEMINI_MODEL =", repr(model))

if not model:
    print("\nNo GEMINI_MODEL set. Models your key can use:")
    for m in client.models.list():
        if "flash" in m.id.lower():
            print(" ", m.id)
else:
    try:
        print("Calling", model, "...")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say hello in five words."}],
        )
        print("Gemini replied:", resp.choices[0].message.content)
        print("Tokens in/out:", resp.usage.prompt_tokens, resp.usage.completion_tokens)
    except Exception as e:
        print("Gemini call FAILED:", type(e).__name__, str(e)[:400])