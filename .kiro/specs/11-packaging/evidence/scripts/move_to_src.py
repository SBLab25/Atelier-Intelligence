"""Spec 11 T2: move the application into src/cji and qualify first-party imports (design §2).

Usage (from anywhere):  python move_to_src.py [--apply]
Without --apply it is a dry run: nothing is moved or written except the report.

1. Moves every application module/package into cji_agent/src/cji/ (plain filesystem moves: most of the code is
   untracked, and the index is left alone; git detects the renames by content when the work is committed).
   generate_diverse.py -> src/cji/tools/; tracker/snippet_generator.py and tracker.js -> src/cji/tracker/.
2. Rewrites level-0 import statements in src/ and tests/ (AST-located, single line edits):
   `from X... import` -> `from cji.X... import`; `import X.Y as Z` -> `import cji.X.Y as Z`;
   `import X` / `import X as Z` -> `from cji import X [as Z]`.
3. Rewrites first-party module paths inside string literals (`"mcp_servers.insight_server"`,
   `"collector.api:app"`, `"agents.workers.call_tool"` patch targets) when the dotted path names a real module or
   a name defined in a first-party module file.
4. Writes evidence/move-report.txt: moves, every changed line, and every first-party name left unqualified.
Idempotent: already-qualified code (`cji.X`) is not matched again. tests/test_packaging.py is not rewritten (its
strings name the old modules on purpose).
"""
from __future__ import annotations

import ast
import io
import re
import shutil
import sys
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve()
SPEC = HERE.parents[2]                      # .kiro/specs/11-packaging
REPO = SPEC.parents[2]                      # TCS-CJI
APP = REPO / "cji_agent"
SRC = APP / "src" / "cji"
REPORT = SPEC / "evidence" / "move-report.txt"
APPLY = "--apply" in sys.argv

PACKAGES = ["agents", "collector", "domain", "guardrails", "integrations", "mcp_servers", "reporting",
            "repositories", "settings", "tools", "workflow"]
MODULES = ["config", "graph", "main", "state", "dashboard", "run_servers"]
FIRST = set(PACKAGES) | set(MODULES) | {"tracker", "generate_diverse"}
SPECIAL = {  # old dotted prefix -> new dotted name (outside the plain cji.<old> rule)
    "generate_diverse": "cji.tools.generate_diverse",
}
SKIP_REWRITE = {"test_packaging.py"}

report: list[str] = []


def log(line: str) -> None:
    report.append(line)


