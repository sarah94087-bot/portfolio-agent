---
id: postgres-rls-backbone
type: project
title:
  en: "PostgreSQL backbone: schemas, row-level security and safe concurrent writes"
  he: "שכבת PostgreSQL: סכמות, הרשאות ברמת שורה וכתיבות בטוחות במקביל"
aliases: ["RLS", "row-level security", "database design", "migrations", "optimistic concurrency", "idempotency keys", "SECURITY DEFINER", "הרשאות ברמת שורה", "תכנון דאטהבייס", "מיגרציות", "נעילה אופטימית", "מפתחות idempotency"]
period: "2026"
experience: ainsof-capital
role: "Sole engineer"
tech: [PostgreSQL, Supabase, Row-Level Security]
tags: [databases, security, backend]
metrics:
  - label: "SQL migrations"
    value: "108 (about 9,800 lines)"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Database schemas"
    value: "3"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Core tables / RPC functions / RLS policies / triggers"
    value: "27 / 15 / 31 / 44"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
architecture:
  components:
    - { id: site, label: "Public site" }
    - { id: data_center, label: "Data center (admin UI)" }
    - { id: api, label: "Governance API" }
    - { id: rpc, label: "SECURITY DEFINER RPCs" }
    - { id: public_schema, label: "public schema" }
    - { id: admin_schema, label: "admin schema" }
    - { id: ingestion_schema, label: "ingestion schema" }
    - { id: triggers, label: "Triggers (audit, conflicts, field rules)" }
  edges:
    - { from: site, to: public_schema, label: "read, under RLS" }
    - { from: site, to: rpc, label: "controlled public writes" }
    - { from: data_center, to: api, label: "versioned writes + idempotency key" }
    - { from: api, to: admin_schema, label: "service role" }
    - { from: admin_schema, to: triggers, label: "every write" }
code_allowed: false
depth: full
related: [claims-trust-model, api-latency-582-to-40, governance-center-pwa]
answers:
  - "How did she keep public users away from internal data?"
  - "What stops two editors from overwriting each other's changes?"
  - "איך היא בנתה את ההרשאות בדאטהבייס?"
  - "מה קורה אצלה כשבקשה נכשלת באמצע ונשלחת שוב?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # product and business domain are not named
---

## Problem

One PostgreSQL database served three different audiences: the public site, the internal data center where editors review and approve data, and the ingestion of data from sources. Each needed different access, and public visitors could never reach internal data. Several editors could work on the same data at the same time, and a request could fail halfway and be sent again.

The product and its business domain are not described here.

## Why it was hard

Permissions had to be enforced in the database itself, not only in application code. At the same time, editors working in parallel must not silently overwrite each other, and a retried request must not be applied twice.

## My role

Sarah designed and built the database layer end to end: the schemas, all migrations, the RLS policies, the triggers, the RPC functions, and the governance API in front of it.

## Architecture

**Three schemas, separated by permission:** `public` for the site, `admin` for the data center, and `ingestion` for incoming data.

**Row-level security:** the public catalog is readable by anyone; admin tables are reachable only with the service role; personal data is limited to its owner through `auth.uid()`.

**Controlled public writes:** visitors never write to tables directly. Writes such as submitting a suggestion or a report go through `SECURITY DEFINER` RPC functions, and they arrive in the data center as drafts.

**Triggers:** an automatic audit trail on every table, automatic opening of a conflict when a contradicting claim arrives, and enforcement of the per-field rules in the field catalog.

**Safe concurrent writes:** every write carries `expected_version`, like `UPDATE ... WHERE version = expected`. A stale version returns 409; the client re-reads and retries quietly, so two editors do not overwrite each other. Idempotency keys stop a request that failed halfway and was sent again from being applied twice.

**Closing the database:** in July, direct database access was closed at the infrastructure level, and the data center moved to work only through the governance API.

Auth is Supabase Auth (magic link and OAuth), with JWTs verified locally against JWKS.

## Decisions and alternatives

**Closing direct database access, everything through the API.** Rejected: keeping direct access for the data center alongside the API. Why: one entry point means one place where permissions, versions and idempotency are enforced.

**Permissions in the database, with three schemas.** Access is separated at the database level, not only in application code.

**Public writes through `SECURITY DEFINER` RPCs.** Public writes are controlled: an RPC accepts a fixed shape and lands it as a draft.

**Optimistic concurrency with versions, plus idempotency keys.** Two editors do not overwrite each other, and a retried request is not applied twice.

## Results

The database layer is live in production. The data center works only through the governance API, editors working in parallel do not overwrite each other, and a retried request is not applied twice. Usage numbers are not shared.
