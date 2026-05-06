"""
Collect current Google Play update metadata for the Android apps in data/app_registry.csv.

Important limitation:
Google Play public metadata usually exposes only the current version/release notes.
For multi-year Android history, supplement these rows with AppBrain/APKMirror/manual sources.

Usage:
    python scripts/collect_android.py \
        --registry data/app_registry.csv \
        --output data/raw/android_current_updates.csv
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google_play_scraper import app as google_play_app

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


def normalize_timestamp(value: Any) -> str:
    """Convert Google Play updated timestamp/date into YYYY-MM-DD when possible."""
    if value in (None, "") or pd.isna(value):
        return ""

    # google-play-scraper often returns an integer Unix timestamp in seconds.
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)

    # Sometimes it may already be a date-like string.
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return str(value)


def collect_one(row: pd.Series, country: str, language: str) -> dict[str, Any]:
    package_name = row["android_package"]
    source_url = row.get("android_url", f"https://play.google.com/store/apps/details?id={package_name}")

    try:
        result = google_play_app(package_name, lang=language, country=country)
    except Exception as exc:
        return {
            "app_name": row["app_name"],
            "platform": "Android",
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
            "data_quality_notes": f"Google Play collection failed: {exc}",
        }

    release_notes = result.get("recentChanges") or result.get("whatsNew") or ""

    return {
        "app_name": row["app_name"],
        "platform": "Android",
        "developer_company": result.get("developer", ""),
        "app_category": row["app_category"],
        "version_number": result.get("version", ""),
        "version_release_date": normalize_timestamp(result.get("updated", "")),
        "is_current_version": "Yes",
        "initial_app_release_date": result.get("released", ""),
        "update_description_release_notes": release_notes,
        "standardized_update_categories": "",
        "standardized_update_summary": "",
        "source_url": source_url,
        "data_quality_notes": "Current Google Play metadata collected with google-play-scraper. Public Google Play data usually provides limited historical update history, so Android multi-year history may need supplemental sources such as AppBrain/APKMirror.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect current Android app update metadata from Google Play.")
    parser.add_argument("--registry", default="data/app_registry.csv", help="Path to app registry CSV.")
    parser.add_argument("--output", default="data/raw/android_current_updates.csv", help="Output CSV path.")
    parser.add_argument("--country", default="us", help="Google Play country code.")
    parser.add_argument("--language", default="en", help="Google Play language code.")
    args = parser.parse_args()

    registry = pd.read_csv(args.registry)
    rows = [collect_one(row, args.country, args.language) for _, row in registry.iterrows()]
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} Android rows to {output_path}")


if __name__ == "__main__":
    main()
