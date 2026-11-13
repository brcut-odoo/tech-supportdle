"""Questions from XML data records and get_param defaults."""
import re
from collections import Counter, defaultdict

from .common import BASE_DEFAULTS, Scan, numeric_distractors, pick, question, stable_rng

UNITS = {"minutes": "minute", "hours": "hour", "days": "day", "weeks": "week", "months": "month"}
STD_INTERVALS = [(1, "minutes"), (5, "minutes"), (10, "minutes"), (15, "minutes"), (30, "minutes"),
                 (1, "hours"), (2, "hours"), (4, "hours"), (6, "hours"), (12, "hours"),
                 (1, "days"), (2, "days"), (1, "weeks"), (1, "months"), (3, "months")]


def interval(n: int, unit: str) -> str:
    return f"Every {UNITS[unit]}" if n == 1 else f"Every {n} {unit}"


def generate(scan: Scan) -> list[dict]:
    out: list[dict] = []
    imp = {m.name: m.importance for m in scan.modules.values()}
    recs = sorted(scan.records, key=lambda r: (-imp.get(r.module, 0), r.xmlid))

    # ---- crons
    crons = [r for r in recs if r.model == "ir.cron" and r.fields.get("name")]
    names = Counter(r.fields["name"] for r in crons)
    for r in crons:
        try:
            num = int(r.fields.get("interval_number") or r.evals.get("interval_number") or BASE_DEFAULTS["interval_number"])
        except ValueError:
            continue
        unit = r.fields.get("interval_type") or BASE_DEFAULTS["interval_type"]
        if num >= 999 or unit not in UNITS or names[r.fields["name"]] > 1:
            continue
        ans = interval(num, unit)
        rng = stable_rng("cron", r.xmlid)
        cands = [interval(n, u) for n, u in STD_INTERVALS]
        active = r.evals.get("active", r.fields.get("active", "True"))
        inactive = active.strip() in ("False", "0")
        out.append(question(
            r.xmlid, "cron", 2,
            f"How often does the scheduled action **{r.fields['name']}** run by default?",
            ans, pick(ans, cands, rng),
            f"`{r.xmlid}` is defined with interval_number={num} and interval_type='{unit}'"
            + (" and is **inactive** by default." if inactive else ".")
            + " Admins can change this under Settings > Technical > Scheduled Actions.",
            r.source))

    # ---- sequences
    seqs = [r for r in recs if r.model == "ir.sequence" and r.fields.get("prefix") and r.fields.get("name")]
    prefixes = sorted({r.fields["prefix"] for r in seqs} | {"SO", "INV/", "PO", "WH/OUT/", "BILL/", "MO/"})
    for r in seqs:
        rng = stable_rng("seq", r.xmlid)
        p = r.fields["prefix"]
        pad = r.fields.get("padding")
        out.append(question(
            r.xmlid, "sequence", 2,
            f"What is the default prefix of the **{r.fields['name']}** sequence"
            + (f" (`{r.fields['code']}`)" if r.fields.get("code") else "") + "?",
            p, pick(p, prefixes, rng),
            f"`{r.xmlid}` sets prefix `{p}`" + (f" with padding {pad}" if pad else "")
            + ". `%(year)s` and similar placeholders are filled in when the number is generated.",
            r.source))

    # ---- groups implied
    groups = [r for r in recs if r.model == "res.groups" and "implied_ids" in r.evals]
    all_groups = [g.xmlid for g in recs if g.model == "res.groups"]

    def qualify(ref: str, module: str) -> str:
        return ref if "." in ref else f"{module}.{ref}"

    implied_map = {g.xmlid: [qualify(x, g.module) for x in re.findall(r"ref\(['\"]([\w.]+)['\"]\)", g.evals["implied_ids"])]
                   for g in groups}

    def closure(x, seen=None):
        seen = seen or set()
        for i in implied_map.get(x, []):
            if i not in seen:
                seen.add(i)
                closure(i, seen)
        return seen

    for g in groups:
        implied = implied_map[g.xmlid]
        implied = [i for i in implied if i != "base.group_user"] or implied
        if not implied:
            continue
        rng = stable_rng("grp", g.xmlid)
        ans = rng.choice(sorted(implied))
        excl = closure(g.xmlid) | {g.xmlid} | {k for k in implied_map if g.xmlid in closure(k)}
        mod_groups = [x for x in all_groups if x.split(".")[0] == g.module]
        dist = pick(ans, mod_groups + all_groups, rng, exclude=excl, pool_head=len(mod_groups) + 5)
        if len(dist) < 3:
            continue
        out.append(question(
            g.xmlid, "group-implied", 2,
            f"Granting the group `{g.xmlid}` ({g.fields.get('name', '?')}) also grants which group directly?",
            ans, dist,
            f"`{g.xmlid}` has `implied_ids` -> {', '.join(f'`{i}`' for i in implied_map[g.xmlid])}. Implied "
            "groups are added automatically, which often explains 'why does this user see X?' questions.",
            g.source))

    # ---- mail templates -> module
    tmpls = [r for r in recs if r.model == "mail.template" and r.fields.get("name")]
    tn = Counter(t.fields["name"] for t in tmpls)
    for t in tmpls[:80]:
        if tn[t.fields["name"]] > 1:
            continue
        rng = stable_rng("tmpl", t.xmlid)
        out.append(question(
            t.xmlid, "mail-template", 2,
            f"Which module ships the email template **{t.fields['name']}**?",
            t.module, pick(t.module, scan.related_modules(t.module), rng, pool_head=15),
            f"The template is the XML record `{t.xmlid}`, whose prefix is the module name. Reinstalling or "
            "updating that module can reset it unless it is `noupdate`.",
            t.source))

    # ---- system parameter defaults
    xml_params = {r.fields.get("key") for r in scan.records if r.model == "ir.config_parameter"}
    defaults = defaultdict(set)
    first: dict[str, tuple] = {}
    for key, default, module, src in scan.get_params:
        defaults[key].add(repr(default))
        first.setdefault(key, (default, module, src))
    str_defaults = sorted({d for k, (d, *_ ) in first.items() if isinstance(d, str) and d and len(d) <= 20 and d.replace("_", "").isalnum() and not d.isdigit()})
    for key in sorted(first):
        default, module, src = first[key]
        if len(defaults[key]) > 1 or key in xml_params or isinstance(default, bool) or default in (None, "", [], {}):
            continue
        rng = stable_rng("param", key)
        if isinstance(default, (int, float)):
            ans = str(default)
            dist = numeric_distractors(default, rng)
        elif isinstance(default, str):
            if default.lstrip("-").isdigit():
                ans = default
                dist = numeric_distractors(int(default), rng)
            elif default in str_defaults:
                ans = default
                dist = pick(ans, str_defaults, rng)
            else:
                continue
        else:
            continue
        if len(dist) < 3:
            continue
        out.append(question(
            key, "config-param", 2,
            f"If the system parameter `{key}` is not set, what default value does the code use?",
            ans, dist,
            f"The code reads it with `get_param('{key}', {default!r})`. You can override it under Settings > "
            "Technical > System Parameters.",
            src))
    return out
