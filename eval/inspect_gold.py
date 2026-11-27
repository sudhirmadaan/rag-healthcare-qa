import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector

load_dotenv(override=True)


def main():
    questions = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)

        for q in questions:
            if not q.get("answerable"):
                continue

            print(f"\n=== Q{q['id']}: {q['question']} ===")
            phrases = q.get("gold_phrases", [])

            for phrase in phrases:
                # ILIKE search (case-insensitive)
                rows = conn.execute(
                    "SELECT id, source, page, content FROM documents WHERE content ILIKE %s",
                    (f"%{phrase}%",),
                ).fetchall()

                count = len(rows)
                flag = ""
                if count > 3:
                    flag = " *** TOO MANY MATCHES ( > 3 )"

                plural = "s" if count != 1 else ""
                print(f'\nPhrase: "{phrase}"{count} matching chunk{plural}{flag}')
                for row in rows:
                    chunk_id, source, page, content = row
                    preview = content[:200]
                    print(f'  id={chunk_id}, source={source}, page={page}')
                    print(f'    content preview: {preview}')
                if count == 0:
                    print('  (no matching chunks)')


if __name__ == "__main__":
    main()