---
id: this-agent
type: project
title:
  en: "This agent: a public RAG agent that answers questions about Sarah, with sources and numbers"
  he: "הסוכן הזה: סוכן RAG ציבורי שעונה על שאלות על שרה, עם מקורות ומספרים"
aliases: ["this agent", "this project", "the portfolio agent", "RAG", "retrieval", "hybrid search", "BM25", "embeddings", "pgvector", "reranking", "evals", "evaluation", "golden set", "ADR", "הסוכן הזה", "הפרויקט הזה", "הסוכן שאני מדבר איתו", "אחזור", "חיפוש היברידי", "הערכה", "מדדי איכות"]
period: "2026"
role: "Sole engineer, built with Claude Code"
tech: [Python, FastAPI, Pydantic, PostgreSQL, Neon, pgvector, pg_trgm, multilingual-e5-small, ONNX Runtime, Groq, Next.js, TypeScript, Tailwind CSS, Vercel, PGlite, pytest, GitHub Actions]
tags: [ai-agents, rag, retrieval, evaluation, llm, backend, frontend]
metrics:
  - label: "Recall@5, chunking (C1 → C4, lexical retrieval R1)"
    before: "0.46"
    after: "0.76"
    how_measured: "D1 dev split, 50 questions with hand-labeled gold chunks; paired bootstrap, 10,000 resamples, 95% interval; docs/experiments/retrieval-2026-11-04.md, stage 1"
  - label: "Recall@5, retrieval method (lexical R1 → hybrid R3 with e5-small, on C4)"
    before: "0.76"
    after: "0.88"
    how_measured: "Same D1 dev split and bootstrap; stage 2 of the same report; difference significant (ADR-0011)"
architecture:
  components:
    - { id: web, label: "Next.js UI (Hebrew RTL and English)" }
    - { id: api, label: "FastAPI agent, SSE streaming" }
    - { id: rewrite, label: "Query written by the agent (Q1), name stripped" }
    - { id: lexical, label: "R1: BM25 + trigrams, RRF" }
    - { id: vector, label: "R2: e5-small embeddings, pgvector" }
    - { id: hybrid, label: "R3: RRF of R1 and R2" }
    - { id: db, label: "Neon Postgres: knowledge base chunks (C4: one per record)" }
    - { id: llm, label: "Groq LLM" }
    - { id: kb, label: "portfolio/ Markdown records, checked in CI" }
    - { id: evals, label: "Eval sets D1-D4 + experiment report" }
  edges:
    - { from: web, to: api, label: "question, SSE answer" }
    - { from: api, to: rewrite, label: "search_portfolio(query)" }
    - { from: rewrite, to: lexical }
    - { from: rewrite, to: vector }
    - { from: lexical, to: hybrid }
    - { from: vector, to: hybrid }
    - { from: hybrid, to: db, label: "top candidates" }
    - { from: api, to: llm, label: "answer with citations" }
    - { from: kb, to: db, label: "ingest" }
    - { from: evals, to: hybrid, label: "measured on D1" }
code_allowed: true
depth: full
related: [clip-embeddings-kafka, git-mcp-server, human-gated-translation]
answers:
  - "How does this agent work?"
  - "How did she measure retrieval quality?"
  - "Why hybrid search and not just embeddings?"
  - "איך הסוכן הזה בנוי?"
  - "איך היא בדקה שהשליפה טובה?"
  - "האם היא בנתה מערכת RAG בעצמה?"
review:
  approved: true
  approved_on: 2026-11-05
  publication_check: own-project
---

## Problem

A CV compresses years of work into a few lines that nobody can verify. "Built a RAG system" looks the same from someone who shipped one and someone who followed a tutorial, and most of Sarah's best work was done for employers, so it has no public link. This agent is one link where anyone can ask what matters to them about her experience, get an answer grounded in cited sources, and inspect the engineering behind it: the sources, the quality numbers, the decisions and the code.

## Why it was hard

