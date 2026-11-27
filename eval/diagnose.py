import json
import sys
import os
from pathlib import Path

sys.path.insert(0, ".")

import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv(override=True)

from ask import get_embedder, retrieve

QUESTIONS_PATH = Path("eval/questions.json")


def main():
    question_ids = sys.argv[1:]
    if not question_ids:
        question_ids = list(range(4, 11))

    questions = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))
    q_map = {q["id"]: q for q in questions}

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)

        for qid_str in question_ids:
            qid = int(qid_str)
            if qid not in q_map:
                print(f"Question {qid} not found in questions.json")
                continue

            q = q_map[qid]
            print(f"\n=== Q{qid}: {q['question']} ===")
            print()

            chunks = retrieve(conn, q["question"])

            print("Top 5 retrieved chunks (id, source, page, distance, first 300 chars):")
            for i, c in enumerate(chunks, start=1):
                preview = c["content"][:300]
                print(
                    f"  [{i}] id={c['id']}, source={c['source']}, page={c['page']}, "
                    f"distance={c['distance']:.4f}"
                )
                print(f"      content: {preview}")
            print()

            gold_ids_set = set()
            for phrase in q.get("gold_phrases", []):
                rows = conn.execute(
                    "SELECT id FROM documents WHERE content ILIKE %s",
                    (f"%{phrase}%",),
                ).fetchall()
                gold_ids_set.update(r[0] for r in rows)

            gold_ids = sorted(gold_ids_set)

            print("Gold chunk ids with first 300 chars:")
            gold_chunks = []
            for gid in gold_ids:
                row = conn.execute(
                    "SELECT id, source, page, content FROM documents WHERE id = %s",
                    (gid,),
                ).fetchone()
                if row:
                    chunk_id, source, page, content = row
                    preview = content[:300]
                    gold_chunks.append(
                        {"id": chunk_id, "source": source, "page": page, "preview": preview}
                    )
                    print(f'  id={chunk_id}, source={source}, page={page}')
                    print(f"      content: {preview}")

            print()

            # Side-by-side comparison
            header = (
                f"{'#':<4}"
                f"{'Retrieved id':<15}"
                f"{'Retrieved src':<15}"
                f"{'Retrieved pg':<8} | "
                f"{'Gold id':<15}"
                f"{'Gold src':<15}"
                f"{'Gold pg':<8}"
            )
            print(header)
            print("-" * 75)

            for i in range(max(len(chunks), len(gold_chunks))):
                c = chunks[i] if i < len(chunks) else None
                g = gold_chunks[i] if i < len(gold_chunks) else None

                if c and g:
                    print(
                        f"{i+1:<4} {c['id']:<15} {c['source']:<15} {c['page']:<8} | "
                        f"{g['id']:<15} {g['source']:<15} {g['page']:<8}"
                    )
                elif c:
                    print(
                        f"{i+1:<4} {c['id']:<15} {c['source']:<15} {c['page']:<8} | "
                        f"{'':<15} {'':<15} {'':<8}"
                    )
                elif g:
                    print(
                        f"{i+1:<4} {'':<15} {'':<15} {'':<8} | "
                        f"{g['id']:<15} {g['source']:<15} {g['page']:<8}"
                    )
            print()

            retrieved_ids = [c["id"] for c in chunks]
            gold_in_retrieved = [gid for gid in gold_ids if gid in retrieved_ids]
            if gold_in_retrieved:
                print(f"Gold chunk ids found in top 5 retrieved: {gold_in_retrieved}")
            else:
                print("No gold chunk ids found in top 5 retrieved chunks.")


if __name__ == "__main__":
    main()