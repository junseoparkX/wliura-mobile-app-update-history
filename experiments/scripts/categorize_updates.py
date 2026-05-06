"""
Categorize mobile app update release notes into standardized categories.

Usage:
    python scripts/categorize_updates.py \
        --input output/app_update_history.xlsx \
        --sheet "Update History" \
        --output data/processed/app_update_history_categorized.xlsx

This script is intentionally simple and transparent. It uses keyword-based rules
so that the categorization logic can be reviewed and modified easily.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List

import pandas as pd


CATEGORY_RULES = {
    "Bug fixes / performance improvements": [
        r"\bbug\b",
        r"\bbugs\b",
        r"\bfix\b",
        r"\bfixed\b",
        r"\bfixes\b",
        r"\bperformance\b",
        r"\bstability\b",
        r"\bcrash\b",
        r"\bcrashes\b",
        r"\bspeed\b",
        r"\bfaster\b",
        r"\bimprovement\b",
        r"\bimprovements\b",
    ],
    "UI / design changes": [
        r"\bUI\b",
        r"\binterface\b",
        r"\bdesign\b",
        r"\blayout\b",
        r"\bnavigation\b",
        r"\blook\b",
        r"\btheme\b",
        r"\bdark mode\b",
        r"\bhome screen\b",
        r"\btab\b",
    ],
    "Privacy / data policy changes": [
        r"\bprivacy\b",
        r"\bdata policy\b",
        r"\btracking\b",
        r"\bconsent\b",
        r"\bpermissions?\b",
        r"\bGDPR\b",
        r"\bdata sharing\b",
        r"\bpersonal data\b",
    ],
    "AI-related features": [
        r"\bAI\b",
        r"\bartificial intelligence\b",
        r"\bgenerative\b",
        r"\bgenerate\b",
        r"\bassistant\b",
        r"\bchatbot\b",
        r"\bLLM\b",
        r"\bmachine learning\b",
        r"\bsmart\b",
    ],
    "Payments / monetization": [
        r"\bpayment\b",
        r"\bpayments\b",
        r"\bcheckout\b",
        r"\bsubscription\b",
        r"\bsubscribe\b",
        r"\bprice\b",
        r"\bpricing\b",
        r"\bpremium\b",
        r"\bwallet\b",
        r"\bcoupon\b",
        r"\boffer\b",
        r"\bad\b",
        r"\bads\b",
    ],
    "Personalization / recommendations": [
        r"\bpersonalized\b",
        r"\bpersonalization\b",
        r"\brecommend\b",
        r"\brecommendation\b",
        r"\brecommendations\b",
        r"\bfor you\b",
        r"\bdiscover\b",
        r"\bsuggested\b",
        r"\bfeed\b",
    ],
    "Security / account safety": [
        r"\bsecurity\b",
        r"\bsafe\b",
        r"\bsafety\b",
        r"\blogin\b",
        r"\bsign in\b",
        r"\baccount\b",
        r"\bauthentication\b",
        r"\bpassword\b",
        r"\bpasskey\b",
        r"\b2FA\b",
        r"\btwo-factor\b",
        r"\bverification\b",
        r"\bfraud\b",
    ],
    "SDK / API / developer integration": [
        r"\bSDK\b",
        r"\bAPI\b",
        r"\bdeveloper\b",
        r"\bintegration\b",
        r"\bwebhook\b",
        r"\bplatform support\b",
    ],
    "New product feature": [
        r"\bnew\b",
        r"\bintroducing\b",
        r"\badded\b",
        r"\bnow you can\b",
        r"\bfeature\b",
        r"\bfeatures\b",
        r"\bsupport for\b",
        r"\blaunched\b",
    ],
}


def normalize_text(value: object) -> str:
    """Convert missing or non-string values into a safe lowercase-searchable string."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def match_any_pattern(text: str, patterns: Iterable[str]) -> bool:
    """Return True if any regex pattern matches the text."""
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def categorize_release_notes(notes: object) -> List[str]:
    """
    Assign one or more standardized categories to release notes.

    If no category matches, return ["Other"].
    """
    text = normalize_text(notes)
    if not text:
        return ["Other"]

    categories = [
        category
        for category, patterns in CATEGORY_RULES.items()
        if match_any_pattern(text, patterns)
    ]

    return categories if categories else ["Other"]


def build_standardized_summary(notes: object, categories: List[str]) -> str:
    """
    Create a short, standardized summary that can later be converted into variables.

    The summary intentionally avoids app-specific marketing language and focuses on
    the analytical meaning of the update.
    """
    text = normalize_text(notes)
    category_set = set(categories)

    if not text:
        return "Release notes unavailable or missing."

    if category_set == {"Other"}:
        return "Update type unclear from available release notes."

    summary_parts = []

    if "Bug fixes / performance improvements" in category_set:
        summary_parts.append("maintenance update focused on bug fixes, stability, or performance")
    if "UI / design changes" in category_set:
        summary_parts.append("user interface or design update")
    if "Privacy / data policy changes" in category_set:
        summary_parts.append("privacy, data policy, or permission-related update")
    if "AI-related features" in category_set:
        summary_parts.append("AI-related feature or smart assistant update")
    if "Payments / monetization" in category_set:
        summary_parts.append("payment, subscription, pricing, advertising, or monetization update")
    if "Personalization / recommendations" in category_set:
        summary_parts.append("personalization, recommendation, or discovery update")
    if "Security / account safety" in category_set:
        summary_parts.append("security, login, account safety, or fraud-prevention update")
    if "SDK / API / developer integration" in category_set:
        summary_parts.append("SDK, API, or developer integration update")
    if "New product feature" in category_set:
        summary_parts.append("new product feature or functionality update")

    if not summary_parts:
        return "Update category identified, but detailed description is limited."

    return "This is a " + "; ".join(summary_parts) + "."


def read_input(path: Path, sheet_name: str | None) -> pd.DataFrame:
    """Read an Excel or CSV input file."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported input file type: {path.suffix}")


def write_output(df: pd.DataFrame, path: Path) -> None:
    """Write output as Excel or CSV based on the output suffix."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() in {".xlsx", ".xls"}:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Update History", index=False)
        return

    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
        return

    raise ValueError(f"Unsupported output file type: {path.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Categorize app update release notes into standardized update categories."
    )
    parser.add_argument("--input", required=True, help="Path to input .xlsx or .csv file.")
    parser.add_argument(
        "--sheet",
        default="Update History",
        help="Excel sheet name to read. Ignored for CSV files.",
    )
    parser.add_argument("--output", required=True, help="Path to output .xlsx or .csv file.")
    parser.add_argument(
        "--notes-column",
        default="update_description_release_notes",
        help="Column containing raw release notes.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    df = read_input(input_path, args.sheet)

    if args.notes_column not in df.columns:
        raise KeyError(
            f"Missing notes column '{args.notes_column}'. "
            f"Available columns: {list(df.columns)}"
        )

    category_values = []
    summary_values = []

    for notes in df[args.notes_column]:
        categories = categorize_release_notes(notes)
        category_values.append("; ".join(categories))
        summary_values.append(build_standardized_summary(notes, categories))

    df["standardized_update_categories"] = category_values
    df["standardized_update_summary"] = summary_values

    write_output(df, output_path)

    print(f"Saved categorized output to: {output_path}")


if __name__ == "__main__":
    main()
