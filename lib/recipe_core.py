from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = REPO_ROOT / "recipes"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def read_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(p: Path, data: Dict[str, Any]):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def recipe_dir(slug: str) -> Path:
    return RECIPES_DIR / slug


def recipe_file(slug: str) -> Path:
    return recipe_dir(slug) / "recipe.json"


def load_recipe(slug: str) -> Dict[str, Any]:
    p = recipe_file(slug)
    if not p.exists():
        raise FileNotFoundError(f"Recipe not found: {p}")
    return read_json(p)


def parse_semver(v: str) -> Tuple[int, int, int]:
    try:
        parts = v.split("-")[0].split("+")[0].split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch
    except Exception:
        return 0, 0, 0


def satisfies_caret(version: str, constraint: str) -> bool:
    if not constraint or not constraint.startswith("^"):
        return True
    base = constraint[1:]
    vmaj, vmin, vpatch = parse_semver(version)
    bmaj, bmin, bpatch = parse_semver(base)
    if vmaj != bmaj:
        return False
    if (vmin, vpatch) < (bmin, bpatch):
        return False
    return True


def index_by_id(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: dict(item) for item in items}


def apply_patches(base_items: List[Dict[str, Any]], patches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = index_by_id(base_items)
    for patch in patches or []:
        op = patch.get("op", "replace")
        pid = patch.get("id")
        if not pid:
            continue
        if op == "remove":
            items.pop(pid, None)
        elif op in ("add", "replace"):
            current = items.get(pid, {"id": pid})
            new_item = dict(current)
            for k, v in patch.items():
                if k not in ("op",):
                    new_item[k] = v
            items[pid] = new_item
    return list(items.values())


def prefix_step_ids(steps: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    out = []
    for s in steps:
        ns = dict(s)
        old_id = s["id"]
        ns["id"] = f"{prefix}.{old_id}"
        if "depends_on" in s and isinstance(s["depends_on"], list):
            ns["depends_on"] = [f"{prefix}.{dep}" for dep in s["depends_on"]]
        out.append(ns)
    return out


def merge_unique_by_id(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = index_by_id(a)
    for item in b:
        out[item["id"]] = item
    return list(out.values())


def resolve_recipe(slug: str, _stack: Set[str] | None = None) -> Dict[str, Any]:
    if _stack is None:
        _stack = set()
    if slug in _stack:
        raise ValueError(f"Cycle detected in recipe dependencies: {' -> '.join(list(_stack) + [slug])}")
    _stack.add(slug)

    raw = load_recipe(slug)

    # Start from either base (if derives_from) or self
    base: Dict[str, Any]
    if raw.get("derives_from"):
        base_ref = raw["derives_from"]
        base_slug = base_ref["id"]
        base_recipe = resolve_recipe(base_slug, _stack)
        if not satisfies_caret(base_recipe.get("version", "0.0.0"), base_ref.get("constraint", "")):
            raise ValueError(f"Base recipe {base_slug} version {base_recipe.get('version')} does not satisfy {base_ref.get('constraint')}")

        ingredients = apply_patches(base_recipe.get("ingredients", []), base_ref.get("ingredient_patches", []))
        steps = apply_patches(base_recipe.get("steps", []), base_ref.get("step_patches", []))

        if raw.get("ingredients"):
            ingredients = merge_unique_by_id(ingredients, raw["ingredients"])
        if raw.get("steps"):
            steps = merge_unique_by_id(steps, raw["steps"])

        base = dict(base_recipe)
        base.update({
            "id": raw.get("id", base_recipe.get("id")),
            "lineage_id": raw.get("lineage_id", base_recipe.get("lineage_id")),
            "name": raw.get("name", base_recipe.get("name")),
            "iteration": raw.get("iteration", base_recipe.get("iteration")),
            "version": raw.get("version", base_recipe.get("version")),
            "authors": raw.get("authors", base_recipe.get("authors")),
            "tags": raw.get("tags", base_recipe.get("tags")),
            "yield": raw.get("yield", base_recipe.get("yield")),
            "ingredients": ingredients,
            "steps": steps,
            "uses": raw.get("uses", [])
        })
    else:
        base = dict(raw)

    uses = base.get("uses", []) or []
    resolved_steps = list(base.get("steps", []))
    resolved_ingredients = list(base.get("ingredients", []))
    for dep in uses:
        alias = dep["id"]
        dep_slug = dep["recipe"]
        dep_recipe = resolve_recipe(dep_slug, _stack)
        if not satisfies_caret(dep_recipe.get("version", "0.0.0"), dep.get("constraint", "")):
            raise ValueError(f"Dependency {dep_slug} version {dep_recipe.get('version')} does not satisfy {dep.get('constraint')}")

        dep_steps = dep_recipe.get("steps", [])
        if dep.get("include_steps"):
            keep = set(dep["include_steps"])
            dep_steps = [s for s in dep_steps if s["id"] in keep]
        dep_steps_prefixed = prefix_step_ids(dep_steps, alias)
        resolved_steps = resolved_steps + dep_steps_prefixed

        expose = dep.get("expose_ingredients", True)
        if expose:
            for ing in dep_recipe.get("ingredients", []):
                new_ing = dict(ing)
                new_ing["from"] = alias
                if not new_ing.get("id", "").startswith(f"{alias}."):
                    new_ing["id"] = f"{alias}.{new_ing['id']}"
                resolved_ingredients.append(new_ing)

    _stack.remove(slug)

    resolved = dict(base)
    resolved["steps"] = resolved_steps
    resolved["ingredients"] = resolved_ingredients
    return resolved


def validate_unique_ids(items: List[Dict[str, Any]], kind: str) -> List[str]:
    seen: Set[str] = set()
    errs: List[str] = []
    for item in items:
        iid = item.get("id")
        if not iid:
            errs.append(f"{kind} missing id: {item}")
            continue
        if iid in seen:
            errs.append(f"Duplicate {kind} id: {iid}")
        seen.add(iid)
    return errs


def validate_steps_dag(steps: List[Dict[str, Any]]) -> List[str]:
    errs: List[str] = []
    ids = {s["id"] for s in steps if "id" in s}
    for s in steps:
        for dep in s.get("depends_on", []) or []:
            if dep not in ids:
                errs.append(f"Step {s['id']} depends on unknown step {dep}")
    graph = {s["id"]: set(s.get("depends_on", []) or []) for s in steps}
    temp: Set[str] = set()
    perm: Set[str] = set()

    def visit(n: str):
        if n in perm:
            return
        if n in temp:
            raise ValueError(f"Cycle detected in steps at {n}")
        temp.add(n)
        for m in graph.get(n, []):
            visit(m)
        temp.remove(n)
        perm.add(n)

    try:
        for node in graph:
            if node not in perm:
                visit(node)
    except ValueError as e:
        errs.append(str(e))
    return errs


def scale_ingredients(ingredients: List[Dict[str, Any]], base_amount: float, target_amount: float) -> List[Dict[str, Any]]:
    if not base_amount or not target_amount or base_amount == target_amount:
        return ingredients
    factor = target_amount / base_amount
    out = []
    for ing in ingredients:
        new_ing = dict(ing)
        q = ing.get("quantity")
        if isinstance(q, (int, float)):
            new_ing["quantity"] = round(q * factor, 2)
        out.append(new_ing)
    return out


# --- Iterations helpers ---

def iteration_dir(slug: str) -> Path:
    return recipe_dir(slug) / "iterations"


def iteration_path(slug: str, date_str: str) -> Path:
    return iteration_dir(slug) / date_str


def list_iterations(slug: str) -> List[str]:
    d = iteration_dir(slug)
    if not d.exists():
        return []
    return sorted([p.name for p in d.iterdir() if p.is_dir()])


def snapshot_recipe(slug: str, day: str, note: Optional[str] = None) -> Path:
    raw = load_recipe(slug)
    dest = iteration_path(slug, day)
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "recipe.json", raw)
    try:
        resolved = resolve_recipe(slug)
        write_json(dest / "resolved.json", resolved)
    except Exception:
        # Best-effort snapshot; ignore resolve failures
        pass
    if note:
        (dest / "NOTE.md").write_text(note + "\n", encoding="utf-8")
    return dest


def load_iteration(slug: str, day: str) -> Dict[str, Any]:
    d = iteration_path(slug, day)
    raw_p = d / "recipe.json"
    resolved_p = d / "resolved.json"
    note_p = d / "NOTE.md"
    if not raw_p.exists():
        raise FileNotFoundError(f"Iteration not found: {raw_p}")
    out: Dict[str, Any] = {"date": day}
    out["raw"] = read_json(raw_p)
    out["resolved"] = read_json(resolved_p) if resolved_p.exists() else resolve_recipe(slug)
    if note_p.exists():
        out["note"] = note_p.read_text(encoding="utf-8").strip()
    return out


def promote_iteration(slug: str, day: str) -> Dict[str, Any]:
    d = iteration_path(slug, day)
    raw_p = d / "recipe.json"
    if not raw_p.exists():
        raise FileNotFoundError(f"Iteration not found: {raw_p}")
    raw = read_json(raw_p)
    # Write over magnum opus
    write_json(recipe_file(slug), raw)
    return raw
