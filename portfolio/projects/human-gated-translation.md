---
id: human-gated-translation
type: project
title:
  en: "Human-gated machine translation pipeline with the Claude API"
  he: "צנרת תרגום מכונה עם שער אנושי, על Claude API"
aliases: ["translation pipeline", "machine translation", "Claude API", "trust gate", "human in the loop", "i18n", "bilingual content", "צנרת תרגום", "תרגום מכונה", "שער אמון", "אדם בלולאה", "תוכן דו-לשוני"]
period: "2026"
experience: ainsof-capital
role: "Sole engineer"
tech: [Claude API, GitHub Actions, PostgreSQL]
tags: [ai, llm, i18n, automation]
metrics: []
architecture:
  components:
    - { id: cron, label: "GitHub Actions schedule (every 6 hours)" }
    - { id: worker, label: "Translation worker (no dependencies)" }
    - { id: providers, label: "Claude API" }
    - { id: catalog, label: "Field catalog (machine translation allowed?)" }
    - { id: overlay, label: "Translation overlay (machine / human / rejected)" }
    - { id: editor, label: "Human editor (data center)" }
  edges:
    - { from: cron, to: worker, label: "runs" }
    - { from: worker, to: catalog, label: "skips human-only fields" }
    - { from: worker, to: providers, label: "missing translations only" }
    - { from: worker, to: overlay, label: "writes as machine" }
    - { from: editor, to: overlay, label: "approve or fix -> human" }
code_allowed: false
depth: full
related: [claims-trust-model, governance-center-pwa]
answers:
  - "Has she put an LLM into a production workflow?"
  - "How did she stop automatic translation from undoing an editor's work?"
  - "איך היא שילבה את Claude API במערכת אמיתית?"
  - "מה קורה אצלה כשתרגום אוטומטי מתנגש בעריכה של בן אדם?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # product and business domain are not named
---

## Problem

The public site is bilingual, Hebrew and English, so every piece of content needs a translation. Not everything can be translated by a machine: a person's name needs transliteration, not translation, and some fields are sensitive enough that a machine must never translate them.

The product and its business domain are not described here.

## Why it was hard

The challenge was to run automatic translation without hurting the reliability of the content, so that the model's output never overwrites a person's edit.

## My role

Sarah designed and built the pipeline end to end.

## Architecture

A worker with no dependencies runs on a GitHub Actions schedule every 6 hours. It translates only what is missing, using the Claude API, and marks every result as a machine translation.

Translations live in an overlay with a status per field: `machine`, `human` or `rejected`. An editor approves or fixes a machine translation. Once a person has touched a field, the machine never overwrites it.

The field catalog defines, per field, whether machine translation is allowed. Fields marked `human_only` are skipped by the worker.

The workflow uses retry with exponential backoff, concurrency groups so two runs do not overlap, and a manual trigger with parameters.

## Decisions and alternatives

**Every model output goes through a human approval gate, and never overwrites a person's edit.** This is the principle the whole pipeline is built around.

## Results

The pipeline went to production as part of the data-governance platform Sarah built alone, end to end.
