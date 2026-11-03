---
id: weed-detection-pipeline
type: project
title:
  en: "Weed detection pipeline on CPU with MobileNetV3"
  he: "צנרת לזיהוי עשבים שוטים על CPU, עם MobileNetV3"
aliases: ["weed detection", "computer vision", "image classification", "MobileNetV3", "UNet", "transfer learning", "PyTorch", "MinIO", "inference on CPU", "זיהוי עשבים", "עשבים שוטים", "ראייה ממוחשבת", "סיווג תמונות", "למידת העברה"]
period: "2025"
experience: vast-data-bootcamp
role: "Sole developer of this component, in a team project"
tech: [Python, PyTorch, MobileNetV3, MinIO, PostgreSQL, Docker]
tags: [computer-vision, ml, data-pipeline]
metrics:
  - label: "Inference time per image"
    value: "about 30-80ms"
    how_measured: "Per image, on CPU, on the machine the service ran on. The tool and the date were not recorded."
architecture:
  components:
    - { id: field, label: "Field images" }
    - { id: minio, label: "MinIO (object storage)" }
    - { id: detector, label: "weed-detector service (MobileNetV3, CPU, Docker)" }
    - { id: db, label: "PostgreSQL (results)" }
    - { id: dashboard, label: "Dashboard (plant health, PHI)" }
  edges:
    - { from: field, to: minio, label: "upload" }
    - { from: minio, to: detector, label: "fetch each image" }
    - { from: detector, to: db, label: "severity, coverage" }
    - { from: db, to: dashboard, label: "read" }
code_allowed: false
depth: full
related: [clip-embeddings-kafka]
answers:
  - "Has she trained a computer vision model herself?"
  - "Why would she pick a small model over a stronger one?"
  - "למה היא ויתרה על מודל סגמנטציה?"
  - "איך היא בדקה שהמודל לא עושה overfitting?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: employer-ok
---

## Problem

Images arrive from the field into object storage, and the system needs to tell, for each one, whether there are weeds and how severe they are. The results feed a dashboard that shows the health of the plants (PHI). The system had to run continuously on a machine with no GPU.

## Why it was hard

There was no local GPU, so a heavy model was not practical, neither to train nor to run continuously. The images come from field conditions, with noise, changing light and small leaves.

## My role

The team built a whole smart agriculture system. Sarah built this part, weed detection, entirely on her own, as one component of that system.

## Architecture

Images from the field land in MinIO. The `weed-detector` service fetches each image, runs MobileNetV3 on it, computes bounding boxes, severity and coverage, and writes the results to PostgreSQL. A dashboard reads these results to show the health of the plants (PHI).

**The model:** a pretrained MobileNetV3, with the last layer replaced by a new layer of two classes, weeds and no weeds. This keeps what the model already learned and trains only the final decision.

**Training and evaluation:** the data was split into train, validation and test sets. Loss and accuracy were tracked on every epoch to check for overfitting, and accuracy was measured on the test set at the end. The model was then also checked on new images from MinIO, to see that it generalizes to real data.

The service runs in Docker, on CPU.

## Decisions and alternatives

**MobileNetV3 classification instead of UNet segmentation.** Sarah started with UNet, a segmentation model that marks weeds pixel by pixel. It performed well, but without a local GPU, training took an unrealistic amount of time, and it is heavy to run. The task did not need a full pixel mask, only whether weeds are present and how severe they are. MobileNetV3 is built for running without a GPU: it is light, fast on CPU, keeps the Docker image lean, and was accurate enough for the task.

## Results

The model was accurate enough for an operational task, with high and stable results on the test set, and it held up on new images from MinIO. Each image takes about 30 to 80 milliseconds on CPU, so hundreds of images can run continuously without loading the system. Sarah presented the pipeline in a demo.
