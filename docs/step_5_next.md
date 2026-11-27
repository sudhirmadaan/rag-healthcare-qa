# Step 5: Diagnose and improve retrieval (next)

1. Freeze the baseline: rename the Nov 26 results file to `eval/baseline.md` and commit it.
2. Diagnose Q7, Q8 and Q10: check the gold chunks in Supabase and the retrieved top 5, and label each cause (chunking, retrieval, prompt, missing from the documents).
3. Test one fix at a time and re-run the 12 questions after each, recording before and after:
   - top_k 5 to 8
   - de-duplicate near-duplicate chunks
   - hybrid keyword plus vector search
   - sentence-aware chunking
   - distance cutoff around 0.4 for off-topic questions
4. Tighten the loose gold phrases so passes mean more.
5. Write the repo README and `data/README.md` (source URLs). Commit and push.

**Then (Phase 1 to 2):** one-page leadership note (RAG vs agents, evals, guardrails, cost, risk); web UI and one cloud deployment; architecture diagram and 2-minute demo video; Dec 16 gate check. Phase 2 adds the LangGraph agent step, MCP, an AI gateway and the AI delivery leadership write-up.
