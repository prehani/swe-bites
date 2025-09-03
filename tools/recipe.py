#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List

# Ensure repo root is importable for `lib` package
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.recipe_core import (
    REPO_ROOT,
    RECIPES_DIR,
    eprint,
    read_json,
    write_json,
    recipe_dir,
    recipe_file,
    load_recipe,
    resolve_recipe,
    validate_unique_ids,
    validate_steps_dag,
    scale_ingredients,
    iteration_dir,
    iteration_path,
    list_iterations,
    snapshot_recipe,
    load_iteration,
)


def cmd_init(args: argparse.Namespace) -> int:
    slug = args.slug
    d = recipe_dir(slug)
    if d.exists():
        eprint(f"Directory already exists: {d}")
        return 1
    tmpl = {
        "id": slug,
        "lineage_id": "REPLACE-WITH-UUID",
        "name": slug.replace("-", " ").title(),
        "iteration": 1,
        "version": "0.1.0",
        "authors": [],
        "tags": [],
        "yield": {"amount": 1000, "unit": "g"},
        "ingredients": [],
        "steps": []
    }
    write_json(recipe_file(slug), tmpl)
    (d / "README.md").write_text(f"## {tmpl['name']}\n\nDescribe the recipe.\n", encoding="utf-8")
    print(f"Initialized {d}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    slugs: List[str] = []
    if args.all:
        for child in RECIPES_DIR.iterdir():
            if (child / "recipe.json").exists():
                slugs.append(child.name)
    elif args.slug:
        slugs = [args.slug]
    else:
        eprint("Provide a slug or --all")
        return 1

    ok = True
    for slug in slugs:
        try:
            resolved = resolve_recipe(slug)
            errs: List[str] = []
            errs += validate_unique_ids(resolved.get("ingredients", []), "ingredient")
            errs += validate_unique_ids(resolved.get("steps", []), "step")
            errs += validate_steps_dag(resolved.get("steps", []))
            if errs:
                ok = False
                print(f"[INVALID] {slug}")
                for e in errs:
                    print(f"  - {e}")
            else:
                print(f"[VALID] {slug}")
        except Exception as e:
            ok = False
            print(f"[ERROR] {slug}: {e}")
    return 0 if ok else 2


def cmd_render(args: argparse.Namespace) -> int:
    slug = args.slug
    try:
        resolved = resolve_recipe(slug)
    except Exception as e:
        eprint(f"Failed to resolve: {e}")
        return 1

    target_yield = args.yield_amount
    if target_yield is not None:
        base_yield = resolved.get("yield", {}).get("amount")
        resolved["ingredients"] = scale_ingredients(resolved.get("ingredients", []), base_yield, target_yield)
        resolved["yield"]["amount"] = target_yield

    if args.format == "json":
        print(json.dumps(resolved, indent=2, ensure_ascii=False))
    else:
        # Minimal Markdown rendering
        lines: List[str] = []
        lines.append(f"# {resolved.get('name')} ({resolved.get('version')})")
        y = resolved.get("yield", {})
        lines.append(f"Yield: {y.get('amount')} {y.get('unit')}")
        lines.append("")
        lines.append("## Ingredients")
        for ing in resolved.get("ingredients", []):
            qty = ing.get("quantity")
            unit = ing.get("unit")
            src = f" [{ing['from']}]" if ing.get("from") else ""
            note = f" — {ing['note']}" if ing.get("note") else ""
            lines.append(f"- {qty} {unit} {ing.get('name')}{src}{note}")
        lines.append("")
        lines.append("## Steps")
        for i, st in enumerate(resolved.get("steps", []), start=1):
            time = st.get("time")
            t = f" ({time['amount']} {time['unit']})" if time else ""
            lines.append(f"{i}. {st['text']}{t}")
        print("\n".join(lines))
    return 0


def cmd_lineage(args: argparse.Namespace) -> int:
    slug = args.slug
    try:
        raw = load_recipe(slug)
    except Exception as e:
        eprint(str(e))
        return 1
    print(f"Recipe: {slug}")
    print(f"  Name: {raw.get('name')} | Iteration: {raw.get('iteration')} | Version: {raw.get('version')}")
    if raw.get("derives_from"):
        print(f"  Derives from: {raw['derives_from'].get('id')} {raw['derives_from'].get('constraint','')}")
    uses = raw.get("uses", []) or []
    if uses:
        print("  Uses:")
        for dep in uses:
            print(f"    - {dep['id']}: {dep['recipe']} {dep.get('constraint','')}")
    else:
        print("  Uses: none")
    return 0


# --- Iterations (daily snapshots) ---

def cmd_snapshot(args: argparse.Namespace) -> int:
    slug = args.slug
    try:
        raw = load_recipe(slug)
    except Exception as e:
        eprint(str(e))
        return 1

    day = args.date or date.today().isoformat()
    # Validate date format
    try:
        datetime.fromisoformat(day)
    except ValueError:
        eprint("Invalid date. Use YYYY-MM-DD.")
        return 1

    dest = snapshot_recipe(slug, day, note=args.note)
    print(f"Snapshot saved: {dest}")
    return 0


def cmd_list_iterations(args: argparse.Namespace) -> int:
    slug = args.slug
    dates = list_iterations(slug)
    if not dates:
        print("No iterations yet.")
    else:
        for s in dates:
            print(s)
    return 0


def cmd_render_iteration(args: argparse.Namespace) -> int:
    slug = args.slug
    day = args.date
    d = iteration_path(slug, day)
    try:
        iteration = load_iteration(slug, day)
        resolved = iteration["resolved"]
    except Exception as e:
        eprint(f"Failed to load iteration: {e}")
        return 1

    target_yield = args.yield_amount
    if target_yield is not None:
        base_yield = resolved.get("yield", {}).get("amount")
        resolved["ingredients"] = scale_ingredients(resolved.get("ingredients", []), base_yield, target_yield)
        resolved["yield"]["amount"] = target_yield

    if args.format == "json":
        print(json.dumps(resolved, indent=2, ensure_ascii=False))
    else:
        lines: List[str] = []
        lines.append(f"# {resolved.get('name')} ({resolved.get('version')}) — {day}")
        y = resolved.get("yield", {})
        lines.append(f"Yield: {y.get('amount')} {y.get('unit')}")
        lines.append("")
        lines.append("## Ingredients")
        for ing in resolved.get("ingredients", []):
            qty = ing.get("quantity")
            unit = ing.get("unit")
            src = f" [{ing['from']}]" if ing.get("from") else ""
            note = f" — {ing['note']}" if ing.get("note") else ""
            lines.append(f"- {qty} {unit} {ing.get('name')}{src}{note}")
        lines.append("")
        lines.append("## Steps")
        for i, st in enumerate(resolved.get("steps", []), start=1):
            time = st.get("time")
            t = f" ({time['amount']} {time['unit']})" if time else ""
            lines.append(f"{i}. {st['text']}{t}")
        print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recipe", description="Recipe system CLI")
    sub = p.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Scaffold a new recipe")
    p_init.add_argument("slug", help="recipe slug, e.g., ragu")
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser("validate", help="Validate recipes")
    g = p_val.add_mutually_exclusive_group(required=True)
    g.add_argument("slug", nargs="?", help="recipe slug")
    g.add_argument("--all", action="store_true", help="validate all recipes")
    p_val.set_defaults(func=cmd_validate)

    p_r = sub.add_parser("render", help="Render a resolved recipe")
    p_r.add_argument("slug", help="recipe slug")
    p_r.add_argument("--format", choices=["json", "md"], default="md")
    p_r.add_argument("--yield", dest="yield_amount", type=float, help="target yield amount (unit unchanged)")
    p_r.set_defaults(func=cmd_render)

    p_l = sub.add_parser("lineage", help="Show ancestry and dependencies")
    p_l.add_argument("slug", help="recipe slug")
    p_l.set_defaults(func=cmd_lineage)

    # Iterations
    p_snap = sub.add_parser("snapshot", help="Save daily snapshot of a recipe")
    p_snap.add_argument("slug", help="recipe slug")
    p_snap.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    p_snap.add_argument("--note", help="note to store in NOTE.md")
    p_snap.set_defaults(func=cmd_snapshot)

    p_list = sub.add_parser("list-iterations", help="List iteration dates for a recipe")
    p_list.add_argument("slug", help="recipe slug")
    p_list.set_defaults(func=cmd_list_iterations)

    p_ri = sub.add_parser("render-iteration", help="Render a specific iteration by date")
    p_ri.add_argument("slug", help="recipe slug")
    p_ri.add_argument("date", help="YYYY-MM-DD iteration date")
    p_ri.add_argument("--format", choices=["json", "md"], default="md")
    p_ri.add_argument("--yield", dest="yield_amount", type=float, help="target yield amount (unit unchanged)")
    p_ri.set_defaults(func=cmd_render_iteration)

    return p


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
