# SWE Bytes - Version-Controlled Recipe System: Architecture

This document outlines a pragmatic, Git-native architecture for a recipe system that supports iterations, inheritance, and composition (e.g., lasagna uses ragu and bechamel/cheese sauce).

## Goals

- Reproducible: a recipe resolved at a commit renders the same result.
- Composable: recipes can depend on other recipes (DAG, no cycles).
- Evolvable: clear lineage with iterations and history.
- Portable: plain files, human-diffable, minimal dependencies.
- Scriptable: a small CLI validates and renders recipes.

## Core Concepts

- Recipe: a named unit with metadata, ingredients, and steps.
- Lineage ID: stable UUID for the conceptual recipe across versions.
- Versioning:
  - `iteration`: big conceptual shifts (like semver major).
  - `version`: semver-style string, for smaller changes within an iteration.
  - Git tags recommended to mark released versions (e.g., `ragu@2.1.0`).
- Inheritance (Derivation): a recipe may extend a base recipe, overriding or patching metadata, ingredients, and steps.
- Composition (Dependencies): a recipe may declare `uses` dependencies on other recipes with version constraints, and optionally select or rename their steps.
- Parameters (Vars): names and values that allow scaling yields or changing options; evaluated at render time.

## Repository Layout

```
docs/
schema/
  recipe.schema.json
recipes/
  ragu/
    recipe.json
    README.md
    iterations/
      2025-09-02/
        recipe.json        # raw snapshot (as authored that day)
        resolved.json      # fully resolved snapshot
        NOTE.md            # optional notes for the day
  bechamel/
    recipe.json
    README.md
  lasagna/
    recipe.json
    README.md
tools/
  recipe.py  # CLI
lib/
  recipe_core.py  # shared core logic
server/
  app.py          # FastAPI API (serves Astro build too)
apps/web/
  ...             # Astro frontend (build to apps/web/dist)
```

Each recipe lives in its own directory with a single `recipe.json` (machine) and optional `README.md` (human narrative). Versioning is Git-native; the `recipe.json` contains `iteration` and `version` fields.

The top-level `recipe.json` inside `recipes/<slug>/` is the curated “magnum opus” copy. Daily snapshots are stored under `recipes/<slug>/iterations/YYYY-MM-DD/` to preserve exactly what was cooked/recorded that day. A snapshot includes both the raw recipe and a resolved copy for reproducibility.

## Data Model (JSON)

- id: stable slug (unique within repo).
- lineage_id: UUID, stable across versions and forks.
- name: human-friendly name.
- iteration: integer, conceptual iteration.
- version: semver string (e.g., "2.1.0").
- authors, tags, cuisine, difficulty: optional metadata.
- yield: { amount, unit } — canonical yield; scaling happens relative to this.
- vars: { name: value } — simple key/value parameters.
- ingredients: list of items
  - { id, name, quantity, unit, note?, from?: dependency_id, optional?: bool }
- steps: list of steps
  - { id, text, time?: { amount, unit }, tools?: [..], depends_on?: [step_id] }
- derives_from: optional reference to a base recipe
  - { id: recipe_slug, constraint?: "^2.0.0", step_patches?: [...], ingredient_patches?: [...] }
- uses: list of dependency references
  - { id: alias, recipe: recipe_slug, constraint?: "^1.2.0", include_steps?: [...], expose_ingredients?: true/false }

Notes:
- Ingredient and step IDs must be unique within a recipe after resolution.
- Dependencies form a DAG; cycles are invalid.

## Inheritance (Derivation) Rules

- Start with base recipe resolved at a version that satisfies the constraint.
- Apply patches in order:
  - Metadata: override scalar fields if present.
  - Ingredients: add/replace/remove by `id`.
  - Steps: add/replace/remove by `id`.
- IDs are the merge key; text comparisons are not required.

## Composition Rules

- For each `uses` dependency:
  - Resolve the dependency recipe.
  - Prefix imported step IDs with the dependency `id` alias to avoid collisions (e.g., `ragu.simmer`).
  - Optionally include a subset of steps; default is all.
  - Ingredients can be imported or just referenced by `from` so they remain attributed.
- Top-level recipe may reference dependency steps in its own steps via `depends_on`.

## Rendering (Resolution)

1. Load the target recipe by slug.
2. Resolve any `derives_from` chain first (base → leaf).
3. Resolve and embed `uses` dependencies (breadth-first; enforce DAG).
4. Apply parameter values and yield scaling to quantities.
5. Validate constraints (unique IDs, unit sanity, no cycles in steps).
6. Output a flattened representation for consumption (JSON/Markdown).

## Versioning & Lineage

- Keep all edits in Git. Use tags per release: `<slug>@<version>`.
- The `lineage_id` remains stable across iterations and versions.
- Forks should generate a new `lineage_id` and record `derives_from` with the upstream slug/version.

### Daily Iterations

- Use the CLI `snapshot` command to capture the day’s state:
  - `python tools/recipe.py snapshot <slug> --note "what changed"`
- This creates `iterations/YYYY-MM-DD/` with `recipe.json` (raw) and `resolved.json` (rendered). These are immutable records tied to that date.
- The curated top-level `recipe.json` continues to evolve toward the “magnum opus”.

## CLI (tools/recipe.py)

- `init <slug>`: scaffold a new recipe directory.
- `validate [<slug>|--all]`: validate against schema and rules.
- `render <slug> [--format json|md] [--yield <amount>]`: output a resolved recipe.
- `lineage <slug>`: show ancestry and dependency graph summary.
- `snapshot <slug> [--date YYYY-MM-DD] [--note TEXT]`: save the day’s raw + resolved snapshots.
- `list-iterations <slug>`: list all snapshot dates for a recipe.
- `render-iteration <slug> <date> [--format json|md] [--yield <amount>]`: render a specific day’s snapshot.

The initial implementation prefers zero third-party dependencies (JSON over YAML) to keep bootstrapping simple.

## Future Enhancements

- YAML support; Markdown rendering templates.
- Unit conversion and dimensional analysis.
- Rich patch language for derivations.
- Git integration helpers (diff, blame on fields).
- Web UI backed by the same core model.

## Deployment (Heroku + Astro)

- API: FastAPI app in `server/app.py` mounts the built Astro site from `apps/web/dist` at `/` and exposes JSON endpoints under `/api/...`.
- Frontend: Astro project in `apps/web/`, built during Heroku deploy (Node buildpack).
- Procfile runs `uvicorn` to serve both API and static site.

