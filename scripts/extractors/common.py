"""Shared scanning helpers for the trivia generator (community addons only)."""
from __future__ import annotations

import ast
import random
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from lxml import etree

SKIP_PREFIXES = ("test_", "l10n_", "hw_")
SKIP_CONTAINS = ("_test", "test_")
SKIP_DIRS = {"tests", "migrations", "upgrades", "static", "__pycache__", "populate"}

BASE_DEFAULTS = {"interval_number": "1", "interval_type": "months"}


def stable_rng(*parts: object) -> random.Random:
    return random.Random(":".join(str(p) for p in parts))


@dataclass
class Module:
    name: str
    path: Path
    manifest: dict
    importance: float = 0.0

    @property
    def category(self) -> str:
        return self.manifest.get("category", "Uncategorized")

    @property
    def top_category(self) -> str:
        return self.category.split("/")[0]

    @property
    def depends(self) -> list[str]:
        return list(self.manifest.get("depends", []))

    @property
    def is_app(self) -> bool:
        return bool(self.manifest.get("application"))

    def py_files(self):
        for p in sorted(self.path.rglob("*.py")):
            rel = p.relative_to(self.path)
            if any(part in SKIP_DIRS for part in rel.parts[:-1]):
                continue
            if p.name in ("__manifest__.py", "__init__.py"):
                continue
            yield p

    def data_files(self):
        for f in self.manifest.get("data", []):
            p = self.path / f
            if p.suffix == ".xml" and p.is_file():
                yield p


@dataclass
class Record:
    module: str
    xmlid: str
    model: str
    fields: dict[str, str]
    refs: dict[str, str]
    evals: dict[str, str]
    source: str


@dataclass
class ModelClass:
    module: str
    cls: str
    name: str | None
    inherit: list[str]
    description: str | None
    order: str | None
    kind: str  # Model / TransientModel / AbstractModel
    source: str

    @property
    def model(self) -> str | None:
        return self.name or (self.inherit[0] if self.inherit else None)


@dataclass
class Raise:
    module: str
    model: str
    exc: str
    message: str
    source: str


@dataclass
class Constraint:
    module: str
    model: str
    message: str
    definition: str
    source: str


@dataclass
class Scan:
    root: Path  # the community checkout, e.g. .../19.0/odoo
    modules: dict[str, Module] = field(default_factory=dict)
    models: list[ModelClass] = field(default_factory=list)
    raises: list[Raise] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    get_params: list[tuple[str, object, str, str]] = field(default_factory=list)  # key, default, module, source
    records: list[Record] = field(default_factory=list)

    def rel(self, p: Path, line: int | None = None) -> str:
        s = str(p.relative_to(self.root.parent))
        return f"{s}:{line}" if line else s

    @cached_property
    def by_importance(self) -> list[Module]:
        return sorted(self.modules.values(), key=lambda m: (-m.importance, m.name))

    @cached_property
    def model_owner(self) -> dict[str, str]:
        """model name -> module that defines it via _name (first definition wins)."""
        out: dict[str, str] = {}
        for m in self.models:
            if m.name and not (m.inherit and m.name in m.inherit):
                out.setdefault(m.name, m.module)
        return out

    def transitive_deps(self, name: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.modules[name].depends) if name in self.modules else []
        while stack:
            d = stack.pop()
            if d in seen:
                continue
            seen.add(d)
            if d in self.modules:
                stack.extend(self.modules[d].depends)
        return seen

    def related_modules(self, name: str) -> list[str]:
        """Plausible module distractors: same top category first, then by importance."""
        me = self.modules[name]
        same = [m.name for m in self.by_importance if m.top_category == me.top_category and m.name != name]
        rest = [m.name for m in self.by_importance if m.name != name and m.name not in same]
        return same + rest

    def models_near(self, module: str) -> list[str]:
        """Model names defined in this module, its deps, then globally by module importance."""
        order = [module, *sorted(self.transitive_deps(module))]
        rank = {m: i for i, m in enumerate(order)}
        owners = self.model_owner
        imp = {m.name: m.importance for m in self.modules.values()}
        return sorted(
            owners,
            key=lambda mdl: (rank.get(owners[mdl], len(order)), -imp.get(owners[mdl], 0), mdl),
        )


