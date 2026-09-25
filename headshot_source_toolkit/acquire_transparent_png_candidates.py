from __future__ import annotations

import csv
import io
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "player_headshots_final_v1" / "player_headshot_registry_final_v1.csv"
REPLACEMENT_QUEUE = ROOT / "data" / "headshot_replacement_candidates_v1.csv"
OUT = ROOT / "headshot_source_toolkit"
CANDIDATES_DIR = OUT / "candidates"
MANIFEST = OUT / "candidate_manifest.csv"
REVIEW = OUT / "needs_review.csv"
FAILURES = OUT / "source_failures.csv"

HEADERS = {
    "User-Agent": "NBA-PER75-Headshot-Source-Toolkit/1.0",
    "Accept": "application/json,image/png,image/*;q=0.8",
}

COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def norm_name(value: str) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return value.strip("._") or "player"


def is_transparent_png(data: bytes) -> tuple[bool, int, int]:
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG":
                return False, im.width, im.height
            rgba = im.convert("RGBA")
            alpha = rgba.getchannel("A")
            amin, amax = alpha.getextrema()
            # Require at least some transparent pixels and some opaque pixels.
            return amin < 255 and amax > 0, im.width, im.height
    except Exception:
        return False, 0, 0


def commons_search(session: requests.Session, player_name: str) -> list[dict]:
    # Exact title/name search first, then a looser text search.
    queries = [player_name, f"{player_name} basketball"]
    hits: list[dict] = []
    seen = set()

    for q in queries:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": q,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
        }
        r = session.get(COMMONS_API, params=params, timeout=20)
        r.raise_for_status()
        payload = r.json()
        pages = payload.get("query", {}).get("pages", {})
        for p in pages.values():
            title = p.get("title", "")
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("url")
            mime = ii.get("mime")
            if not url or p.get("pageid") in seen:
                continue
            seen.add(p.get("pageid"))
            hits.append({
                "title": title,
                "url": url,
                "mime": mime,
                "size": ii.get("size"),
                "width": ii.get("width"),
                "height": ii.get("height"),
            })
    return hits


def pick_transparent_candidate(session: requests.Session, hits: list[dict], player_name: str):
    target = norm_name(player_name)
    scored = []
    for hit in hits:
        if str(hit.get("mime") or "").lower() != "image/png":
            continue
        title_norm = norm_name(hit.get("title", ""))
        score = 0
        if target in title_norm:
            score += 10
        # Basketball-specific title signal.
        if "basketball" in title_norm or "nba" in title_norm:
            score += 2
        # Prefer larger source files.
        try:
            score += min(float(hit.get("width") or 0) / 1000.0, 2.0)
        except Exception:
            pass
        scored.append((score, hit))

    for _, hit in sorted(scored, key=lambda x: x[0], reverse=True):
        try:
            r = session.get(hit["url"], timeout=30)
            if not r.ok:
                continue
            transparent, w, h = is_transparent_png(r.content)
            if transparent:
                return hit, r.content, w, h
        except requests.RequestException:
            continue
    return None, None, 0, 0


def load_targets() -> list[dict]:
    if REPLACEMENT_QUEUE.exists():
        with REPLACEMENT_QUEUE.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    # Fallback: derive from registry statuses.
    with REGISTRY.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if str(r.get("Headshot_Status", "")).lower() in {
        "unavailable", "not_found", "needs_review", "alternate_candidate"
    }]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

    targets = load_targets()
    session = requests.Session()
    session.headers.update(HEADERS)

    existing = {}
    if MANIFEST.exists():
        with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                existing[row["Player_ID"]] = row

    manifest_rows = []
    failures = []
    review = []

    for idx, row in enumerate(targets, start=1):
        pid = row.get("Player_ID", "")
        player = row.get("Player", "")
        if not pid or not player:
            continue
        if pid in existing:
            manifest_rows.append(existing[pid])
            continue

        print(f"[{idx}/{len(targets)}] {player}")
        try:
            hits = commons_search(session, player)
            hit, data, w, h = pick_transparent_candidate(session, hits, player)
            if hit and data:
                fname = f"{safe_filename(pid)}.png"
                path = CANDIDATES_DIR / fname
                path.write_bytes(data)
                out = {
                    "Player_ID": pid,
                    "Player": player,
                    "Source": "Wikimedia Commons",
                    "Source_Title": hit["title"],
                    "Source_URL": hit["url"],
                    "Local_File": str(path.relative_to(ROOT)),
                    "MIME": "image/png",
                    "Width": w,
                    "Height": h,
                    "Transparency": "PASS",
                    "Status": "candidate",
                    "Review": "REQUIRED",
                }
                manifest_rows.append(out)
                review.append(out)
            else:
                failures.append({
                    "Player_ID": pid,
                    "Player": player,
                    "Status": "NO_TRANSPARENT_PNG_FOUND",
                    "Source": "Wikimedia Commons",
                })
        except Exception as exc:
            failures.append({
                "Player_ID": pid,
                "Player": player,
                "Status": f"ERROR: {exc}",
                "Source": "Wikimedia Commons",
            })

        if idx % 10 == 0:
            time.sleep(0.5)

    fields = [
        "Player_ID", "Player", "Source", "Source_Title", "Source_URL",
        "Local_File", "MIME", "Width", "Height", "Transparency", "Status", "Review"
    ]
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(manifest_rows)

    with REVIEW.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(review)

    with FAILURES.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["Player_ID", "Player", "Status", "Source"])
        wr.writeheader()
        wr.writerows(failures)

    print("\nDONE")
    print(f"Targets:                       {len(targets):,}")
    print(f"Transparent PNG candidates:    {len(manifest_rows):,}")
    print(f"Needs visual review:           {len(review):,}")
    print(f"No qualifying PNG / failures:  {len(failures):,}")
    print(f"Manifest:                      {MANIFEST}")


if __name__ == "__main__":
    main()
