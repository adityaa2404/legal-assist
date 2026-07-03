---
title: La Space Worker
emoji: ⚙️
colorFrom: blue
colorTo: yellow
sdk: docker
dockerfile: Dockerfile.worker
app_port: 7860
pinned: false
---

Legal Assist AI — Celery worker (OCR, PII, HTOC, BM25 background processing). Talks to the same Redis broker and MongoDB as the API Space. See the [main repo](https://github.com/adityaa2404/legal-assist) for full documentation.

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
