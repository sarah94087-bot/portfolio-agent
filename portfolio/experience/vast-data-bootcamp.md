---
id: vast-data-bootcamp
type: experience
title:
  en: "Data / ML Engineering Bootcamp at VAST Data"
  he: "Bootcamp בהנדסת Data / ML ב-VAST Data"
aliases: ["VAST", "VAST Data", "bootcamp", "internship", "smart agriculture", "data engineering", "ML engineering", "בוטקאמפ", "התמחות", "חקלאות חכמה", "הנדסת נתונים"]
employer: "VAST Data"
role: "Data / ML Engineering Bootcamp (internship)"
period: "2025"
projects: [weed-detection-pipeline]
tags: [ml, computer-vision, data-pipeline]
answers:
  - "Has she worked with machine learning outside her studies?"
  - "What did she do at VAST Data?"
  - "מה היא עשתה ב-bootcamp של VAST?"
  - "היא עבדה בצוות או לבד ב-VAST?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: employer-ok
---

## Context

A Data / ML Engineering Bootcamp at VAST Data in 2025, as an internship. The team built a smart agriculture system. Sarah built the weed detection component entirely on her own, as one part of that system.

## Responsibilities

- An end-to-end weed detection pipeline with Python, PyTorch and MobileNetV3: fetching images from MinIO, running inference, and storing the results in PostgreSQL.
- An image embedding system with CLIP / ViT-mini, publishing vectors to Kafka and loading them into pgvector for similarity search and analytics.
- Containerizing backend and AI services in Docker, for reproducible development and deployment.

## Projects

- `weed-detection-pipeline`: weed detection on CPU with MobileNetV3, after UNet proved impractical without a GPU.