- **Every claim must come from a source.** The agent may only say what the knowledge base says, and cite it, so retrieval quality is the product, not a detail.
- **Hebrew and English.** Most visitors ask in Hebrew, while the records are written in English. Plain keyword search fails across languages.
- **Zero cost, public traffic.** Only free tiers, and no free service whose terms forbid a public app (ADR-0009 rules out the free Gemini tier on the visitor path). Groq quotas cap how many experiments can run in a day.
- **Numbers, not impressions.** Every design choice is decided by a rule written before the experiment runs, on a labeled dataset, with confidence intervals.

## My role

Sarah owns the product, the specification and every decision: she wrote and approved the spec chapter by chapter, labeled the evaluation sets, and approved each ADR before it was accepted. She built the system with Claude Code as her coding partner, which is why the commits carry a Claude co-author line.

## Architecture

The knowledge base is a folder of Markdown records (`portfolio/`) with a strict frontmatter schema, checked in CI by a Pydantic validator, plus a publication check that blocks banned terms in any tracked file. Records are ingested into Neon Postgres, one chunk per record (C4), with `tsvector`, trigram and pgvector indexes. Postgres has no Hebrew dictionary, so text is normalized the same way at ingestion and at query time: final letters become regular letters, and niqqud and cantillation marks are removed. Embedding models run in process with ONNX Runtime (quantized, CPU).

The FastAPI agent streams answers over SSE. To search, it writes its own English query (Q1) through the `search_portfolio` tool; code strips Sarah's name from that query, because the name pulled generic records to the top. Retrieval is hybrid (R3): a lexical ranking (BM25 and trigrams, fused with RRF) and a vector ranking (multilingual-e5-small, cosine) fused again with RRF, k = 60. Each hit keeps its lexical, vector and fused scores so the trace panel can show why it was chosen. The LLM runs on Groq.

The UI is Next.js with Hebrew (RTL) and English routes, deployed with the backend in one Vercel project (ADR-0004).

Quality is measured on four datasets: D1 (96 retrieval questions with gold chunks, split dev/test, test never read), D2 (36 adversarial cases), D3 (11 job ads with labeled requirements, including injection attempts) and D4 (12 multi-turn conversations). Database tests run against PGlite in CI.

## Decisions and alternatives

**Chunking: one chunk per record (C4).** Rejected: a chunk per heading (C1), with or without a context header (C2), and grouped sections (C3). Why: C4 had the highest Recall@5 (0.76 vs 0.46 for C1), significantly better than all three, and the records are small enough to fit (ADR-0010).

**Hybrid retrieval (R3).** Rejected: lexical only (R1) and vectors only (R2). Why: R1 and e5 missed different questions, and fusing them reached 0.88, significantly better than either alone (ADR-0011).

**multilingual-e5-small for embeddings.** Rejected: e5-base and bge-m3 (no better, and slower: bge-m3 ~800 ms per query), MiniLM and Qwen3 (weaker), and Gemini (best on quality, 0.90, but its free tier is not allowed on the visitor path). Why: as good as the larger models in R3, and the smallest and simplest (ADR-0012).

**The agent writes the query, and code strips the name (Q1).** The first Q1 run scored worse than the raw question (0.78 vs 0.88), because the model added "Sarah Halevy" to 36 of 50 queries and that pulled the FAQ record to the top. Sarah chose to keep Q1 and strip the name in code, which brought it to 0.87 (ADR-0013).

## What broke

The first reranking run reported a median of 16.5 seconds per call, far too slow for a chat. The number was wrong, not the model: Groq's rate limit answered with 429, the client waited and retried, and the timer counted the waiting as part of the call. The fix was to record the wait separately from the call time. Measured that way, the real rerank call takes 1.5 seconds at the median and 1.9 at p95 (31 calls). Latency is now reported without rate-limit waits, and the waits are counted on their own.

## Results

On the D1 dev split, hybrid retrieval with one chunk per record finds the right sources in the top 5 for 0.88 of the labeled sources (Hebrew 0.86, cross-lingual 0.91). LLM reranking (R4) is under evaluation: its first run scored significantly higher, and by the stopping rule written before the run, two more runs decide whether it is adopted. The agent loop, the UI and the hardening are still being built (milestones M4-M6), and this record is updated as each one lands.
