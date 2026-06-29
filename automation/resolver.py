"""
Universal Jira -> Wiki destination resolver.

Resolution order (first hit wins):
  1. CLI overrides (handled in sync.py before resolver is called)
  2. config.yaml exact project_key match
  3. Cached previous resolution (automation/cache/resolved_<project_key>.json)
  4. Keyword overlap: Jira project_name + components -> wiki book name
  5. Claude API classification (uses ANTHROPIC_API_KEY)
  6. Error with helpful suggestions

Output of every resolver call is cached so repeated syncs for the same project
don't re-classify.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
WIKI_CACHE = WORKSPACE / "wiki_cache"
RESOLVE_CACHE = HERE / "cache"
RESOLVE_CACHE.mkdir(parents=True, exist_ok=True)

# Inventory paths (already produced by fetch_wiki_inventory.py earlier in the session)
INVENTORY_JSON = WIKI_CACHE / "wiki_inventory.json"
ALL_BOOKS_JSON = WIKI_CACHE / "all_books.json"
ALL_CHAPTERS_JSON = WIKI_CACHE / "all_chapters.json"

STOPWORDS = {
    "the", "and", "for", "with", "from", "of", "to", "a", "an",
    "system", "module", "page", "spec", "specification", "project",
    "ongoing", "general", "test", "tests", "fix", "fixes", "fixed",
    "phase", "release", "pilot", "core", "configuration", "v", "ohrm",
    "orangehrm", "7", "8", "0", "1", "2", "3", "4", "5", "6", "9",
}

# Team-named projects (Game of Thrones / LOTR houses + sprint teams) that
# don't map to a single feature area. These always need a CLI override.
TEAM_PROJECTS = {
    "AN":  "Baratheons", "BW": "BlackWood", "ENG": "Velaryons",
    "HT":  "HighTower", "LAN": "Lannisters", "RV": "Rivendell",
    "TAR": "Targaryens", "TEC": "TechNext", "GD": "Starks",
}


@dataclass
class Resolution:
    project_key: str
    project_name: str
    source_page_id: Optional[int] = None
    target_page_id: Optional[int] = None
    target_chapter_id: Optional[int] = None
    new_page_title: Optional[str] = None
    book_id: Optional[int] = None
    book_name: Optional[str] = None
    chapter_name: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    suggestions: list = None
    op: str = "create"   # "create" or "update"

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v not in (None, [], "")}


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return {w for w in text.split() if len(w) > 2 and w not in STOPWORDS}


def _load_inventory():
    if not INVENTORY_JSON.exists():
        raise SystemExit(
            f"Missing {INVENTORY_JSON}. Run fetch_wiki_inventory.py first to cache "
            "the wiki tree, or the resolver can't pick a destination."
        )
    pages = json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))
    books = json.loads(ALL_BOOKS_JSON.read_text(encoding="utf-8"))
    chapters = json.loads(ALL_CHAPTERS_JSON.read_text(encoding="utf-8"))
    return pages, books, chapters


def _keyword_match(project_name: str, components: list[str], books) -> Optional[tuple]:
    """Score every book by token overlap with project_name + components. Return best (book, score)."""
    pname_tokens = _tokens(project_name)
    comp_tokens = set()
    for c in components or []:
        comp_tokens |= _tokens(c)
    query_tokens = pname_tokens | comp_tokens
    if not query_tokens:
        return None

    scored = []
    for b in books:
        btokens = _tokens(b["name"])
        if not btokens:
            continue
        overlap = query_tokens & btokens
        if overlap:
            # Score = overlap count / size of smaller side
            score = len(overlap) / min(len(query_tokens), len(btokens))
            scored.append((b, score, sorted(overlap)))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[1])
    return scored[0]


def _ai_classify(project_name: str, summary: str, components: list[str], issue_type: str,
                 books: list[dict], model: str = "claude-sonnet-4-6") -> Optional[dict]:
    """Ask Claude to pick the best wiki book + chapter for this Jira issue."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None

    book_list = "\n".join(f"- id={b['id']}  name={b['name']!r}" for b in books)
    user = (
        f"Pick the single best wiki book for this Jira issue.\n\n"
        f"Jira project: {project_name}\n"
        f"Issue type:   {issue_type}\n"
        f"Summary:      {summary}\n"
        f"Components:   {', '.join(components) if components else '(none)'}\n\n"
        f"Available wiki books:\n{book_list}\n\n"
        f"Return STRICT JSON: {{\"book_id\": <int>, \"book_name\": \"...\", \"confidence\": <0..1>, \"reason\": \"...\"}}\n"
        f"Confidence 1.0 = perfect match. <0.5 = unsure, treat as failure.\n"
        f"If no book is a good fit, return {{\"book_id\": null, \"confidence\": 0.0, \"reason\": \"...\"}}."
    )
    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": user}],
    )
    text = resp.content[0].text
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def resolve(project_key: str, project_name: str = "", issue_summary: str = "",
            issue_type: str = "Story", components: Optional[list] = None,
            config: Optional[dict] = None, use_ai: bool = True,
            min_confidence: float = 0.5) -> Resolution:
    """Main entry point. Returns a Resolution with as many fields filled as possible."""
    config = config or {}
    components = components or []

    # ---- Strategy 1: complete config.yaml entry ----
    proj_cfg = config.get("projects", {}).get(project_key, {})
    cfg_has_source = bool(proj_cfg.get("source_page_id"))
    cfg_has_target = bool(proj_cfg.get("target_page_id") or
                          (proj_cfg.get("target_chapter_id") and proj_cfg.get("new_page_title")))
    if proj_cfg and cfg_has_source and cfg_has_target:
        return Resolution(
            project_key=project_key,
            project_name=proj_cfg.get("project_name", project_name) or project_key,
            source_page_id=proj_cfg.get("source_page_id"),
            target_page_id=proj_cfg.get("target_page_id"),
            target_chapter_id=proj_cfg.get("target_chapter_id"),
            new_page_title=proj_cfg.get("new_page_title"),
            book_id=proj_cfg.get("book_id"),
            book_name=proj_cfg.get("book_name"),
            chapter_name=proj_cfg.get("chapter_name"),
            confidence=1.0,
            reason="config.yaml exact match",
            op="update" if proj_cfg.get("target_page_id") else "create",
        )

    # ---- Strategy 2: cached previous resolution ----
    cache_path = RESOLVE_CACHE / f"resolved_{project_key}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return Resolution(**cached, reason=cached.get("reason", "") + " (cache hit)")

    # ---- Inventory load (needed for the next strategies) ----
    pages, books, chapters = _load_inventory()

    # ---- Detect team projects early — they always need an override ----
    if project_key in TEAM_PROJECTS:
        return Resolution(
            project_key=project_key,
            project_name=project_name or TEAM_PROJECTS[project_key],
            confidence=0.0,
            reason=f"{project_key} is a sprint-team project ({TEAM_PROJECTS[project_key]}) without a single feature area — pass --target-chapter-id and --new-page-title explicitly, or add a config.yaml entry per epic.",
            suggestions=["use --target-chapter-id <id>", "use --new-page-title <str>", "or pin to a specific feature via config.yaml"],
        )

    # ---- Strategy 3: keyword overlap ----
    km = _keyword_match(project_name, components, books)
    if km and km[1] >= 0.5:
        book, score, overlap = km
        # Pick the first chapter in that book as a default (user can override)
        book_chapters = [c for c in chapters if c["book_id"] == book["id"]]
        chap = book_chapters[0] if book_chapters else None
        # Style reference: pick the first existing page in the target chapter as the
        # source. Falls back to any page in the book if the chapter is empty.
        src_candidates = [p for p in pages if p["chapter_id"] == (chap["id"] if chap else 0)]
        if not src_candidates:
            src_candidates = [p for p in pages if p["book_id"] == book["id"]]
        src_page_id = src_candidates[0]["id"] if src_candidates else None
        result = Resolution(
            project_key=project_key,
            project_name=project_name,
            source_page_id=src_page_id,
            target_page_id=None,
            target_chapter_id=chap["id"] if chap else None,
            new_page_title=project_name or project_key,
            book_id=book["id"],
            book_name=book["name"],
            chapter_name=chap["name"] if chap else None,
            confidence=score,
            reason=f"keyword overlap on {overlap}; book='{book['name']}'; "
                   f"source_page_id={src_page_id} (style reference, first page in chapter)",
            op="create",
        )
        cache_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    # ---- Strategy 4: AI classification ----
    if use_ai:
        ai = _ai_classify(project_name, issue_summary, components, issue_type, books)
        if ai and ai.get("book_id") and ai.get("confidence", 0) >= min_confidence:
            book = next((b for b in books if b["id"] == ai["book_id"]), None)
            if book:
                book_chapters = [c for c in chapters if c["book_id"] == book["id"]]
                chap = book_chapters[0] if book_chapters else None
                src_candidates = [p for p in pages if p["chapter_id"] == (chap["id"] if chap else 0)]
                if not src_candidates:
                    src_candidates = [p for p in pages if p["book_id"] == book["id"]]
                src_page_id = src_candidates[0]["id"] if src_candidates else None
                result = Resolution(
                    project_key=project_key,
                    project_name=project_name,
                    source_page_id=src_page_id,
                    target_chapter_id=chap["id"] if chap else None,
                    new_page_title=issue_summary or project_name or project_key,
                    book_id=book["id"],
                    book_name=book["name"],
                    chapter_name=chap["name"] if chap else None,
                    confidence=ai["confidence"],
                    reason=f"AI classification: {ai.get('reason', '(no reason given)')}",
                    op="create",
                )
                cache_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
                return result

    # ---- Strategy 5: error with suggestions ----
    top3 = []
    km_all = _keyword_match(project_name, components, books)
    if km_all:
        top3 = [f"{km_all[0]['name']} (score {km_all[1]:.2f})"]
    return Resolution(
        project_key=project_key,
        project_name=project_name,
        confidence=0.0,
        reason="No high-confidence destination found. Add to config.yaml or pass --target-chapter-id explicitly.",
        suggestions=top3 + [
            "Pass --target-chapter-id <id>",
            "Pass --target-page-id <id> for an update",
            "Pass --source-page-id <id> for the comparison source",
            "Or run: py resolver.py <project_key> to inspect what the resolver sees",
        ],
    )


# ----------------------------------------------------------------------
# Debug CLI: py resolver.py <project_key> [project_name] [components...]
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("Usage: py resolver.py <project_key> [project_name] [issue_summary]")
    pk = sys.argv[1]
    pname = sys.argv[2] if len(sys.argv) > 2 else ""
    summ = sys.argv[3] if len(sys.argv) > 3 else ""

    # Try to load config.yaml if present
    config = {}
    cfg_path = HERE / "config.yaml"
    if cfg_path.exists():
        import yaml
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    r = resolve(pk, pname, summ, config=config)
    print(json.dumps(r.to_dict(), indent=2, default=str))
