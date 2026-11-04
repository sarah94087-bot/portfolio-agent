---
id: plant-health-classification
type: project
title:
  en: "Plant species and health classification with YOLO and CLIP"
  he: "זיהוי מיני צמחים ובריאותם עם YOLO ו-CLIP"
aliases: ["plant classification", "plant health", "plant species", "computer vision", "YOLO", "CLIP", "FastAPI", "AWS EC2", "GPU inference", "סיווג צמחים", "בריאות צמחים", "מיני צמחים", "ראייה ממוחשבת", "הסקה על GPU"]
period: "2025"
role: "Sole developer"
tech: [Python, YOLO, CLIP, FastAPI, AWS EC2]
tags: [computer-vision, ml, backend]
metrics: []
architecture:
  components:
    - { id: image, label: "Plant image" }
    - { id: yolo, label: "YOLO: plant detection" }
    - { id: clip, label: "CLIP: classification and health analysis" }
    - { id: api, label: "FastAPI backend on GPU" }
    - { id: ec2, label: "AWS EC2 GPU instance" }
  edges:
    - { from: image, to: api, label: "request" }
    - { from: api, to: yolo, label: "detect" }
    - { from: yolo, to: clip, label: "detected plants" }
    - { from: api, to: ec2, label: "deployed on" }
code_allowed: false
depth: overview
related: [weed-detection-pipeline, clip-embeddings-kafka]
answers:
  - "Has she deployed a model on a cloud GPU?"
  - "Has she worked with YOLO?"
  - "איזה ניסיון יש לה עם FastAPI?"
  - "היא עבדה עם AWS?"
review:
  approved: true
  approved_on: 2026-11-04
  publication_check: own-project
---

## Problem

Identify plants in an image, classify their species, and analyze their health, end to end, with inference fast enough to serve over an API.

## My role

Sarah built the whole system on her own.

## Architecture

An end-to-end computer vision pipeline: YOLO detects the plants, and CLIP classifies them and analyzes their health. A GPU-accelerated FastAPI backend serves the pipeline, optimized for low-latency inference, and the system is deployed on AWS EC2.

Only an overview of this project is recorded. For details beyond it, ask Sarah directly.

## Results

The system was built end to end and deployed on an AWS EC2 GPU instance.
