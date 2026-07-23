#!/usr/bin/env python3
"""Build ``apps/wallpapers/fixtures/seed_content.json`` from the crawled Pexels dataset.

Inputs (produced by the crawl script, live outside this repo):
- ``manifest.json`` — per-clip provenance: pexels id, page_url, CDN link, poster, author, tags,
  file_size, local path.
- ``video_index.json`` — actual local-file facts (duration, size, resolution) keyed by path;
  used as the source of truth for media-derived fields when both disagree.

Deterministic and offline: same inputs → byte-identical fixture. The seeder
(``manage.py seed_content``) stays the single write path into the DB (spec FR-016);
this script only (re)generates the committed fixture.

Both JSON inputs are committed under ``data/crawl/`` (the defaults) so the fixture can be
regenerated on any machine; only the 22.4 GB of video files stay outside the repo.

Usage:
    python scripts/build_seed_fixture.py            # uses the committed data/crawl/ inputs
    python scripts/build_seed_fixture.py --manifest <path> --video-index <path>  # fresh crawl
"""

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "data" / "crawl" / "manifest.json"
DEFAULT_VIDEO_INDEX = REPO_ROOT / "data" / "crawl" / "video_index.json"
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "wallpapers" / "fixtures" / "seed_content.json"

LICENSE_TYPE = "Pexels License"

# 5 broad browse categories; the 21 crawl folders become curated tags (Constitution IX).
CATEGORIES = [
    {"slug": "nature", "name": "Thiên nhiên", "icon_url": ""},
    {"slug": "sky", "name": "Bầu trời & Vũ trụ", "icon_url": ""},
    {"slug": "city", "name": "Thành phố & Ánh đèn", "icon_url": ""},
    {"slug": "abstract", "name": "Trừu tượng", "icon_url": ""},
    {"slug": "anime", "name": "Anime", "icon_url": ""},
]

# folder slug → (category slug, Vietnamese tag display name)
FOLDER_MAP = {
    "forest": ("nature", "Rừng"),
    "waterfall": ("nature", "Thác nước"),
    "ocean-waves": ("nature", "Sóng biển"),
    "underwater": ("nature", "Dưới đại dương"),
    "flowers-blooming": ("nature", "Hoa nở"),
    "rain": ("nature", "Mưa"),
    "snow-falling": ("nature", "Tuyết rơi"),
    "fog": ("nature", "Sương mù"),
    "stars-night-sky": ("sky", "Trời sao"),
    "aurora-borealis": ("sky", "Cực quang"),
    "clouds-timelapse": ("sky", "Mây trôi"),
    "sunset": ("sky", "Hoàng hôn"),
    "city-night": ("city", "Thành phố về đêm"),
    "neon-lights": ("city", "Đèn neon"),
    "bokeh-lights": ("city", "Bokeh"),
    "abstract-motion": ("abstract", "Chuyển động trừu tượng"),
    "particles": ("abstract", "Hạt sáng"),
    "ink-water": ("abstract", "Mực loang"),
    "smoke": ("abstract", "Khói"),
    "fire": ("abstract", "Lửa"),
    "anime": ("anime", "Anime"),
}

# Share of each folder marked premium (highest-bitrate clips first) — entitlement test data
# for BE-005. Roughly 20–25% overall.
PREMIUM_RATIO = 0.22
PREMIUM_MIN_PER_FOLDER = 3

# Curated sample collections: (slug, title, description, accent, premium,
# [(folder, take_n), ...]). Items are the first N clips of each folder ordered by pexels id —
# deterministic, no taste involved; admins re-curate via BE-004.
COLLECTIONS = [
    (
        "calm-nights",
        "Đêm yên bình",
        "Trời sao, cực quang và ánh đèn thành phố về khuya.",
        "#1B2A4A",
        False,
        [("stars-night-sky", 4), ("aurora-borealis", 3), ("city-night", 3)],
    ),
    (
        "zen-nature",
        "Thiên nhiên tĩnh lặng",
        "Rừng sâu, mưa rơi và sương mù cho những phút thư giãn.",
        "#2F4F3E",
        False,
        [("forest", 3), ("rain", 3), ("fog", 2), ("waterfall", 2)],
    ),
    (
        "ocean-escape",
        "Hơi thở đại dương",
        "Sóng biển và thế giới dưới mặt nước.",
        "#0E4C6B",
        False,
        [("ocean-waves", 5), ("underwater", 5)],
    ),
    (
        "neon-vibes",
        "Neon Vibes",
        "Neon rực rỡ và bokeh lung linh của thành phố đêm.",
        "#8A2BE2",
        True,
        [("neon-lights", 4), ("bokeh-lights", 3), ("city-night", 3)],
    ),
    (
        "smoke-and-fire",
        "Khói & Lửa",
        "Lửa cháy, khói cuộn và mực loang đầy mê hoặc.",
        "#B33A1E",
        False,
        [("fire", 4), ("smoke", 3), ("ink-water", 3)],
    ),
]


