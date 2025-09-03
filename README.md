# swe-bytes

Version-controlled recipes from the Instagram account @swe_bytes.

This repo contains a Git-native recipe system supporting iterations, inheritance, and composition (e.g., Lasagna uses Ragu and Bechamel). See `docs/ARCHITECTURE.md` for the full design.

## Quick start

Prereqs: Python 3.9+

- Validate all recipes:
  - `python tools/recipe.py validate --all`

- Render a recipe (Markdown or JSON):
  - `python tools/recipe.py render lasagna --format md`
  - `python tools/recipe.py render ragu --format json --yield 1000`

- Show lineage and dependencies:
  - `python tools/recipe.py lineage lasagna`

- Scaffold a new recipe:
  - `python tools/recipe.py init my-new-recipe`

## Daily Iterations vs Magnum Opus

- The curated “magnum opus” for each recipe lives at `recipes/<slug>/recipe.json`.
- Daily snapshots are saved under `recipes/<slug>/iterations/YYYY-MM-DD/` and include:
  - `recipe.json` (raw as authored that day)
  - `resolved.json` (fully resolved for reproducibility)
  - `NOTE.md` (optional notes)
- Commands:
  - `python tools/recipe.py snapshot ragu --note "tweaked simmer time"`
  - `python tools/recipe.py list-iterations ragu`
  - `python tools/recipe.py render-iteration ragu 2025-09-02 --format md`

## Layout

- `recipes/<slug>/recipe.json` — machine-readable recipe
- `recipes/<slug>/README.md` — human notes
- `schema/recipe.schema.json` — JSON schema (reference)
- `tools/recipe.py` — minimal CLI
- `lib/recipe_core.py` — shared core logic for CLI/API
- `server/app.py` — FastAPI API + static serving
- `apps/web/` — Astro frontend (builds to `apps/web/dist`)
- `docs/ARCHITECTURE.md` — architecture and concepts

## Deploy to Heroku

- This repo is ready for Heroku with Node + Python buildpacks (see `app.json`).
- The Node buildpack runs `npm --prefix apps/web ci && npm --prefix apps/web run build` and outputs `apps/web/dist`.
- The Python buildpack installs `requirements.txt` and `Procfile` runs `uvicorn` to serve the API and static site.

Steps:
- `heroku create <app-name>`
- `heroku buildpacks:add -i 1 heroku/nodejs`
- `heroku buildpacks:add -i 2 heroku/python`
- `git push heroku main`
- Open: `heroku open`
