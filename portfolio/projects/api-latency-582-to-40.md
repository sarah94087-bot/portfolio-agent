---
id: api-latency-582-to-40
type: project
title:
  en: "Cutting API latency from 582ms to 40ms"
  he: "שיפור זמן התגובה של ה-API מ-582ms ל-40ms"
aliases: ["latency", "performance", "API speed", "N+1", "keyset pagination", "edge pinning", "caching", "זמן תגובה", "ביצועים", "מהירות API", "דפדוף", "מטמון"]
period: "2026"
experience: ainsof-capital
role: "Sole engineer"
tech: [PostgreSQL, Supabase Edge Functions, Next.js, React]
tags: [performance, backend, databases]
metrics:
  - label: "API latency per request"
    before: "582ms"
    after: "40ms"
    how_measured: "Same endpoint, per request, before and after pinning the API to the database region. The tool and the date were not recorded."
  - label: "Records silently dropped by offset pagination"
    value: "3.2%"
    how_measured: "Found during live QA rounds on production. How the share was counted was not recorded."
architecture:
  components:
    - { id: ui, label: "Data center (Next.js)" }
    - { id: cache, label: "Caching: per request, process memo, Next data cache" }
    - { id: api, label: "Governance API (Edge Functions, pinned to the DB region)" }
    - { id: db, label: "PostgreSQL (Europe)" }
  edges:
    - { from: ui, to: cache, label: "deduplicated, batched reads" }
    - { from: cache, to: api, label: "cache miss" }
    - { from: api, to: db, label: "same region; keyset pagination" }
code_allowed: false
depth: full
related: [postgres-rls-backbone, governance-center-pwa]
answers:
  - "Has she done any performance work on a backend?"
  - "How did she find and fix a bug that lost data without any error?"
  - "איך היא הפכה API איטי למהיר?"
  - "מה היא עשתה כשחלק מהנתונים נעלמו בשקט?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # product and business domain are not named
---

## Problem

The governance API that the data center works against was slow. Each request on the same endpoint took 582ms.

The product and its business domain are not described here.

## Why it was hard

The slowness did not come from one place. It came from the distance between the API and the database, from repeated queries for the same data (N+1), and from fetches that ran one after another instead of together.

## My role

Sarah found and fixed the causes herself, as the sole engineer on the platform.

## Architecture

**Region pinning:** the API's Edge Functions were pinned to the database's region in Europe, so each request no longer crossed regions to reach the database.

**Fewer queries:** N+1 patterns were removed with React `cache()`, which deduplicates reads within a request, and sequential waves of fetches were merged into one batch.

**Three caching layers:** per request, a process-level memo, and the Next.js data cache.

**Connection pool:** when the connection pool was exhausted, requests retried instead of failing.

The work also covered SQL optimization and backend tuning.

## Decisions and alternatives

**Move the API to the database, not the other way round.** Rejected: adding caching alone and leaving the API in another region. Why: every cache miss would still pay the cross-region trip.

**Keyset pagination instead of offset.** Offset pagination stopped at 10,000 rows and dropped records silently; a keyset cursor reads every row.

## What broke

During live QA rounds on production, Sarah found that data was disappearing silently. The cause was offset pagination: it stopped at 10,000 rows and dropped 3.2% of the records without any error. She fixed it by moving to a keyset cursor.

## Results

Latency on the same endpoint went from 582ms to 40ms per request, and pagination no longer drops records.
