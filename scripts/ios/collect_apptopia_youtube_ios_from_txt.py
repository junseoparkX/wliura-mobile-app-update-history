import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


APP_NAME = "YouTube"
PLATFORM = "iOS"
DEVELOPER_COMPANY = "Google"
APP_CATEGORY = "Photo & Video; Entertainment"
INITIAL_APP_RELEASE_DATE = "September 11, 2012"

IOS_APP_ID = "544007664"
BUNDLE_ID_FALLBACK = "com.google.ios.youtube"
SOURCE_URL = "https://apptopia.com/ios/app/544007664/about"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_SOURCE_TEXT = PROJECT_DIR / "data" / "ios_txt" / "youtube_apptopia_about.txt"
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "ios" / "youtube_apptopia_versions_enriched.csv"

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


def extract_other_information_lines(lines):
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "other information") + 1
    except StopIteration:
        return []

    # Stop around permissions / in-app products only after capturing normal metadata.
    out = []
    for line in lines[start:]:
        out.append(line)

    return out


def parse_permissions(lines):
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "permissions") + 1
    except StopIteration:
        return "", "", ""

    top_permissions = []
    usage_keys = []
    stop_labels = {"in-app products", "hide details"}

    for line in lines[start:]:
        low = line.lower()

        if low == "in-app products":
            break

        # Top compact list appears right after "Permissions", before "Hide Details".
        if not top_permissions:
            # First line after Permissions can be: "Camera, Contacts, Location, Other"
            if "," in line and not line.startswith("NS"):
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

    # Apptopia text structure:
    # 1. YouTube Premium
    # $20.99
    # 2. Movies & Shows
    # $3.99
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
        "has_home_recommendations_feature": any(x in text for x in ["personal recommendations", "home", "recommendations"]),
        "has_subscriptions_feature": "subscriptions" in text or "subscribe" in text,
        "has_library_history_feature": any(x in text for x in ["library", "history", "saved for later"]),
        "has_explore_trending_feature": any(x in text for x in ["explore", "trending", "on the rise", "popular"]),
        "has_community_feature": any(x in text for x in ["comments", "community", "posts", "stories", "premieres"]),
        "has_creator_tools_feature": any(x in text for x in ["create content", "create or upload", "upload your own videos"]),
        "has_live_streaming_feature": any(x in text for x in ["live streams", "live streaming", "live chats"]),
        "has_family_safety_feature": any(x in text for x in ["family", "youtube kids", "supervised", "myfamily"]),
        "has_memberships_feature": any(x in text for x in ["channel memberships", "paid monthly memberships", "loyalty badge"]),
        "has_premium_subscription_feature": any(x in text for x in ["youtube premium", "premium", "ads", "screen is locked", "youtube music premium"]),
        "has_music_feature": any(x in text for x in ["music", "music premium"]),
        "has_privacy_policy_feature": any(x in text for x in ["privacy policy", "paid service terms"]),
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

    # Apptopia page has a subtitle near the app name.
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


def parse_versions_from_text(text: str, max_versions=None, start_date=None):
    lines = text_to_lines(text)

    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == "version history") + 1
    except StopIteration:
        raise RuntimeError("Could not find Version History section in Apptopia text.")

    rows = []
    i = start

    while i < len(lines):
        line = lines[i].strip()

        # Stop before the app-level metadata repeats after version history.
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

            if passes_start_date_filter(release_date, start_date):
                rows.append(build_base_row(version, release_date, update_desc))

            if max_versions is not None and len(rows) >= max_versions:
                break
        else:
            i += 1

    return rows


def parse_date(date_text: str):
    return datetime.strptime(date_text, "%b %d, %Y")


def passes_start_date_filter(release_date: str, start_date):
    if start_date is None:
        return True

    try:
        return parse_date(release_date) >= start_date
    except Exception:
        return True


def infer_update_categories(description: str):
    text = description.lower()
    categories = []

    if any(x in text for x in [
        "bug", "bugs", "fix", "fixed", "repair", "repairs", "stability", "performance",
        "improvement", "improvements", "squished", "crash", "battery", "unresponsive"
    ]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in [
        "design", "layout", "header", "logo", "navigation", "tab", "tabs", "library tab",
        "font size", "fullscreen", "player controls", "2-column", "ipad", "iphone x"
    ]):
        categories.append("UI / design changes")

    if any(x in text for x in ["privacy", "tracking", "data policy", "consent"]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in ["ai", "artificial intelligence", "machine learning"]):
        categories.append("AI-related features")

    if any(x in text for x in [
        "premium", "paid", "subscription", "memberships", "super chat", "movies", "ads",
        "youtube red", "offline content", "purchase"
    ]):
        categories.append("Payments / monetization")

    if any(x in text for x in [
        "recommend", "recommended", "recommendations", "suggestions", "up next", "not interested",
        "home feed", "trending", "on the rise", "explore"
    ]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in [
        "security", "account", "accessibility", "voiceover", "right to left", "family",
        "kids", "supervised"
    ]):
        categories.append("Security / account safety")

    if any(x in text for x in ["sdk", "api", "developer", "replaykit", "chromecast", "cardboard"]):
        categories.append("SDK / API / developer integration")

    if any(x in text for x in [
        "added", "support", "new", "now", "introducing", "live streaming", "activity tab",
        "playback speed", "double-tapping", "chromecast", "watch history", "comments",
        "playlists", "imessage", "shorts"
    ]):
        categories.append("New product feature")

    if not categories:
        categories.append("Other")

    return "; ".join(dict.fromkeys(categories))


