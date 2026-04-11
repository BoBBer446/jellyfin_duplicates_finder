from __future__ import annotations

import argparse
import json

from app.duplicate_finder import find_duplicate_groups
from app.jellyfin_client import JellyfinApiError, JellyfinClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find duplicate Jellyfin media items.")
    parser.add_argument("--base-url", required=True, help="Jellyfin server URL")
    parser.add_argument("--api-key", required=True, help="Jellyfin API key")
    parser.add_argument(
        "--types",
        default="Movie",
        help="Comma separated IncludeItemTypes (default: Movie)",
    )
    parser.add_argument(
        "--sequences",
        default="",
        help="Comma separated sequence markers, e.g. CD1,CD2,Part1,Part2",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    include_types = [entry.strip() for entry in args.types.split(",") if entry.strip()]
    sequences = [entry.strip() for entry in args.sequences.split(",") if entry.strip()] or None

    client = JellyfinClient(args.base_url, args.api_key)
    try:
        items = client.get_all_media_items(include_types)
    except JellyfinApiError as exc:
        print(f"Error: {exc}")
        return 1

    groups, summary = find_duplicate_groups(items, sequences)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary.model_dump(),
                    "groups": [group.model_dump() for group in groups],
                },
                indent=2,
            )
        )
        return 0

    print(
        f"Scanned {summary.total_items} items, found {summary.duplicate_groups} duplicate groups "
        f"with {summary.duplicate_items_to_delete} deletion candidates."
    )
    for group in groups:
        print(f"\nDuplicate: {group.identifier} (keep: {group.keep_item_id})")
        for item in group.items:
            marker = "KEEP" if item.id == group.keep_item_id else "DELETE"
            print(
                f"  [{marker}] {item.id} | {item.path} | size={item.size} | res={item.resolution}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

