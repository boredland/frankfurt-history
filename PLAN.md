# Frankfurt History Web App — Plan

## Goal

A static web app for exploring the Frankfurt History archive on an interactive map. Supports layer filtering, German/English, deep-linkable articles, turn-by-turn navigation between locations, and local TTS article reading via an in-browser ONNX engine.

## Tech Stack

| Concern | Choice | Why |
|---------|--------|-----|
| Framework | **Astro** + islands (Svelte) | Static-first, markdown-native via content collections, minimal JS by default |
| Map | **MapLibre GL JS** | Free Mapbox GL fork, vector tiles, clustering, no API key needed |
| Tiles | **MapTiler** free tier or self-hosted PMTiles | Vector basemap; PMTiles removes the tile server dependency entirely |
| Routing | **OSRM** (demo server) or **Valhalla** | Walking directions between POIs |
| TTS | **Piper ONNX** via `onnxruntime-web` | Offline, runs in browser, good German voices (~20 MB model) |
| Translation | **DeepL API** at build time | Pre-translate all markdown to English, ship both locales as static files |
| Styling | **Tailwind CSS** | Utility-first, small bundle |
| Hosting | **GitHub Pages** | Free, deploys from the same repo |

## Architecture

```
src/
├── content/
│   ├── de/                    ← generated from data/ at build time
│   │   ├── frankfurt-und-der-ns/
│   │   │   ├── 0017-hochbunker.md
│   │   │   └── ...
│   │   └── ...
│   └── en/                    ← DeepL-translated copies
│       └── ...
├── components/
│   ├── Map.svelte             ← MapLibre map with marker clusters
│   ├── ArticlePanel.svelte    ← slide-over panel for reading a POI
│   ├── LayerPicker.svelte     ← theme/filter toggles
│   ├── Navigation.svelte      ← walking route overlay + instructions
│   ├── TTSPlayer.svelte       ← play/pause/progress bar, Piper ONNX
│   └── LanguageToggle.svelte
├── layouts/
│   └── Layout.astro
├── pages/
│   ├── index.astro            ← full-screen map view
│   └── [lang]/[theme]/[slug].astro  ← deep-linkable article page
├── lib/
│   ├── tts.ts                 ← Piper ONNX wrapper (web worker)
│   ├── router.ts              ← OSRM fetch + GeoJSON route
│   └── i18n.ts                ← locale state, URL helpers
└── scripts/
    ├── translate.py           ← batch-translate markdown via DeepL
    └── geojson.py             ← build GeoJSON feature collections per theme
```

## Data Pipeline (build time)

1. **`archive.py`** — already done — fetches API data into `data/<theme>/<poi>.md` + images
2. **`scripts/geojson.py`** — reads all markdown frontmatter, emits one `<theme>.geojson` per theme with POI id, title, coordinates, categories, filters, and a slug for linking
3. **`scripts/translate.py`** — for each `data/<theme>/*.md`, calls DeepL to translate body text, writes translated copy to `src/content/en/<theme>/<slug>.md`; caches translations by content hash so re-runs only translate changed articles
4. Astro content collections load both `de/` and `en/` at build, generating static pages for every `/:lang/:theme/:slug` route

## Features

### 1. Map View (home page)

- Full-screen MapLibre map centered on Frankfurt (50.11, 8.68), zoom ~13
- POIs rendered as clustered circle markers, colored by theme
- Click cluster → zoom in; click marker → open article panel
- URL hash tracks map center/zoom so links preserve map state: `/#50.11,8.68,14z`

### 2. Layer Picker

- Sidebar or bottom sheet listing themes (Frankfurt und der NS, Neues Frankfurt, …)
- Each theme is a toggleable layer; toggling hides/shows its markers
- Within a theme, filters (e.g. "Orte der Verfolgung", "Orte des Wohnens") are sub-toggles
- State persisted in URL query params: `?layers=1,3&filters=2,5`

### 3. Article Panel

- Slide-in panel (right on desktop, bottom sheet on mobile)
- Shows: title, subtitle, thumbnail, full text, image gallery (lightbox on tap), audio/video embeds
- Deep link URL: `/de/frankfurt-und-der-ns/0017-hochbunker`
- Opening a deep link centers the map on that POI and highlights its marker
- "Navigate here" button activates routing
- "Read aloud" button activates TTS

### 4. Navigation

- User taps "Navigate here" on an article → browser geolocation prompt
- Fetch walking route from OSRM: `https://router.project-osrm.org/route/v1/foot/{lng},{lat};{poi_lng},{poi_lat}?geometries=geojson&steps=true`
- Draw route polyline on map, show step-by-step turn instructions in a bottom bar
- "Next location" suggests the nearest unvisited POI in the active layers

### 5. Language Toggle

- `de` / `en` toggle in header
- Switches URL prefix (`/de/...` ↔ `/en/...`), Astro serves the pre-translated static page
- Map UI labels (buttons, placeholders) from a small i18n dict
- Falls back to German if an English translation is missing

### 6. TTS (Text-to-Speech)

- Uses **Piper** ONNX voices running entirely in the browser via `onnxruntime-web`
- German voice: `de_DE-thorsten-medium` (~18 MB ONNX + ~1 MB config)
- English voice: `en_US-amy-medium` (~18 MB)
- Models lazy-loaded on first "Read aloud" tap, cached in IndexedDB
- Processing runs in a Web Worker to keep the UI responsive
- Player UI: play/pause, progress bar (by sentence), speed control (0.75×–1.5×)
- Sentences are split and synthesized one at a time for streaming playback

## URL Scheme

| URL | View |
|-----|------|
| `/` | Redirects to `/de/` |
| `/de/` | Map with all layers, German UI |
| `/en/` | Map with all layers, English UI |
| `/de/frankfurt-und-der-ns/0017-hochbunker` | Article + map centered on POI |
| `/de/?layers=1,3&filters=2,5` | Map with specific layers active |
| `/de/#50.09,8.67,15z` | Map at specific position/zoom |

## Build & Deploy

- Single GitHub Actions workflow: archive → translate → build → deploy
- `archive.py` runs first (weekly, or on push)
- `scripts/translate.py` runs next (only translates new/changed content)
- `astro build` produces a static site in `dist/`
- Deploy to GitHub Pages via `actions/deploy-pages`

## Milestones

1. **Map + articles** — Astro project, MapLibre map with POI markers from GeoJSON, click-to-open article panel, deep links
2. **Layers + filters** — theme/filter toggle UI, URL state sync
3. **Translation** — DeepL build-time translation script, EN content collection, language toggle
4. **Navigation** — geolocation, OSRM route fetch, route overlay, turn instructions
5. **TTS** — Piper ONNX integration, web worker, player UI, model caching
6. **Polish** — mobile layout, lightbox gallery, offline PWA shell, loading states

## Open Questions

- **Tile source**: MapTiler free tier (100k loads/month) vs self-hosted PMTiles on GitHub Pages (free, no rate limit, ~50 MB file)?
- **Historical map overlays**: the original app has Mapbox tilesets for historical maps. We could add georeferenced historical map overlays if the tile data is accessible, or skip this for v1.
- **Image hosting**: currently images are in Git LFS (~1 GB). For the web app, serve them directly from LFS or copy to the static build output?
