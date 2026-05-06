import argparse
import re
from pathlib import Path

import pandas as pd


APP_NAME = "Google Docs"
PLATFORM = "iOS"
DEVELOPER_COMPANY = "Google"
APP_CATEGORY = "Productivity; Business"
INITIAL_APP_RELEASE_DATE = "April 30, 2014"

IOS_APP_ID = "842842640"
BUNDLE_ID_FALLBACK = "com.google.Docs"
SOURCE_URL = "https://apptopia.com/ios/app/842842640/about"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_SOURCE_TEXT = PROJECT_DIR / "data" / "ios_txt" / "google_docs_apptopia_about.txt"
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "ios" / "google_docs_apptopia_versions_enriched.csv"

MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_PATTERN = rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}"
VERSION_PATTERN = r"v?\d+(?:\.\d+)*"


def clean_text(text: str) -> str:
    text = str(text).replace("\u2028", " ").replace("\u2029", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_to_lines(text: str):
    return [line.strip() for line in text.splitlines() if line.strip()]


def find_value_after_label(lines, label):
    label_lower = label.lower()
    for i, line in enumerate(lines):
        if line.lower() == label_lower and i + 1 < len(lines):
            return lines[i + 1].strip()
    return ""


def find_block_between(lines, start_label, end_labels):
    start_idx = None
    for i, line in enumerate(lines):
        if line.lower() == start_label.lower():
            start_idx = i + 1
            break

    if start_idx is None:
        return ""

    end_labels_lower = {x.lower() for x in end_labels}
    out = []

    for line in lines[start_idx:]:
        if line.lower() in end_labels_lower:
            break
        out.append(line)

    return clean_text(" ".join(out))


def parse_store_categories(lines):
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "store categories") + 1
    except StopIteration:
        return ""

    cats = []
    stop_labels = {"total ratings", "description", "screenshots", "version history"}

    for line in lines[start:]:
        low = line.lower()
        if low in stop_labels:
            break
        if line == "|":
            continue
        if line not in cats:
            cats.append(line)

    return "; ".join(cats)


def parse_total_ratings_us(lines):
    for i, line in enumerate(lines):
        if line.lower() == "total ratings":
            window = lines[i:i + 8]
            for j, item in enumerate(window):
                if item.lower() == "united states" and i + j + 1 < len(lines):
                    return lines[i + j + 1]
    return ""


def extract_description(lines):
    return find_block_between(
        lines,
        "Description",
        ["Screenshots", "Version History"]
    )


def parse_update_frequency_note(lines):
    for i, line in enumerate(lines):
        if line.lower() == "version history" and i + 1 < len(lines):
            if "releasing updates" in lines[i + 1].lower():
                return lines[i + 1]
    return ""


def parse_permissions(lines):
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "permissions") + 1
    except StopIteration:
        return "", "", ""

    top_permissions = []
    usage_keys = []

    for line in lines[start:]:
        low = line.lower()

        if low == "in-app products":
            break

        if not top_permissions and "," in line and not line.startswith("NS"):
            top_permissions = [x.strip() for x in line.split(",") if x.strip()]
            continue

        if line.startswith("NS") and "UsageDescription" in line:
            usage_keys.append(line.strip())

    permission_categories = "; ".join(dict.fromkeys(top_permissions))
    permission_usage_keys = "; ".join(dict.fromkeys(usage_keys))
    permission_count = str(len(usage_keys)) if usage_keys else ""

    return permission_categories, permission_usage_keys, permission_count


def parse_in_app_products(lines):
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "in-app products") + 1
    except StopIteration:
        return "", ""

    products = []
    i = start

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r"^\d+\.\s+", line):
            name = re.sub(r"^\d+\.\s+", "", line).strip()
            price = ""
            if i + 1 < len(lines) and re.match(r"^\$?\d+(?:\.\d{2})?$", lines[i + 1].strip()):
                price = lines[i + 1].strip()
                i += 1
            products.append(f"{name} ({price})" if price else name)

        i += 1

    return "; ".join(products), str(len(products)) if products else ""


