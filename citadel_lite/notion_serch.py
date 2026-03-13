# notion_serch.py
# Notion "Google-like" search → export matched pages (title + recursive blocks) to txt.
#
# Required env:
#   NOTION_API_KEY
# Optional env:
#   NOTION_DATABASE_ID   (if set, prefer database query)
#
# Examples:
#   py notion_serch.py --query "VCC blueprint"
#   py notion_serch.py --query "VCC" --limit 5 --out "C:\Users\Kohei\Desktop\notion_exports"
#   py notion_serch.py --page-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
#   py notion_serch.py --query "Sherlock" --mode search   (force workspace search)

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

# Optional .env support
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip()
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

if not NOTION_API_KEY:
    raise SystemExit("NOTION_API_KEY is missing. Set env NOTION_API_KEY first.")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# -------------------------
# HTTP helpers
# -------------------------

def _request_json(method: str, url: str, payload: Optional[dict] = None, retries: int = 4, backoff_s: float = 0.8) -> Dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    last_err = None

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            last_err = e
            # 429 / 5xx: retry
            if e.code in (429, 500, 502, 503, 504):
                sleep_s = backoff_s * (2 ** attempt)
                sys.stderr.write(f"[HTTP {e.code}] retry in {sleep_s:.1f}s: {url}\n")
                time.sleep(sleep_s)
                continue
            # other errors: show body if possible then abort
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            raise SystemExit(f"HTTPError {e.code} for {url}\n{body}")
        except urllib.error.URLError as e:
            last_err = e
            sleep_s = backoff_s * (2 ** attempt)
            sys.stderr.write(f"[URLError] retry in {sleep_s:.1f}s: {url} ({e})\n")
            time.sleep(sleep_s)

    raise SystemExit(f"Request failed after retries: {url} ({last_err})")

# -------------------------
# Notion API
# -------------------------

