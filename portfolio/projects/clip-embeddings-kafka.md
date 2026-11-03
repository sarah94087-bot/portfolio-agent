---
id: clip-embeddings-kafka
type: project
title:
  en: "Image embeddings with CLIP, Kafka and pgvector for similarity search"
  he: "וקטורים לתמונות עם CLIP, Kafka ו-pgvector, לחיפוש דמיון"
aliases: ["embeddings", "image embeddings", "vector search", "similarity search", "CLIP", "ViT-mini", "pgvector", "Kafka", "anomaly detection", "וקטורים", "ייצוג וקטורי", "חיפוש דמיון", "חיפוש וקטורי", "תמונות דומות", "זיהוי חריגות"]
period: "2025"
experience: vast-data-bootcamp
role: "Sole developer of this component, in a team project"
tech: [Python, CLIP, ViT-mini, Kafka, PostgreSQL, pgvector]
tags: [embeddings, vector-search, computer-vision, data-pipeline]
metrics: []
architecture:
  components:
    - { id: images, label: "Incoming images" }
    - { id: embedder, label: "Embedding service (CLIP / ViT-mini)" }
    - { id: kafka, label: "Kafka" }
    - { id: pgvector, label: "PostgreSQL + pgvector" }
    - { id: requester, label: "Requesting user or service (e.g. QA)" }
  edges:
    - { from: images, to: embedder, label: "one vector per image, once" }
    - { from: embedder, to: kafka, label: "publish vectors" }
    - { from: kafka, to: pgvector, label: "load" }
    - { from: requester, to: pgvector, label: "similarity search, on request" }
code_allowed: false
depth: full
related: [weed-detection-pipeline]
answers:
  - "Has she built vector search before?"
  - "How would she find images similar to a new one?"
  - "יש לה ניסיון עם embeddings ו-pgvector?"
  - "למה היא לא מריצה חיפוש דמיון על כל תמונה שנכנסת?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: employer-ok
---

## Problem

The weed detector answers one fixed question about an image. This part turns each whole image into an embedding vector instead, so the system can ask open questions: how similar two images are, whether this is the same disease or the same phenomenon, and whether an image deviates from a set of normal ones.

## Why it was hard

Finding similar images had to be fast, without reprocessing the original images or reloading the model for every query.

## My role

The team built a whole smart agriculture system. Sarah built this part, image embeddings and similarity search, entirely on her own, as one component of that system.

## Architecture

An embedding model that captures visual similarity, CLIP / ViT-mini, turns each image into a vector of hundreds of numbers. The vectors are published to Kafka and loaded into PostgreSQL with pgvector.

When a new image arrives, the only automatic step is computing its vector and storing it. Similarity search runs only on request, from a user, another service, or the QA system: it takes an image's vector and compares it with the stored vectors to find the most similar images.

There are no folders or categories in pgvector. Similar images sit close to each other in the vector space, so groups form on their own, without a manual split.

## Decisions and alternatives

**Compute each embedding once and store it.** Rejected: computing embeddings at query time. Why: a stored vector lets search run without touching the original images or reloading the model.

**Separate ingestion from query.** Rejected: running a similarity search automatically for every incoming image. Why: ingestion stays a single cheap step, and search runs only when someone needs it.

**Vectors instead of another classifier.** A classifier answers one fixed question. Vectors work on any image and allow similarity, clustering, and spotting anomalies and recurring problems.

## Results

Every incoming image gets a vector once, and any image can then be compared with the whole collection on request. Together with the weed detector, the system can both tell what is in an image and how close it is to known cases. Sarah presented it in a demo.