def parse_description_features(description: str):
    text = description.lower()

    features = {
        "has_document_creation_feature": any(x in text for x in ["create", "online documents", "documents"]),
        "has_real_time_collaboration_feature": any(x in text for x in ["work together in real time", "real time", "collaborate"]),
        "has_sharing_feature": any(x in text for x in ["share documents", "share"]),
        "has_comments_action_items_feature": any(x in text for x in ["comment", "action items"]),
        "has_offline_mode_feature": any(x in text for x in ["offline mode", "offline"]),
        "has_templates_feature": "templates" in text,
        "has_word_file_support_feature": any(x in text for x in ["microsoft word", "word files", "file types"]),
        "has_convert_export_feature": any(x in text for x in ["convert", "export"]),
        "has_google_workspace_feature": "google workspace" in text,
        "has_gemini_ai_feature": any(x in text for x in ["gemini", "ai-powered", "ai powered"]),
        "has_drafting_editing_ai_feature": any(x in text for x in ["draft outlines", "improve your writing", "ai-powered suggestions"]),
        "has_social_links_feature": any(x in text for x in ["x:", "linkedin", "facebook"]),
    }

    active = [k.replace("has_", "").replace("_feature", "") for k, v in features.items() if v]
    features["description_feature_flags"] = "; ".join(active)

    return features


def parse_app_metadata(text: str):
    lines = text_to_lines(text)
    description = extract_description(lines)
    permissions, permission_keys, permission_count = parse_permissions(lines)
    in_app_products, in_app_products_count = parse_in_app_products(lines)

    metadata = {
        "ios_app_id": find_value_after_label(lines, "Store ID") or IOS_APP_ID,
        "bundle_id": find_value_after_label(lines, "Bundle ID") or BUNDLE_ID_FALLBACK,
        "app_store_price": find_value_after_label(lines, "Price"),
        "in_app_purchase": find_value_after_label(lines, "In-App Purchase"),
        "launch_date_from_source": find_value_after_label(lines, "Launched"),
        "store_categories": parse_store_categories(lines),
        "total_ratings_us": parse_total_ratings_us(lines),
        "app_subtitle": "",
        "app_description": description,
        "update_frequency_note": parse_update_frequency_note(lines),
        "file_size": find_value_after_label(lines, "File Size"),
        "os_compatibility": find_value_after_label(lines, "OS Compatibility"),
        "device_compatibility": find_value_after_label(lines, "Device Compatibility"),
        "age_rating": find_value_after_label(lines, "Age Rating"),
        "languages": find_value_after_label(lines, "Languages"),
        "permission_categories": permissions,
        "permission_usage_keys": permission_keys,
        "permission_count": permission_count,
        "in_app_products": in_app_products,
        "in_app_products_count": in_app_products_count,
        **parse_description_features(description),
    }

    for i, line in enumerate(lines):
        if line == APP_NAME and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate and candidate.lower() not in {"free", "price", "app store"}:
                metadata["app_subtitle"] = candidate
                break

    return metadata


def is_version_line(line: str) -> bool:
    return re.fullmatch(VERSION_PATTERN, line.strip()) is not None


def is_date_line(line: str) -> bool:
    return re.fullmatch(DATE_PATTERN, line.strip(), flags=re.IGNORECASE) is not None


def parse_versions_from_text(text: str, max_versions=None):
    """
    All-history by default:
    - No start-date filter.
    - Reads every version listed in the copied Apptopia Version History section.
    """
    lines = text_to_lines(text)

    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "version history") + 1
    except StopIteration:
        raise RuntimeError("Could not find Version History section in Apptopia text.")

    rows = []
    i = start

    while i < len(lines):
        line = lines[i].strip()

        if line.lower() == "other information":
            break

        if is_version_line(line) and i + 1 < len(lines) and is_date_line(lines[i + 1]):
            version = line.lstrip("v")
            release_date = lines[i + 1].strip()

            desc_parts = []
            i += 2

            while i < len(lines):
                if lines[i].lower() == "other information":
                    break
                if is_version_line(lines[i]) and i + 1 < len(lines) and is_date_line(lines[i + 1]):
                    break
                desc_parts.append(lines[i])
                i += 1

            update_desc = clean_text(" ".join(desc_parts))
            rows.append(build_base_row(version, release_date, update_desc))

            if max_versions is not None and len(rows) >= max_versions:
                break
        else:
            i += 1

    return rows


