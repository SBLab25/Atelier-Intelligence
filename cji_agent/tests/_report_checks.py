"""
Spec 10 report checks (design §9), shared by tests/test_reports.py and the gate.

check_inert(html)    -> problems that would let report content execute or load something.
check_contract(html) -> problems with the self-contained output contract (CSP, one style, one data block, size).
Both parse with html.parser (no browser engine is available here; requirements §4).
"""
from __future__ import annotations

import base64
import hashlib
import json
from html.parser import HTMLParser

MAX_REPORT_BYTES = 1024 * 1024

ALLOWED_ELEMENTS = frozenset({
    "html", "head", "meta", "title", "style", "body", "header", "footer", "div", "p", "h1", "h2", "h4", "span",
    "strong", "table", "thead", "tbody", "tr", "th", "td", "dl", "dt", "dd", "svg", "g", "rect", "text", "script",
})
ALLOWED_ATTRIBUTES = frozenset({
    "lang", "charset", "http-equiv", "content", "name", "class", "id", "type", "xmlns", "viewbox", "width",
    "height", "role", "aria-label", "x", "y", "fill", "text-anchor", "font-size", "dominant-baseline",
    "preserveaspectratio",
})
URL_MARKERS = ("javascript:", "data:", "vbscript:", "http:", "https:", "//", "url(")


def expected_csp(style_body: str) -> str:
    digest = base64.b64encode(hashlib.sha256(style_body.encode("utf-8")).digest()).decode("ascii")
    return (f"default-src 'none'; style-src 'sha256-{digest}'; img-src 'none'; script-src 'none'; "
            "base-uri 'none'; form-action 'none'")


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.problems: list[str] = []
        self.styles: list[str] = []
        self.scripts: list[tuple[dict[str, str | None], str]] = []
        self.head_children: list[tuple[str, dict[str, str | None]]] = []
        self._stack: list[str] = []
        self._raw: str | None = None
        self._raw_attrs: dict[str, str | None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self.elements.append((tag, a))
        if self._stack and self._stack[-1] == "head":
            self.head_children.append((tag, a))
        if tag in ("style", "script"):
            self._raw, self._raw_attrs = tag, a
        if tag not in ("meta",):
            self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self.elements.append((tag, a))
        if self._stack and self._stack[-1] == "head":
            self.head_children.append((tag, a))

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._raw = None
        while self._stack and self._stack[-1] != tag:
            self._stack.pop()
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._raw == "style":
            self.styles.append(data)
        elif self._raw == "script":
            self.scripts.append((self._raw_attrs, data))

    def handle_comment(self, data: str) -> None:
        self.problems.append("comment in output")

    def handle_pi(self, data: str) -> None:
        self.problems.append("processing instruction in output")

    def unknown_decl(self, data: str) -> None:
        self.problems.append(f"unknown declaration in output: {data[:40]!r}")


def _parse(html: str) -> _Parser:
    p = _Parser()
    p.feed(html)
    p.close()
    return p


def check_inert(html: str) -> list[str]:
    p = _parse(html)
    problems = list(p.problems)
    script_tags = [a for t, a in p.elements if t == "script"]
    if len(script_tags) != 1 or script_tags[0].get("type") != "application/json":
        problems.append(f"expected exactly one JSON data block, found script tags {script_tags}")
    for tag, attrs in p.elements:
        if tag not in ALLOWED_ELEMENTS:
            problems.append(f"unexpected element <{tag}>")
        for name, value in attrs.items():
            if name.startswith("on"):
                problems.append(f"event handler attribute {name} on <{tag}>")
            elif name not in ALLOWED_ATTRIBUTES:
                problems.append(f"unexpected attribute {name} on <{tag}>")
            low = (value or "").lower()
            if tag != "meta" and any(m in low for m in URL_MARKERS):
                problems.append(f"URL-like attribute value on <{tag} {name}>")
    for attrs, body in p.scripts:
        if "<" in body:
            problems.append("raw '<' inside the JSON data block")
    return problems


def check_contract(html: str) -> list[str]:
    p = _parse(html)
    problems = list(p.problems)
    size = len(html.encode("utf-8"))
    if size > MAX_REPORT_BYTES:
        problems.append(f"report is {size} bytes, over {MAX_REPORT_BYTES}")
    if not html.startswith("<!DOCTYPE html>"):
        problems.append("missing <!DOCTYPE html>")
    if len(p.styles) != 1:
        problems.append(f"expected one <style> block, found {len(p.styles)}")
    if not p.head_children or p.head_children[0][0] != "meta" or \
            p.head_children[0][1].get("http-equiv") != "Content-Security-Policy":
        problems.append("the first element of <head> is not the CSP meta")
    elif p.styles and p.head_children[0][1].get("content") != expected_csp(p.styles[0]):
        problems.append(f"CSP does not match the policy and style hash: {p.head_children[0][1].get('content')}")
    csp_metas = [a for t, a in p.elements if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"]
    if len(csp_metas) != 1:
        problems.append(f"expected one CSP meta, found {len(csp_metas)}")
    if [a.get("charset") for t, a in p.elements if t == "meta" and "charset" in a] != ["utf-8"]:
        problems.append("missing or repeated <meta charset=utf-8>")
    if html.encode("utf-8").find(b'charset="utf-8"') > 1024:
        problems.append("charset declaration is not within the first 1024 bytes")
    data = report_data(html)
    if data is None:
        problems.append("JSON data block missing or not valid JSON")
    elif data.get("schema") != "cji-report/1":
        problems.append(f"unexpected schema {data.get('schema')!r}")
    for tag, attrs in p.elements:
        if tag in ("link", "img", "iframe", "object", "embed", "base", "form", "audio", "video", "source"):
            problems.append(f"external-resource element <{tag}>")
        for name in ("src", "href", "xlink:href", "style", "srcset", "poster", "action"):
            if name in attrs:
                problems.append(f"attribute {name} on <{tag}>")
    for body in p.styles:
        if "@import" in body or "url(" in body:
            problems.append("@import or url() in the style block")
    return problems


def report_data(html: str) -> dict | None:
    p = _parse(html)
    bodies = [body for attrs, body in p.scripts if attrs.get("type") == "application/json"]
    if len(bodies) != 1:
        return None
    try:
        data = json.loads(bodies[0])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def elements(html: str, tag: str) -> list[dict[str, str | None]]:
    return [a for t, a in _parse(html).elements if t == tag]


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def text_content(html: str) -> str:
    """The text a reader sees (character references decoded), without the style and data blocks."""
    p = _Text()
    p.feed(html)
    p.close()
    return "".join(p.parts)
