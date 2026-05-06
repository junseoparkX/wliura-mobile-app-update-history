import argparse
import re
from pathlib import Path

import pandas as pd


APP_NAME = "Amazon Shopping"
PLATFORM = "iOS"
DEVELOPER_COMPANY = "AMZN Mobile LLC"
APP_CATEGORY = "Shopping; Lifestyle"
INITIAL_APP_RELEASE_DATE = "December 3, 2008"

IOS_APP_ID = "297606951"
BUNDLE_ID_FALLBACK = "com.amazon.Amazon"
SOURCE_URL = "https://apptopia.com/ios/app/297606951/about"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_SOURCE_TEXT = PROJECT_DIR / "data" / "ios_txt" / "amazon_shopping_apptopia_about.txt"
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "ios" / "amazon_shopping_apptopia_versions_enriched.csv"

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
        "has_product_browsing_feature": any(x in text for x in ["browse", "product details", "millions of products"]),
        "has_reviews_feature": "reviews" in text,
        "has_order_tracking_feature": any(x in text for x in ["tracking", "delivery notifications", "package"]),
        "has_360_product_view_feature": any(x in text for x in ["360° product view", "360 product view"]),
        "has_ar_view_feature": any(x in text for x in ["view in your room", "view in you room", "vr", "trueDepth".lower(), "virtually try-on"]),
        "has_deals_price_alert_feature": any(x in text for x in ["price drops", "sale", "deal", "deals"]),
        "has_lists_feature": any(x in text for x in ["your lists", "save items"]),
        "has_biometric_login_feature": any(x in text for x in ["facial", "fingerprint", "securely signed in", "face id", "touch id"]),
        "has_live_chat_support_feature": any(x in text for x in ["live chat", "support"]),
        "has_visual_search_feature": any(x in text for x in ["scan icon", "barcode", "visual search", "take a picture"]),
        "has_voice_shopping_feature": any(x in text for x in ["voice shopping", "microphone", "voice"]),
        "has_international_shopping_feature": any(x in text for x in ["international shopping", "100+ countries", "amazon.ca", "amazon.co.uk"]),
        "has_privacy_policy_feature": any(x in text for x in ["privacy notice", "cookies notice", "interest-based ads notice", "privacy"]),
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
        "bug", "bugs", "fix", "fixed", "performance", "improved", "improvements",
        "faster", "smoother", "seamless", "reliable", "crash", "critical"
    ]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in [
        "new design", "design", "homepage", "navigation", "menu", "toolbar",
        "portrait mode", "landscape", "ipad", "wkwebview"
    ]):
        categories.append("UI / design changes")

    if any(x in text for x in [
        "privacy", "cookies notice", "interest-based ads", "truedepth", "data"
    ]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in [
        "health ai", "ai", "artificial intelligence", "personalized health guidance"
    ]):
        categories.append("AI-related features")

    if any(x in text for x in [
        "payment", "checkout", "gift card", "registry", "subscription", "subscribe",
        "audible", "amazon music unlimited", "sell on amazon", "trade-in", "deals"
    ]):
        categories.append("Payments / monetization")

    if any(x in text for x in [
        "recommendations", "personalized", "interesting finds", "gift finder",
        "style", "stylesnap", "discover", "spark", "programs"
    ]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in [
        "security", "sign-in", "login", "password", "facial", "fingerprint",
        "account", "authentication", "safety"
    ]):
        categories.append("Security / account safety")

    if any(x in text for x in [
        "wkwebview", "api", "sdk", "developer", "integration", "apple health",
        "amazon one medical", "siri"
    ]):
        categories.append("SDK / API / developer integration")

    if any(x in text for x in [
        "new", "launched", "introducing", "try", "alexa", "ar view", "ar stickers",
        "stylesnap", "treasure truck", "amazon spark", "amazon restaurants",
        "international shopping", "amazon launchpad", "subscribe & save",
        "dash buttons", "health ai", "amazon one medical", "apple health",
        "camera", "scanner", "barcode"
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
        "health ai",
        "apple health",
        "amazon one medical",
        "stylesnap",
        "ar view",
        "ar stickers",
        "alexa",
        "international shopping",
        "treasure truck",
        "interesting finds",
        "gift finder",
        "amazon launchpad",
        "today's deals",
        "sell on amazon",
        "trade-in",
        "amazon spark",
        "subscribe & save",
        "amazon restaurants",
        "dash buttons",
        "wkwebview",
        "3d touch",
        "spotlight search",
        "portrait mode",
        "landscape mode",
        "new design",
    ]

    if any(p in desc for p in feature_patterns):
        return "version_specific_or_actionable"

    generic_patterns = [
        "fixed some bugs",
        "bug fixes",
        "performance improvements",
        "seamless shopping experience",
        "new design provides easier access",
        "the new design provides you easier access",
    ]

    if any(p in desc for p in generic_patterns):
        return "generic_or_routine_maintenance"

    return "version_specific_or_actionable"


def make_standardized_summary(description: str, categories: str):
    desc = description.strip()
    lower = desc.lower()

    if not desc:
        return "No version-specific update reason was provided by Apptopia."

    if "health ai" in lower or "amazon one medical" in lower or "apple health" in lower:
        return "Feature update connecting Apple Health data with Amazon One Medical Health AI for personalized health guidance and vitals tracking."

    if "stylesnap" in lower:
        return "Visual shopping update introducing or promoting StyleSnap for finding outfits using the camera."

    if "ar view" in lower or "ar stickers" in lower or "view in room" in lower:
        return "Augmented reality shopping update for viewing products in the user's space or using AR shopping features."

    if "alexa" in lower:
        return "Voice assistant update adding or promoting Alexa voice shopping and smart-home related actions."

    if "international shopping" in lower:
        return "International shopping update allowing users to shop products deliverable across countries and languages."

    if "treasure truck" in lower:
        return "Shopping program update promoting Amazon Treasure Truck access through the app."

    if "interesting finds" in lower:
        return "Discovery update promoting Interesting Finds for product discovery."

    if "gift finder" in lower:
        return "Shopping discovery update promoting Gift Finder."

    if "amazon launchpad" in lower:
        return "Shopping program update promoting Amazon Launchpad products from startups."

    if "today's deals" in lower:
        return "Deals update promoting Today's Deals access through the app."

    if "sell on amazon" in lower:
        return "Marketplace update promoting Sell on Amazon access through the app."

    if "trade-in" in lower:
        return "Commerce feature update promoting device trade-in credits and discounts."

    if "amazon spark" in lower:
        return "Social/discovery shopping update promoting Amazon Spark."

    if "subscribe & save" in lower or "subscribe to receive recurring orders" in lower:
        return "Subscription commerce update promoting Subscribe & Save recurring orders."

    if "portrait mode" in lower or "landscape mode" in lower:
        return "Device-layout fix addressing iPad orientation or landscape behavior."

    if "new design" in lower:
        return "UI/navigation update emphasizing easier access to homepage, account, orders, cart, departments, products, programs, and features."

    if "fixed some bugs" in lower or "bug fixes" in lower:
        return "Routine maintenance update focused on bug fixes and shopping experience improvements."

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
        "has_product_browsing_feature": False,
        "has_reviews_feature": False,
        "has_order_tracking_feature": False,
        "has_360_product_view_feature": False,
        "has_ar_view_feature": False,
        "has_deals_price_alert_feature": False,
        "has_lists_feature": False,
        "has_biometric_login_feature": False,
        "has_live_chat_support_feature": False,
        "has_visual_search_feature": False,
        "has_voice_shopping_feature": False,
        "has_international_shopping_feature": False,
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
            "Amazon Shopping release notes often repeat a generic new-design note, with occasional specific feature, program, AR, Alexa, or Health AI updates."
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
