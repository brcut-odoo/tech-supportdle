"""Questions from model class definitions, raises and constraints."""
from collections import Counter

from .common import Scan, clean_message, model_distractor_pool, pick, question, stable_rng


def generate(scan: Scan) -> list[dict]:
    out: list[dict] = []
    imp = {m.name: m.importance for m in scan.modules.values()}
    owners = scan.model_owner

    defining = [m for m in scan.models if m.name and m.module == owners.get(m.name) and m.source]
    desc_count = Counter(m.description for m in defining if m.description)
    defining.sort(key=lambda m: (-imp.get(m.module, 0), m.name))

    # Description -> technical name
    n = 0
    for m in defining:
        if m.kind != "Model" or not m.description or desc_count[m.description] > 1 or n >= 160:
            continue
        if m.description.lower().replace(" ", ".") == m.name:  # too obvious
            continue
        rng = stable_rng("mname", m.name)
        diff = 1 if imp.get(m.module, 0) >= 40 and m.name.count(".") <= 1 else 2
        out.append(question(
            m.name, "model-name", diff,
            f"What is the technical model name for **{m.description}** records?",
            m.name, pick(m.name, model_distractor_pool(scan, m.name, m.module), rng, pool_head=16),
            f"`{m.cls}` in module `{m.module}` sets `_name = '{m.name}'` and "
            f"`_description = '{m.description}'`.",
            m.source))
        n += 1

    # Model -> defining module
    n = 0
    for m in defining:
        if m.kind != "Model" or n >= 90 or "." not in m.name:
            continue
        # skip when the prefix is a giveaway (module name == model prefix)
        if m.name.split(".")[0] == m.module:
            continue
        rng = stable_rng("mmod", m.name)
        cands = [d for d in scan.related_modules(m.module)]
        out.append(question(
            m.name, "model-module", 2,
            f"Which module defines the model `{m.name}`?",
            m.module, pick(m.module, cands, rng, pool_head=20),
            f"`{m.name}` is declared with `_name` in the `{m.module}` module ({m.cls}). Other modules may "
            "extend it through `_inherit`.",
            m.source))
        n += 1

    # Default _order
    orders = [m for m in defining if m.order and m.name in scan.familiar_models
              and m.order.strip() not in ("id", "id desc")]
    all_orders = sorted({m.order for m in orders})
    for m in orders[:70]:
        rng = stable_rng("order", m.name)
        out.append(question(
            m.name, "model-order", 3,
            f"What is the default `_order` of `{m.name}` ({m.description or m.cls})?",
            m.order, pick(m.order, all_orders, rng),
            f"`{m.cls}._order = '{m.order}'`. This is the default sort for searches and list views when "
            "no other order is given.",
            m.source))

    # Error message -> model
    msg_models = Counter()
    for r in scan.raises:
        msg = clean_message(r.message)
        if msg:
            msg_models[msg] += 1
    seen: set[str] = set()
    raises = sorted(scan.raises, key=lambda r: (-imp.get(r.module, 0), r.source))
    n = 0
    for r in raises:
        msg = clean_message(r.message)
        if not msg or msg_models[msg] > 1 or msg in seen or n >= 170 or r.model.endswith("mixin"):
            continue
        seen.add(msg)
        rng = stable_rng("raise", r.source)
        out.append(question(
            r.source, "error-origin", 2,
            f"A customer reports this `{r.exc}`. On which model is it raised?",
            r.model, pick(r.model, model_distractor_pool(scan, r.model, r.module), rng, pool_head=16),
            f"It is raised from a method of `{r.model}` in module `{r.module}`.",
            r.source, code=msg))
        n += 1

    # SQL / model constraints
    cmsgs = Counter(c.message for c in scan.constraints)
    for c in sorted(scan.constraints, key=lambda c: (-imp.get(c.module, 0), c.source))[:110]:
        msg = " ".join(c.message.split())
        if cmsgs[c.message] > 1 or "%" in msg or "{" in msg:
            continue
        rng = stable_rng("cons", c.source)
        out.append(question(
            c.source, "constraint", 2,
            "Saving a record fails with this database constraint message. Which model declares the constraint?",
            c.model, pick(c.model, model_distractor_pool(scan, c.model, c.module), rng, pool_head=16),
            f"`{c.model}` declares `models.Constraint(\"{' '.join(c.definition.split())}\", ...)` in "
            f"module `{c.module}`.",
            c.source, code=msg))
    return out
