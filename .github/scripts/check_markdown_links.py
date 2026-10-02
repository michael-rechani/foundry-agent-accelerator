"""Check relative links, image paths, and heading anchors in tracked Markdown.

Run from anywhere in the repository:

    python .github/scripts/check_markdown_links.py

External URLs are not fetched. Fenced code blocks and inline code are ignored,
so examples of Markdown or HTML don't count as links.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

GIT = shutil.which("git") or "git"
EXTERNAL = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
EXPLICIT_ANCHOR = re.compile(r"<a\s[^>]*?\b(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)")
REFERENCE_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
REFERENCE_LABEL = re.compile(r"^\s{0,3}\[([^\]]+)\]:")
REFERENCE_USE = re.compile(r"(?<![\w\]])!?\[((?:[^\[\]]|\[[^\[\]]*\])+)\]\[([^\]]*)\]")
HTML_ATTR = re.compile(r"\b(href|src|srcset)=[\"']([^\"']+)[\"']", re.IGNORECASE)


def git(*args: str, cwd: Path | None = None) -> bytes:
    # Fixed git arguments only; nothing comes from user input.
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, check=True).stdout  # noqa: S603


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel").decode("utf-8").strip())


def tracked_markdown(root: Path) -> list[Path]:
    names = git("ls-files", "-z", "--", "*.md", cwd=root).decode("utf-8").split("\0")
    return [root / name for name in names if name]


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) pairs outside fenced code, with inline code removed."""
    lines, fence = [], None
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            continue
        lines.append((number, INLINE_CODE.sub("", line)))
    return lines


def slugify(heading: str) -> str:
    """Approximate GitHub's anchor for the rendered heading text."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").replace("*", "")
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


_anchor_cache: dict[Path, set[str]] = {}


def anchors(path: Path) -> set[str]:
    if path not in _anchor_cache:
        found: set[str] = set()
        counts: dict[str, int] = {}
        # Headings keep their inline code for the slug, so read raw lines outside fences.
        text = path.read_text(encoding="utf-8")
        raw = text.splitlines()
        for number, line in prose_lines(text):
            found.update(EXPLICIT_ANCHOR.findall(line))
            match = HEADING.match(raw[number - 1])
            if match:
                slug = slugify(match.group(2))
                n = counts.get(slug, 0)
                counts[slug] = n + 1
                found.add(slug if n == 0 else f"{slug}-{n}")
        _anchor_cache[path] = found
    return _anchor_cache[path]


def targets(line: str) -> list[str]:
    found = [m.group(1) for m in INLINE_LINK.finditer(line)]
    match = REFERENCE_DEF.match(line)
    if match:
        found.append(match.group(1))
    for attr, value in HTML_ATTR.findall(line):
        if attr.lower() == "srcset":
            found.extend(part.strip().split()[0] for part in value.split(",") if part.strip())
        else:
            found.append(value)
    return [t[1:-1] if t.startswith("<") and t.endswith(">") else t for t in found]


def normalize_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def undefined_references(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return (line number, label) for [text][label] and [label][] uses with no [label]: definition."""
    defined = set()
    for _, line in lines:
        match = REFERENCE_LABEL.match(line)
        if match:
            defined.add(normalize_label(match.group(1)))
    missing = []
    for number, line in lines:
        for text, explicit in REFERENCE_USE.findall(line):
            label = explicit or text
            if normalize_label(label) not in defined:
                missing.append((number, label))
    return missing


def check_target(root: Path, source: Path, target: str) -> str | None:
    if not target or EXTERNAL.match(target) or target.startswith("//"):
        return None
    path_part, _, fragment = target.partition("#")
    path_part = unquote(path_part.split("?", 1)[0])
    if path_part:
        base = root if path_part.startswith("/") else source.parent
        resolved = (base / path_part.lstrip("/")).resolve()
        if not resolved.exists():
            return f"missing file: {target}"
    else:
        resolved = source
    if not fragment or re.fullmatch(r"L\d+(-L\d+)?", fragment):
        return None
    if resolved.is_dir():
        resolved = resolved / "README.md"
    if resolved.suffix.lower() != ".md" or not resolved.exists():
        return None
    if unquote(fragment) not in anchors(resolved):
        return f"missing anchor: {target}"
    return None


def main() -> int:
    root = repo_root()
    problems = []
    files = tracked_markdown(root)
    for source in files:
        name = source.relative_to(root).as_posix()
        lines = prose_lines(source.read_text(encoding="utf-8"))
        for number, line in lines:
            for target in targets(line):
                problem = check_target(root, source, target)
                if problem:
                    problems.append(f"{name}:{number}: {problem}")
        for number, label in undefined_references(lines):
            problems.append(f"{name}:{number}: undefined reference: [{label}]")
    for problem in problems:
        print(problem)
    print(f"Checked {len(files)} Markdown files: {len(problems)} broken link(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
