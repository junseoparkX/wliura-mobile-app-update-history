import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


APP_NAME = "Instagram"
PLATFORM = "iOS"
DEVELOPER_COMPANY = "Instagram, Inc."
APP_CATEGORY = "Photo & Video; Social Networking"
INITIAL_APP_RELEASE_DATE = "October 6, 2010"
IOS_APP_ID = "389801252"
SOURCE_URL = "https://apptopia.com/ios/app/389801252/about"

# Expected project structure:
# project/
#   code/collect_apptopia_instagram_ios_from_txt.py
#   data/ios_txt/instagram_apptopia_about.txt
#   data/raw/ios/instagram_apptopia_versions_enriched.csv
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_SOURCE_TEXT = PROJECT_DIR / "data" / "ios_txt" / "instagram_apptopia_about.txt"
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "ios" / "instagram_apptopia_versions_enriched.csv"

MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_PATTERN = rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}"
VERSION_PATTERN = r"\d+(?:\.\d+)*"

FIELDNAMES = [
    "app_name",
    "platform",
    "developer_company",
    "app_category",
    "version_number",
    "version_release_date",
    "is_current_version",
    "initial_app_release_date",
    "update_description",
    "update_description_raw",
    "standardized_update_categories",
    "standardized_summary",
    "feature_specificity",
    "feature_text_sufficient_for_research",
    "version_history_source",
    "version_history_source_url",
    "source_note",
    "ios_app_id",
    "bundle_id",
    "app_store_price",
    "in_app_purchase",
    "launch_date_from_source",
    "store_categories",
    "total_ratings_us",
    "app_subtitle",
    "app_description",
    "update_frequency_note",
    "file_size",
    "os_compatibility",
    "device_compatibility",
    "age_rating",
    "privacy_label",
    "languages",
    "ios_permissions_categories",
    "ios_permissions_count",
    "ios_permission_keys",
    "in_app_products_count",
    "in_app_products_sample",
    "description_feature_flags",
    "has_reels_feature",
    "has_stories_feature",
    "has_notes_feature",
    "has_direct_messaging_feature",
    "has_close_friends_feature",
    "has_feed_feature",
    "has_post_customization_feature",
    "has_explore_discovery_feature",
    "has_shopping_feature",
    "has_safety_policy_feature",
]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def text_to_lines(text: str):
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_date_line(line: str) -> bool:
    return re.fullmatch(DATE_PATTERN, line.strip(), flags=re.IGNORECASE) is not None


def is_version_line(line: str) -> bool:
    return re.fullmatch(VERSION_PATTERN, line.strip()) is not None


def parse_apptopia_date(value: str):
    try:
        return datetime.strptime(value, "%b %d, %Y").date()
    except ValueError:
        return datetime.strptime(value, "%B %d, %Y").date()


def parse_iso_date(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def find_value_after_label(lines, label, start_index=0):
    label_lower = label.lower()
    for i in range(start_index, len(lines)):
        if lines[i].lower() == label_lower and i + 1 < len(lines):
            return lines[i + 1].strip()
    return ""


def find_first_index(lines, label, start_index=0):
    label_lower = label.lower()
    for i in range(start_index, len(lines)):
        if lines[i].lower() == label_lower:
            return i
    return -1


def normalize_price(value: str) -> str:
    value = clean_text(value)
    if value.lower().startswith("free"):
        return "Free"
    return value


def parse_store_categories(lines):
    start = find_first_index(lines, "Store Categories")
    if start == -1:
        return ""

    stop_labels = {"total ratings", "description", "screenshots", "version history"}
    categories = []

    for line in lines[start + 1:]:
        lower = line.lower()
        if lower in stop_labels:
            break
        if line == "|":
            continue
        if line and line not in categories:
            categories.append(line)

    return "; ".join(categories)


def parse_total_ratings_us(lines):
    start = find_first_index(lines, "Total Ratings")
    if start == -1:
        return ""

    for i in range(start, min(start + 10, len(lines))):
        if lines[i].lower() == "united states" and i + 1 < len(lines):
            return lines[i + 1].strip()

    return ""


def parse_description(lines):
    start = find_first_index(lines, "Description")
    if start == -1:
        return ""

    stop_labels = {"screenshots", "version history"}
    parts = []

    for line in lines[start + 1:]:
        if line.lower() in stop_labels:
            break
        parts.append(line)

    return clean_text(" ".join(parts))


def parse_update_frequency_note(lines):
    start = find_first_index(lines, "Version History")
    if start != -1 and start + 1 < len(lines):
        candidate = lines[start + 1].strip()
        if "releasing updates" in candidate.lower() or "last update" in candidate.lower():
            return candidate
    return ""


def parse_subtitle(lines):
    # In the copied Apptopia text, the subtitle usually appears after the second app-name line:
    # Instagram
    # Videos, creators & friends
    candidates = []
    for i, line in enumerate(lines):
        if line == APP_NAME and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and next_line.lower() not in {"price", "free", "app store", "screenshots", "version history"}:
                candidates.append(next_line)
    return candidates[-1] if candidates else ""


def parse_permissions(lines):
    start = find_first_index(lines, "Permissions")
    if start == -1:
        return {
            "ios_permissions_categories": "",
            "ios_permissions_count": "",
            "ios_permission_keys": "",
        }

    categories = ""
    if start + 1 < len(lines) and lines[start + 1].lower() != "hide details":
        categories = lines[start + 1].strip()

    keys = []
    for line in lines[start + 1:]:
        if line.lower() == "in-app products":
            break
        if re.fullmatch(r"NS[A-Za-z0-9]+", line):
            keys.append(line)

    return {
        "ios_permissions_categories": categories,
        "ios_permissions_count": len(keys) if keys else "",
        "ios_permission_keys": "; ".join(keys),
    }


def parse_in_app_products(lines):
    start = find_first_index(lines, "In-App Products")
    if start == -1:
        return {
            "in_app_products_count": "",
            "in_app_products_sample": "",
        }

    products = []
    i = start + 1
    while i < len(lines):
        line = lines[i].strip()
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            name = match.group(1).strip()
            price = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].startswith("$") else ""
            products.append(f"{name} ({price})" if price else name)
        i += 1

    return {
        "in_app_products_count": len(products) if products else "",
        "in_app_products_sample": "; ".join(products[:5]),
    }