def load_manifest(path: Path) -> dict | None:
    try:
        return ast.literal_eval(path.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError):
        return None


def skip_module(name: str, manifest: dict) -> bool:
    if name.startswith(SKIP_PREFIXES) or any(s in name for s in SKIP_CONTAINS):
        return True
    if not manifest.get("installable", True):
        return True
    cat = manifest.get("category", "")
    return cat.startswith(("Hidden/Tests", "Localization", "Accounting/Localizations"))


def discover(root: Path) -> Scan:
    scan = Scan(root=root)
    for addons_dir in (root / "odoo" / "addons", root / "addons"):
        for mf in sorted(addons_dir.glob("*/__manifest__.py")):
            manifest = load_manifest(mf)
            name = mf.parent.name
            if manifest is None or skip_module(name, manifest):
                continue
            scan.modules[name] = Module(name, mf.parent, manifest)
    # importance = number of (transitive) dependents + bonus for applications
    for name in scan.modules:
        for dep in scan.transitive_deps(name):
            if dep in scan.modules:
                scan.modules[dep].importance += 1
    for m in scan.modules.values():
        if m.is_app:
            m.importance += 40
    for m in scan.modules.values():
        _scan_python(scan, m)
        _scan_xml(scan, m)
    return scan


# ---------------------------------------------------------------- python ---

EXC_NAMES = {"UserError", "ValidationError", "AccessError", "RedirectWarning", "MissingError"}


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):  # "a" "b" concatenations
        l, r = _const_str(node.left), _const_str(node.right)
        return l + r if l is not None and r is not None else None
    return None


def _translated_str(node: ast.AST) -> str | None:
    """_("...") / self.env._("...") / _lt("...") with a constant string."""
    if isinstance(node, ast.Call) and node.args:
        f = node.func
        fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if fname in ("_", "_lt"):
            return _const_str(node.args[0])
    return _const_str(node)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        f = node.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
    return None


def _scan_python(scan: Scan, mod: Module) -> None:
    for py in mod.py_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        # get_param anywhere in the file
        for node in ast.walk(tree):
            if _call_name(node) == "get_param" and node.args:
                key = _const_str(node.args[0])
                default_node = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg == "default"), None)
                if key and default_node is not None:
                    try:
                        default = ast.literal_eval(default_node)
                    except ValueError:
                        continue
                    scan.get_params.append((key, default, mod.name, scan.rel(py, node.lineno)))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            attrs: dict[str, object] = {}
            for stmt in cls.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    tname = stmt.targets[0].id
                    if tname in ("_name", "_inherit", "_description", "_order"):
                        try:
                            attrs[tname] = ast.literal_eval(stmt.value)
                        except ValueError:
                            pass
            kind = next((b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
                         for b in cls.bases), "")
            if kind not in ("Model", "TransientModel", "AbstractModel"):
                continue
            inherit = attrs.get("_inherit", [])
            inherit = [inherit] if isinstance(inherit, str) else list(inherit or [])
            mc = ModelClass(
                module=mod.name, cls=cls.name,
                name=attrs.get("_name") if isinstance(attrs.get("_name"), str) else None,
                inherit=inherit,
                description=attrs.get("_description") if isinstance(attrs.get("_description"), str) else None,
                order=attrs.get("_order") if isinstance(attrs.get("_order"), str) else None,
                kind=kind, source=scan.rel(py, cls.lineno),
            )
            scan.models.append(mc)
            model = mc.model
            if not model:
                continue
            for stmt in cls.body:
                # models.Constraint("CHECK ...", "message")
                if (isinstance(stmt, ast.Assign) and _call_name(stmt.value) == "Constraint"
                        and len(stmt.value.args) >= 2):
                    msg = _translated_str(stmt.value.args[1])
                    definition = _const_str(stmt.value.args[0])
                    if msg and definition:
                        scan.constraints.append(Constraint(mod.name, model, msg, definition,
                                                           scan.rel(py, stmt.lineno)))
            for node in ast.walk(cls):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    exc = _call_name(node.exc)
                    if exc in EXC_NAMES and node.exc.args:
                        msg = _translated_str(node.exc.args[0])
                        if msg:
                            scan.raises.append(Raise(mod.name, model, exc, msg, scan.rel(py, node.lineno)))


# ------------------------------------------------------------------- xml ---

def _scan_xml(scan: Scan, mod: Module) -> None:
    parser = etree.XMLParser(recover=True, remove_comments=True)
    for xf in mod.data_files():
        try:
            tree = etree.parse(str(xf), parser)
        except (etree.XMLSyntaxError, OSError):
            continue
        root = tree.getroot()
        if root is None:
            continue
        for rec in root.iter("record"):
            model = rec.get("model")
            xid = rec.get("id")
            if not model or not xid:
                continue
            fields_, refs, evals = {}, {}, {}
            for f in rec.findall("field"):
                n = f.get("name")
                if not n:
                    continue
                if f.get("ref"):
                    refs[n] = f.get("ref")
                elif f.get("eval") is not None:
                    evals[n] = f.get("eval")
                else:
                    fields_[n] = (f.text or "").strip()
            xmlid = xid if "." in xid else f"{mod.name}.{xid}"
            scan.records.append(Record(mod.name, xmlid, model, fields_, refs, evals,
                                       scan.rel(xf, rec.sourceline)))


# ------------------------------------------------------------- questions ---

def question(id: str, family: str, difficulty: int, text: str, answer: str,
             distractors: list[str], explanation: str, source: str, code: str | None = None) -> dict:
    q = {
        "id": f"{family}:{id}",
        "family": family,
        "difficulty": difficulty,
        "question": text,
        "answer": answer,
        "distractors": distractors,
        "explanation": explanation,
        "source": source,
    }
    if code:
        q["code"] = code
    return q


def pick(answer: str, candidates, rng: random.Random, n: int = 5, exclude=(), pool_head: int = 0) -> list[str]:
    """Pick n unique distractors != answer. If pool_head > 0, sample from the first pool_head
    plausible candidates (keeps distractors 'nearby') before falling back to the rest."""
    excl = {answer, *exclude}
    cands = [c for c in dict.fromkeys(candidates) if c not in excl and c]
    head = cands[:pool_head] if pool_head else cands
    out = rng.sample(head, min(n, len(head)))
    if len(out) < n:
        rest = [c for c in cands if c not in out]
        out += rng.sample(rest, min(n - len(out), len(rest)))
    return out


PLACEHOLDER = re.compile(r"%[(\w)]*[sdfr]|\{[^}]*\}")


def clean_message(msg: str) -> str | None:
    msg = " ".join(msg.split())
    if PLACEHOLDER.search(msg) or len(msg) < 25 or len(msg) > 220:
        return None
    return msg


def numeric_distractors(value: int | float, rng: random.Random, n: int = 5) -> list[str]:
    v = value
    cands = {v * 2, v // 2 if isinstance(v, int) else v / 2, v * 10, v + 1, v - 1, v * 3, v * 4, v + 5,
             v // 10 if isinstance(v, int) else v / 10, 0, 1, 10, 30, 60, 100, 120, 300, 3600}
    cands = sorted(c for c in cands if c != v and c >= 0)
    rng.shuffle(cands)
    return [fmt_num(c) for c in cands[:n]]


def fmt_num(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def model_distractor_pool(scan: Scan, answer: str, module: str) -> list[str]:
    """Concrete (non-transient, non-abstract) models, favouring the same name prefix
    (e.g. res.* for res.company) and the same/related modules."""
    concrete = {m.name for m in scan.models if m.name and m.kind == "Model"}
    near = [m for m in scan.models_near(module) if m in concrete]
    prefix = answer.split(".")[0]
    same_prefix = [m for m in near if m.split(".")[0] == prefix]
    return same_prefix[:10] + near[:12]
