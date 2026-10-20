#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edu.py — local-first learning workspace CLI for the education-mode skill.

Standard library only. The script itself never makes network requests.
Python 3.8+.

Commands:
  doctor      check the deployment environment and retrieval mode
  init        create a learning workspace
  status      show learner state
  config      show or change retrieval mode and model assumptions
  ingest      index a local or cached web txt/md/epub/pdf source
  search      BM25 keyword search over indexed chunks
  source      show corpus metadata (including web URL / access date)
  read        print a full source or a character range (large-context models)
  outline     print chunk locators and opening lines (structure map)
  add-review  add a spaced-repetition item
  due         list due review items
  review      record a review grade and reschedule (SM-2)
  checkpoint  append a session record and update learner state
  validate    check workspace integrity
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

VERSION = "0.3.0"

DEFAULT_CONFIG = {
    "version": 2,
    "language": "auto",
    "session_minutes": 20,
    "max_explanation_words": 250,
    "hint_policy": "one_level_at_a_time",
    "retrieval_mode": "ask",
    "web_cache": True,
    "context_window": 1000000,
    "multimodal": False,
    "corpus_dir": "corpus",
    "review_algorithm": "sm2",
}

ALLOWED_RETRIEVAL = ("local", "web", "ask", "auto")

UNDERSTANDING_LABELS = {
    0: "刚接触",
    1: "能复述",
    2: "能解释或应用",
    3: "能迁移或创造",
}

STATUS_LABELS = {
    "new": "刚接触",
    "learning": "探索中",
    "review": "巩固中",
    "mastered": "能应用",
}

PROFILE_TEMPLATE = """# Learner Profile

- 姓名/称呼：
- 语言偏好：auto
- 每次可用时间：20 分钟
- 目标（学成后要做什么）：
- 已有基础：
- 偏好（例子/图/公式/代码/先练后讲）：
- 不喜欢的教学方式：
- 备注：

## 当前重点

-
"""


# ---------------------------------------------------------------- utilities


def today() -> date:
    return date.today()


def today_str() -> str:
    return today().isoformat()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SystemExit("Invalid date %r; expected YYYY-MM-DD" % value)


def slugify(text: str, maxlen: int = 60) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w一-鿿.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return (text or "item")[:maxlen]


def workspace(args) -> Path:
    home = Path(args.home).expanduser()
    return home.resolve()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit("Cannot read %s: %s" % (path, exc))


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(str(tmp), str(path))


def print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def normalize_config(cfg: dict):
    """Migrate v1 configs and fill missing v2 keys."""
    cfg = dict(cfg or {})
    changed = False

    if "retrieval_mode" not in cfg:
        legacy = cfg.get("allow_network")
        cfg["retrieval_mode"] = "web" if legacy else "local"
        changed = True
    if "allow_network" in cfg:
        cfg.pop("allow_network", None)
        changed = True
    if "mastery_threshold" in cfg:
        cfg.pop("mastery_threshold", None)
        changed = True

    for key, value in DEFAULT_CONFIG.items():
        if key not in cfg:
            cfg[key] = value
            changed = True

    if cfg.get("version") != DEFAULT_CONFIG["version"]:
        cfg["version"] = DEFAULT_CONFIG["version"]
        changed = True

    if cfg.get("retrieval_mode") not in ALLOWED_RETRIEVAL:
        cfg["retrieval_mode"] = "ask"
        changed = True

    return cfg, changed


def ensure_home(home: Path, lang: str = "auto") -> Path:
    for rel in ("learner", "sessions", "notes", "corpus/inbox"):
        (home / rel).mkdir(parents=True, exist_ok=True)

    config_path = home / "config.json"
    if not config_path.exists():
        cfg = dict(DEFAULT_CONFIG)
        cfg["language"] = lang
        save_json(config_path, cfg)
    else:
        cfg, changed = normalize_config(load_json(config_path, DEFAULT_CONFIG))
        if changed:
            save_json(config_path, cfg)

    profile = home / "learner" / "profile.md"
    if not profile.exists():
        profile.write_text(PROFILE_TEMPLATE, encoding="utf-8")

    for name in ("topics.json", "misconceptions.json", "schedule.json"):
        path = home / "learner" / name
        if not path.exists():
            save_json(path, {"version": 1, "items": []})

    return home


