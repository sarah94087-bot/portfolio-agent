# Portfolio Agent

A public AI agent that answers questions about Sarah Halevy's work, in Hebrew and English. Every claim cites its source, and a trace panel shows how each answer was built: the searches, the scores, the timing, the tokens and the model.

**[Try it](https://portfolio-agent-rosy.vercel.app/en)** · [Quality page](https://portfolio-agent-rosy.vercel.app/en/quality) · [How it works](https://portfolio-agent-rosy.vercel.app/en/how-it-works)

On the development question set, Recall@5 went from 0.76 with keyword search (50 questions) to 0.96 with hybrid search and reranking (58 questions). Each of those two steps was significant in a paired test.

**Status:** live, and still being hardened. The retrieval numbers here are development measurements. Answer quality with the real model has not been measured yet. [Status](#status) lists what is done and what isn't.

It runs on free tiers only, with no payment method on any service: Vercel, Neon, Groq and Langfuse.

Built with Claude Code as the coding partner. Sarah Halevy set the requirements and approved each spec chapter, knowledge-base record and architecture decision, and each ADR records that approval.

## 10-minute review path

| Minutes | Open | What to look for |
|---|---|---|
| 0–1 | [The live site](https://portfolio-agent-rosy.vercel.app/en) | Ask about a project, then open the trace panel |
| 1–3 | [Architecture](#architecture), then [`agent/loop.py`](backend/portfolio_agent/agent/loop.py) | The whole agent loop in one file, with no framework |
| 3–6 | [How retrieval was chosen](#how-retrieval-was-chosen) | A rule set before the results, and the experiment that went wrong |
| 6–8 | [`agent/citations.py`](backend/portfolio_agent/agent/citations.py) and [`test_citations.py`](backend/tests/test_citations.py) | A made-up citation never reaches the browser, even when it arrives split across tokens |
| 8–10 | [Run the tests](#run-it) | The first set of commands needs no keys, database or model |

The spec, ADRs and experiment report are in Hebrew. The tables, numbers and code paths still read well, and a browser translation covers the rest.

## Architecture

```mermaid
flowchart LR
  B["Browser"] --> WEB
  B -- "POST /api/chat, SSE back" --> API
  subgraph V["Vercel: one project, fra1"]
    WEB["Next.js<br/>chat, trace, quality page"]
    API["FastAPI<br/>guards, agent loop, tools,<br/>citation filter, e5-small (ONNX)"]
  end
  API --> DB[("Neon Postgres<br/>pgvector, pg_trgm<br/>knowledge, chats, quotas, cache")]
  API --> G["Groq<br/>answers and reranking"]
  API -. "traces" .-> L["Langfuse"]
  CI["GitHub Actions"] -- "migrate, load" --> DB
  CI -- "deploy after CI passes" --> V
```

Three structural rules:

1. **One service decides.** Guards, the agent and the tools all live in FastAPI. The web app only displays, and holds no keys.
2. **One database.** Neon holds the knowledge base, conversations, quotas and cache. At 56 passages, Redis or a search service would add parts with no benefit.
3. **One definition per tool.** [`tools/registry.py`](backend/portfolio_agent/tools/registry.py) holds each tool's schema and handler. The agent has two read-only tools today, `search_portfolio` and `get_project`.

**One request, in order:**

1. Length check, signed visitor cookie, and an atomic quota update in Postgres.
2. The agent loop runs for at most 4 rounds. The last round offers no tools, so there is always an answer.
3. The model writes an English search query. The code drops Sarah's name, runs hybrid search, reranks the top 10 and returns at most 5 passages and 3,000 tokens.
4. Before any token reaches the browser, a guard checks for the canary string, email addresses and phone numbers. Then the citation filter runs.
5. The answer is saved exactly as the visitor saw it. A retry with the same idempotency key replays it without calling the model.

**Citations are enforced while streaming.** The model marks a source as `[[chunk_id]]`. Plain text passes straight through. From `[[` to `]]` the server holds up to 200 characters and checks the id against the passages actually retrieved in this conversation. A valid id becomes a numbered citation, and an invalid one is deleted and logged. This proves a citation points at a retrieved passage. Whether that passage supports the claim is the judge's job ([ADR-0006](docs/adr/0006-streaming-citation-enforcement.md)).

## How retrieval was chosen

**The rule, written before any results:** pick the simplest setup that isn't significantly worse than the best one ([spec, section 5](docs/04-retrieval-design.md)). "Significantly" means a paired, question-by-question bootstrap whose 95% interval excludes zero. If keyword search had tied with everything else, keyword search would have shipped.

**The bar:** Recall@5 of at least 0.90 overall, and 0.85 for Hebrew and for Hebrew questions answered from English text.

**The data:** D1, a hand-labeled question set, written so the wording differs from the source text. Only its `dev` split was used. Numbers below are Recall@5, with 95% intervals in brackets.

| Stage | Question | Result | Decision |
|---|---|---|---|
| 1. Chunking | By heading, heading with context, sliding windows, or whole records? | Keyword search: 0.51, 0.52, 0.66, **0.76** | Whole records ([ADR-0010](docs/adr/0010-chunking.md)) |
| 2a. Embeddings | Which free model, on its own? | e5-small 0.77, e5-base 0.78, bge-m3 0.78, MiniLM 0.61, Qwen3 0.52 | None beats keyword search significantly |
| 2b. Hybrid | Does fusing keyword and vector search pay off? | **0.88 [0.80, 0.95]**, +0.12 over keyword, Hebrew 0.71 → 0.86 | Hybrid with RRF ([ADR-0011](docs/adr/0011-retrieval-method.md)) |
| 2c. Model size | Does a bigger model help inside hybrid? | e5-base −0.02, bge-m3 −0.03, neither significant | e5-small: 9 ms a query on a laptop, 135 MB, inside the function, no provider or quota ([ADR-0012](docs/adr/0012-embeddings-model.md)) |
| 3. Query rewriting | Search the visitor's words, or the model's English query? | 0.78, then **0.87 [0.79, 0.94]** after a fix in code | The model's query, with the name removed ([ADR-0013](docs/adr/0013-query-processing.md)) |
| 4. Reranking | Is an LLM reranker worth its tokens? | 0.89 → **0.96 [0.93, 0.99]**, +0.07 [+0.02, +0.14], 58 questions | Adopted ([ADR-0014](docs/adr/0014-reranking.md)) |

What the table doesn't show:

- **Rewriting first made search worse.** The model added "Sarah Halevy" to 36 of 50 queries. Every record is about her, so the name carried no signal and pulled the FAQ up the ranking. Prompting wasn't trusted to fix it: [`retrieval/query.py`](backend/portfolio_agent/retrieval/query.py) strips the name.
- **Stage 3 is a human call, on the record.** On D1 alone the rule picked the visitor's raw words. Sarah chose the rewritten query anyway, because raw words can't handle a follow-up like "and what was hardest there?", and D1 had no follow-ups then. Six were added before stage 4.
- **The best model isn't in production.** Gemini embeddings reached 0.90 alone and 0.94 in hybrid, and hybrid with e5-small isn't significantly behind Gemini alone. Gemini's free terms exclude apps serving users in the EEA, Switzerland or the UK, so it stayed a reference point ([ADR-0009](docs/adr/0009-no-free-gemini-in-production.md)).
- **Reranking has a stopping rule and a price.** The rule was written before run 1: no significant win, no runs 2 and 3. It improved 9 questions, hurt 1 and left 6 incomplete. It costs about 2,300 tokens a question, so about 27% fewer answers a day, and adds about 1.4 s at p50. If it fails, search falls back to the hybrid order.

**Limits of these numbers:**

- They come from `dev`. The 25 `test` questions are untouched, so there is no official score yet.
- Chunking's lead partly reflects more text per passage. At similar text volume the gap isn't significant.
- Stages 1 to 3 used 50 questions, where an interval is about ±0.1. That hides most differences between the open models.
- Part of run 2 was lost to a failed push. The averaging rule was changed in writing before run 3, and the report shows why the Recall@5 result is unaffected.
- The stored vectors were recalculated afterwards for stability ([ADR-0015](docs/adr/0015-embed-one-text-at-a-time.md)), and the knowledge base has since grown. Reranking hasn't been re-measured on the new state.

[The full report](docs/experiments/retrieval-2026-11-04.md) has every table and comparison. [`evals/results/`](evals/results) stores a score per question, so any comparison can be recomputed without rerunning it. `/quality` reads only from those files, and a test fails CI if the two differ.

## Other decisions

| Decision | Evidence | ADR |
|---|---|---|
| Own agent loop, no framework | Every step is streamed, filtered and traced, which is what a framework hides. The loop is tested with a scripted model, with no network | [0001](docs/adr/0001-own-agent-loop.md) |
| One agent, not several | 1–2 model calls an answer instead of 3–4, so about 72 answers a day instead of 23–31, before reranking | [0002](docs/adr/0002-single-agent.md) |
| Groq first, not Gemini as planned | Measured in a spike: Gemini 0 of 20 questions at 20 requests a day. Groq's main model 20 of 20 at 1,000 a day | [0005](docs/adr/0005-llm-providers.md) |
| Tools run in process | No extra network hop or second cold start | [0007](docs/adr/0007-tool-registry-in-process.md) |
| Next.js and FastAPI in one Vercel project | Spike confirmed SSE streams incrementally on the free plan | [0004](docs/adr/0004-vercel-services.md) |
| Embed one text at a time | Batches of 16 gave 0 of 56 identical vectors when load order changed. One at a time gave 56 of 56, and was faster (6.1 s vs 8.0 s) | [0015](docs/adr/0015-embed-one-text-at-a-time.md) |
| Browser tests on recorded streams | Tests can pause or cut a stream, at no quota cost, and any request leaving the site fails the test | [0017](docs/adr/0017-browser-tests-on-recorded-streams.md) |

The cost of running a model inside a free function is real: one cold start measured 9.0 s to the first embedding, and a warm request 0.7 s ([ADR-0012](docs/adr/0012-embeddings-model.md)).

## How it's tested

**Datasets** ([`evals/datasets/`](evals/datasets)): D1 has 96 questions (71 `dev`, 25 `test`, of which 58 `dev` questions are scored for retrieval), D2 has 36 attacks, D3 has 11 job descriptions, and D4 has 12 conversations.

**Statistics** ([`evals/stats.py`](evals/stats.py)): paired bootstrap for comparisons and Wilson intervals for rates. If an interval includes zero, no improvement is claimed. The thresholds are in [the evaluation spec, section 6](docs/03-evaluation-methodology.md).

| Layer | When | What it does | State |
|---|---|---|---|
| Backend | Every PR and push to `main` | `ruff`, publication check, `pytest` against pgvector | In [`ci.yml`](.github/workflows/ci.yml) |
| Web | Same | ESLint, unit tests, types, build, `npm audit` | In `ci.yml` |
| Browser | Same | Playwright on recorded streams, axe on every page and state | In `ci.yml` |
| T1 harness | Same | T1 cases through the real agent, tools and filters, with a scripted model and keyword search only, so it proves the plumbing and not answer quality | In `ci.yml` |
| Secrets | Same | gitleaks over the full history | In `ci.yml` |
| Live T1 | By hand | Real model plus a judge from a different model family | Workflow exists in [`groq.yml`](.github/workflows/groq.yml), **never run** |
| T2, T3 | Planned: nightly and at release | Full sets, and the official score | **Not in CI** |

Production deploys only through [`deploy.yml`](.github/workflows/deploy.yml), after CI passes on `main`: migrations, knowledge base load, deploy, smoke test, automatic rollback. [`retention.yml`](.github/workflows/retention.yml) runs the daily deletions promised on the privacy page.

Because the repo is public, CI also checks every tracked file against a private list of terms that must never be published ([`publication_check.py`](backend/portfolio_agent/publication_check.py)).

## Run it

You need Python 3.11 or later (CI uses 3.12) and Node 24. Docker is needed for the database tests and to run the app locally.

**Fastest check.** No Docker, keys or model files:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -e "backend[dev]"
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q ../evals
```

On Windows, use `.venv/Scripts/python` (`backend/.venv/Scripts/python` from the repo root). Tests that need Postgres or the model files skip themselves. On 2026-11-09, 335 passed and 91 skipped this way.

**All Python tests, with Postgres.** These run on Linux or macOS, or use the commands in the [`Makefile`](Makefile) directly:

```bash
make setup
make test
```

**Web tests,** from `apps/web`:

```bash
npm ci
npm test
npx playwright install chromium
npm run test:e2e
```

**Rebuild the quality page's numbers** from the stored results, from the repo root. It needs no model or database:

```bash
backend/.venv/bin/python evals/publish_quality.py
```

**Rerun an experiment.** From `evals/`, with `DATABASE_URL` pointing at a Postgres with the migrations and `EMBEDDING_MODELS_DIR` at the folder holding the model, run `../backend/.venv/bin/python -m retrieval.run_stage2 e5-small`. Stages 3 and 4 reuse the model output saved in `evals/datasets/`, and only new output needs a Groq key. The [report](docs/experiments/retrieval-2026-11-04.md) gives the command for each stage.

**Run the app.** It needs Docker and a free Groq key. The backend reads real environment variables and doesn't load `.env`, so export them first. [`.env.example`](.env.example) documents each one.

```bash
make db
export DATABASE_URL=postgresql://agent:agent@localhost:5432/agent
export EMBEDDING_MODEL_DIR="$PWD/models/multilingual-e5-small"
export GROQ_API_KEY=your-key
backend/.venv/bin/python -m portfolio_agent.retrieval.fetch_model
backend/.venv/bin/python -m portfolio_agent.load
make api
```

Then run `make web` in a second terminal and open <http://localhost:3000>.

## Status

**Working on `main`:** streamed chat in Hebrew and English, enforced citations, the trace panel, hybrid search with reranking, quotas and a kill switch, feedback, conversation delete, daily data deletion, and the `/quality`, `/how-it-works` and `/privacy` pages.

**Not done yet:**

| Area | What's missing |
|---|---|
| Answer quality | Live T1 has never run, and the judge hasn't been calibrated against human labels |
| Official score | T3 hasn't run. `/quality` shows `dev` retrieval numbers and says so |
| Deploy gates | CI doesn't run the real model yet, so answer-quality thresholds don't block a deploy |
| Security scanning | No OWASP ZAP or `pip-audit` in CI |
| Evals in CI | T2 isn't scheduled |
| Features | Job match is on a branch, not on `main`, and hasn't passed its gap-coverage gate. `/stats`, cards and diagrams, company links, the contact flow and the `/mcp` endpoint aren't built |
| Accessibility | Automated checks run in Chromium only. Safari, Firefox and real screen readers need manual testing |
| Docs | ADRs 0003 and 0008 aren't written, and ADR-0016 is on the job-match branch. The spec describes the planned system, so where it differs from this README, this README describes what exists |

## Where things are

```
apps/web/                 Next.js: pages, chat, trace panel, Playwright tests
backend/portfolio_agent/
  agent/                  loop, prompts, citation filter, stream guard
  tools/                  registry and the two tools
  retrieval/              keyword, vector, hybrid, rerank, Hebrew normalization
  providers/              one OpenAI-compatible client, routing and fallback
  guards/                 quotas and visitor identity
  db/                     conversations, feedback, response cache
backend/migrations/       numbered SQL
portfolio/                the knowledge base: one Markdown file per record
evals/                    datasets, experiments, stored results, statistics
docs/                     spec, ADRs, experiment reports
spikes/                   the first milestone's feasibility tests
```

Spec index: [`docs/README.md`](docs/README.md). Decisions: [`docs/adr/`](docs/adr). Threat model: [`docs/09-security-privacy.md`](docs/09-security-privacy.md). Free-tier limits and budget: [`docs/10-ops-and-costs.md`](docs/10-ops-and-costs.md). Milestones: [`docs/11-roadmap.md`](docs/11-roadmap.md).
