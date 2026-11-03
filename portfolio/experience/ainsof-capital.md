---
id: ainsof-capital
type: experience
title:
  en: "AI Engineer at Ainsof Capital"
  he: "AI Engineer ב-Ainsof Capital"
aliases: ["Ainsof", "Ainsof Capital", "AI Engineer", "current job", "work experience", "data-governance platform", "ניסיון תעסוקתי", "מקום עבודה", "פלטפורמת ממשל נתונים"]
employer: "Ainsof Capital"
role: "AI Engineer"
period: "2026"
location: "Remote"
projects: [claims-trust-model, postgres-rls-backbone, api-latency-582-to-40, human-gated-translation, governance-center-pwa]
tags: [data-governance, full-stack, backend, ai]
answers:
  - "Where has she worked as an engineer?"
  - "What did she own in her last job?"
  - "מה היא עשתה ב-Ainsof Capital?"
  - "היא עבדה לבד או בצוות?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # employer named as on the CV; product and domain are not
---

## Context

AI Engineer at Ainsof Capital in 2026, working remotely. Sarah was the sole engineer of a production data-governance platform, and owned it end to end, from architecture design through launch.

The platform manages reliable information. Every piece of information has a source, a trust score, and a full record of who changed what and when. When two sources contradict each other, the system detects it and sends it to a person to check, instead of deciding on its own.

The product and its business domain are not described here.

## Responsibilities

- Designing the claims-based data model: every fact is sourced, trust-scored, auditable and checked for conflicts.
- Building the PostgreSQL layer: schemas, migrations, row-level security, triggers, RPC functions, optimistic concurrency and idempotency keys.
- Building the governance API that the data center works against.
- Performance work on the API.
- Building a machine translation pipeline on the Claude API, behind a human approval gate.
- Building the 28-screen governance center and the bilingual, offline-first travel PWA.

A separate team built the scraping that pulls data from websites, which is one of the sources of claims.

## Projects

- `claims-trust-model`: the claims-based data model, with trust, conflicts and human review.
- `postgres-rls-backbone`: the PostgreSQL layer, with three schemas, row-level security and safe concurrent writes.
- `api-latency-582-to-40`: cutting API latency from 582ms to 40ms per request.
- `human-gated-translation`: machine translation with the Claude API that never overwrites a person's edit.
- `governance-center-pwa`: the 28-screen governance center and the bilingual offline-first PWA.
