#!/usr/bin/env python3
"""Copy new batch files from the shared Google Drive queue folder into queue/.

Each batch is a small plain-text file in the queue folder, named like
`2026-12-a1b2c3d4-7f3e` (month, 8-character client code, 4-character run code), with one video per line:
    <url> | <optional note>

The folder ID comes from the QUEUE_FOLDER_ID secret, so it never appears in this
repo. The folder is shared "anyone with the link can view"; listing uses the
Drive API when DRIVE_API_KEY is set, otherwise Drive's public folder view.

Only TikTok, Instagram and YouTube links are accepted. Anything else in a
queue file is dropped, so the folder can't be used to make this job download
arbitrary URLs.

Prints the queue files it wrote, one per line, for the workflow to process.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BATCH_RE = re.compile(r"^\d{4}-\d{2}-[0-9a-f]{8}(-[0-9a-f]{4})?$")
ALLOWED_HOSTS = (
    "tiktok.com", "www.tiktok.com", "m.tiktok.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
)
UA = {"User-Agent": "Mozilla/5.0 (format-scout)"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def list_folder(folder_id: str, api_key: str | None) -> list[tuple[str, str]]:
    """Return [(file_id, name), ...] for files in the public folder."""
    if api_key:
        q = urllib.parse.quote(f"'{folder_id}' in parents and trashed=false")
        url = (f"https://www.googleapis.com/drive/v3/files?q={q}"
               f"&fields=files(id,name)&pageSize=1000&key={urllib.parse.quote(api_key)}")
        data = json.loads(get(url))
        return [(f["id"], f["name"]) for f in data.get("files", [])]
    page = get(f"https://drive.google.com/embeddedfolderview?id={urllib.parse.quote(folder_id)}").decode(
        "utf-8", "replace")
    out = []
    for m in re.finditer(r'id="entry-([A-Za-z0-9_-]+)".*?class="flip-entry-title">(.*?)</div>', page, re.S):
        out.append((m.group(1), html.unescape(m.group(2)).strip()))
    return out


def download(file_id: str, api_key: str | None) -> str:
    if api_key:
        url = (f"https://www.googleapis.com/drive/v3/files/{urllib.parse.quote(file_id)}"
               f"?alt=media&key={urllib.parse.quote(api_key)}")
        try:
            return get(url).decode("utf-8", "replace")
        except Exception:
            pass  # Google Docs can't be fetched with alt=media; try export below.
    for url in (f"https://drive.google.com/uc?export=download&id={file_id}",
                f"https://docs.google.com/document/d/{file_id}/export?format=txt"):
        try:
            text = get(url).decode("utf-8-sig", "replace")
            if "<html" not in text[:500].lower():
                return text
        except Exception:
            continue
    raise RuntimeError(f"could not download {file_id}")


def clean_lines(text: str) -> list[str]:
    keep = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        url = line.split("|", 1)[0].strip()
        try:
            host = urllib.parse.urlparse(url).hostname or ""
        except ValueError:
            continue
        if url.startswith("https://") and host in ALLOWED_HOSTS:
            note = line.split("|", 1)[1].strip() if "|" in line else ""
            note = re.sub(r"[^\w .,:;'()&/+-]", "", note)[:120]
            keep.append(f"{url} | {note}" if note else url)
    return keep


def main() -> int:
    folder = os.environ.get("QUEUE_FOLDER_ID", "").strip()
    if not folder:
        print("QUEUE_FOLDER_ID is not set; nothing to fetch.", file=sys.stderr)
        return 0
    api_key = os.environ.get("DRIVE_API_KEY", "").strip() or None
    try:
        entries = list_folder(folder, api_key)
    except Exception as exc:
        print(f"Could not list the queue folder: {exc}", file=sys.stderr)
        return 1
    print(f"Queue folder has {len(entries)} file(s).", file=sys.stderr)
    Path("queue").mkdir(exist_ok=True)
    for file_id, name in entries:
        name = re.sub(r"\.txt$", "", name.strip())
        if not BATCH_RE.match(name):
            continue
        if Path(f"reports/{name}/DONE").exists() or Path(f"queue/{name}.txt").exists():
            continue
        try:
            lines = clean_lines(download(file_id, api_key))
        except Exception as exc:
            print(f"Skipping {name}: {exc}", file=sys.stderr)
            continue
        if not lines:
            print(f"Skipping {name}: no allowed links", file=sys.stderr)
            continue
        path = Path(f"queue/{name}.txt")
        path.write_text("\n".join(lines[:15]) + "\n", encoding="utf-8")
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