def parse_description_features(description: str):
    text = description.lower()

    flags = {
        "has_reels_feature": any(x in text for x in ["reels", "short, entertaining videos"]),
        "has_stories_feature": "stories" in text,
        "has_notes_feature": "notes" in text,
        "has_direct_messaging_feature": any(x in text for x in ["group chats", "chat", "messages", "direct"]),
        "has_close_friends_feature": "close friends" in text,
        "has_feed_feature": "feed" in text,
        "has_post_customization_feature": any(x in text for x in ["templates", "music", "stickers", "filters"]),
        "has_explore_discovery_feature": any(x in text for x in ["explore", "discover", "personalized"]),
        "has_shopping_feature": any(x in text for x in ["shop", "shopping", "brands", "small businesses"]),
        "has_safety_policy_feature": any(x in text for x in ["safety", "privacy", "terms", "policy", "safe"]),
    }

    active = [
        key.replace("has_", "").replace("_feature", "")
        for key, value in flags.items()
        if value
    ]
    flags["description_feature_flags"] = "; ".join(active)
    return flags


def parse_metadata(text: str):
    lines = text_to_lines(text)
    other_info_start = find_first_index(lines, "Other Information")
    description = parse_description(lines)

    metadata = {
        "ios_app_id": IOS_APP_ID,
        "bundle_id": find_value_after_label(lines, "Bundle ID", other_info_start if other_info_start != -1 else 0),
        "app_store_price": normalize_price(find_value_after_label(lines, "Price")),
        "in_app_purchase": find_value_after_label(lines, "In-App Purchase"),
        "launch_date_from_source": find_value_after_label(lines, "Launched", other_info_start if other_info_start != -1 else 0) or find_value_after_label(lines, "Launched"),
        "store_categories": parse_store_categories(lines),
        "total_ratings_us": parse_total_ratings_us(lines),
        "app_subtitle": parse_subtitle(lines),
        "app_description": description,
        "update_frequency_note": parse_update_frequency_note(lines),
        "file_size": find_value_after_label(lines, "File Size", other_info_start if other_info_start != -1 else 0),
        "os_compatibility": find_value_after_label(lines, "OS Compatibility", other_info_start if other_info_start != -1 else 0),
        "device_compatibility": find_value_after_label(lines, "Device Compatibility", other_info_start if other_info_start != -1 else 0),
        "age_rating": find_value_after_label(lines, "Age Rating", other_info_start if other_info_start != -1 else 0),
        "privacy_label": find_value_after_label(lines, "Privacy", other_info_start if other_info_start != -1 else 0),
        "languages": find_value_after_label(lines, "Languages", other_info_start if other_info_start != -1 else 0),
    }

    metadata.update(parse_permissions(lines))
    metadata.update(parse_in_app_products(lines))
    metadata.update(parse_description_features(description))
    return metadata


def find_version_history_bounds(lines):
    start = find_first_index(lines, "Version History")
    if start == -1:
        raise RuntimeError("Could not find 'Version History' in the source text.")

    start += 1
    if start < len(lines) and ("releasing updates" in lines[start].lower() or "last update" in lines[start].lower()):
        start += 1

    # The copied Apptopia text places another 'Launched' / 'Other Information' block after version history.
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].lower() == "other information":
            end = i
            break
        if lines[i].lower() == "launched" and i + 1 < len(lines) and is_date_line(lines[i + 1]):
            end = i
            break

    return start, end