# ── module inventory (from whichever layout exists) ───────────────────────────────────────────────────────────
def inventory() -> tuple[set[str], dict[str, set[str]]]:
    """Dotted first-party module names (old spelling) and top-level names defined in module files."""
    mods: set[str] = set()
    names: dict[str, set[str]] = {}
    base = SRC if SRC.exists() and not (APP / "config.py").exists() else APP

    def add_file(path: Path, dotted: str) -> None:
        mods.add(dotted)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            return
        defined = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        defined.add(t.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    defined.add((a.asname or a.name).split(".")[0])
        names[dotted] = defined

    for pkg in PACKAGES:
        for f in (base / pkg).rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            rel = f.relative_to(base).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            add_file(f, ".".join(parts))
    for mod in MODULES:
        add_file(base / f"{mod}.py", mod)
    if base == APP:
        add_file(APP / "generate_diverse.py", "generate_diverse")
        add_file(APP / "tracker" / "snippet_generator.py", "tracker.snippet_generator")
    else:
        add_file(SRC / "tools" / "generate_diverse.py", "generate_diverse")
        add_file(SRC / "tracker" / "snippet_generator.py", "tracker.snippet_generator")
    mods.add("tracker")
    # generate_diverse also lives at tools.generate_diverse after the move
    mods.discard("tools.generate_diverse")
    return mods, names


MODS, NAMES = inventory()


def qualify(dotted: str) -> str:
    top = dotted.split(".")[0]
    if top in SPECIAL:
        return SPECIAL[top] + dotted[len(top):]
    return "cji." + dotted


def string_target(value: str) -> str | None:
    """New spelling for a string that is exactly a first-party module path / patch target, else None."""
    m = re.fullmatch(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(:[A-Za-z_]\w*)?", value)
    if not m or m.group(1).split(".")[0] not in FIRST:
        return None
    dotted, attr = m.group(1), m.group(2) or ""
    if "." not in dotted and not attr:
        return None                          # bare "settings" etc.: reviewed by hand (reported below)
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):     # longest module prefix, the rest must be names in that module
        mod = ".".join(parts[:cut])
        if mod in MODS:
            rest = parts[cut:]
            if not rest or (rest[0] in NAMES.get(mod, set())) or (cut < len(parts) and f"{mod}.{rest[0]}" in MODS):
                return qualify(dotted) + attr
            return None
    return None


EMBEDDED = re.compile(r"(?<![\w./\\-])((?:" + "|".join(sorted(FIRST, key=len, reverse=True)) +
                      r")(?:\.[A-Za-z_]\w*)+)(?![\w/\\])")


def rewrite_embedded(text: str) -> str:
    """Module paths inside a longer string (e.g. code passed to `python -c`)."""
    def sub(m: re.Match[str]) -> str:
        if m.group(1) not in MODS:           # only whole module paths: `config.X` in code strings is an attribute
            return m.group(1)
        return qualify(m.group(1))
    return EMBEDDED.sub(sub, text)


# ── step 1: moves ─────────────────────────────────────────────────────────────────────────────────────────────
def plan_moves() -> list[tuple[Path, Path]]:
    moves = []
    for pkg in PACKAGES:
        if (APP / pkg).is_dir():
            moves.append((APP / pkg, SRC / pkg))
    for mod in MODULES:
        if (APP / f"{mod}.py").is_file():
            moves.append((APP / f"{mod}.py", SRC / f"{mod}.py"))
    if (APP / "generate_diverse.py").is_file():
        moves.append((APP / "generate_diverse.py", SRC / "tools" / "generate_diverse.py"))
    for name in ("snippet_generator.py", "tracker.js"):
        if (APP / "tracker" / name).is_file():
            moves.append((APP / "tracker" / name, SRC / "tracker" / name))
    return moves


def do_moves() -> None:
    moves = plan_moves()
    log(f"== moves ({len(moves)}){' [dry run]' if not APPLY else ''}")
    for a, b in moves:
        log(f"  {a.relative_to(APP).as_posix()} -> {b.relative_to(APP).as_posix()}")
    if not APPLY:
        return
    SRC.mkdir(parents=True, exist_ok=True)
    for a, b in moves:
        if a.is_dir():
            for cache in list(a.rglob("__pycache__")):
                shutil.rmtree(cache)
        b.parent.mkdir(parents=True, exist_ok=True)
        if b.exists():
            raise SystemExit(f"target exists: {b}")
        shutil.move(str(a), str(b))
    gitkeep = APP / "tracker" / ".gitkeep"
    if gitkeep.exists():
        gitkeep.unlink()
        log("  deleted tracker/.gitkeep (tracker/ now holds only the snippet launcher)")
    init = SRC / "__init__.py"
    if not init.exists():
        init.write_text('"""Customer Journey Intelligence (CJI) agent package. Spec 11."""\r\n\r\n'
                        '__version__ = "0.11.0"\r\n', encoding="utf-8", newline="")
        log("  created src/cji/__init__.py")
    tinit = SRC / "tracker" / "__init__.py"
    if not tinit.exists():
        tinit.write_text('"""Browser tracker (tracker.js, package data) and the snippet generator."""\r\n',
                         encoding="utf-8", newline="")
        log("  created src/cji/tracker/__init__.py")


# ── steps 2 and 3: rewrites ───────────────────────────────────────────────────────────────────────────────────
def rewrite_file(path: Path, rel: str) -> tuple[str, list[str], list[str]]:
    raw = path.read_bytes().decode("utf-8")
    lines = raw.splitlines(keepends=True)
    tree = ast.parse(raw)
    changes: list[str] = []
    manual: list[str] = []
    new_lines = list(lines)

    def set_line(no: int, text: str) -> None:
        old = new_lines[no - 1]
        if old != text:
            new_lines[no - 1] = text
            changes.append(f"  {rel}:{no}: {old.strip()}  =>  {text.strip()}")

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top = node.module.split(".")[0]
            if top not in FIRST:
                continue
            line = new_lines[node.lineno - 1]
            col = node.col_offset
            head = re.match(r"from\s+([\w.]+)", line[col:])
            if not head or head.group(1) != node.module:
                manual.append(f"  {rel}:{node.lineno}: unparsed from-import: {line.strip()}")
                continue
            new = line[:col] + "from " + qualify(node.module) + line[col + head.end():]
            set_line(node.lineno, new)
        elif isinstance(node, ast.Import):
            firsts = [a for a in node.names if a.name.split(".")[0] in FIRST]
            if not firsts:
                continue
            line = new_lines[node.lineno - 1]
            if len(node.names) != 1 or node.end_lineno != node.lineno:
                manual.append(f"  {rel}:{node.lineno}: multi-name import: {line.strip()}")
                continue
            a = node.names[0]
            col = node.col_offset
            m = re.match(r"import\s+[\w.]+(\s+as\s+\w+)?", line[col:])
            if not m:
                manual.append(f"  {rel}:{node.lineno}: unparsed import: {line.strip()}")
                continue
            q = qualify(a.name)
            if "." in a.name:
                if not a.asname:
                    manual.append(f"  {rel}:{node.lineno}: dotted import without alias: {line.strip()}")
                    continue
                stmt = f"import {q} as {a.asname}"
            else:
                pkg, _, leaf = q.rpartition(".")
                stmt = f"from {pkg} import {leaf}" + (f" as {a.asname}" if a.asname and a.asname != leaf else
                                                      ("" if leaf == a.name else f" as {a.name}"))
            set_line(node.lineno, line[:col] + stmt + line[col + m.end():])

    text = "".join(new_lines)
    # string literals, via tokens (keeps quoting and prefixes)
    out_tokens = []
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    string_changes = []
    for tok in toks:
        if tok.type == tokenize.STRING:
            m = re.match(r"([rRbBuUfF]*)(['\"]{3}|['\"])(.*)\2$", tok.string, re.S)
            if m and "b" not in m.group(1).lower():
                body = m.group(3)
                exact = string_target(body)
                new_body = exact if exact else rewrite_embedded(body)
                if new_body != body:
                    string_changes.append((tok.start, tok.end, tok.string, m.group(1) + m.group(2) + new_body + m.group(2)))
        elif tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
            new_body = rewrite_embedded(tok.string)
            if new_body != tok.string:
                string_changes.append((tok.start, tok.end, tok.string, new_body))
    if string_changes:
        tl = text.splitlines(keepends=True)
        for (sr, sc), (er, ec), old, new in reversed(string_changes):
            if sr != er:
                # multi-line literal: replace within the joined span
                span_start = sum(len(x) for x in tl[:sr - 1]) + sc
                span_end = sum(len(x) for x in tl[:er - 1]) + ec
                joined = "".join(tl)
                if joined[span_start:span_end].replace("\r\n", "\n") != old.replace("\r\n", "\n"):
                    manual.append(f"  {rel}:{sr}: could not place multi-line string rewrite")
                    continue
                orig = joined[span_start:span_end]
                repl = rewrite_embedded(orig)
                joined = joined[:span_start] + repl + joined[span_end:]
                tl = joined.splitlines(keepends=True)
                changes.append(f"  {rel}:{sr}-{er}: multi-line string: module paths qualified")
            else:
                line = tl[sr - 1]
                if line[sc:ec] != old:
                    manual.append(f"  {rel}:{sr}: string moved, not rewritten: {old[:80]}")
                    continue
                tl[sr - 1] = line[:sc] + new + line[ec:]
                changes.append(f"  {rel}:{sr}: string {old[:90]}  =>  {new[:90]}")
        text = "".join(tl)
    ast.parse(text)  # must still parse
    return text, changes, manual


def leftovers(path: Path, rel: str, text: str) -> list[str]:
    out = []
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in FIRST:
                    out.append(f"  {rel}:{node.lineno}: import {a.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in FIRST:
                out.append(f"  {rel}:{node.lineno}: from {node.module}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if re.fullmatch(r"(" + "|".join(FIRST) + r")([.:]\w[\w.:]*)?", v):
                out.append(f"  {rel}:{node.lineno}: string {v!r} (review)")
    return out


def main() -> int:
    do_moves()
    roots = [SRC if APPLY or SRC.exists() else APP, APP / "tests"]
    files: list[tuple[Path, str]] = []
    if roots[0] == APP:  # dry run before the move: the files that will move
        for a, _ in plan_moves():
            items = a.rglob("*.py") if a.is_dir() else ([a] if a.suffix == ".py" else [])
            files += [(f, f.relative_to(APP).as_posix()) for f in items if "__pycache__" not in f.parts]
    else:
        files += [(f, f.relative_to(APP).as_posix()) for f in SRC.rglob("*.py") if "__pycache__" not in f.parts]
    files += [(f, f.relative_to(APP).as_posix()) for f in (APP / "tests").rglob("*.py")
              if "__pycache__" not in f.parts and f.name not in SKIP_REWRITE]
    all_changes, all_manual, all_left = [], [], []
    for f, rel in sorted(files, key=lambda x: x[1]):
        text, changes, manual = rewrite_file(f, rel)
        all_changes += changes
        all_manual += manual
        all_left += leftovers(f, rel, text)
        if APPLY and changes:
            f.write_bytes(text.encode("utf-8"))
    log(f"\n== changed lines ({len(all_changes)})")
    report.extend(all_changes)
    log(f"\n== needs manual edit ({len(all_manual)})")
    report.extend(all_manual)
    log(f"\n== first-party names left unqualified after the rewrite ({len(all_left)})")
    report.extend(all_left)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    name = REPORT if APPLY else REPORT.with_name("move-report-dryrun.txt")
    name.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print(f"{'applied' if APPLY else 'dry run'}: {len(all_changes)} changes, {len(all_manual)} manual, "
          f"{len(all_left)} left -> {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