def title_from_page_url(page_url: str, pexels_id: int) -> str:
    """'…/video/dynamic-ocean-waves-captured-from-above-29285421/' → 'Dynamic Ocean Waves…'."""
    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    suffix = f"-{pexels_id}"
    if slug.endswith(suffix):
        slug = slug[: -len(suffix)]
    return slug.replace("-", " ").title()


def orientation_of(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "portrait" if height > width else "landscape"


def build(manifest_path: Path, video_index_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    video_index = json.loads(video_index_path.read_text(encoding="utf-8"))

    # Actual local-file facts by relative path — overrides manifest metadata when present.
    local_by_path = {
        v["path"]: v for cat in video_index["categories"].values() for v in cat["videos"]
    }

    clips = sorted(manifest["clips"], key=lambda c: c["id"])
    folders: dict[str, list[dict]] = {}
    for clip in clips:
        folder = clip["path"].split("/", 1)[0]
        if folder not in FOLDER_MAP:
            raise SystemExit(f"Unmapped folder {folder!r} — add it to FOLDER_MAP.")
        folders.setdefault(folder, []).append(clip)

    def bitrate(clip: dict) -> float:
        local = local_by_path.get(clip["path"])
        size = local["size"] if local else clip["file_size"]
        duration = local["duration"] if local else clip["duration"]
        return size / max(duration, 1)

    # Premium = top-bitrate share per folder (bitrate ≈ quality for same-resolution clips).
    premium_ids: set[int] = set()
    for folder_clips in folders.values():
        take = max(PREMIUM_MIN_PER_FOLDER, round(len(folder_clips) * PREMIUM_RATIO))
        by_bitrate = sorted(folder_clips, key=lambda c: (-bitrate(c), c["id"]))
        premium_ids.update(c["id"] for c in by_bitrate[:take])

    wallpapers = []
    for clip in clips:
        folder = clip["path"].split("/", 1)[0]
        local = local_by_path.get(clip["path"])
        width = local["width"] if local else clip["width"]
        height = local["height"] if local else clip["height"]
        wallpapers.append(
            {
                "key": str(clip["id"]),
                "title": title_from_page_url(clip["page_url"], clip["id"]),
                "category": FOLDER_MAP[folder][0],
                "tags": [folder],
                "orientation": orientation_of(width, height),
                "is_premium": clip["id"] in premium_ids,
                # Interim CDN media until the BE-004 pipeline serves our own S3/CDN URLs.
                "thumbnail_url": clip["poster"],
                "preview_video_url": clip["link"],
                "resolution": f"{width}x{height}",
                "duration_seconds": float(local["duration"] if local else clip["duration"]),
                "file_size_bytes": local["size"] if local else clip["file_size"],
                "source_url": clip["page_url"],
                "license_type": LICENSE_TYPE,
                # Informational only (ignored by the seeder): Pexels attribution + the local
                # file this row corresponds to, for the BE-004 upload/backfill step.
                "author": clip["author"],
                "author_url": clip["author_url"],
                "local_path": clip["path"],
            }
        )

    collections = []
    for slug, title, description, accent, is_premium, picks in COLLECTIONS:
        items = [str(c["id"]) for folder, take_n in picks for c in folders[folder][:take_n]]
        cover_clip_id = items[0]
        cover = next(w["thumbnail_url"] for w in wallpapers if w["key"] == cover_clip_id)
        collections.append(
            {
                "slug": slug,
                "title": title,
                "author": "LiveCanvas",
                "description": description,
                "cover_url": cover,
                "accent_color": accent,
                "is_premium": is_premium,
                "items": items,
            }
        )

    tags = [
        {"slug": folder, "name": FOLDER_MAP[folder][1]}
        for folder in sorted(FOLDER_MAP)
        if folder in folders
    ]

    return {
        "generated_from": {
            "manifest": manifest.get("generated"),
            "video_index": video_index.get("generated"),
            "source": manifest.get("source"),
        },
        "categories": CATEGORIES,
        "tags": tags,
        "wallpapers": wallpapers,
        "collections": collections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--video-index", type=Path, default=DEFAULT_VIDEO_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = build(args.manifest.expanduser(), args.video_index.expanduser())
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output}: {len(data['categories'])} categories, {len(data['tags'])} tags, "
        f"{len(data['wallpapers'])} wallpapers "
        f"({sum(w['is_premium'] for w in data['wallpapers'])} premium), "
        f"{len(data['collections'])} collections."
    )


if __name__ == "__main__":
    main()