def parse_versions(text: str):
    lines = text_to_lines(text)
    start, end = find_version_history_bounds(lines)
    rows = []
    i = start

    while i < end:
        if is_version_line(lines[i]) and i + 1 < end and is_date_line(lines[i + 1]):
            version_number = lines[i].strip()
            release_date = lines[i + 1].strip()
            i += 2

            desc_parts = []
            while i < end:
                if is_version_line(lines[i]) and i + 1 < end and is_date_line(lines[i + 1]):
                    break
                desc_parts.append(lines[i])
                i += 1

            update_description = clean_text(" ".join(desc_parts))
            rows.append(build_base_row(version_number, release_date, update_description))
        else:
            i += 1

    return rows


def infer_update_categories(description: str):
    text = description.lower()
    categories = []

    if any(x in text for x in ["bug", "fix", "fixed", "crash", "stability", "performance", "optimization", "optimizations", "improvement", "improvements"]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in ["ui", "design", "layout", "interface", "redesign", "visual", "settings menu", "bigger screen", "ipad", "type mode"]):
        categories.append("UI / design changes")

    if any(x in text for x in ["privacy", "data policy", "consent", "tracking", "privacy settings", "health privacy"]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in ["ai", "artificial intelligence", "generative", "meta ai", "ai-powered"]):
        categories.append("AI-related features")

    if any(x in text for x in ["payment", "checkout", "subscription", "monetization", "purchase", "ads", "shop", "shopping", "brands", "badge", "verified"]):
        categories.append("Payments / monetization")

    if any(x in text for x in ["personalized", "recommendation", "recommendations", "discover", "explore", "feed suggested", "suggested post", "algorithm", "topic channels", "hashtag"]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in ["security", "account safety", "login", "password", "two-factor", "2fa", "authenticator", "safe", "safety", "bullying", "verification", "report", "harass"]):
        categories.append("Security / account safety")

    if any(x in text for x in ["sdk", "api", "developer", "integration"]):
        categories.append("SDK / API / developer integration")

    if any(
        x in text
        for x in [
            "new feature", "introducing", "now you can", "added", "launch", "launched",
            "reels", "stories", "notes", "direct", "message", "messaging", "chat",
            "live", "igtv", "video", "creator", "close friends", "stickers", "filters",
            "template", "feed", "explore", "ipad", "superzoom", "face filters", "nametags",
            "gif", "voice messaging", "messenger", "watch together",
        ]
    ):
        categories.append("New product feature")

    if not categories:
        categories.append("Other")

    return "; ".join(dict.fromkeys(categories))


def classify_feature_specificity(description: str):
    desc = clean_text(description).lower()

    if not desc:
        return "not_provided"

    generic_notes = {
        "bug fixes and performance improvements.",
        "bug fixes and performance improvements",
        "general bug fixes and performance improvements",
        "general bug fixes and performance improvements.",
        "the latest version contains bug fixes and performance improvements.",
        "the latest version contains bug fixes and performance improvements",
        "performance optimizations and stability improvements for a smoother, more reliable experience.",
        "performance optimizations and stability improvements for a smoother, more reliable experience",
        "we’ve updated the app to improve performance and bring you even closer to the people and things you love.",
        "we've updated the app to improve performance and bring you even closer to the people and things you love.",
        "we’ve updated the app to improve performance and bring you even closer to the people and things you love",
        "we've updated the app to improve performance and bring you even closer to the people and things you love",
        "bug fixes",
        "bug fixes.",
    }

    if desc in generic_notes:
        return "generic_maintenance_note"

    return "version_specific_or_actionable"


def make_standardized_summary(description: str, categories: str):
    desc = clean_text(description)
    lower = desc.lower()

    if not desc:
        return "No update description was provided in the Apptopia version-history text."

    routine_phrases = [
        "bug fixes and performance improvements",
        "performance optimizations and stability improvements",
        "improve performance",
        "bug fixes",
    ]

    if any(x in lower for x in routine_phrases) and len(desc.split()) <= 22:
        return "Routine maintenance update focused on bug fixes, performance optimization, or stability improvements."

    if "ipad" in lower:
        return "Feature update introducing or improving Instagram's iPad experience, especially for larger-screen Reels viewing."

    if "critical fix" in lower or "crash" in lower:
        return "Critical maintenance update addressing a specific issue or crash; no new feature described."

    if "authenticator" in lower or "verification" in lower:
        return "Account safety update adding verification or authentication-related controls."

    if "bullying" in lower or "harass" in lower:
        return "Safety update focused on reducing bullying, harassment, or harmful comments."

    if "reels" in lower:
        return "Product feature update related to Reels or short-form video experience."

    if "stories" in lower:
        return "Product feature update related to Stories creation, viewing, or sharing."

    if "direct" in lower or "message" in lower or "chat" in lower:
        return "Product feature update related to messaging, Direct, chat, or social interaction."

    if "explore" in lower or "personalized" in lower or "hashtag" in lower:
        return "Discovery update related to Explore, personalization, hashtags, or recommended content."

    return f"Version-specific note suggests: {desc[:250]}"


