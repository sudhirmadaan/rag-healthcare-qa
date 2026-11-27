import json
import os
import re
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv(override=True)

from ask import ask, generate  # noqa: E402

QUESTIONS = Path("eval/questions.json")
REFUSAL = "can't find that in the documents"

JUDGE_SYSTEM = (
    "You are a strict fact-checker. You are given numbered passages and an "
    "answer that cites them. Decide whether every claim in the answer is "
    "supported by the passages. Reply on the first line with exactly one word: "
    "SUPPORTED, PARTIAL or UNSUPPORTED. Then give one short sentence of reasoning. "
    "Use only the passages, never outside knowledge."
)


def find_gold_ids(conn, phrases):
    ids = set()
    for p in phrases:
        rows = conn.execute(
            "select id from documents where content ilike %s", (f"%{p}%",)
        ).fetchall()
        ids.update(r[0] for r in rows)
    return ids


def cited_numbers(answer: str) -> list[int]:
    return [int(n) for n in re.findall(r"\[(\d+)\]", answer)]


def missing_details(answer: str, cited_text: str) -> list[str]:
    """Numbers, versions and acronyms in the answer that are absent from the cited text."""
    body = re.sub(r"\[\d+\]", "", answer)
    details = set(re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)*", body))
    details |= set(re.findall(r"\b[A-Z][A-Z0-9]+\b", body))
    low = cited_text.lower()
    return sorted(d for d in details if d.lower() not in low)


def judge(answer: str, cited: list[tuple[int, dict]]):
    passages = "\n\n".join(f"[{n}] {c['content']}" for n, c in cited)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Passages:\n\n{passages}\n\nAnswer to check:\n{answer}"},
    ]
    text = generate(messages)["text"].strip()
    first = text.split()[0].strip(".:,*").upper() if text else ""
    verdict = first if first in {"SUPPORTED", "PARTIAL", "UNSUPPORTED"} else "UNKNOWN"
    return verdict, text


def main():
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    results = []

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        for q in questions:
            print(f"Q{q['id']}: {q['question']}")
            rec = ask(conn, q["question"])
            answer = rec["answer"]
            chunks = rec["chunks"]
            refused = REFUSAL in answer.lower().replace("\u2019", "'")

            gold_ids = find_gold_ids(conn, q.get("gold_phrases", []))
            retrieved_ids = [c["id"] for c in chunks]
            gold_ranks = [i + 1 for i, cid in enumerate(retrieved_ids) if cid in gold_ids]
            retrieval_hit = bool(gold_ranks)

            nums = cited_numbers(answer)
            valid = sorted({n for n in nums if 1 <= n <= len(chunks)})
            invalid = sorted({n for n in nums if not 1 <= n <= len(chunks)})
            cited = [(n, chunks[n - 1]) for n in valid]
            cited_gold = any(c["id"] in gold_ids for _, c in cited)

            verdict, verdict_text, missing = "N/A", "", []
            if q["answerable"] and not refused and cited:
                verdict, verdict_text = judge(answer, cited)
                missing = missing_details(answer, " ".join(c["content"] for _, c in cited))

            warnings = []
            if q["answerable"] and not gold_ids:
                warnings.append("no chunk matches gold_phrases: fix the phrase")
            if not q["answerable"] and gold_ids:
                warnings.append("documents may contain the answer: check this question")
            if q["answerable"] and not refused and not valid:
                warnings.append("answer has no valid citation")
            if invalid:
                warnings.append(f"invalid citation numbers {invalid}")

            if q["answerable"]:
                auto_pass = (
                    retrieval_hit and cited_gold and not refused and verdict == "SUPPORTED"
                )
            else:
                auto_pass = refused

            results.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "answerable": q["answerable"],
                    "answer": answer,
                    "gold_chunk_count": len(gold_ids),
                    "gold_rank": min(gold_ranks) if gold_ranks else None,
                    "retrieval_hit": retrieval_hit,
                    "cited_gold": cited_gold,
                    "refused": refused,
                    "judge": verdict,
                    "judge_reason": verdict_text,
                    "missing_details": missing,
                    "warnings": warnings,
                    "auto_pass": auto_pass,
                    "model": rec["model"],
                    "attempts": rec["attempts"],
                    "generate_s": rec["generate_s"],
                    "cost_usd": rec["notional_cost_usd"],
                    "sources": rec["sources"],
                }
            )
            time.sleep(2)  # be gentle with free-tier rate limits

    stamp = time.strftime("%Y%m%d-%H%M%S")
    Path(f"eval/results-{stamp}.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    lines = [f"# Eval run {stamp}", ""]
    for r in results:
        lines += [
            f"## Q{r['id']}: {r['question']}",
            f"- auto_pass: **{r['auto_pass']}**",
            f"- gold chunks in database: {r['gold_chunk_count']}; best gold rank in top 5: {r['gold_rank']}",
            f"- retrieval_hit={r['retrieval_hit']}  cited_gold={r['cited_gold']}  refused={r['refused']}",
            f"- judge: {r['judge']} {('- ' + r['judge_reason']) if r['judge_reason'] else ''}",
            f"- details in the answer not found in cited text: {r['missing_details']}",
            f"- warnings: {r['warnings']}",
            f"- answer: {r['answer']}",
            "- top sources: "
            + "; ".join(f"{s['source']} p.{s['page']} ({s['distance']})" for s in r["sources"]),
            "- your spot check (agree with the verdicts? yes / no): ",
            "",
        ]
    Path(f"eval/results-{stamp}.md").write_text("\n".join(lines), encoding="utf-8")

    ans = [r for r in results if r["answerable"]]
    unans = [r for r in results if not r["answerable"]]
    print("\n=== PER QUESTION ===")
    for r in results:
        print(
            f"Q{r['id']:>2} pass={str(r['auto_pass']):5} gold_chunks={r['gold_chunk_count']:>2} "
            f"gold_rank={r['gold_rank']} cited_gold={r['cited_gold']} judge={r['judge']} "
            f"missing={r['missing_details']} {r['warnings']}"
        )
    print("\n=== SUMMARY ===")
    print(f"auto pass:           {sum(r['auto_pass'] for r in results)}/{len(results)}")
    print(f"retrieval hit:       {sum(r['retrieval_hit'] for r in ans)}/{len(ans)}")
    print(f"cited a gold chunk:  {sum(r['cited_gold'] for r in ans)}/{len(ans)}")
    print(f"judge SUPPORTED:     {sum(r['judge'] == 'SUPPORTED' for r in ans)}/{len(ans)}")
    print(f"correctly refused:   {sum(r['refused'] for r in unans)}/{len(unans)}")
    print(f"avg generate time:   {sum(r['generate_s'] for r in results) / len(results):.1f}s")
    print(f"details file:        eval/results-{stamp}.md")


if __name__ == "__main__":
    main()