def infer_update_categories(description: str):
    text = description.lower()
    categories = []

    if any(x in text for x in [
        "bug", "bugs", "fix", "fixed", "performance", "improvement", "improvements",
        "security improvements", "autocorrect", "sign-in", "support"
    ]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in [
        "dark mode", "updated look and feel", "redesigned", "sidebar", "toolbar",
        "document outline", "print layout", "page setup", "headers", "footers",
        "page numbers", "table", "image", "headings", "orientation", "paper size"
    ]):
        categories.append("UI / design changes")

    if any(x in text for x in ["privacy", "data policy", "tracking", "consent"]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in [
        "gemini", "ai-powered", "ai powered", "ai", "explore", "content suggestions"
    ]):
        categories.append("AI-related features")

    if any(x in text for x in [
        "paid subscribers", "workspace paid", "2 tb", "200 gb", "subscription", "purchase"
    ]):
        categories.append("Payments / monetization")

    if any(x in text for x in [
        "suggestions", "smart chips", "people chips", "recommended", "explore",
        "content suggestions"
    ]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in [
        "security", "sign-in", "account", "login", "password", "access documents"
    ]):
        categories.append("Security / account safety")

    if any(x in text for x in [
        "ios 13", "ios 11", "ipad pro", "split-screen", "drag and drop",
        "3d touch", "office compatibility", "microsoft word"
    ]):
        categories.append("SDK / API / developer integration")

    if any(x in text for x in [
        "ability", "added", "support", "welcome", "insert", "convert", "smart chips",
        "people chips", "dark mode", "link", "thumbnail", "table of contents",
        "merge table cells", "drag and drop", "suggest edits", "action items",
        "document outline", "word count", "track your changes", "gemini"
    ]):
        categories.append("New product feature")

    if not categories:
        categories.append("Other")

    return "; ".join(dict.fromkeys(categories))


def classify_feature_specificity(description: str):
    desc = description.strip().lower()

    if not desc:
        return "not_provided"

    feature_patterns = [
        "people chips",
        "smart chips",
        "dark mode",
        "title and thumbnail preview",
        "ios 13",
        "table of contents",
        "merge table cells",
        "drag and drop",
        "equations",
        "redesigned sidebar",
        "link sharing",
        "automatic page numbers",
        "style individual cells",
        "crop, mask",
        "suggest edits",
        "format tables",
        "action items",
        "explore:",
        "split-screen multitasking",
        "document outline",
        "word count",
        "recent documents will be saved automatically",
        "3d touch",
        "word count",
        "track your changes",
        "insert links",
        "gemini",
    ]

    if any(p in desc for p in feature_patterns):
        return "version_specific_or_actionable"

    generic_patterns = [
        "bug fixes and performance improvements",
        "security improvements, bug fixes, and performance improvements",
    ]

    if any(p in desc for p in generic_patterns):
        return "generic_or_routine_maintenance"

    return "version_specific_or_actionable"


def make_standardized_summary(description: str, categories: str):
    desc = description.strip()
    lower = desc.lower()

    if not desc:
        return "No version-specific update reason was provided by Apptopia."

    if "people chips" in lower or "smart chips" in lower:
        return "Collaboration/editor update adding people chips and smart chip conversion for supported pasted links."

    if "dark mode" in lower:
        return "UI update introducing Dark Mode for Google Docs."

    if "title and thumbnail preview" in lower:
        return "Link-preview update allowing users to tap links and see title and thumbnail previews."

    if "ios 13" in lower:
        return "Platform compatibility update adding support for iOS 13."

    if "table of contents" in lower or "merge table cells" in lower:
        return "Document editing update adding table of contents support, table cell merging, or related formatting improvements."

    if "drag and drop" in lower:
        return "iOS productivity update adding drag-and-drop support for moving content into or within Docs."

    if "equations" in lower:
        return "Document rendering update improving how equations are shown."

    if "suggest edits" in lower:
        return "Collaboration update adding suggested edits without changing original text."

    if "action items" in lower:
        return "Collaboration update adding action item creation, assignment, or visibility."

    if "explore:" in lower or "content suggestions" in lower:
        return "Research assistance update adding Explore content suggestions."

    if "document outline" in lower:
        return "Navigation update adding or improving Document Outline."

    if "word count" in lower:
        return "Writing utility update adding Word Count support."

    if "track your changes" in lower:
        return "Editing workflow update adding track changes support."

    if "insert links" in lower:
        return "Editing update adding link insertion."

    if "security improvements" in lower:
        return "Routine maintenance update focused on security, bug fixes, and performance improvements."

    if "bug fixes and performance improvements" in lower:
        return "Routine maintenance update focused on bug fixes and performance improvements."

    return f"Version-specific note suggests: {desc[:250]}"


