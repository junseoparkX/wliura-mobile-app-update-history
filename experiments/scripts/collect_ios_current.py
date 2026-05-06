"""
Collect current iOS App Store metadata using Apple's public iTunes Lookup API.

This script gets current version metadata only. For longer iOS version history,
use scripts/collect_ios_history.js with app-store-scraper.

Usage:
    python scripts/collect_ios_current.py \
        --registry data/app_registry.csv \
        --output data/raw/ios_current_updates.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import requests

OUTPUT_COLUMNS = [
    "app_name",
    "platform",
    "developer_company",
    "app_category",
    "version_number",
    "version_release_date",
    "is_current_version",
    "initial_app_release_date",
    "update_description_release_notes",
    "standardized_update_categories",
    "standardized_update_summary",
    "source_url",
    "data_quality_notes",
]


def date_only(value: Any) -> str:
    if not value or pd.isna(value):
        return ""
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return str(value)


def lookup_ios_app(app_id: str, country: str) -> dict[str, Any]:
    url = "https://itunes.apple.com/lookup"
    response = requests.get(url, params={"id": app_id, "country": country}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("resultCount", 0) < 1:
        raise ValueError(f"No iTunes Lookup result for app id {app_id}")
    return payload["results"][0]


def collect_one(row: pd.Series, country: str) -> dict[str, Any]:
    app_id = str(row["ios_app_id"])
    source_url = row.get("ios_url", f"https://apps.apple.com/app/id{app_id}")

    try:
        result = lookup_ios_app(app_id, country)
    except Exception as exc:
        return {
            "app_name": row["app_name"],
            "platform": "iOS",
            "developer_company": "",
            "app_category": row["app_category"],
            "version_number": "",
            "version_release_date": "",
            "is_current_version": "",
            "initial_app_release_date": "",
            "update_description_release_notes": "",
            "standardized_update_categories": "",
            "standardized_update_summary": "",
            "source_url": source_url,
            "data_quality_notes": f"iTunes Lookup collection failed: {exc}",
        }

    return {
        "app_name": row["app_name"],
        "platform": "iOS",
        "developer_company": result.get("sellerName", ""),
        "app_category": row["app_category"],
        "version_number": result.get("version", ""),
        "version_release_date": date_only(result.get("currentVersionReleaseDate", "")),
        "is_current_version": "Yes",
        "initial_app_release_date": date_only(result.get("releaseDate", "")),
        "update_description_release_notes": result.get("releaseNotes", ""),
        "standardized_update_categories": "",
        "standardized_update_summary": "",
        "source_url": result.get("trackViewUrl", source_url),
        "data_quality_notes": "Current iOS metadata collected with Apple iTunes Lookup API. For longer iOS version history, use app-store-scraper versionHistory output if available.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect current iOS app metadata from Apple's iTunes Lookup API.")
    parser.add_argument("--registry", default="data/app_registry.csv", help="Path to app registry CSV.")
    parser.add_argument("--output", default="data/raw/ios_current_updates.csv", help="Output CSV path.")
    parser.add_argument("--country", default="us", help="App Store country code.")
    args = parser.parse_args()

    registry = pd.read_csv(args.registry)
    rows = [collect_one(row, args.country) for _, row in registry.iterrows()]
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} iOS current rows to {output_path}")


if __name__ == "__main__":
    main()
