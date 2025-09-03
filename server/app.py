from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional

from lib.recipe_core import (
    RECIPES_DIR,
    read_json,
    load_recipe,
    resolve_recipe,
    validate_unique_ids,
    validate_steps_dag,
    list_iterations,
    load_iteration,
    snapshot_recipe,
    promote_iteration,
)

app = FastAPI(title="swe-bytes recipes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/recipes")
def list_recipes(details: bool = False):
    slugs = []
    for child in RECIPES_DIR.iterdir():
        if (child / "recipe.json").exists():
            slugs.append(child.name)
    slugs = sorted(slugs)
    if not details:
        return {"recipes": slugs}
    out = []
    for slug in slugs:
        try:
            raw = load_recipe(slug)
            out.append({
                "slug": slug,
                "name": raw.get("name", slug),
                "tags": raw.get("tags", []),
                "yield": raw.get("yield", {}),
                "version": raw.get("version")
            })
        except Exception:
            out.append({"slug": slug})
    return {"recipes": out}


@app.get("/api/recipes/{slug}")
def get_recipe(slug: str):
    try:
        raw = load_recipe(slug)
        return raw
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")


@app.get("/api/recipes/{slug}/resolved")
def get_resolved(slug: str, target_yield: Optional[float] = Query(None, alias="yield")):
    try:
        resolved = resolve_recipe(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target_yield is not None:
        from lib.recipe_core import scale_ingredients

        base_yield = resolved.get("yield", {}).get("amount")
        resolved["ingredients"] = scale_ingredients(resolved.get("ingredients", []), base_yield, target_yield)
        if "yield" in resolved:
            resolved["yield"]["amount"] = target_yield
    return resolved


@app.get("/api/recipes/{slug}/validate")
def validate(slug: str):
    try:
        resolved = resolve_recipe(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")
    errs = []
    errs += validate_unique_ids(resolved.get("ingredients", []), "ingredient")
    errs += validate_unique_ids(resolved.get("steps", []), "step")
    errs += validate_steps_dag(resolved.get("steps", []))
    ok = len(errs) == 0
    return {"valid": ok, "errors": errs}


@app.get("/api/recipes/{slug}/iterations")
def get_iterations(slug: str):
    try:
        _ = load_recipe(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")
    dates = list_iterations(slug)
    out = []
    for d in dates:
        try:
            iter_data = load_iteration(slug, d)
            out.append({
                "date": d,
                "note": iter_data.get("note")
            })
        except Exception:
            out.append({"date": d})
    return {"iterations": out}


@app.get("/api/recipes/{slug}/iterations/{date}")
def get_iteration(slug: str, date: str):
    try:
        data = load_iteration(slug, date)
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Iteration not found")


@app.post("/api/recipes/{slug}/iterations")
def post_iteration(slug: str, payload: dict = Body(...)):
    day = payload.get("date")
    note = payload.get("note")
    from datetime import date as dt
    if not day:
        day = dt.today().isoformat()
    try:
        dest = snapshot_recipe(slug, day, note=note)
        return {"ok": True, "path": str(dest)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")


@app.post("/api/recipes/{slug}/promote")
def post_promote(slug: str, payload: dict = Body(...)):
    day = payload.get("date")
    if not day:
        raise HTTPException(status_code=400, detail="'date' is required to promote")
    try:
        raw = promote_iteration(slug, day)
        return {"ok": True, "recipe": raw}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Iteration not found")


# Optional: serve built Astro site if present
DIST = Path("apps/web/dist").resolve()
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="static")