def build_base_row(version, release_date, update_description):
    categories = infer_update_categories(update_description)
    specificity = classify_feature_specificity(update_description)

    return {
        "app_name": APP_NAME,
        "platform": PLATFORM,
        "developer_company": DEVELOPER_COMPANY,
        "app_category": APP_CATEGORY,
        "version_number": version,
        "version_release_date": release_date,
        "is_current_version": False,
        "initial_app_release_date": INITIAL_APP_RELEASE_DATE,

        # iOS / Apptopia app-level metadata filled later
        "ios_app_id": IOS_APP_ID,
        "bundle_id": BUNDLE_ID_FALLBACK,
        "app_store_price": "",
        "in_app_purchase": "",
        "launch_date_from_source": "",
        "store_categories": "",
        "total_ratings_us": "",
        "app_subtitle": "",
        "app_description": "",
        "update_frequency_note": "",
        "file_size": "",
        "os_compatibility": "",
        "device_compatibility": "",
        "age_rating": "",
        "languages": "",
        "permission_categories": "",
        "permission_usage_keys": "",
        "permission_count": "",
        "in_app_products": "",
        "in_app_products_count": "",

        # App description feature flags
        "description_feature_flags": "",
        "has_document_creation_feature": False,
        "has_real_time_collaboration_feature": False,
        "has_sharing_feature": False,
        "has_comments_action_items_feature": False,
        "has_offline_mode_feature": False,
        "has_templates_feature": False,
        "has_word_file_support_feature": False,
        "has_convert_export_feature": False,
        "has_google_workspace_feature": False,
        "has_gemini_ai_feature": False,
        "has_drafting_editing_ai_feature": False,
        "has_social_links_feature": False,

        # Version-level update fields
        "update_description": update_description,
        "update_description_raw": update_description,
        "standardized_update_categories": categories,
        "standardized_summary": make_standardized_summary(update_description, categories),
        "feature_specificity": specificity,
        "feature_text_sufficient_for_research": specificity == "version_specific_or_actionable",

        # Source fields
        "version_history_source": "Apptopia",
        "version_history_source_url": SOURCE_URL,
        "source_note": (
            "Apptopia iOS version history and app metadata. "
            "Google Docs release notes are often generic bug-fix/performance notes, with occasional specific editing, collaboration, platform, and AI-related feature updates."
        ),
    }


def attach_app_metadata(rows, metadata):
    for row in rows:
        for key, value in metadata.items():
            row[key] = value
    return rows


def save_csv_only(rows, output_csv):
    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError("No Apptopia iOS version rows found. Check the copied source text.")

    latest_version = df.iloc[0]["version_number"]
    df["is_current_version"] = df["version_number"].eq(latest_version)

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print(f"Saved CSV: {output_csv}")
    print(f"Total rows saved: {len(df)}")
    print()
    print("Preview:")

    preview_cols = [
        "version_number",
        "version_release_date",
        "is_current_version",
        "initial_app_release_date",
        "store_categories",
        "file_size",
        "os_compatibility",
        "age_rating",
        "description_feature_flags",
        "update_description",
        "standardized_update_categories",
        "standardized_summary",
        "feature_specificity",
    ]

    existing_cols = [c for c in preview_cols if c in df.columns]
    print(df[existing_cols].head(10).to_string(index=False))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-text",
        default=str(DEFAULT_SOURCE_TEXT),
        help="Browser-copied Apptopia iOS app page text file.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path.",
    )

    parser.add_argument(
        "--max-versions",
        type=int,
        default=-1,
        help="Maximum number of version rows to save. Default -1 saves all history.",
    )

    args = parser.parse_args()

    # all-history is default. No start-date filter is applied.
    max_versions = None if args.max_versions < 0 else args.max_versions

    source_text = Path(args.source_text).read_text(encoding="utf-8", errors="ignore")

    metadata = parse_app_metadata(source_text)
    rows = parse_versions_from_text(source_text, max_versions=max_versions)
    rows = attach_app_metadata(rows, metadata)

    save_csv_only(rows, args.output)


if __name__ == "__main__":
    main()