def classify_feature_specificity(description: str):
    desc = description.strip().lower()

    if not desc:
        return "not_provided"

    routine_patterns = [
        "bug fixes",
        "fixed bugs",
        "performance improvements",
        "stability improvements",
        "we fixed the tubes",
        "cat videos",
        "space-time continuum",
        "drank way too much coffee",
        "took the afternoon off",
        "squished some bugs",
        "shinier bells and whistles",
    ]

    if any(p in desc for p in routine_patterns):
        # It is still a real release-note text, but usually not feature-specific.
        return "generic_or_routine_maintenance"

    return "version_specific_or_actionable"


def make_standardized_summary(description: str, categories: str):
    desc = description.strip()
    lower = desc.lower()

    if not desc:
        return "No version-specific update reason was provided by Apptopia."

    if any(x in lower for x in [
        "bug fixes", "fixed bugs", "performance improvements", "stability improvements",
        "we fixed the tubes", "space-time continuum", "cat videos", "squished some bugs"
    ]):
        return "Routine maintenance update focused on bug fixes, stability, or performance improvements."

    if "iphone x" in lower:
        return "Feature/UI update adding or improving support for iPhone X display behavior."

    if "playback speed" in lower:
        return "Player feature update adding or improving video playback speed controls."

    if "live streaming" in lower or "replaykit" in lower:
        return "Live/video creation update related to live streaming support or capture integration."

    if "activity tab" in lower or "notifications" in lower:
        return "Navigation/community update adding notification management through an Activity tab."

    if "playlist" in lower:
        return "Library or playlist update improving playlist management or playback organization."

    if "comments" in lower or "replies" in lower:
        return "Community interaction update improving comments or replies."

    if "accessibility" in lower or "voiceover" in lower:
        return "Accessibility or usability update improving support for assistive features."

    if "recommend" in lower or "not interested" in lower:
        return "Recommendation control update affecting suggested videos or personalization."

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
        "has_home_recommendations_feature": False,
        "has_subscriptions_feature": False,
        "has_library_history_feature": False,
        "has_explore_trending_feature": False,
        "has_community_feature": False,
        "has_creator_tools_feature": False,
        "has_live_streaming_feature": False,
        "has_family_safety_feature": False,
        "has_memberships_feature": False,
        "has_premium_subscription_feature": False,
        "has_music_feature": False,
        "has_privacy_policy_feature": False,

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
            "Many YouTube release notes are playful generic maintenance notes rather than detailed feature-specific changelogs."
        ),
    }


def attach_app_metadata(rows, metadata):
    for row in rows:
        for key, value in metadata.items():
            row[key] = value
    return rows


def save_outputs(rows, output_csv):
    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError("No Apptopia iOS version rows found. Check the copied source text.")

    latest_version = df.iloc[0]["version_number"]
    df["is_current_version"] = df["version_number"].eq(latest_version)

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    output_xlsx = output_csv.with_suffix(".xlsx")
    try:
        df.to_excel(output_xlsx, index=False)
        print(f"Saved XLSX: {output_xlsx}")
    except Exception as e:
        print(f"Could not save XLSX. CSV was saved. Reason: {e}")

    print(f"Saved CSV:  {output_csv}")
    print(f"Total rows saved: {len(df)}")
    print()
    print("Preview:")

    preview_cols = [
        "version_number",
        "version_release_date",
        "is_current_version",
        "initial_app_release_date",
        "app_store_price",
        "in_app_purchase",
        "store_categories",
        "file_size",
        "os_compatibility",
        "age_rating",
        "permission_categories",
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
        default=200,
        help="Maximum number of version rows to save. Use -1 for all available rows.",
    )

    parser.add_argument(
        "--start-date",
        default="2024-01-01",
        help="Keep versions on/after this date. Use empty string with --all-history or pass --all-history.",
    )

    parser.add_argument(
        "--all-history",
        action="store_true",
        help="Save all available version history instead of filtering from 2024-01-01.",
    )

    args = parser.parse_args()

    max_versions = None if args.max_versions < 0 else args.max_versions

    if args.all_history:
        start_date = None
    else:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else None

    source_text = Path(args.source_text).read_text(encoding="utf-8", errors="ignore")

    metadata = parse_app_metadata(source_text)
    rows = parse_versions_from_text(
        source_text,
        max_versions=max_versions,
        start_date=start_date,
    )
    rows = attach_app_metadata(rows, metadata)

    save_outputs(rows, args.output)


if __name__ == "__main__":
    main()
