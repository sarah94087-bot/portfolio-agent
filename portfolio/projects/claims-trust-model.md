---
id: claims-trust-model
type: project
title:
  en: "Claims-based data model with trust, conflicts and human review"
  he: "מודל נתונים מבוסס טענות, עם אמון, סתירות וסקירה אנושית"
aliases: ["claims model", "data governance", "trust score", "conflict detection", "human review queue", "audit trail", "מודל טענות", "ממשל נתונים", "ציון אמינות", "זיהוי סתירות", "תור ביקורת", "היסטוריית החלטות"]
period: "2026"
experience: ainsof-capital
role: "Sole engineer"
tech: [PostgreSQL, Supabase, Next.js, TypeScript]
tags: [data-governance, databases, backend]
metrics: []                                # no number with how_measured yet
architecture:
  components:
    - { id: sources, label: "External sources" }
    - { id: claims, label: "Claims (source + trust + status)" }
    - { id: conflict_trigger, label: "Conflict-detection trigger (DB)" }
    - { id: review, label: "Review queue (data center)" }
    - { id: audit, label: "Audit log" }
    - { id: catalog, label: "Published catalog" }
    - { id: site, label: "Public bilingual site" }
  edges:
    - { from: sources, to: claims, label: "ingested as claims" }
    - { from: claims, to: conflict_trigger, label: "contradicting claim" }
    - { from: conflict_trigger, to: review, label: "opens a conflict" }
    - { from: review, to: audit, label: "who, when, what, why" }
    - { from: review, to: catalog, label: "approve / publish" }
    - { from: catalog, to: site, label: "read" }
code_allowed: false
depth: full
related: [postgres-rls-backbone, human-gated-translation, governance-center-pwa]
answers:
  - "How did she make sure the facts shown to users were correct?"
  - "What happens in her system when two sources disagree?"
  - "איך המערכת שלה מחליטה איזה מידע מתפרסם לציבור?"
  - "מה קורה כשמקור חדש סותר מידע שכבר קיים?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # product and business domain are not named
---

## Problem

A platform for managing reliable information. Data about the places it covers came from many sources, was often out of date, and sources contradicted each other: one says a place is open, another that it closed a year ago. Showing wrong information to the public was not acceptable. So every piece of information could not simply be stored: it needed a source, a trust score, and a full record of who changed what and when. When two sources contradict each other, the system detects it and sends it to a person to check, instead of deciding on its own.

The product and its business domain are not described here.

## Why it was hard

Sources contradict each other, and a wrong fact on the public site was not acceptable. At the same time, a person could not check every fact by hand. The model had to keep people in charge of what is uncertain, while letting trusted sources through on their own.

## My role

Sarah designed and built the claims model end to end, including the governance API that the data center works against. A separate team built the scraping that pulls data from websites, which is one of the sources of claims.

## Architecture

Every fact about an entity is stored as a claim: it has an identified source, a trust score and a verification status. Nothing reaches the public site before it has gone through this process.

Trust is assigned per source. A source's claims are first checked by a person. After that, trust is updated automatically: a source that already has a high trust score gains more. A claim from a high-trust source is verified without a person; conflicts always go to a person.

A fact's path:

1. **Ingestion.** A new fact enters as a claim with its source and trust level. It does not touch the site.
2. **Conflict check.** If another source makes a contradicting claim, a database trigger opens a conflict automatically. Conflicts can involve three or more sources at once.
3. **Human decision.** An editor sees the versions side by side in the review queue and decides. The losing claim is marked `superseded`.
4. **Audit.** The decision is recorded: who, when, what exactly, and why.
5. **Publication.** The entity is published to the site, in both languages.

Claim states: `unverified` → `verified` / `conflict` / `superseded`. Entity lifecycle: `draft` → `review` → `approved` → `published`. A published entity can be reverted to draft, together with its linked contacts, without losing history. Duplicate entities can be merged.

A field catalog defines rules per field, such as who may verify it and whether machine translation is allowed, and these rules are enforced in the database. Places suggested by the public through an "add a place" form enter the data center as drafts, not directly on the site.

## Decisions and alternatives

**A person resolves conflicts, not the system.** When sources contradict each other, the conflict goes to a review queue. Rejected: letting the system pick a winner on its own, for example by trust score. Why: a wrong fact on the public site was not acceptable, and an automatic pick can be confidently wrong.

**Every fact is a claim, not a field value.** Each source's version is kept as a separate claim with its own source and trust. Rejected: one value per field, overwritten by the latest source. Why: overwriting loses where a value came from, and contradictions become invisible.

**Conflict detection in the database.** A trigger opens a conflict when a contradicting claim arrives. Rejected: detecting conflicts in application code. Why: a trigger catches every write path, including writes that do not go through the app.

**Losing claims are superseded, not deleted.** Why: the history stays complete, and a published entity can be reverted to draft without losing it.

## Results

The system is live in production, and no fact is published without a source. Usage numbers are not shared.
