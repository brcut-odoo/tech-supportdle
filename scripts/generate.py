#!/usr/bin/env python3
"""Generate trivia questions from an Odoo community checkout.

Usage: python3 scripts/generate.py [ODOO_SRC]
ODOO_SRC defaults to $ODOO_SRC or /home/odoo/odoo/dev/src/19.0/odoo (the community repo root).
Enterprise is intentionally never scanned.
"""
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extractors import advanced, core, data, manifests, models  # noqa: E402
from extractors.common import discover  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "src" / "lib" / "data" / "generated.json"


def validate(qs: list[dict]) -> list[str]:
    errors, ids = [], Counter(q["id"] for q in qs)
    for q in qs:
        if ids[q["id"]] > 1:
            errors.append(f"duplicate id {q['id']}")
        d = q["distractors"]
        if len(set(d)) < 3:
            errors.append(f"{q['id']}: only {len(set(d))} distractors")
        if q["answer"] in d:
            errors.append(f"{q['id']}: answer among distractors")
        if not q["question"].strip() or not str(q["answer"]).strip():
            errors.append(f"{q['id']}: empty text")
    return errors


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ODOO_SRC", "/home/odoo/odoo/dev/src/19.0/odoo")).resolve()
    if not (root / "odoo" / "release.py").exists():
        sys.exit(f"{root} does not look like an Odoo community checkout")
    scan = discover(root)
    print(f"scanned {len(scan.modules)} modules, {len(scan.models)} model classes, "
          f"{len(scan.raises)} raises, {len(scan.records)} XML records", file=sys.stderr)

    qs = []
    for gen in (manifests, models, data, core, advanced):
        qs += gen.generate(scan)
    # keep at most 6 distractors and dedupe ids deterministically
    seen, uniq = set(), []
    for q in qs:
        q["distractors"] = list(dict.fromkeys(q["distractors"]))[:6]
        if q["id"] not in seen:
            seen.add(q["id"])
            uniq.append(q)
    # Advanced audience: only medium and hard questions make it into the pool.
    qs = sorted((q for q in uniq if q["difficulty"] >= 2), key=lambda q: q["id"])
    errors = validate(qs)
    if errors:
        print("\n".join(errors[:50]), file=sys.stderr)
        sys.exit(f"{len(errors)} validation errors")

    release = {}
    exec((root / "odoo" / "release.py").read_text(), release)
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = None
    fam = Counter(q["family"] for q in qs)
    diff = Counter(q["difficulty"] for q in qs)
    meta = {"version": release.get("version"), "commit": commit, "modules": len(scan.modules),
            "families": dict(sorted(fam.items())), "difficulties": {str(k): v for k, v in sorted(diff.items())}}
    OUT.write_text(json.dumps({"meta": meta, "questions": qs}, indent=1, ensure_ascii=False) + "\n")
    for f, c in sorted(fam.items()):
        print(f"  {f:22} {c}", file=sys.stderr)
    print(f"wrote {len(qs)} questions ({dict(diff)}) to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