def notion_search_workspace(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """POST /search across the workspace."""
    url = f"{BASE_URL}/search"
    payload = {
        "query": query,
        "filter": {"property": "object", "value": "page"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "page_size": min(max(limit, 1), 100),
    }
    data = _request_json("POST", url, payload)
    return data.get("results", [])

def get_database_title_property(database_id: str) -> Tuple[str, Dict[str, Any]]:
    """GET /databases/{id} and find the property whose type == 'title'."""
    url = f"{BASE_URL}/databases/{database_id}"
    db = _request_json("GET", url)
    props = db.get("properties", {}) or {}
    for prop_name, prop_def in props.items():
        if isinstance(prop_def, dict) and prop_def.get("type") == "title":
            return prop_name, db
    raise SystemExit("Could not find title property in database metadata.")

def notion_query_database_contains(database_id: str, title_prop_name: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """POST /databases/{id}/query filter by title contains query."""
    url = f"{BASE_URL}/databases/{database_id}/query"
    payload = {
        "filter": {
            "property": title_prop_name,
            "title": {"contains": query},
        },
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        "page_size": min(max(limit, 1), 100),
    }
    data = _request_json("POST", url, payload)
    return data.get("results", [])

def fetch_page(page_id: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/pages/{page_id}"
    return _request_json("GET", url)

def fetch_blocks_children(block_id: str) -> List[Dict[str, Any]]:
    """GET /blocks/{id}/children with pagination."""
    all_results: List[Dict[str, Any]] = []
    next_cursor = None

    while True:
        url = f"{BASE_URL}/blocks/{block_id}/children?page_size=100"
        if next_cursor:
            url += f"&start_cursor={next_cursor}"
        data = _request_json("GET", url)
        all_results.extend(data.get("results", []) or [])
        if data.get("has_more") and data.get("next_cursor"):
            next_cursor = data["next_cursor"]
        else:
            break
    return all_results

# -------------------------
# Rendering (markdown-ish)
# -------------------------

def get_rich_text(rich_text_list: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for rt in rich_text_list or []:
        text = rt.get("plain_text", "") or ""
        ann = rt.get("annotations", {}) or {}
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"_{text}_"
        if ann.get("code"):
            text = f"`{text}`"
        parts.append(text)
    return "".join(parts)

def extract_page_title(page: Dict[str, Any]) -> str:
    """Find the title property by scanning properties where type == title."""
    props = page.get("properties", {}) or {}
    for _, prop in props.items():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title_texts = prop.get("title", []) or []
            title = get_rich_text(title_texts).strip()
            return title if title else "Untitled"
    return "Untitled"

def render_blocks(blocks: List[Dict[str, Any]], depth: int = 0) -> List[str]:
    lines: List[str] = []
    indent = "  " * depth

    for block in blocks:
        btype = block.get("type", "")
        has_children = bool(block.get("has_children"))
        block_id = block.get("id", "")

        def children_lines(next_depth: int) -> List[str]:
            if not (has_children and block_id):
                return []
            children = fetch_blocks_children(block_id)
            return render_blocks(children, next_depth)

        if btype == "heading_1":
            text = get_rich_text(block.get("heading_1", {}).get("rich_text", []))
            lines += ["", f"{indent}# {text}", ""]
            lines += children_lines(depth + 1)

        elif btype == "heading_2":
            text = get_rich_text(block.get("heading_2", {}).get("rich_text", []))
            lines += ["", f"{indent}## {text}", ""]
            lines += children_lines(depth + 1)

        elif btype == "heading_3":
            text = get_rich_text(block.get("heading_3", {}).get("rich_text", []))
            lines += ["", f"{indent}### {text}", ""]
            lines += children_lines(depth + 1)

        elif btype == "paragraph":
            text = get_rich_text(block.get("paragraph", {}).get("rich_text", []))
            lines.append(f"{indent}{text}" if text.strip() else "")
            lines += children_lines(depth + 1)

        elif btype == "bulleted_list_item":
            text = get_rich_text(block.get("bulleted_list_item", {}).get("rich_text", []))
            lines.append(f"{indent}- {text}")
            lines += children_lines(depth + 1)

        elif btype == "numbered_list_item":
            text = get_rich_text(block.get("numbered_list_item", {}).get("rich_text", []))
            lines.append(f"{indent}1. {text}")
            lines += children_lines(depth + 1)

        elif btype == "to_do":
            text = get_rich_text(block.get("to_do", {}).get("rich_text", []))
            checked = bool(block.get("to_do", {}).get("checked", False))
            mark = "x" if checked else " "
            lines.append(f"{indent}- [{mark}] {text}")
            lines += children_lines(depth + 1)

        elif btype == "quote":
            text = get_rich_text(block.get("quote", {}).get("rich_text", []))
            lines.append(f"{indent}> {text}")
            lines += children_lines(depth + 1)

        elif btype == "callout":
            callout = block.get("callout", {}) or {}
            text = get_rich_text(callout.get("rich_text", []))
            icon = callout.get("icon", {}) or {}
            emoji = icon.get("emoji", "")
            tag = f"{emoji} " if emoji else ""
            lines += ["", f"{indent}[CALLOUT] {tag}{text}", ""]
            lines += children_lines(depth + 1)

        elif btype == "code":
            code = block.get("code", {}) or {}
            text = get_rich_text(code.get("rich_text", []))
            lang = code.get("language", "") or ""
            lines.append(f"{indent}```{lang}")
            lines.append(f"{indent}{text}")
            lines.append(f"{indent}```")
            lines += children_lines(depth + 1)

        elif btype == "divider":
            lines += ["", f"{indent}---", ""]

        elif btype == "image":
            img = block.get("image", {}) or {}
            url = (img.get("external", {}) or {}).get("url") or (img.get("file", {}) or {}).get("url") or ""
            caption = get_rich_text(img.get("caption", []))
            lines.append(f"{indent}[IMAGE] {caption or url}")
            lines += children_lines(depth + 1)

        elif btype == "toggle":
            tog = block.get("toggle", {}) or {}
            text = get_rich_text(tog.get("rich_text", []))
            lines += ["", f"{indent}[TOGGLE] {text}"]
            lines += children_lines(depth + 1)

        elif btype == "child_page":
            title = (block.get("child_page", {}) or {}).get("title", "") or ""
            lines.append(f"{indent}[Child Page] {title}")

        elif btype == "table":
            # Render basic table rows
            if has_children and block_id:
                rows = fetch_blocks_children(block_id)
                for row in rows:
                    if row.get("type") == "table_row":
                        cells = (row.get("table_row", {}) or {}).get("cells", []) or []
                        cell_texts = [get_rich_text(cell) for cell in cells]
                        lines.append(f"{indent}| " + " | ".join(cell_texts) + " |")

        else:
            # Unknown block type: still recurse into children
            lines += children_lines(depth)

    return lines

# -------------------------
# Export helpers
# -------------------------

def sanitize_filename(name: str) -> str:
    name = name.strip() or "Untitled"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120]

def export_page_to_txt(page_id: str, out_dir: str) -> str:
    page = fetch_page(page_id)
    title = extract_page_title(page)
    top_blocks = fetch_blocks_children(page_id)

    header = []
    header.append(f"# {title}")
    header.append(f"(Page ID: {page_id})")
    url = page.get("url")
    if url:
        header.append(f"(URL: {url})")
    header.append("")
    header.append(f"[Total top-level blocks: {len(top_blocks)}]")
    header.append("")

    body_lines = render_blocks(top_blocks)
    text = "\n".join(header + body_lines).strip() + "\n"

    os.makedirs(out_dir, exist_ok=True)
    filename = f"{sanitize_filename(title)}__{page_id.replace('-', '')[:10]}.txt"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path

def pick_pages(query: str, mode: str, limit: int) -> List[str]:
    # mode: "auto" | "db" | "search"
    if mode == "db" or (mode == "auto" and NOTION_DATABASE_ID):
        if not NOTION_DATABASE_ID:
            raise SystemExit("NOTION_DATABASE_ID is missing, and mode=db was requested.")
        title_prop_name, _db = get_database_title_property(NOTION_DATABASE_ID)
        results = notion_query_database_contains(NOTION_DATABASE_ID, title_prop_name, query, limit=limit)
        return [r.get("id") for r in results if r.get("id")]
    else:
        results = notion_search_workspace(query, limit=limit)
        return [r.get("id") for r in results if r.get("id")]

# -------------------------
# CLI
# -------------------------

def main():
    parser = argparse.ArgumentParser(description="Notion search and export pages to text.")
    parser.add_argument("--query", "-q", default="", help="Search query text, e.g. 'VCC blueprint'")
    parser.add_argument("--page-id", default="", help="Export a specific page_id (skips search)")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max pages to export (1-100)")
    parser.add_argument("--out", default=r"C:\Users\Kohei\Desktop\notion_exports", help="Output directory")
    parser.add_argument("--mode", choices=["auto", "db", "search"], default="auto",
                        help="auto: prefer DB if NOTION_DATABASE_ID exists, else workspace search")
    args = parser.parse_args()

    limit = min(max(args.limit, 1), 100)

    page_ids: List[str] = []
    if args.page_id.strip():
        page_ids = [args.page_id.strip()]
    else:
        if not args.query.strip():
            raise SystemExit("Provide --query or --page-id.")
        page_ids = pick_pages(args.query.strip(), args.mode, limit=limit)

    if not page_ids:
        raise SystemExit("No pages matched. Try --mode search, or confirm DB ID, or query string.")

    sys.stdout.write(f"Matched pages: {len(page_ids)}\n")
    for i, pid in enumerate(page_ids, 1):
        try:
            out_path = export_page_to_txt(pid, args.out)
            sys.stdout.write(f"[{i}/{len(page_ids)}] exported: {out_path}\n")
        except Exception as ex:
            sys.stderr.write(f"[{i}/{len(page_ids)}] failed page {pid}: {ex}\n")

if __name__ == "__main__":
    main()