def load_items(home: Path, name: str) -> dict:
    data = load_json(home / "learner" / name, {"version": 1, "items": []})
    if name == "topics.json":
        changed = False
        for item in data.get("items", []):
            if "understanding" not in item and "mastery" in item:
                item["understanding"] = item.pop("mastery")
                changed = True
            if "understanding" in item:
                try:
                    level = max(0, min(3, int(item["understanding"])))
                except (TypeError, ValueError):
                    level = 0
                if item["understanding"] != level:
                    item["understanding"] = level
                    changed = True
        if changed:
            save_json(home / "learner" / name, data)
    return data


def save_items(home: Path, name: str, data: dict) -> None:
    save_json(home / "learner" / name, data)


# ---------------------------------------------------------------- extraction


class _HTMLText(HTMLParser):
    BLOCK = {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "tr", "section", "article", "blockquote", "pre", "table",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def _decode_html(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def extract_pdf(path: Path):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            proc = subprocess.run(
                [exe, "-layout", str(path), "-"],
                capture_output=True,
                timeout=180,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        import pypdf  # type: ignore
    except ImportError:
        try:
            import PyPDF2 as pypdf  # type: ignore
        except ImportError:
            raise SystemExit(
                "PDF extraction needs pdftotext (poppler) or pypdf.\n"
                "Convert the PDF to .txt/.md first, or install one of them."
            )

    try:
        reader = pypdf.PdfReader(str(path))
        parts = []
        for index, page in enumerate(reader.pages, 1):
            parts.append("\n<<<PAGE %d>>>\n" % index)
            parts.append(page.extract_text() or "")
        return "".join(parts)
    except Exception as exc:  # noqa: BLE001 - report extraction failure clearly
        raise SystemExit("PDF extraction failed: %s" % exc)


def extract_epub(path: Path):
    sections = []
    with zipfile.ZipFile(str(path)) as archive:
        names = [
            n for n in archive.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
        ]
        names.sort()
        for name in names:
            parser = _HTMLText()
            parser.feed(_decode_html(archive.read(name)))
            text = parser.text()
            if len(text) >= 40:
                sections.append((name, text))
    return sections


def chunk_by_size(text: str, size: int = 900, overlap: int = 120):
    chunks = []
    total = len(text)
    start = 0
    while start < total:
        end = min(start + size, total)
        if end < total:
            window = text[start:end]
            cuts = [
                window.rfind("\n\n"),
                window.rfind("。"),
                window.rfind("！"),
                window.rfind("？"),
                window.rfind(". "),
                window.rfind("\n"),
            ]
            cut = max(cuts)
            if cut >= int(size * 0.5):
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= total:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_by_lines(text: str, size: int = 900):
    chunks = []
    buffer = []
    length = 0
    start_line = 1
    line_no = 1
    for line in text.splitlines():
        if buffer and length + len(line) + 1 > size:
            body = "\n".join(buffer).strip()
            if body:
                chunks.append(("lines %d-%d" % (start_line, line_no - 1), body))
            buffer = []
            length = 0
            start_line = line_no
        buffer.append(line)
        length += len(line) + 1
        line_no += 1
    if buffer:
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(("lines %d-%d" % (start_line, line_no - 1), body))
    return chunks


def split_pages(text: str):
    pages = []
    marker = re.split(r"<<<PAGE (\d+)>>>", text)
    if len(marker) > 1:
        for i in range(1, len(marker), 2):
            pages.append(("p.%s" % marker[i], marker[i + 1]))
        return pages
    raw = text.split("\f")
    for i, page in enumerate(raw, 1):
        if page.strip():
            pages.append(("p.%d" % i, page))
    return pages


def build_chunks(source_id: str, segments, url: str = ""):
    chunks = []
    counter = 0
    for locator, text in segments:
        if locator is None:
            pieces = chunk_by_lines(text)
        else:
            pieces = [(locator, p) for p in chunk_by_size(text)]
        for loc, body in pieces:
            counter += 1
            chunks.append({
                "id": "%s-c%04d" % (source_id, counter),
                "source": source_id,
                "locator": loc,
                "text": body,
                "url": url,
            })
    return chunks


# ---------------------------------------------------------------- search


TOKEN_RE = re.compile(r"[a-z0-9_]+|[一-鿿]+")


def tokenize(text: str):
    tokens = []
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if re.fullmatch(r"[一-鿿]+", token):
            tokens.extend(token)
            tokens.extend(token[i:i + 2] for i in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


def bm25(query_tokens, docs_tokens, k1: float = 1.5, b: float = 0.75):
    count = len(docs_tokens)
    if not count:
        return []
    avg_len = sum(len(doc) for doc in docs_tokens) / count
    doc_freq = Counter()
    for doc in docs_tokens:
        doc_freq.update(set(doc))
    query = Counter(query_tokens)
    scores = []
    for doc in docs_tokens:
        term_freq = Counter(doc)
        length = len(doc)
        score = 0.0
        for term, qtf in query.items():
            if term not in term_freq:
                continue
            idf = math.log(1 + (count - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            tf = term_freq[term]
            score += idf * (tf * (k1 + 1)) / (
                tf + k1 * (1 - b + b * length / (avg_len or 1))
            ) * qtf
        scores.append(score)
    return scores


def snippet(text: str, query: str, width: int = 160) -> str:
    terms = [t for t in tokenize(query) if len(t) >= 2 or re.match(r"[a-z0-9]", t)]
    lowered = text.lower()
    position = -1
    for term in terms:
        found = lowered.find(term.lower())
        if found >= 0 and (position < 0 or found < position):
            position = found
    if position < 0:
        body = text[:width]
        prefix = ""
        suffix = "..." if len(text) > width else ""
    else:
        start = max(0, position - width // 3)
        end = min(len(text), start + width)
        body = text[start:end]
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
    return (prefix + body + suffix).replace("\n", " ").strip()


# ---------------------------------------------------------------- SM-2


def sm2_update(item: dict, grade: int, on_date: date) -> dict:
    grade = max(0, min(5, int(grade)))
    ease = float(item.get("ease", 2.5))
    interval = int(item.get("interval", 0))
    reps = int(item.get("reps", 0))

    if grade < 3:
        reps = 0
        interval = 1
        item["lapses"] = int(item.get("lapses", 0)) + 1
        ease = max(1.3, ease - 0.2)
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = max(1, round(interval * ease))
        ease = max(1.3, ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))

    item.update({
        "ease": round(ease, 3),
        "interval": interval,
        "reps": reps,
        "last_grade": grade,
        "last_review": on_date.isoformat(),
        "due": (on_date + timedelta(days=interval)).isoformat(),
    })
    return item


# ---------------------------------------------------------------- commands


def cmd_doctor(args) -> int:
    home = workspace(args)
    print("education-mode %s" % VERSION)
    print("python      : %s" % sys.version.split()[0])
    print("platform    : %s" % sys.platform)
    print("workspace   : %s" % home)

    writable = False
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError as exc:
        print("writable    : NO (%s)" % exc)
    if writable:
        print("writable    : yes")

    pdftotext = shutil.which("pdftotext")
    print("pdftotext   : %s" % (pdftotext or "not found"))
    try:
        import pypdf  # type: ignore  # noqa: F401
        print("pypdf       : available")
    except ImportError:
        print("pypdf       : not found")

    config_path = home / "config.json"
    if config_path.exists():
        cfg, _ = normalize_config(load_json(config_path, DEFAULT_CONFIG))
        print("retrieval   : %s" % cfg.get("retrieval_mode"))
        print("web_cache   : %s" % cfg.get("web_cache"))
        print("context     : %s tokens" % cfg.get("context_window"))
        print("multimodal  : %s" % cfg.get("multimodal"))
        if cfg.get("retrieval_mode") == "local":
            print("network     : disabled by retrieval_mode=local")
        if cfg.get("multimodal"):
            print("WARNING     : multimodal is true, but this skill is designed for non-multimodal models")
    else:
        print("config      : missing (run init)")

    for name in ("topics.json", "misconceptions.json", "schedule.json"):
        path = home / "learner" / name
        if path.exists():
            data = load_json(path, {"items": []})
            print("%-12s: %d items" % (name, len(data.get("items", []))))
    return 0


def cmd_init(args) -> int:
    home = ensure_home(workspace(args), lang=args.lang)
    print("workspace ready: %s" % home)
    print("next: put sources in %s" % (home / "corpus" / "inbox"))
    return 0


def cmd_status(args) -> int:
    home = ensure_home(workspace(args))
    config, _ = normalize_config(load_json(home / "config.json", DEFAULT_CONFIG))
    topics = load_items(home, "topics.json")["items"]
    misconceptions = load_items(home, "misconceptions.json")["items"]
    schedule = load_items(home, "schedule.json")["items"]
    current = today()

    due = [item for item in schedule if item.get("due", "9999-12-31") <= current.isoformat()]
    open_mis = [item for item in misconceptions if item.get("status") == "open"]
    sessions = sorted((home / "sessions").glob("*.md"))
    corpus = [p for p in (home / "corpus").iterdir() if p.is_dir() and p.name != "inbox"]

    if args.json:
        print_json({
            "home": str(home),
            "config": config,
            "topics": topics,
            "due": due,
            "open_misconceptions": open_mis,
            "recent_sessions": [p.name for p in sessions[-5:]],
            "corpus_sources": [p.name for p in corpus],
        })
        return 0

    print("workspace: %s" % home)
    print("retrieval: %s  (context %s, multimodal %s)" % (
        config.get("retrieval_mode"), config.get("context_window"), config.get("multimodal"),
    ))
    print("topics   : %d  (能应用 %d, 探索中 %d)" % (
        len(topics),
        sum(1 for t in topics if t.get("status") == "mastered"),
        sum(1 for t in topics if t.get("status") == "learning"),
    ))
    print("reviews  : %d total, %d due today" % (len(schedule), len(due)))
    print("open misconceptions: %d" % len(open_mis))
    print("corpus   : %d sources" % len(corpus))
    if topics:
        print("\nTop topics:")
        for topic in topics[:8]:
            level = int(topic.get("understanding", topic.get("mastery", 0)) or 0)
            print("  %-28s %-10s %-16s next=%s" % (
                topic.get("id", "?"),
                STATUS_LABELS.get(topic.get("status", ""), topic.get("status", "?")),
                UNDERSTANDING_LABELS.get(level, str(level)),
                topic.get("next_review") or "-",
            ))
    if due:
        print("\nDue now:")
        for item in due[:8]:
            print("  %-6s %-28s %s" % (
                item.get("id", "?"),
                item.get("topic_id", "?"),
                item.get("question", "")[:60],
            ))
    if sessions:
        print("\nRecent sessions:")
        for path in sessions[-5:]:
            print("  %s" % path.name)
    return 0


CONFIG_BOOL_KEYS = {"web_cache", "multimodal"}
CONFIG_INT_KEYS = {"session_minutes", "max_explanation_words", "context_window"}


def cmd_config(args) -> int:
    home = ensure_home(workspace(args))
    config, _ = normalize_config(load_json(home / "config.json", DEFAULT_CONFIG))

    if not args.set_values:
        print_json(config)
        return 0

    for pair in args.set_values:
        if "=" not in pair:
            raise SystemExit("Expected KEY=VALUE, got %r" % pair)
        key, raw = pair.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if key == "retrieval_mode":
            if raw not in ALLOWED_RETRIEVAL:
                raise SystemExit("retrieval_mode must be one of %s" % (ALLOWED_RETRIEVAL,))
            config[key] = raw
        elif key in CONFIG_BOOL_KEYS:
            config[key] = raw.lower() in ("1", "true", "yes", "on")
        elif key in CONFIG_INT_KEYS:
            try:
                config[key] = int(raw)
            except ValueError:
                raise SystemExit("%s must be an integer" % key)
        elif key in ("language", "hint_policy", "review_algorithm"):
            config[key] = raw
        else:
            raise SystemExit("Unknown config key: %s" % key)

    if config["context_window"] < 8000:
        raise SystemExit("context_window must be >= 8000")
    if config["max_explanation_words"] < 50:
        raise SystemExit("max_explanation_words must be >= 50")
    if config["session_minutes"] < 5:
        raise SystemExit("session_minutes must be >= 5")
    if config["language"] not in ("auto", "zh", "en"):
        raise SystemExit("language must be auto, zh or en")
    if config["hint_policy"] != "one_level_at_a_time":
        raise SystemExit("hint_policy is currently fixed to one_level_at_a_time")
    if config["review_algorithm"] != "sm2":
        raise SystemExit("review_algorithm is currently fixed to sm2")

    save_json(home / "config.json", config)
    print_json(config)
    return 0


def cmd_source(args) -> int:
    home = ensure_home(workspace(args))
    if args.id:
        path = home / "corpus" / args.id / "meta.json"
        if not path.exists():
            raise SystemExit("Source not found: %s" % args.id)
        print_json(load_json(path, {}))
        return 0

    rows = []
    for path in sorted((home / "corpus").glob("*/meta.json")):
        rows.append(load_json(path, {}))
    if args.json:
        print_json(rows)
        return 0
    if not rows:
        print("No sources indexed.")
        return 0
    for meta in rows:
        print("%-20s %-6s %-6s %s" % (
            meta.get("id", "?"),
            meta.get("source_kind", "local"),
            meta.get("chunks", 0),
            meta.get("title", ""),
        ))
        if meta.get("url"):
            print("  url: %s (accessed %s)" % (meta["url"], meta.get("retrieved_at") or "-"))
    return 0


def cmd_read(args) -> int:
    home = ensure_home(workspace(args))
    path = home / "corpus" / args.source / "text.txt"
    if not path.exists():
        raise SystemExit("Source not found: %s" % args.source)
    text = read_text(path)
    total = len(text)
    start = max(0, args.offset)
    if start >= total:
        raise SystemExit("Offset %d is beyond the end (%d chars)" % (start, total))
    limit = args.max_chars if args.max_chars and args.max_chars > 0 else total
    end = min(total, start + limit)
    print(text[start:end])
    if end < total:
        eprint("[truncated] showed %d-%d of %d chars; next --offset %d" % (
            start, end, total, end,
        ))
    return 0


def cmd_outline(args) -> int:
    home = ensure_home(workspace(args))
    chunks = _load_chunks(home, args.source)
    if not chunks:
        raise SystemExit("Source not indexed: %s" % args.source)
    for chunk in chunks:
        first_line = " ".join(chunk.get("text", "").split())
        print("%-16s %s" % (chunk.get("locator", "?"), first_line[:120]))
    print("chunks: %d" % len(chunks))
    return 0


def cmd_ingest(args) -> int:
    home = ensure_home(workspace(args))
    source = Path(args.file).expanduser().resolve()
    if not source.exists():
        raise SystemExit("File not found: %s" % source)

    source_id = slugify(args.id or source.stem)
    suffix = source.suffix.lower()

    if suffix in (".txt", ".md", ".markdown"):
        text = read_text(source)
        segments = [(None, text)]
        fmt = suffix.lstrip(".")
    elif suffix == ".pdf":
        text = extract_pdf(source)
        segments = split_pages(text)
        fmt = "pdf"
    elif suffix == ".epub":
        segments = extract_epub(source)
        text = "\n\n".join(body for _, body in segments)
        fmt = "epub"
    else:
        raise SystemExit("Unsupported format %r; use .txt, .md, .epub or .pdf" % suffix)

    if not text.strip():
        raise SystemExit("No text extracted from %s" % source)

    url = (args.url or "").strip()
    retrieved_at = (args.retrieved_at or "").strip()
    if url and not retrieved_at:
        retrieved_at = today_str()
    if retrieved_at:
        parse_date(retrieved_at)
    title = (args.title or source.stem).strip()

    chunks = build_chunks(source_id, segments, url=url)
    dest = home / "corpus" / source_id
    dest.mkdir(parents=True, exist_ok=True)

    with (dest / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    (dest / "text.txt").write_text(text, encoding="utf-8", newline="\n")
    save_json(dest / "meta.json", {
        "id": source_id,
        "title": title,
        "source_path": str(source),
        "format": fmt,
        "source_kind": "web" if url else "local",
        "url": url,
        "retrieved_at": retrieved_at,
        "created": today_str(),
        "chars": len(text),
        "chunks": len(chunks),
    })

    print("indexed %s: %d chars, %d chunks, kind=%s" % (
        source_id, len(text), len(chunks), "web" if url else "local",
    ))
    print("path: %s" % dest)
    if url:
        print("cite: [W:%s %s accessed %s]" % (source_id, url, retrieved_at))
    print("search: python edu.py search --home %s --query \"...\" --source %s" % (home, source_id))
    return 0


def _load_chunks(home: Path, source_id=None):
    root = home / "corpus"
    if source_id:
        paths = [root / source_id / "chunks.jsonl"]
    else:
        paths = sorted(root.glob("*/chunks.jsonl"))
    chunks = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunks.append(json.loads(line))
                except ValueError:
                    continue
    return chunks


def cmd_search(args) -> int:
    home = ensure_home(workspace(args))
    chunks = _load_chunks(home, args.source)
    if not chunks:
        print("No indexed chunks. Run ingest first.")
        return 0

    query_tokens = tokenize(args.query)
    docs = [tokenize(chunk.get("text", "")) for chunk in chunks]
    scores = bm25(query_tokens, docs)
    ranked = sorted(
        ((score, chunk) for score, chunk in zip(scores, chunks) if score > 0),
        key=lambda pair: pair[0],
        reverse=True,
    )[: max(1, args.top)]

    if args.json:
        print_json([
            {
                "id": chunk.get("id"),
                "source": chunk.get("source"),
                "locator": chunk.get("locator"),
                "url": chunk.get("url", ""),
                "score": round(score, 4),
                "text": chunk.get("text", ""),
            }
            for score, chunk in ranked
        ])
        return 0

    if not ranked:
        print("No matches for %r" % args.query)
        return 0

    for index, (score, chunk) in enumerate(ranked, 1):
        print("[%d] %s %s  score=%.3f" % (
            index, chunk.get("source"), chunk.get("locator"), score,
        ))
        if chunk.get("url"):
            print("    url: %s" % chunk.get("url"))
        print("    %s" % snippet(chunk.get("text", ""), args.query))
        print("    chunk=%s" % chunk.get("id"))
    return 0


def cmd_add_review(args) -> int:
    home = ensure_home(workspace(args))
    schedule = load_items(home, "schedule.json")
    items = schedule["items"]
    next_id = 1
    for item in items:
        match = re.fullmatch(r"r(\d+)", item.get("id", ""))
        if match:
            next_id = max(next_id, int(match.group(1)) + 1)

    due = args.due or today_str()
    parse_date(due)
    item = {
        "id": "r%04d" % next_id,
        "topic_id": args.topic_id.strip(),
        "question": args.question,
        "answer": args.answer,
        "ease": 2.5,
        "interval": 1,
        "reps": 0,
        "lapses": 0,
        "due": due,
        "last_grade": None,
        "created": today_str(),
    }
    items.append(item)
    save_items(home, "schedule.json", schedule)
    print("added %s due %s: %s" % (item["id"], item["due"], item["question"]))
    return 0


def cmd_due(args) -> int:
    home = ensure_home(workspace(args))
    target = parse_date(args.date) if args.date else today()
    schedule = load_items(home, "schedule.json")["items"]
    due = [item for item in schedule if item.get("due", "9999-12-31") <= target.isoformat()]
    due.sort(key=lambda item: (item.get("due", ""), item.get("id", "")))

    if args.json:
        print_json(due)
        return 0
    if not due:
        print("No reviews due on %s." % target.isoformat())
        return 0
    for item in due:
        print("%-6s %-10s %-28s %s" % (
            item.get("id"), item.get("due"), item.get("topic_id"),
            item.get("question", "")[:70],
        ))
    return 0


def cmd_review(args) -> int:
    home = ensure_home(workspace(args))
    schedule = load_items(home, "schedule.json")
    item = next((entry for entry in schedule["items"] if entry.get("id") == args.item_id), None)
    if item is None:
        raise SystemExit("Review item not found: %s" % args.item_id)
    on_date = parse_date(args.date) if args.date else today()
    sm2_update(item, args.grade, on_date)
    save_items(home, "schedule.json", schedule)
    print("%s graded %d -> interval %d, due %s" % (
        item["id"], args.grade, item["interval"], item["due"],
    ))
    return 0


def _next_session_number(home: Path) -> int:
    highest = 0
    for path in (home / "sessions").glob("*.md"):
        match = re.match(r"(\d{4})-", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _append_misconceptions(home: Path, topic_id: str, raw_entries):
    if not raw_entries:
        return []
    store = load_items(home, "misconceptions.json")
    items = store["items"]
    next_id = 1
    for item in items:
        match = re.fullmatch(r"M(\d+)", item.get("id", ""))
        if match:
            next_id = max(next_id, int(match.group(1)) + 1)

    created = []
    for raw in raw_entries:
        parts = [part.strip() for part in raw.split("|")]
        wrong = parts[0] if parts else raw.strip()
        evidence = parts[1] if len(parts) > 1 else ""
        correction = parts[2] if len(parts) > 2 else ""
        entry = {
            "id": "M%04d" % next_id,
            "topic_id": topic_id,
            "wrong_model": wrong,
            "evidence": evidence,
            "correction": correction,
            "status": "open",
            "created": today_str(),
        }
        items.append(entry)
        created.append(entry)
        next_id += 1

    save_items(home, "misconceptions.json", store)
    return created


def cmd_checkpoint(args) -> int:
    home = ensure_home(workspace(args))
    topic_id = args.topic_id.strip()
    if not topic_id:
        raise SystemExit("--topic-id is required")

    topics = load_items(home, "topics.json")
    topic = next((entry for entry in topics["items"] if entry.get("id") == topic_id), None)
    if topic is None:
        topic = {
            "id": topic_id,
            "title": args.topic_title or topic_id,
            "prereqs": [],
            "status": "learning",
            "understanding": 0,
            "sessions": 0,
            "last_seen": today_str(),
            "next_review": None,
        }
        topics["items"].append(topic)

    topic["sessions"] = int(topic.get("sessions", 0)) + 1
    topic["last_seen"] = today_str()
    if args.topic_title:
        topic["title"] = args.topic_title
    level = args.understanding if args.understanding is not None else args.mastery
    if level is not None:
        topic["understanding"] = max(0, min(3, level))
    if args.status:
        topic["status"] = args.status
    if args.next_review:
        parse_date(args.next_review)
        topic["next_review"] = args.next_review
    save_items(home, "topics.json", topics)

    created = _append_misconceptions(home, topic_id, args.misconception)

    number = _next_session_number(home)
    filename = "%04d-%s-%s.md" % (number, today_str(), slugify(topic_id.replace("/", "-")))
    path = home / "sessions" / filename

    lines = [
        "# Session %04d — %s — %s" % (number, today_str(), args.mode),
        "",
        "- Topic: %s" % topic_id,
        "- Goal: %s" % (args.goal or "-"),
        "- Time box: %s" % (args.time or "-"),
        "- Mode: %s" % args.mode,
        "- Retrieval: %s" % (args.retrieval or "-"),
        "",
        "## 用户表达",
        "",
        args.summary or "<未记录>",
        "",
        "## 观察",
        "",
        "- 理解状态: %s" % (
            UNDERSTANDING_LABELS.get(level, "未记录") if level is not None else "未记录"
        ),
        "- 支持程度: %s" % (args.highest_hint or "-"),
        "",
        "## 证据",
        "",
    ]
    if args.evidence:
        lines.extend("- %s" % entry for entry in args.evidence)
    else:
        lines.append("- <未记录>")
    lines.extend(["", "## 误解", ""])
    if created:
        for entry in created:
            lines.append("- %s：%s（证据：%s；纠正：%s）" % (
                entry["id"], entry["wrong_model"],
                entry["evidence"] or "-", entry["correction"] or "-",
            ))
    else:
        lines.append("- none")
    lines.extend(["", "## 下一步", "", "- %s" % (args.next or "<未记录>"), ""])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print("session written: %s" % path)
    if created:
        print("misconceptions: %s" % ", ".join(entry["id"] for entry in created))
    return 0


def cmd_validate(args) -> int:
    home = ensure_home(workspace(args))
    errors = []
    warnings = []

    config, _ = normalize_config(load_json(home / "config.json", DEFAULT_CONFIG))
    if config.get("retrieval_mode") not in ALLOWED_RETRIEVAL:
        errors.append("invalid retrieval_mode: %r" % config.get("retrieval_mode"))
    if not isinstance(config.get("context_window"), int) or config.get("context_window", 0) < 8000:
        errors.append("context_window must be an integer >= 8000")
    if config.get("multimodal"):
        warnings.append("multimodal is true, but this skill is designed for non-multimodal models")

    seen_topics = set()
    for topic in load_items(home, "topics.json")["items"]:
        missing = [key for key in ("id", "status", "understanding") if key not in topic]
        if missing:
            errors.append("topic missing fields %s: %r" % (missing, topic))
        if topic.get("id") in seen_topics:
            errors.append("duplicate topic id: %s" % topic.get("id"))
        seen_topics.add(topic.get("id"))
        if topic.get("status") not in ("new", "learning", "review", "mastered"):
            warnings.append("unknown topic status: %r" % topic.get("status"))
        if not isinstance(topic.get("understanding"), int) or not 0 <= topic.get("understanding", 0) <= 3:
            errors.append("topic understanding out of range: %r" % topic)

    seen_mis = set()
    for item in load_items(home, "misconceptions.json")["items"]:
        if item.get("id") in seen_mis:
            errors.append("duplicate misconception id: %s" % item.get("id"))
        seen_mis.add(item.get("id"))

    seen_reviews = set()
    for item in load_items(home, "schedule.json")["items"]:
        if item.get("id") in seen_reviews:
            errors.append("duplicate review id: %s" % item.get("id"))
        seen_reviews.add(item.get("id"))
        if "due" not in item:
            errors.append("review missing due: %s" % item.get("id"))
        else:
            try:
                parse_date(item["due"])
            except SystemExit:
                errors.append("bad due date on %s: %r" % (item.get("id"), item.get("due")))

    seen_sessions = set()
    for path in sorted((home / "sessions").glob("*.md")):
        match = re.match(r"(\d{4})-", path.name)
        if match:
            number = int(match.group(1))
            if number in seen_sessions:
                errors.append("duplicate session number: %04d" % number)
            seen_sessions.add(number)

    for path in sorted((home / "corpus").glob("*/meta.json")):
        meta = load_json(path, {})
        if not meta.get("id"):
            errors.append("corpus meta missing id: %s" % path)
        if meta.get("source_kind") == "web" and not meta.get("url"):
            errors.append("web source missing url: %s" % path)
        if meta.get("url") and not meta.get("retrieved_at"):
            errors.append("web source missing retrieved_at: %s" % path)

    for path in sorted((home / "corpus").glob("*/chunks.jsonl")):
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    errors.append("%s line %d is not valid JSON" % (path, line_no))
                    break
                if not chunk.get("text") or not chunk.get("source"):
                    errors.append("%s line %d missing text/source" % (path, line_no))

    for warning in warnings:
        print("WARN: %s" % warning)
    for error in errors:
        print("ERROR: %s" % error)
    if errors:
        print("validation failed: %d error(s)" % len(errors))
        return 1
    print("validation ok: retrieval=%s, %d topic(s), %d review(s), %d session(s)" % (
        config.get("retrieval_mode"), len(seen_topics), len(seen_reviews), len(seen_sessions),
    ))
    return 0


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edu.py",
        description="Local-first learning workspace CLI for education-mode.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_home(sp):
        sp.add_argument("--home", default=os.environ.get("EDU_HOME", str(Path.home() / ".edu")),
                        help="learning workspace (default: $EDU_HOME or ~/.edu)")

    p = sub.add_parser("doctor", help="check deployment environment")
    add_home(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init", help="create a learning workspace")
    add_home(p)
    p.add_argument("--lang", default="auto", choices=("auto", "zh", "en"))
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="show learner state")
    add_home(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("config", help="show or change configuration")
    add_home(p)
    p.add_argument("--set", dest="set_values", action="append", default=[],
                   metavar="KEY=VALUE", help="e.g. --set retrieval_mode=local")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("ingest", help="index a local or cached web source")
    add_home(p)
    p.add_argument("--file", required=True)
    p.add_argument("--id", default=None, help="source id (default: file stem)")
    p.add_argument("--title", default=None, help="human-readable title")
    p.add_argument("--url", default=None, help="source URL for web-derived material")
    p.add_argument("--retrieved-at", default=None, help="YYYY-MM-DD (default: today for web)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("source", help="show corpus metadata")
    add_home(p)
    p.add_argument("--id", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source)

    p = sub.add_parser("read", help="print a full source or character range")
    add_home(p)
    p.add_argument("--source", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--max-chars", type=int, default=400000,
                   help="0 means no limit (default: 400000)")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("outline", help="print chunk locators and opening lines")
    add_home(p)
    p.add_argument("--source", required=True)
    p.set_defaults(func=cmd_outline)

    p = sub.add_parser("search", help="BM25 search over indexed chunks")
    add_home(p)
    p.add_argument("--query", required=True)
    p.add_argument("--source", default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("add-review", help="add a spaced-repetition item")
    add_home(p)
    p.add_argument("--topic-id", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--due", default=None)
    p.set_defaults(func=cmd_add_review)

    p = sub.add_parser("due", help="list due reviews")
    add_home(p)
    p.add_argument("--date", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("review", help="grade a review item (SM-2)")
    add_home(p)
    p.add_argument("--item-id", required=True)
    p.add_argument("--grade", type=int, required=True)
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("checkpoint", help="append a session record")
    add_home(p)
    p.add_argument("--topic-id", required=True)
    p.add_argument("--topic-title", default=None)
    p.add_argument("--mode", required=True,
                   choices=("curiosity", "systematic", "skill-drill", "deep-read"))
    p.add_argument("--retrieval", default=None, choices=ALLOWED_RETRIEVAL)
    p.add_argument("--goal", default=None)
    p.add_argument("--time", default=None)
    p.add_argument("--summary", default=None, help="what the learner said or did")
    p.add_argument("--evidence", action="append", default=[])
    p.add_argument("--misconception", action="append", default=[],
                   help='format: "wrong | evidence | correction"')
    p.add_argument("--next", default=None)
    p.add_argument("--understanding", type=int, default=None, choices=(0, 1, 2, 3))
    p.add_argument("--mastery", type=int, default=None, help=argparse.SUPPRESS)
    p.add_argument("--status", default=None,
                   choices=("new", "learning", "review", "mastered"),
                   help=argparse.SUPPRESS)
    p.add_argument("--next-review", default=None)
    p.add_argument("--highest-hint", default=None)
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("validate", help="check workspace integrity")
    add_home(p)
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
