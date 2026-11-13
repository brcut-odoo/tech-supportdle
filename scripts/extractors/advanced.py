"""Harder questions for experienced support engineers: where fields come from, related paths,
ondelete policies, company-dependent fields, access rights and record rules."""
import re
from collections import Counter, defaultdict

from .common import Scan, pick, question, stable_rng

ONDELETE = {
    "cascade": "deleting the target also deletes this record",
    "restrict": "deleting the target is refused while this record points to it",
    "set null": "the field is emptied when the target is deleted",
}
PERM_NAMES = ("Read", "Write", "Create", "Delete")


def _tokens(module: str) -> set[str]:
    return {t for t in module.split("_") if len(t) >= 3}


def _model_rank(scan: Scan):
    imp = {m.name: m.importance for m in scan.modules.values()}
    owners = scan.model_owner
    return lambda model: -imp.get(owners.get(model, ""), 0)


def generate(scan: Scan) -> list[dict]:
    out: list[dict] = []
    imp = {m.name: m.importance for m in scan.modules.values()}
    owners = scan.model_owner
    # Hard questions only cover models users meet in the UI (see Scan.familiar_models).
    familiar = scan.familiar_models
    model_rank = _model_rank(scan)

    defs = defaultdict(list)  # (model, field) -> [FieldDef]
    for f in scan.fields:
        defs[(f.model, f.name)].append(f)

    # ---- field-origin: which module adds this field to a core model?
    extenders = defaultdict(set)
    for m in scan.models:
        for parent in m.inherit:
            if m.name in (None, parent):
                extenders[parent].add(m.module)
    def well_known(module: str) -> bool:
        m = scan.modules.get(module)
        return bool(m) and (m.is_app or m.importance >= 5)

    def known_extenders(model: str) -> set[str]:
        return {m for m in extenders[model] if well_known(m)}

    cands = []
    for (model, name), fs in defs.items():
        mods = {f.module for f in fs}
        owner = owners.get(model)
        if len(mods) != 1 or model not in familiar or not owner or owner in mods:
            continue
        f = fs[0]
        if not f.extension or name.startswith("x_") or _tokens(f.module) & set(name.split("_")):
            continue
        if f.attrs.get("related") or len(known_extenders(model) - {f.module}) < 4:
            continue
        if not well_known(f.module):  # the answer should be a module people have heard of
            continue
        cands.append(f)
    cands.sort(key=lambda f: (model_rank(f.model), -imp.get(f.module, 0), f.model, f.name))
    per_model = Counter()
    for f in cands:
        if per_model[f.model] >= 10 or sum(per_model.values()) >= 160:
            continue
        per_model[f.model] += 1
        rng = stable_rng("forigin", f.model, f.name)
        others = sorted(known_extenders(f.model) - {f.module}, key=lambda m: (-imp.get(m, 0), m))
        label = f.attrs.get("string")
        label = f" (**{label}**)" if isinstance(label, str) and label else ""
        out.append(question(
            f"{f.model}.{f.name}", "field-origin", 3,
            f"`{f.model}` has a field `{f.name}`{label}. Which module adds it?",
            f.module, pick(f.module, others, rng, pool_head=12),
            f"`{f.model}` is defined in `{owners[f.model]}`. `{f.module}` extends it with `_inherit` and "
            f"declares `{f.name} = fields.{f.ftype}(...)`. Without `{f.module}` installed the field does not "
            "exist, which explains many 'Invalid field' errors in custom code and imports.",
            f.source))

    # ---- field-related: the related path of a field
    by_model_fields = defaultdict(list)
    for f in scan.fields:
        by_model_fields[f.model].append(f)
    related = [f for f in scan.fields if isinstance(f.attrs.get("related"), str) and "." in f.attrs["related"]
               and f.model in familiar]
    by_last = defaultdict(set)
    by_model = defaultdict(set)
    for f in related:
        by_last[f.attrs["related"].rsplit(".", 1)[1]].add(f.attrs["related"])
        by_model[f.model].add(f.attrs["related"])
    seen = set()
    related.sort(key=lambda f: (model_rank(f.model), -f.attrs["related"].count("."), f.model, f.name))
    n = 0
    for f in related:
        path = f.attrs["related"]
        last = path.rsplit(".", 1)[1]
        key = (f.model, f.name)
        if key in seen or len(defs[key]) > 1 or n >= 90:
            continue
        # Distractors share the answer's tail: same final field reached through another relation
        # of this model, or the same final field on other models' related paths.
        tail = path.split(".", 1)[1]
        hops = sorted({g.name for g in by_model_fields[f.model]
                       if g.ftype == "Many2one" and g.name != path.split(".", 1)[0]})
        pool = [f"{h}.{tail}" for h in hops] + sorted(by_last[last] - {path})
        if len(set(pool) - {path}) < 3:
            continue
        seen.add(key)
        n += 1
        rng = stable_rng("frel", f.model, f.name)
        out.append(question(
            f"{f.model}.{f.name}", "field-related", 3,
            f"`{f.model}.{f.name}` is a related field. What is its `related` path?",
            path, pick(path, pool, rng, pool_head=8),
            f"Declared in `{f.module}` as `fields.{f.ftype}(related='{path}')`. Its value follows that "
            "chain of fields, so a wrong value there usually means one link in the chain is wrong.",
            f.source))

    # ---- field-ondelete: explicit ondelete on Many2one
    m2o = [f for f in scan.fields if f.ftype == "Many2one" and f.attrs.get("ondelete") in ONDELETE
           and f.model in familiar and f.comodel and len(defs[(f.model, f.name)]) == 1]
    m2o.sort(key=lambda f: (model_rank(f.model), f.model, f.name))
    # Balance answers so "cascade" is not a safe guess: at most 25 per policy.
    per_val = Counter()
    picked = []
    for f in m2o:
        if per_val[f.attrs["ondelete"]] < 25:
            per_val[f.attrs["ondelete"]] += 1
            picked.append(f)
    for f in picked:
        val = f.attrs["ondelete"]
        rng = stable_rng("fondel", f.model, f.name)
        out.append(question(
            f"{f.model}.{f.name}", "field-ondelete", 3,
            f"`{f.model}.{f.name}` points to `{f.comodel}`. Which `ondelete` policy does it declare?",
            f"`{val}`", [f"`{v}`" for v in pick(val, [*ONDELETE, "set default"], rng)],
            f"`ondelete='{val}'`: {ONDELETE[val]}. A Many2one without `ondelete` defaults to `set null`, "
            "except when the field is required, which defaults to `restrict`.",
            f.source))

    # ---- company-dependent fields (the property_* ones would give themselves away)
    cdep = [f for f in scan.fields if f.attrs.get("company_dependent") is True and f.model in familiar
            and not f.name.startswith("property_")]
    cdep.sort(key=lambda f: (model_rank(f.model), f.model, f.name))
    for f in cdep[:60]:
        names_cd = {g.name for g in by_model_fields[f.model] if g.attrs.get("company_dependent")}
        same_type = [g.name for g in by_model_fields[f.model]
                     if g.name not in names_cd and g.ftype == f.ftype and not g.attrs.get("related")
                     and "compute" not in g.attrs]
        any_type = [g.name for g in by_model_fields[f.model]
                    if g.name not in names_cd and not g.attrs.get("related") and "compute" not in g.attrs]
        pool = list(dict.fromkeys(same_type + any_type))
        if len(pool) < 3:
            continue
        rng = stable_rng("fcdep", f.model, f.name)
        out.append(question(
            f"{f.model}.{f.name}", "company-dependent", 3,
            f"Which of these `{f.model}` fields is `company_dependent` (one value per company)?",
            f.name, pick(f.name, pool, rng, pool_head=10),
            f"`{f.name}` is declared with `company_dependent=True` in `{f.module}`. Its values are "
            "stored in a jsonb column keyed by company id, so it can differ between companies even "
            "though the record is shared.",
            f.source))

    # ---- access rights (ir.model.access.csv)
    model_by_ref = {f"model_{m.replace('.', '_')}": m for m in owners}
    group_names = {r.xmlid: r.fields.get("name") for r in scan.records if r.model == "res.groups"}
    union: dict[tuple[str, str], list] = {}
    first_src: dict[tuple[str, str], tuple] = {}
    everyone: dict[str, list] = {}
    for a in scan.accesses:
        model = model_by_ref.get(a.model_ref.split(".", 1)[-1])
        if not model or model not in familiar:
            continue
        if not a.group_ref:  # line for every user
            everyone[model] = [x or y for x, y in zip(everyone.get(model, [False] * 4), a.perms)]
            continue
        key = (model, a.group_ref)
        cur = union.setdefault(key, [False] * 4)
        union[key] = [x or y for x, y in zip(cur, a.perms)]
        first_src.setdefault(key, (a.source, a.module))

    # "Who can delete invoices?": for a model and a right, exactly one group's own ACL lines grant it
    # while at least three other groups have ACL lines on the model without it.
    groups_on = defaultdict(dict)  # model -> {group: perms}
    for (model, group), perms in union.items():
        groups_on[model][group] = perms
    acl = []
    for model, gp in groups_on.items():
        for idx in (3, 2, 1):  # Delete, Create, Write
            have = [g for g, p in gp.items() if p[idx]]
            lack = sorted(g for g, p in gp.items() if not p[idx])
            if len(have) == 1 and len(lack) >= 3 and not everyone.get(model, [False] * 4)[idx]:
                acl.append((model, idx, have[0], lack))
                break
    acl.sort(key=lambda x: (model_rank(x[0]), x[0]))
    for model, idx, group, lack in acl[:90]:
        right = PERM_NAMES[idx]
        rng = stable_rng("acl", model, idx)
        src, _module = first_src[(model, group)]
        name = group_names.get(group)
        out.append(question(
            f"{model}:{right.lower()}", "access-rights", 3,
            f"Several groups have `ir.model.access` lines on `{model}`. Whose own lines grant "
            f"**{right}**?",
            group, pick(group, lack, rng),
            f"Only `{group}`{f' ({name})' if name else ''} gets {right.lower()} access on `{model}` from its "
            "own ACL lines. Other users get it only by belonging to a group that implies this one, which "
            "is why the same error shows for some users and not others.",
            src))

    # ---- record rules
    rules = []
    for r in scan.records:
        if r.model != "ir.rule":
            continue
        dom = " ".join(r.fields.get("domain_force", "").split())
        dom = re.sub(r"\[\s+", "[", re.sub(r",?\s*\]", "]", re.sub(r"\(\s+", "(", re.sub(r",?\s*\)", ")", dom))))
        ref = r.refs.get("model_id", "")
        model = model_by_ref.get(ref.split(".", 1)[-1])
        if not dom or model not in familiar or len(dom) > 110 or "company_ids" in dom or not r.fields.get("name"):
            continue
        rules.append((r, dom, model))
    dom_count = Counter(d for _, d, _ in rules)
    all_doms = sorted(set(dom_count))
    same_model_doms = defaultdict(set)
    for _, d, m in rules:
        same_model_doms[m].add(d)
    rules.sort(key=lambda x: (model_rank(x[2]), x[0].source))
    for r, dom, model in rules[:120]:
        if dom_count[dom] > 1:
            continue
        # Most similar domains first (shared field names / operators), same model before others.
        words = set(re.findall(r"[\w.]+", dom))
        pool = sorted((d for d in all_doms if d != dom),
                      key=lambda d: (-(d in same_model_doms[model]), -len(words & set(re.findall(r"[\w.]+", d))), d))
        rng = stable_rng("rule", r.xmlid)
        groups = r.evals.get("groups", "")
        scope = "a global rule (no groups), so it applies to everyone and is intersected with other rules" \
            if not groups else "a group rule: rules of the user's groups are combined with OR"
        out.append(question(
            r.xmlid, "record-rule", 3,
            f"The record rule **{r.fields['name']}** on `{model}` enforces which domain?",
            f"`{dom}`", [f"`{d}`" for d in pick(dom, pool, rng, pool_head=8)],
            f"`{r.xmlid}` in `{r.module}` is {scope}.",
            r.source))
    return out