def build_base_row(version_number, release_date, update_description):
    categories = infer_update_categories(update_description)
    specificity = classify_feature_specificity(update_description)

    return {
        "app_name": APP_NAME,
        "platform": PLATFORM,
        "developer_company": DEVELOPER_COMPANY,
        "app_category": APP_CATEGORY,
        "version_number": version_number,
        "version_release_date": release_date,
        "is_current_version": False,
        "initial_app_release_date": INITIAL_APP_RELEASE_DATE,
        "update_description": update_description,
        "update_description_raw": update_description,
        "standardized_update_categories": categories,
        "standardized_summary": make_standardized_summary(update_description, categories),
        "feature_specificity": specificity,
        "feature_text_sufficient_for_research": specificity != "not_provided",
        "version_history_source": "Apptopia copied page text",
        "version_history_source_url": SOURCE_URL,
        "source_note": (
            "Parsed from browser-copied Apptopia iOS About page text stored under data/ios_txt. "
            "Some release notes are generic maintenance text rather than detailed feature-specific changelogs."
        ),
    }


def attach_metadata(rows, metadata):
    for row in rows:
        for key, value in metadata.items():
            row[key] = value
    return rows


def filter_rows(rows, start_date=None, end_date=None, all_history=False):
    if all_history:
        return rows

    start = parse_iso_date(start_date) if start_date else None
    end = parse_iso_date(end_date) if end_date else None

    if not start and not end:
        return rows

    filtered = []
    for row in rows:
        row_date = parse_apptopia_date(row["version_release_date"])
        if start and row_date < start:
            continue
        if end and row_date > end:
            continue
        filtered.append(row)

    return filtered


def save_csv(rows, output_path):
    if not rows:
        raise RuntimeError("No rows to save. Check the source text or date filters.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    latest_version = rows[0]["version_number"]
    for row in rows:
        row["is_current_version"] = row["version_number"] == latest_version

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def print_preview(rows, limit=10):
    print(f"Total rows: {len(rows)}")
    print("Preview:")
    cols = [
        "version_number",
        "version_release_date",
        "is_current_version",
        "update_description",
        "standardized_update_categories",
        "standardized_summary",
        "feature_specificity",
    ]
    print(" | ".join(cols))
    for row in rows[:limit]:
        print(" | ".join(clean_text(row.get(col, ""))[:100] for col in cols))


def main():
    parser = argparse.ArgumentParser(
        description="Parse browser-copied Apptopia Instagram iOS page text into a CSV under data/raw/ios."
    )
    parser.add_argument(
        "--source-text",
        default=str(DEFAULT_SOURCE_TEXT),
        help="Path to browser-copied Apptopia text. Default: data/ios_txt/instagram_apptopia_about.txt",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path. Default: data/raw/ios/instagram_apptopia_versions_enriched.csv",
    )
    parser.add_argument(
        "--start-date",
        default="2024-01-01",
        help="Keep versions on/after this YYYY-MM-DD date. Default: 2024-01-01. Use --all-history to disable.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Optional YYYY-MM-DD upper date filter.",
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help="Keep all available version history from the copied Apptopia text.",
    )
    parser.add_argument(
        "--max-versions",
        type=int,
        default=-1,
        help="Maximum number of rows to save after filtering. Default -1 keeps all filtered rows.",
    )

    args = parser.parse_args()

    source_path = Path(args.source_text)
    if not source_path.exists():
        raise FileNotFoundError(
            f"Source text file not found: {source_path}\n"
            "Expected structure: project/data/ios_txt/instagram_apptopia_about.txt"
        )

    text = source_path.read_text(encoding="utf-8", errors="ignore")
    metadata = parse_metadata(text)
    rows = parse_versions(text)
    rows = attach_metadata(rows, metadata)
    rows = filter_rows(
        rows,
        start_date=args.start_date,
        end_date=args.end_date or None,
        all_history=args.all_history,
    )

    if args.max_versions is not None and args.max_versions >= 0:
        rows = rows[:args.max_versions]

    output_path = save_csv(rows, args.output)
    print(f"Saved CSV: {output_path}")
    print_preview(rows)


if __name__ == "__main__":
    main()
