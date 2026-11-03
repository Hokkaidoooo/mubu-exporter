"""Convert an outline using style intervals, preserving adjacent rich text."""
from __future__ import annotations

import html as html_mod
import json
import posixpath
import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .errors import ExportError

IMG_BASE = "https://document-image.mubu.com/"

# Zero-width / invisible characters Mubu sprinkles through its HTML.
INVISIBLE = dict.fromkeys(map(ord, "\u200b\ufeff"), None)

ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp|#\d{2,5}|#x[0-9a-fA-F]+);")
HIGHLIGHT_RE = re.compile(r"\bhighlight-[\w-]+")
COLOR_CLASS_RE = re.compile(r"\btext-color-([\w-]+)\b")

COLOR_NAMES = {
    "red": "#dc2d1e",
    "blue": "#3da8f5",
    "green": "#75c940",
    "yellow": "#ffaf38",
    "purple": "#a566ff",
    "olive": "#8a8a00",
    "grey": "#8c8c8c",
    "cyan": "#00b8d4",
}

# UI-only elements carrying no user content.
SKIP_CLASSES = {"row-select-btn", "column-select-btn"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

# Innermost -> outermost, so nesting is always well-formed.
STYLE_ORDER = ["code", "strike", "underline", "italic", "bold", "mask", "highlight"]
STYLE_MARKERS = {
    "code": ("`", "`"),
    "strike": ("~~", "~~"),
    "underline": ("<u>", "</u>"),
    "italic": ("*", "*"),
    "bold": ("**", "**"),
    "mask": ("{{", "}}"),
    "highlight": ("==", "=="),
}


@dataclass
class RenderOptions:
    keep_color: bool = True
    image_mode: str = "remote"           # remote | local | skip
    image_dir_rel: str = "images"
    doc_paths: dict = field(default_factory=dict)    # docId -> relative md path
    image_names: dict = field(default_factory=dict)  # image uri -> local filename
    current_dir: str = ""
    preserve_unsafe: bool = False

    def __post_init__(self):
        if self.image_mode not in {"remote", "local", "skip"}:
            raise ExportError("unsupported image mode")


def clean_text(text: str) -> str:
    """Strip invisible glyphs and finish decoding double-escaped entities.

    Mubu stores a user-typed `<` as `&amp;lt;`, so HTMLParser's single decode
    pass leaves a literal `&lt;` behind. Decode again while entities remain.
    """
    text = text or ""
    for _ in range(3):
        if not ENTITY_RE.search(text):
            break
        text = html_mod.unescape(text)
    return text.replace("\xa0", " ").translate(INVISIBLE)


EMPHASIS_PAIR = re.compile(r"_[^_\s][^_]*_")


def escape_md(text: str) -> str:
    """Escape characters that could change the literal text's structure."""
    text = text.replace("\\", "\\\\")
    text = text.replace("*", r"\*")
    text = text.replace("`", r"\`")
    text = text.replace("|", r"\|")
    text = text.replace("[", r"\[").replace("]", r"\]")
    if EMPHASIS_PAIR.search(text):
        text = text.replace("_", r"\_")
    text = text.replace("~~", r"\~\~")
    text = re.sub(r"<(?=[A-Za-z/!])", r"\<", text)
    text = re.sub(r"(?m)^(\s*)([>#])", r"\1\\\2", text)
    text = re.sub(r"(?m)^(\s*)([-+])(?=\s)", r"\1\\\2", text)
    text = re.sub(r"(?m)^(\s*\d+)([.)])(?=\s)", r"\1\\\2", text)
    return text


def _color_value(value: str, opts: RenderOptions) -> str:
    if not opts.preserve_unsafe and not re.fullmatch(
        r"(?:#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)", value
    ):
        raise ExportError("unsafe color value; use --no-color or trusted-input mode")
    return value


def _destination(url: str, opts: RenderOptions, *, image: bool = False) -> str:
    if not opts.preserve_unsafe:
        if any(ord(char) < 32 for char in url) or url.startswith("//"):
            raise ExportError("unsafe link destination")
        scheme = urllib.parse.urlsplit(url).scheme.lower()
        allowed = {"http", "https"} if image else {"", "http", "https", "mailto"}
        if scheme not in allowed:
            raise ExportError("unsupported or unsafe link scheme")
    return urllib.parse.quote(url, safe="/:#?&=%+@,;!~_*$'-")


def _image_markdown(uri: str, opts: RenderOptions) -> str:
    if opts.image_mode == "skip":
        return ""
    if opts.image_mode == "local":
        if uri not in opts.image_names:
            raise ExportError("local image is missing from the download plan")
        target = f"{opts.image_dir_rel}/{opts.image_names[uri]}"
        return f"![]({relative_link(opts.current_dir, target)})"
    return f"![]({_destination(image_url(uri), opts, image=True)})"


def image_url(uri: str) -> str:
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    return IMG_BASE + urllib.parse.quote(uri, safe="/-_.~")


def relative_link(from_dir: str, to_path: str) -> str:
    """POSIX-style relative path between two exported markdown files.

    CJK filenames are left as-is (percent-encoding them makes the links
    unreadable); only characters that would break Markdown link syntax are
    escaped while Chinese characters remain readable.
    """
    from_dir = (from_dir or "").strip("/")
    to_path = to_path.replace("\\", "/").strip("/")
    rel = to_path if not from_dir else posixpath.relpath(to_path, from_dir)
    return "".join(char if ord(char) > 127 else urllib.parse.quote(char, safe="/._~-") for char in rel)


def collect_image_uris(nodes: list[dict]) -> list[str]:
    """Collect each URI once, including images in rich text and table cells."""
    uris: dict[str, None] = {}

    class Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                source = dict(attrs).get("src")
                if source:
                    uris[source] = None

    pending = list(nodes)
    while pending:
        node = pending.pop()
        for image in node.get("images", []):
            uris[image["uri"]] = None
        for field_name in ("text", "note"):
            parser = Collector(convert_charrefs=True)
            parser.feed(node.get(field_name, ""))
            parser.close()
        pending.extend(node.get("children", []))
    return sorted(uris)


@dataclass
class Seg:
    """One run of text plus the styles active over it."""
    text: str
    styles: frozenset = frozenset()
    link: str | None = None
    color: str | None = None
    raw: bool = False        # already Markdown; never escape or wrap

    def key(self):
        return (self.styles, self.link, self.color, self.raw)


def _outermost(styles: frozenset) -> str | None:
    for name in reversed(STYLE_ORDER):
        if name in styles:
            return name
    return None


def _hug(inner: str, open_m: str, close_m: str) -> str:
    """Emphasis markers must touch non-space text: `** x **` does not render."""
    core = inner.strip(" \t")
    if not core:
        return inner
    lead = inner[:len(inner) - len(inner.lstrip(" \t"))]
    trail = inner[len(inner.rstrip(" \t")):]
    return f"{lead}{open_m}{core}{close_m}{trail}"


def render_segments(segs: list[Seg]) -> str:
    """Rebuild nested style regions.

    Styles are treated as intervals, not per-segment flags: for each position
    the longest neighbouring run sharing a style is wrapped once, outermost
    first, then recursed into. Wrapping each segment independently produced
    illegal output like `==A== ==**B**====C==` when siblings shared
    an outer highlight but differed on an inner bold.
    """
    return _build(segs, frozenset(), None, None)


def _build(segs: list[Seg], applied: frozenset,
           applied_link: str | None, applied_color: str | None) -> str:
    out: list[str] = []
    i, n = 0, len(segs)
    while i < n:
        seg = segs[i]

        if seg.color and seg.color != applied_color:
            j = i + 1
            while j < n and segs[j].color == seg.color:
                j += 1
            inner = _build(segs[i:j], applied, applied_link, seg.color)
            out.append(f'<span style="color:{seg.color}">{inner}</span>')
            i = j
            continue

        if seg.link and seg.link != applied_link:
            j = i + 1
            while j < n and segs[j].link == seg.link:
                j += 1
            inner = _build(segs[i:j], applied, seg.link, applied_color)
            out.append(f"[{inner}]({seg.link})")
            i = j
            continue

        style = _outermost(seg.styles - applied)
        if style:
            j = i + 1
            while (j < n and style in (segs[j].styles - applied)
                   and segs[j].color == applied_color
                   and segs[j].link == applied_link):
                j += 1
            inner = _build(segs[i:j], applied | {style}, applied_link, applied_color)
            if style == "code":
                fence = "`" * (max((len(m) for m in re.findall(r"`+", inner)), default=0) + 1)
                needs_pad = inner.startswith("`") or inner.endswith("`") or (
                    inner.strip(" ") and (inner.startswith(" ") or inner.endswith(" "))
                )
                pad = " " if needs_pad else ""
                out.append(f"{fence}{pad}{inner}{pad}{fence}")
            else:
                out.append(_hug(inner, *STYLE_MARKERS[style]))
            i = j
            continue

        if seg.raw:
            out.append(seg.text)
        elif "code" in applied:
            out.append(seg.text)
        else:
            out.append(escape_md(seg.text))
        i += 1
    return "".join(out)


class InlineParser(HTMLParser):
    """Flatten Mubu inline HTML into styled segments."""

    def __init__(self, opts: RenderOptions, in_table: bool = False):
        super().__init__(convert_charrefs=True)
        self.opts = opts
        self.in_table = in_table
        self.segs: list[Seg] = []
        self.stack: list[dict] = []
        self.skip_depth = 0
        self.tables: list[str] = []
        self._table: TableParser | None = None
        self._table_depth = 0

    # -- current style context -------------------------------------------
    def _styles(self) -> frozenset:
        names = set()
        for frame in self.stack:
            names.update(frame.get("styles", ()))
        return frozenset(names)

    def _link(self):
        for frame in reversed(self.stack):
            if frame.get("link"):
                return frame["link"]
        return None

    def _color(self):
        for frame in reversed(self.stack):
            if frame.get("color"):
                return frame["color"]
        return None

    def _add(self, text: str, raw: bool = False):
        if not text:
            return
        self.segs.append(Seg(text, self._styles(), self._link(),
                             self._color(), raw))

    def _newline(self):
        self.segs.append(Seg("<br>" if self.in_table else "\n", raw=True))

    # -- parsing ----------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrd = {k: (v or "") for k, v in attrs}
        class_attr = attrd.get("class", "")
        classes = set(class_attr.split())

        if self._table is not None:
            if tag == "table":
                self._table_depth += 1
            self._table.feed(self.get_starttag_text() or f"<{tag}>")
            return
        if self.skip_depth:
            if tag not in VOID_TAGS:
                self.skip_depth += 1
            return
        if classes & SKIP_CLASSES:
            self.skip_depth = 0 if tag in VOID_TAGS else 1
            return
        if tag == "table" and self._table is None:
            self._table = TableParser(self.opts)
            self._table_depth = 1
            self._table.feed(self.get_starttag_text() or "<table>")
            return
        if tag == "br":
            self._newline()
            return
        if tag == "img":
            if attrd.get("src"):
                self._add(_image_markdown(attrd["src"], self.opts), raw=True)
            return
        if tag in VOID_TAGS:
            return

        # Formula: LaTeX lives in data-raw, the element text is invisible glyphs.
        if "formula" in classes:
            latex = urllib.parse.unquote(attrd.get("data-raw", "")).strip()
            if latex:
                self._add(f"${latex}$", raw=True)
            self.skip_depth = 1
            return

        # Node mention -> link into the other exported document.
        if "node-mention" in classes:
            self._add(self._mention_markdown(attrd), raw=True)
            self.skip_depth = 1
            return

        styles = set()
        if tag in ("b", "strong") or "bold" in classes:
            styles.add("bold")
        if tag in ("i", "em") or "italic" in classes:
            styles.add("italic")
        if tag == "u" or "underline" in classes:
            styles.add("underline")
        if tag in ("s", "del") or "strikethrough" in classes:
            styles.add("strike")
        if tag == "code" or "codespan" in classes:
            styles.add("code")
        if "mask" in classes:
            styles.add("mask")
        if HIGHLIGHT_RE.search(class_attr):
            styles.add("highlight")

        frame: dict = {"styles": styles}

        color_hit = COLOR_CLASS_RE.search(class_attr)
        if self.opts.keep_color:
            if tag == "font" and attrd.get("color"):
                frame["color"] = _color_value(attrd["color"], self.opts)
            elif color_hit:
                name = color_hit.group(1)
                frame["color"] = _color_value(COLOR_NAMES.get(name, name), self.opts)

        if tag == "a":
            href = attrd.get("href", "")
            if href and not href.startswith("https://mubu-action.invalid"):
                frame["link"] = _destination(href, self.opts)

        if tag in ("div", "p", "tr"):
            if self.segs and self.segs[-1].text != "\n":
                self._newline()
            frame["block"] = True

        frame["tag"] = tag
        self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def _mention_markdown(self, attrd: dict) -> str:
        label = ""
        try:
            parts = json.loads(urllib.parse.unquote(attrd.get("data-text", "")))
            label = "".join(p.get("text", "") for p in parts)
        except (json.JSONDecodeError, TypeError, AttributeError):
            raise ExportError("node mention has invalid label metadata") from None
        label = clean_text(label) or "引用"
        document = attrd.get("data-doc", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", document):
            raise ExportError("node mention has an invalid document id")
        target = self.opts.doc_paths.get(document)
        node = attrd.get("data-node", "")
        anchor = f"#{urllib.parse.quote(node, safe='_-')}" if node else ""
        if not target:
            return f"[{escape_md(label)}](https://mubu.com/doc/{document}{anchor})"
        rel = relative_link(self.opts.current_dir, target)
        dest = f"{rel}{anchor}"
        if " " in dest:
            dest = f"<{dest}>"
        return f"[{escape_md(label)}]({dest})"

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self._table is not None:
            self._table.feed(f"</{tag}>")
            if tag == "table":
                self._table_depth -= 1
                if self._table_depth == 0:
                    self._table.close()
                    rendered = self._table.render()
                    if rendered:
                        self.tables.append(rendered)
                    self._table = None
            return

        if self.skip_depth:
            self.skip_depth -= 1
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                frames = self.stack[index:]
                del self.stack[index:]
                if any(frame.get("block") for frame in frames):
                    self._newline()
                return

    def handle_data(self, data):
        if self._table is not None:
            self._table.feed(html_mod.escape(data, quote=False))
            return
        if self.skip_depth:
            return
        self._add(clean_text(data))

    def result(self) -> tuple[str, list[str]]:
        if self._table is not None or self.skip_depth:
            raise ExportError("unclosed rich-text element would lose content")
        text = render_segments(self.segs)
        return text.strip(), self.tables


class TableParser(HTMLParser):
    """Collect table cells; Mubu wraps real cell content in span.edit-area."""

    def __init__(self, opts: RenderOptions):
        super().__init__(convert_charrefs=True)
        self.opts = opts
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    @staticmethod
    def _raw_tag(tag, attrs):
        parts = [tag]
        for k, v in attrs:
            parts.append(f'{k}="{html_mod.escape(v or "", quote=True)}"')
        return "<" + " ".join(parts) + ">"

    def handle_starttag(self, tag, attrs):
        if tag == "table" and getattr(self, "_inside", False):
            raise ExportError("nested tables cannot be represented faithfully in Markdown")
        if tag == "table":
            self._inside = True
        if tag in ("td", "th") and any(
            key in {"rowspan", "colspan"} and value != "1" for key, value in attrs
        ):
            raise ExportError("merged table cells cannot be represented faithfully in Markdown")
        if tag == "tr":
            if self._row is not None:
                raise ExportError("table has an unclosed row")
            self._row = []
        elif tag in ("td", "th"):
            if self._cell is not None:
                raise ExportError("table has an unclosed cell")
            self._cell = []
        elif self._cell is not None:
            self._cell.append(self._raw_tag(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        if self._cell is not None:
            self._cell.append(self._raw_tag(tag, attrs))

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            inline = InlineParser(self.opts, in_table=True)
            inline.feed("".join(self._cell or []))
            inline.close()
            text, _ = inline.result()
            # escape_md already escaped `|`; only newlines still need handling.
            text = text.replace("\n", "<br>")
            if self._row is not None:
                self._row.append(text.strip())
            self._cell = None
        elif tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif self._cell is not None:
            self._cell.append(f"</{tag}>")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(html_mod.escape(data, quote=False))
        elif data.strip():
            raise ExportError("text outside table cells cannot be represented faithfully")

    def render(self) -> str:
        if self._cell is not None or self._row is not None:
            raise ExportError("table has an unclosed row or cell")
        if not self.rows:
            return ""
        width = max(len(r) for r in self.rows)
        rows = [r + [""] * (width - len(r)) for r in self.rows]
        head, body = rows[0], rows[1:]
        lines = ["| " + " | ".join(head) + " |",
                 "| " + " | ".join(["---"] * width) + " |"]
        for row in body:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)


def render_inline(html_src: str, opts: RenderOptions) -> tuple[str, list[str]]:
    if not html_src:
        return "", []
    if "<" not in html_src and "&" not in html_src:
        return escape_md(clean_text(html_src)).strip(), []
    parser = InlineParser(opts)
    parser.feed(html_src)
    parser.close()
    return parser.result()


# ---------------------------------------------------------------------------
# Node tree -> Markdown
# ---------------------------------------------------------------------------

MAX_HEADING_DEPTH = 3      # depth 1..3 sections become ## / ### / ####


def _task_prefix(node: dict) -> str:
    """Only taskStatus represents a checkbox; finish is a legacy field."""
    status = node.get("taskStatus")
    if status == 1:
        return "[ ] "
    if status == 2:
        return "[x] "
    return ""


def _image_lines(node: dict, opts: RenderOptions) -> list[str]:
    if opts.image_mode == "skip":
        return []
    lines = []
    for img in node.get("images") or []:
        uri = img.get("uri") or ""
        if not uri:
            continue
        lines.append(_image_markdown(uri, opts))
    return lines


def _bullet(text: str, indent: str) -> list[str]:
    parts = text.split("\n")
    out = [f"{indent}- {parts[0]}"]
    for extra in parts[1:]:
        out.append(f"{indent}  {extra}" if extra.strip() else "")
    return out


def _blockquote(text: str, indent: str) -> list[str]:
    return [f"{indent}> {ln}" if ln.strip() else f"{indent}>"
            for ln in text.split("\n")]


def render_nodes(nodes: list[dict], opts: RenderOptions,
                 style: str = "adaptive") -> list[str]:
    """Walk the outline into Markdown lines.

    adaptive: depth 1..3 nodes that have children become headings, so the file
              keeps a navigable outline; everything else is a nested bullet
              indented relative to its nearest heading ancestor.
    bullets:  pure nested bullet list, indent == absolute depth.
    """
    lines: list[str] = []

    def blank():
        if lines and lines[-1] != "":
            lines.append("")

    def walk(node_list, depth: int, base: int):
        for node in node_list or []:
            text, tables = render_inline(node.get("text") or "", opts)
            if node.get("id"):
                anchor = html_mod.escape(node["id"], quote=True)
                text = f'<a id="{anchor}"></a>{text}'
            note_text, note_tables = render_inline(node.get("note") or "", opts)

            if node.get("emoji"):
                text = f"{node['emoji']} {text}".strip()

            color = node.get("color")
            if (text and color and opts.keep_color
                    and color not in ("", "#333333")
                    and "<span style" not in text):
                text = f'<span style="color:{_color_value(color, opts)}">{text}</span>'

            task = _task_prefix(node)
            children = node.get("children") or []
            images = _image_lines(node, opts)
            all_tables = [t for t in tables + note_tables if t]

            as_heading = (style == "adaptive" and children
                          and depth <= MAX_HEADING_DEPTH and not task)

            if as_heading:
                blank()
                lines.append("#" * min(depth + 1, 6) + " " + (text or "(无标题)"))
                blank()
                if note_text:
                    lines.extend(_blockquote(note_text, ""))
                    blank()
                for tbl in all_tables:
                    lines.append(tbl)
                    blank()
                if images:
                    lines.extend(images)
                    blank()
                walk(children, depth + 1, depth)
            else:
                indent = "  " * max(depth - base - 1, 0)
                if text or task:
                    lines.extend(_bullet(task + text, indent))
                    child_indent = indent + "  "
                else:
                    # No text: emit the payload directly instead of a bare "-".
                    child_indent = indent
                if note_text:
                    lines.extend(_blockquote(note_text, child_indent))
                for tbl in all_tables:
                    blank()
                    for ln in tbl.split("\n"):
                        lines.append(child_indent + ln)
                    blank()
                for img in images:
                    lines.append(f"{child_indent}{img}")
                walk(children, depth + 1, base)

    walk(nodes, 1, 0)

    cleaned: list[str] = []
    for line in lines:
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned
