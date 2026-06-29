"""
Fetch a snapshot of the BookStack wiki inventory and cache it locally.

WHY
---
`automation/resolver.py` reads three cached JSON files to score Jira
project keys against BookStack books / chapters / pages:

  - wiki_cache/wiki_inventory.json   (flat list of all pages)
  - wiki_cache/all_books.json        (flat list of all books)
  - wiki_cache/all_chapters.json     (flat list of all chapters)

Without these files the resolver aborts immediately. This script
populates them. Run once before the first CLI invocation, and
periodically (e.g. weekly) if the wiki tree changes.

USAGE
-----
  py automation/fetch_wiki_inventory.py
  py automation/fetch_wiki_inventory.py --shelf-only   # only shelf id=3
  py automation/fetch_wiki_inventory.py --out /tmp/wiki_cache/

ENV VARS (loaded from .env at repo root if present)
---------------------------------------------------
  WIKI_BASE_URL        e.g. https://enterprisewiki.orangehrm.com
  WIKI_TOKEN_ID        BookStack token id
  WIKI_TOKEN_SECRET    BookStack token secret

EXIT CODES
----------
  0  cache written
  1  missing env var
  2  HTTP error from BookStack (no retry — operator decides)
  3  wrote 0 books OR 0 pages (suspicious — abort to avoid clobbering
     a good cache with an empty snapshot)
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = REPO_ROOT / "wiki_cache"
PAGE_SIZE = 500   # BookStack max per call (validated against the live API)
REQ_TIMEOUT = 60  # seconds per API call

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass  # optional


def fail(msg: str, code: int = 1) -> None:
    print(f"fetch_wiki_inventory: {msg}", file=sys.stderr)
    sys.exit(code)


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        fail(f"required env var {name} is empty or unset", code=1)
    return val


def bookstack_get(base: str, auth: str, path: str) -> dict:
    """Single GET against BookStack. Raises on non-2xx; caller wraps."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": auth,
            "Accept": "application/json",
            "User-Agent": "ohrm-wiki-sync/fetch_wiki_inventory",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def paginate(base: str, auth: str, endpoint: str) -> list[dict]:
    """Walk a paginated BookStack list endpoint until the page returns
    fewer than PAGE_SIZE items. Returns the concatenated list."""
    out: list[dict] = []
    offset = 0
    while True:
        path = f"{endpoint}?count={PAGE_SIZE}&offset={offset}"
        try:
            body = bookstack_get(base, auth, path)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            fail(f"HTTP {exc.code} on GET {path}: {detail[:240]}", code=2)
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            fail(f"network error on GET {path}: {exc}", code=2)

        chunk = body.get("data") or []
        out.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            return out
        offset += PAGE_SIZE


def filter_to_shelf(items: list[dict], book_ids: set[int],
                    key: str = "book_id") -> list[dict]:
    """Drop items whose `book_id` field is not in `book_ids`."""
    return [it for it in items if it.get(key) in book_ids]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot BookStack books/chapters/pages into wiki_cache/")
    ap.add_argument("--shelf-only", action="store_true",
                    help="restrict the snapshot to shelf id=3 (Specification) — "
                    "smaller cache, faster resolver")
    ap.add_argument("--out", default=str(DEFAULT_CACHE),
                    help=f"output directory (default: {DEFAULT_CACHE})")
    args = ap.parse_args()

    base = require_env("WIKI_BASE_URL")
    token_id = require_env("WIKI_TOKEN_ID")
    token_secret = require_env("WIKI_TOKEN_SECRET")
    auth = f"Token {token_id}:{token_secret}"

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"fetch_wiki_inventory: base={base}", flush=True)
    print(f"fetch_wiki_inventory: scope={'shelf id=3 only' if args.shelf_only else 'entire wiki'}", flush=True)

    # ---- shelf-only path: discover books in shelf 3 first ----
    in_scope_book_ids: set[int] | None = None
    if args.shelf_only:
        try:
            shelf_body = bookstack_get(base, auth, "/api/shelves/3")
        except urllib.error.HTTPError as exc:
            fail(f"HTTP {exc.code} fetching /api/shelves/3: cannot scope to "
                 f"Specification shelf. Drop --shelf-only or fix the token "
                 f"permissions.", code=2)
        shelf_books = shelf_body.get("books") or []
        in_scope_book_ids = {b["id"] for b in shelf_books if b.get("id")}
        print(f"fetch_wiki_inventory: shelf 3 contains {len(in_scope_book_ids)} book(s)", flush=True)
        if not in_scope_book_ids:
            fail("shelf id=3 returned 0 books — aborting before overwriting cache",
                 code=3)

    # ---- fetch books ----
    print("fetch_wiki_inventory: GET /api/books ...", flush=True)
    books = paginate(base, auth, "/api/books")
    if in_scope_book_ids is not None:
        books = [b for b in books if b.get("id") in in_scope_book_ids]
    print(f"fetch_wiki_inventory: {len(books)} book(s) kept", flush=True)

    # ---- fetch chapters ----
    print("fetch_wiki_inventory: GET /api/chapters ...", flush=True)
    chapters = paginate(base, auth, "/api/chapters")
    if in_scope_book_ids is not None:
        chapters = filter_to_shelf(chapters, in_scope_book_ids, key="book_id")
    print(f"fetch_wiki_inventory: {len(chapters)} chapter(s) kept", flush=True)

    # ---- fetch pages ----
    print("fetch_wiki_inventory: GET /api/pages ...", flush=True)
    pages = paginate(base, auth, "/api/pages")
    if in_scope_book_ids is not None:
        pages = filter_to_shelf(pages, in_scope_book_ids, key="book_id")
    print(f"fetch_wiki_inventory: {len(pages)} page(s) kept", flush=True)

    # ---- sanity gate: refuse to clobber the cache with a zero-page snapshot
    if not books:
        fail(f"snapshot has 0 books — refusing to write empty cache to {out_dir}",
             code=3)
    if not pages:
        fail(f"snapshot has 0 pages — refusing to write empty cache to {out_dir}",
             code=3)

    # ---- write three JSON files atomically (write to .tmp, rename) ----
    targets = [
        ("all_books.json", books),
        ("all_chapters.json", chapters),
        ("wiki_inventory.json", pages),
    ]
    for name, payload in targets:
        path = out_dir / name
        tmp = out_dir / (name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic on the same filesystem
        print(f"fetch_wiki_inventory: wrote {path} ({path.stat().st_size} bytes)", flush=True)

    print("fetch_wiki_inventory: OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
