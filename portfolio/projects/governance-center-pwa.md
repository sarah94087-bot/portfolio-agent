---
id: governance-center-pwa
type: project
title:
  en: "A 28-screen governance center and a bilingual offline-first PWA"
  he: "מרכז ממשל של 28 מסכים ו-PWA דו-לשוני שעובד גם בלי אינטרנט"
aliases: ["admin dashboard", "data center", "PWA", "offline-first", "service worker", "RTL", "i18n", "Hebrew", "offline maps", "Next.js", "monorepo", "API contract", "Playwright", "mobile-first", "מסכי ניהול", "מרכז דאטה", "אופליין", "עברית מימין לשמאל", "דו-לשוני", "מפות אופליין", "חוזה API", "מובייל קודם"]
period: "2026"
experience: ainsof-capital
role: "Sole engineer"
tech: [Next.js, React, TypeScript, Tailwind CSS, Turborepo, pnpm, Serwist, Leaflet, MapLibre GL, PMTiles, next-intl, Vitest, Playwright, Vercel, PostHog]
tags: [frontend, pwa, i18n, testing, full-stack]
metrics:
  - label: "Admin screens in the data center"
    value: "28"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Public pages and routes"
    value: "about 20"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Typed API contract"
    value: "1,237 lines of TypeScript"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Test files (Vitest and Playwright)"
    value: "46"
    how_measured: "Counted in the repository at the end of the project, 19.7.2026"
  - label: "Commits"
    value: "782, from 20.5.2026 to 19.7.2026"
    how_measured: "Counted in the git history of the repository"
architecture:
  components:
    - { id: data_center, label: "Data center: 28 admin screens (Next.js 15)" }
    - { id: site, label: "Public bilingual PWA (Next.js 15)" }
    - { id: packages, label: "Shared packages: ui, db, auth, utils" }
    - { id: contract, label: "Typed API contract + mock adapter" }
    - { id: api, label: "Governance API" }
    - { id: sw, label: "Service worker (Serwist)" }
    - { id: maps, label: "Maps: Leaflet + OSM tiles, MapLibre + PMTiles" }
  edges:
    - { from: data_center, to: packages, label: "uses" }
    - { from: site, to: packages, label: "uses" }
    - { from: data_center, to: contract, label: "calls" }
    - { from: contract, to: api, label: "LIVE endpoints" }
    - { from: site, to: sw, label: "precache, CacheFirst" }
    - { from: sw, to: maps, label: "saved areas offline" }
code_allowed: false
depth: full
related: [claims-trust-model, postgres-rls-backbone, api-latency-582-to-40, human-gated-translation]
answers:
  - "Can she build a frontend, or is she backend only?"
  - "Has she built something that keeps working without internet?"
  - "איך היא בדקה שהאתר באמת עובד בלי רשת?"
  - "יש לה ניסיון עם עברית ו-RTL באתר אמיתי?"
review:
  approved: true
  approved_on: 2026-11-03
  publication_check: anonymized            # product and business domain are not named
---

## Problem

The platform needed two applications on top of the same data. An internal data center, where editors review incoming claims, resolve conflicts and publish. And a public bilingual, offline-first travel PWA in Hebrew and English that works on phones and desktops, and keeps working when the connection drops.

The product and its business domain are not described here.

## Why it was hard

Two very different applications, built by one person: a 28-screen governance center, and a bilingual PWA with right-to-left Hebrew that works offline.

## My role

Sarah built both applications end to end, together with the governance API they work against.

## Architecture

**Monorepo:** pnpm and Turborepo, with two applications and four shared packages (UI, database, auth, utilities). The UI package holds design tokens, a shared Tailwind preset and shared primitives, next to a written spec that lists forbidden patterns and documented exceptions.

**Data center:** 28 screens in Next.js 15 (App Router, React Server Components, Server Actions, streaming). The claims screen is the reference screen, and the others follow its design. It covers the review queue, automatic conflict detection, approve or reject in one click, the full history of every decision, the field catalog, connecting new sources, and reports. Switching tabs is instant, and panels open with streaming.

**API contract:** a typed TypeScript contract of 1,237 lines describes the whole API, with each endpoint marked `LIVE`, `PROPOSED` or `DEPRECATED`. A mock adapter implements the full state machine, so the UI was built and tested before the endpoints existed. Writes carry a version, and a stale version is re-read and retried.

**Public site:** search with filters, area pages, a planning wizard with a scoring engine Sarah wrote, maps, and a form for suggesting new entries, which arrive in the data center as drafts. English is the default, Hebrew is under `/he` with full RTL, the sitemap has `hreflang`, and each language has its own fonts through `next/font`.

**Offline:** a Serwist service worker with precache, CacheFirst with expiry, an offline page, and protection against races during sync. A user can save the map of a whole area to the device (tiles for zoom 11 to 15), and a saved plan survives losing the network. Vector maps use MapLibre with PMTiles: one static archive read through HTTP range requests, with no tile server. Routing and geocoding use OSRM and Nominatim, with no API keys.

**Mobile first:** every screen was built for the phone first. No interaction depends on hover, and tables fold into cards on narrow screens.

**Analytics:** PostHog hosted in the EU, with no cookies, typed events and no personal data.

## Decisions and alternatives

**Contract first, with a full mock.** The UI never waited for the server: it was built against the typed contract and the mock, and moved to live endpoints as they shipped.

**Static vector maps with PMTiles.** One static archive is served through HTTP range requests.

**Free routing and geocoding.** OSRM and Nominatim need no API keys.

## Results

Both applications went to production. Tests: 46 files, with Vitest for logic (the scoring engine, the state machine, translations, retry) and Playwright for full browser flows, including a dedicated suite that cuts the network to check that offline really works, and runs in a 390×844 mobile profile. Before every push, typecheck and all tests must pass. Sarah also ran manual QA rounds on production, screen by screen, while watching the Supabase and Vercel logs, and fixed the bugs they found, such as dead buttons and updates that were not saved because of version conflicts.
