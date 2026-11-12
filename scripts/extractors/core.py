"""Questions from odoo/tools/config.py server options."""
import ast

from .common import Scan, fmt_num, numeric_distractors, pick, question, stable_rng

WELL_KNOWN = {"http_port", "gevent_port", "workers", "limit_time_real", "limit_time_cpu", "db_maxconn",
              "max_cron_threads", "limit_memory_hard", "limit_memory_soft", "smtp_port", "log_level",
              "limit_request", "db_template", "http_interface"}
MIB = 1024 * 1024


def _eval(node):
    try:
        return ast.literal_eval(node)
    except ValueError:
        pass
    if isinstance(node, ast.BinOp):
        l, r = _eval(node.left), _eval(node.right)
        if isinstance(l, (int, float)) and isinstance(r, (int, float)):
            if isinstance(node.op, ast.Mult):
                return l * r
            if isinstance(node.op, ast.Pow):
                return l ** r
            if isinstance(node.op, ast.Add):
                return l + r
    raise ValueError


def fmt(dest, v):
    if dest.startswith("limit_memory") and isinstance(v, int) and v % MIB == 0:
        return f"{v // MIB} MiB"
    return fmt_num(v)


def generate(scan: Scan) -> list[dict]:
    path = scan.root / "odoo" / "tools" / "config.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_option"):
            continue
        # unwrap PosixOnlyOption(...) etc.
        call = node.args[0] if node.args and isinstance(node.args[0], ast.Call) else node
        kw = {k.arg: k.value for k in call.keywords}
        if "dest" not in kw or "my_default" not in kw:
            continue
        dest = ast.literal_eval(kw["dest"])
        flags = [a.value for a in call.args if isinstance(a, ast.Constant) and str(a.value).startswith("--")]
        try:
            default = _eval(kw["my_default"])
        except ValueError:
            continue
        if isinstance(default, bool) or default in ("", None, [], ()) or isinstance(default, list):
            continue
        flag = flags[0] if flags else None
        name = f"`{flag}` (`{dest}`)" if flag else f"`{dest}` (config file only)"
        rng = stable_rng("cfg", dest)
        if isinstance(default, (int, float)):
            ans = fmt(dest, default)
            if dest.startswith("limit_memory"):
                dist = [f"{x} MiB" for x in (512, 1024, 1536, 2048, 2560, 3072, 4096) if f"{x} MiB" != ans]
                rng.shuffle(dist)
            else:
                dist = numeric_distractors(default, rng)
        elif dest == "log_level":
            ans, dist = default, ["debug", "warn", "error", "critical", "debug_sql"]
        elif isinstance(default, str) and len(default) < 40:
            ans = default
            others = {"db_template": ["template1", "postgres", "odoo"], "http_interface": ["127.0.0.1", "localhost", "::"]}
            dist = others.get(dest)
            if not dist:
                continue
        else:
            continue
        out.append(question(
            dest, "server-option", 1 if dest in WELL_KNOWN else 2,
            f"What is the default value of the server option {name}?",
            ans, pick(ans, dist, rng),
            f"Defined in `odoo/tools/config.py` with `my_default={ast.unparse(kw['my_default'])}`. You can "
            "override it on the command line or in the `[options]` section of the config file.",
            scan.rel(path, node.lineno)))
    return out
