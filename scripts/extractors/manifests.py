"""Questions from __manifest__.py files."""
from collections import defaultdict

from .common import Scan, pick, question, stable_rng


def generate(scan: Scan, cap: int = 120) -> list[dict]:
    out: list[dict] = []
    mods = scan.by_importance
    apps = [m for m in mods if m.is_app]

    # Category of an application
    categories = sorted(c for c in {m.category for m in apps} | {m.category for m in mods[:150]} if not c.startswith("Hidden"))
    for m in apps:
        rng = stable_rng("cat", m.name)
        same_top = [c for c in categories if c.split("/")[0] == m.top_category]
        out.append(question(
            m.name, "manifest-category", 1,
            f"Which manifest category does the `{m.name}` app ({m.manifest.get('name')}) declare?",
            m.category, pick(m.category, same_top + categories, rng, pool_head=len(same_top) + 6),
            f"`{m.name}/__manifest__.py` declares `'category': '{m.category}'`, which decides where it "
            "is grouped in the Apps menu and in user access settings.",
            scan.rel(m.path / "__manifest__.py")))

    # Which one is an application?
    non_apps = [m.name for m in mods if not m.is_app][:80]
    for m in apps:
        rng = stable_rng("app", m.name)
        out.append(question(
            m.name, "manifest-application", 1,
            "Which of these modules is flagged `'application': True` and shows up as an App?",
            m.name, pick(m.name, non_apps, rng, pool_head=40),
            f"`{m.name}` ({m.manifest.get('name')}) sets `'application': True` in its manifest. The other "
            "modules are technical or bridge modules that are usually installed as dependencies.",
            scan.rel(m.path / "__manifest__.py")))

    # Direct dependency
    count = 0
    for m in mods:
        deps = [d for d in m.depends if d in scan.modules and d != "base"]
        if not deps or count >= cap:
            continue
        rng = stable_rng("dep", m.name)
        answer = rng.choice(sorted(deps))
        trans = scan.transitive_deps(m.name)
        # Distractors: modules m does NOT (transitively) depend on, and that don't depend on m.
        dependents = {n for n in scan.modules if m.name in scan.transitive_deps(n)}
        cands = [r for r in scan.related_modules(m.name) if r not in trans and r not in dependents]
        dist = pick(answer, cands, rng, pool_head=25)
        if len(dist) < 3:
            continue
        out.append(question(
            m.name, "manifest-depends", 2,
            f"Which of these modules is a direct dependency of `{m.name}`?",
            answer, dist,
            f"`{m.name}` depends on: {', '.join(f'`{d}`' for d in m.depends)}. None of the other choices "
            f"is a dependency of `{m.name}`, either direct or transitive.",
            scan.rel(m.path / "__manifest__.py")))
        count += 1

    # auto_install trigger lists -> which bridge module gets auto installed
    triggers = defaultdict(list)
    for m in mods:
        ai = m.manifest.get("auto_install")
        if isinstance(ai, list) and ai:
            triggers[tuple(sorted(ai))].append(m.name)
    bridges = [m for t, ms in triggers.items() if len(ms) == 1 for m in ms]
    by_name = scan.modules
    for name in bridges:
        m = by_name[name]
        trig = sorted(m.manifest["auto_install"])
        rng = stable_rng("auto", name)
        # plausible: other bridge modules sharing a trigger module, then other bridges
        share = [b for b in bridges if b != name and set(by_name[b].manifest["auto_install"]) & set(trig)]
        dist = pick(name, share + bridges, rng, pool_head=len(share) or 20)
        if len(dist) < 3:
            continue
        trig_txt = " and ".join(f"`{t}`" for t in trig)
        out.append(question(
            name, "manifest-autoinstall", 3,
            f"Which module is installed automatically as soon as {trig_txt} "
            f"{'are both' if len(trig) == 2 else 'are all' if len(trig) > 2 else 'is'} installed?",
            name, dist,
            f"`{name}` declares `'auto_install': {trig!r}`. A list makes it a bridge module that Odoo installs "
            "once every listed module is installed, whereas `True` means once all of its dependencies are.",
            scan.rel(m.path / "__manifest__.py")))
    return out
