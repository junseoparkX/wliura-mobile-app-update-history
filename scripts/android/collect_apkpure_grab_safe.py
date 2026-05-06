import argparse
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, unquote

import pandas as pd
import requests
from bs4 import BeautifulSoup


APP_NAME = "Grab"
APP_NAME_FULL = "Grab Taxi & Food Delivery"
PLATFORM = "Android"
DEVELOPER_COMPANY = "Grab Holdings"
APP_CATEGORY = "Travel & Local"
INITIAL_APP_RELEASE_DATE = "May 30, 2013"

VERSIONS_URL = "https://apkpure.com/grab-taxi-food-delivery/com.grabtaxi.passenger/versions"
BASE_URL = "https://apkpure.com"
FALLBACK_DETAIL_BASE_URL = "https://apkpure.com/grab-taxi-food-delivery/com.grabtaxi.passenger/download/"

# If this script is in:
# project/code/collect_apkpure_grab_safe.py
# then data will be saved to:
# project/data/raw/android/...
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "android" / "grab_apkpure_versions_enriched.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

DATE_PATTERN = rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}"
VERSION_PATTERN = r"\d+(?:\.\d+)+"

# Handles versions page cards like:
# Grab 5.407.200
# Latest
# APK
# 233.5 MB
# May 3, 2026
# Download
#
# Also handles:
# Grab 5.407.1
# XAPK
# 289.1 MB
# Apr 28, 2026
# Download
VERSION_CARD_RE = re.compile(
    rf"{re.escape(APP_NAME)}\s+(?P<version>{VERSION_PATTERN})\s*"
    r"(?:(?:Latest|Hot)\s*)?"
    r"(?P<apk_format>(?:APK|XAPK)(?:\s+XAPK|\s+APK)?)?\s*"
    r"(?P<size>\d+(?:\.\d+)?\s*(?:MB|GB|KB))\s*"
    rf"(?P<date>{DATE_PATTERN})\s*"
    r"Download",
    re.IGNORECASE | re.DOTALL,
)

WHATS_NEW_RE = re.compile(
    rf"What's New in the Latest Version\s+(?P<version>{VERSION_PATTERN})\s*"
    rf"Last updated on\s+(?P<date>{DATE_PATTERN})\s*"
    r"(?P<desc>.*?)"
    r"(?=Download APK|Download XAPK|Security Check Completed|0\s*/\s*\d+|Scan Result|Google Chrome Screenshots|Grab Screenshots|Old Versions|All Versions|Related Tags|Also available for other platforms|Popular Apps|APKPure)",
    re.IGNORECASE | re.DOTALL,
)

# Fallback for old-version pages that say:
# What's New in Version 5.371.200
# Aug 19, 2025
WHATS_NEW_OLD_RE = re.compile(
    rf"What's New in Version\s+(?P<version>{VERSION_PATTERN})\s*"
    rf"(?P<date>{DATE_PATTERN})\s*"
    r"(?P<desc>.*?)"
    r"(?=Download the Latest Version|Grab Version Comparison|Download APK|Download XAPK|All Variants|Other Versions|Also available for other platforms|Popular Apps|APKPure)",
    re.IGNORECASE | re.DOTALL,
)


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)

    if response.status_code == 403:
        raise RuntimeError(
            f"403 Forbidden: APKPure blocked Python requests for {url}. "
            "Use --versions-text fallback, or save browser-copied text locally."
        )

    response.raise_for_status()
    return response.text


def soup_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def text_to_lines(text: str):
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_version_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    slug = unquote(slug)

    if re.fullmatch(VERSION_PATTERN, slug):
        return slug

    return ""


def normalize_downloads(value: str) -> str:
    if not value:
        return ""

    return value.strip()


def find_value_after_label(lines, label):
    """
    Handles cases like:
    Requires Android
    Android 6.0+
    """
    label_lower = label.lower()

    for i, line in enumerate(lines):
        if line.lower() == label_lower and i + 1 < len(lines):
            return lines[i + 1].strip()

    return ""


def find_value_before_label(lines, label):
    """
    Handles cases like:
    233.5 MB
    Size

    0/60
    Security
    """
    label_lower = label.lower()

    for i, line in enumerate(lines):
        if line.lower() == label_lower and i - 1 >= 0:
            return lines[i - 1].strip()

    return ""


def find_inline_value(lines, prefix):
    """
    Handles cases like:
    Package Name:com.grabtaxi.passenger
    SHA-256:c26ad5...
    """
    prefix_lower = prefix.lower()

    for line in lines:
        if line.lower().startswith(prefix_lower):
            return line.split(":", 1)[1].strip() if ":" in line else ""

    return ""


def parse_top_detail_metadata(lines):
    """
    Parses top summary area from APKPure detail page:
    5.407.200
    7.8
    287
    Reviews
    May 3, 2026
    Update date
    Security
    Everyone
    Android 6.0+
    Android OS
    Download APK (233.5 MB)
    """
    detail_size = find_value_before_label(lines, "Size")
    detail_downloads = find_value_before_label(lines, "Downloads")
    detail_update_date = find_value_before_label(lines, "Update date")
    detail_security_ratio = find_value_before_label(lines, "Security")
    detail_android_os = find_value_before_label(lines, "Android OS")

    top_content_rating = ""
    for i, line in enumerate(lines):
        if line.lower() == "android os" and i - 2 >= 0:
            # Usually:
            # Security
            # Everyone
            # Android 6.0+
            # Android OS
            top_content_rating = lines[i - 2].strip()
            break

    download_size = ""
    download_format = ""
    for line in lines:
        m = re.search(r"Download\s+(APK|XAPK)\s+\(([^)]+)\)", line, flags=re.IGNORECASE)
        if m:
            download_format = m.group(1).upper()
            download_size = m.group(2).strip()
            break

    if not detail_size and download_size:
        detail_size = download_size

    return {
        "detail_page_size": detail_size,
        "detail_page_downloads": normalize_downloads(detail_downloads),
        "detail_page_security_ratio": detail_security_ratio,
        "detail_page_top_content_rating": top_content_rating,
        "detail_page_top_update_date": detail_update_date,
        "detail_page_android_os": detail_android_os,
        "detail_page_download_format": download_format,
    }


def parse_more_app_info(lines):
    """
    Parses Additional APP Information fields:
    Latest Version
    5.407.200
    Uploaded by
    Grab Holdings
    Requires Android
    Android 6.0+
    Available on
    Category
    Free Travel & Local App
    Content Rating
    Everyone
    Security Report
    Check Now
    """
    return {
        "additional_app_latest_version": find_value_after_label(lines, "Latest Version"),
        "uploaded_by": find_value_after_label(lines, "Uploaded by"),
        "requires_android": find_value_after_label(lines, "Requires Android"),
        "available_on": find_value_after_label(lines, "Available on"),
        "additional_app_category": find_value_after_label(lines, "Category"),
        "content_rating": find_value_after_label(lines, "Content Rating"),
        "security_report_label": find_value_after_label(lines, "Security Report"),
    }


def parse_security_info(lines):
    scan_result = ""
    scan_date = ""
    security_check_completed = False
    verified_by = ""

    for i, line in enumerate(lines):
        lower = line.lower()

        if lower.startswith("scan result"):
            scan_result = line.replace("Scan Result:", "").strip()

        if lower.startswith("scan date"):
            scan_date = line.replace("Scan Date:", "").strip()

        if lower == "security check completed":
            security_check_completed = True

        if lower.startswith("verified by") and i + 1 < len(lines):
            verified_by = lines[i + 1].strip()

    return {
        "security_scan_result": scan_result,
        "security_scan_date": scan_date,
        "security_check_completed": security_check_completed,
        "same_as_package_name": find_inline_value(lines, "Package Name:"),
        "sha256": find_inline_value(lines, "SHA-256:"),
        "verified_by": verified_by,
    }


def find_reasonable_card_text(anchor):
    best_text = ""

    node = anchor
    for _ in range(10):
        if node is None:
            break

        text = node.get_text("\n", strip=True)
        if VERSION_CARD_RE.search(text):
            if not best_text or len(text) < len(best_text):
                best_text = text

        node = node.parent

    return best_text


def parse_versions_from_html(html: str):
    """
    Best mode:
    Read actual <a href> from APKPure versions page.
    This avoids blindly constructing /download/{version}.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/download/" not in href:
            continue

        detail_url = urljoin(BASE_URL, href)
        card_text = find_reasonable_card_text(a)

        if not card_text:
            continue

        match = VERSION_CARD_RE.search(card_text)
        if not match:
            continue

        version = match.group("version").strip()
        size = match.group("size").strip()
        update_date = match.group("date").strip()
        apk_format = clean_text(match.group("apk_format") or "")

        detail_url_version_slug = extract_version_from_url(detail_url)
        url_matches_version = detail_url_version_slug == version

        rows.append(
            build_base_row(
                version=version,
                update_date=update_date,
                size=size,
                apk_format=apk_format,
                detail_url=detail_url,
                url_source_method="actual_href_from_versions_page",
                detail_url_version_slug=detail_url_version_slug,
                url_matches_version=url_matches_version,
            )
        )

    return dedupe_rows(rows)


def parse_versions_from_text(text: str):
    """
    Fallback mode:
    Browser-copied text does not preserve real href.
    So detail URL is constructed from the version.
    """
    rows = []

    for match in VERSION_CARD_RE.finditer(text):
        version = match.group("version").strip()
        size = match.group("size").strip()
        update_date = match.group("date").strip()
        apk_format = clean_text(match.group("apk_format") or "")

        detail_url = FALLBACK_DETAIL_BASE_URL + quote(version, safe="")
        detail_url_version_slug = extract_version_from_url(detail_url)

        rows.append(
            build_base_row(
                version=version,
                update_date=update_date,
                size=size,
                apk_format=apk_format,
                detail_url=detail_url,
                url_source_method="fallback_constructed_from_version",
                detail_url_version_slug=detail_url_version_slug,
                url_matches_version=True,
            )
        )

    return dedupe_rows(rows)


def build_base_row(
    version,
    update_date,
    size,
    apk_format,
    detail_url,
    url_source_method,
    detail_url_version_slug,
    url_matches_version,
):
    note = "APKPure version/date/size; not official Google Play historical release data."

    if url_source_method == "actual_href_from_versions_page":
        note += " Detail URL was read from APKPure page href."
    else:
        note += " Detail URL was constructed from version because copied text has no href."

    if not url_matches_version:
        note += (
            f" Warning: displayed version {version} differs from detail URL slug "
            f"{detail_url_version_slug}."
        )

    return {
        "app_name": APP_NAME,
        "app_name_full": APP_NAME_FULL,
        "platform": PLATFORM,
        "developer_company": DEVELOPER_COMPANY,
        "app_category": APP_CATEGORY,
        "version_number": version,
        "version_release_date": update_date,
        "is_current_version": False,
        "initial_app_release_date": INITIAL_APP_RELEASE_DATE,

        # From /versions page
        "apk_format": apk_format,
        "file_size": size,

        # From detail page top area
        "detail_page_size": "",
        "detail_page_downloads": "",
        "detail_page_security_ratio": "",
        "detail_page_top_content_rating": "",
        "detail_page_top_update_date": "",
        "detail_page_android_os": "",
        "detail_page_download_format": "",

        # From Additional APP Information
        "additional_app_latest_version": "",
        "uploaded_by": "",
        "requires_android": "",
        "available_on": "",
        "additional_app_category": "",
        "content_rating": "",
        "security_report_label": "",

        # Security / scan info
        "security_scan_result": "",
        "security_scan_date": "",
        "security_check_completed": False,
        "same_as_package_name": "",
        "sha256": "",
        "verified_by": "",

        # Update reason / release notes
        "update_description": "",
        "update_description_raw": "",
        "standardized_update_categories": "",
        "standardized_summary": "",
        "feature_specificity": "",
        "feature_text_sufficient_for_research": False,

        # Detail page validation
        "detail_page_version": "",
        "detail_page_update_date": "",
        "version_history_source": "APKPure",
        "version_history_source_url": VERSIONS_URL,
        "detail_source_url": detail_url,
        "detail_url_source_method": url_source_method,
        "detail_url_version_slug": detail_url_version_slug,
        "detail_url_matches_displayed_version": url_matches_version,
        "source_note": note,
    }


def dedupe_rows(rows):
    seen = set()
    out = []

    for row in rows:
        key = (
            row["version_number"],
            row["version_release_date"],
            row["file_size"],
            row["detail_source_url"],
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(row)

    return out


def remove_apkpure_boilerplate(desc: str, version: str) -> str:
    desc = clean_text(desc)

    boilerplate_patterns = [
        rf"{re.escape(APP_NAME)} is .*? app .*?\.",
        rf"Download and install old versions of {re.escape(APP_NAME)} that suits your device model and enjoy your favorite features!?",
        rf"{re.escape(APP_NAME)} old version {re.escape(version)} was released on .*?\.",
        r"The app download size is .*?\.",
        rf"We recommend you download the latest version of {re.escape(APP_NAME)} for the new features and better performance\.?",
        rf"Check out the detailed comparison between the latest and old version of {re.escape(APP_NAME)}.*",
    ]

    cleaned = desc

    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = clean_text(cleaned)
    return cleaned


def parse_detail_page_text(text: str, expected_version: str):
    lines = text_to_lines(text)

    detail_metadata = {}
    detail_metadata.update(parse_top_detail_metadata(lines))
    detail_metadata.update(parse_more_app_info(lines))
    detail_metadata.update(parse_security_info(lines))

    match = WHATS_NEW_RE.search(text)
    if not match:
        match = WHATS_NEW_OLD_RE.search(text)

    if not match:
        return {
            "detail_page_version": "",
            "detail_page_update_date": "",
            "update_description_raw": "",
            "update_description": "",
            "parse_success": False,
            **detail_metadata,
        }

    detail_version = match.group("version").strip()
    detail_date = match.group("date").strip()
    raw_desc = clean_text(match.group("desc"))
    clean_desc = remove_apkpure_boilerplate(raw_desc, detail_version)

    return {
        "detail_page_version": detail_version,
        "detail_page_update_date": detail_date,
        "update_description_raw": raw_desc,
        "update_description": clean_desc,
        "parse_success": True,
        **detail_metadata,
    }


def is_generic_description(raw_desc: str, clean_desc: str) -> bool:
    raw_lower = raw_desc.lower()
    clean_lower = clean_desc.lower()

    if not raw_desc.strip():
        return True

    if not clean_desc.strip():
        return True

    generic_phrases = [
        "download and install old versions",
        "old version",
        "released on",
        "download the latest version",
        "new features and better performance",
        "suits your device model",
    ]

    generic_hits = sum(phrase in raw_lower for phrase in generic_phrases)

    if generic_hits >= 2 and len(clean_desc.split()) < 8:
        return True

    vague_only = [
        "minor bug fixes and improvements",
        "minor bug fixes and improvements.",
        "bug fixes and performance improvements",
        "bug fixes and performance improvements.",
        "bug fixes and improvements",
        "performance improvements",
        "stability improvements",
    ]

    if clean_lower in vague_only:
        return False

    return False


def infer_update_categories(description: str, raw_description: str):
    text = f"{description} {raw_description}".lower()
    categories = []

    if any(x in text for x in ["bug", "fix", "crash", "stability", "performance", "improvement", "improved"]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in ["ui", "design", "layout", "interface", "redesign", "visual"]):
        categories.append("UI / design changes")

    if any(x in text for x in ["privacy", "data policy", "consent", "tracking", "gdpr"]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in ["ai", "artificial intelligence", "generative", "recommendation", "personalized"]):
        categories.append("AI-related features")

    if any(x in text for x in ["payment", "wallet", "paylater", "checkout", "subscription", "monetization", "purchase", "cashless"]):
        categories.append("Payments / monetization")

    if any(x in text for x in ["personalization", "recommendations", "recommended", "feed", "algorithm"]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in ["security", "safety", "login", "password", "two-factor", "2fa", "malware"]):
        categories.append("Security / account safety")

    if any(x in text for x in ["ride", "transport", "taxi", "driver", "delivery", "food", "grocery", "parcel", "express"]):
        categories.append("Mobility / delivery service changes")

    if any(x in text for x in ["sdk", "api", "developer", "integration"]):
        categories.append("SDK / API / developer integration")

    if any(
        x in text
        for x in [
            "new feature",
            "introducing",
            "now you can",
            "added",
            "launch",
            "shortcut",
            "shortcuts",
            "feature",
        ]
    ):
        categories.append("New product feature")

    if not categories:
        categories.append("Other")

    return "; ".join(dict.fromkeys(categories))


def make_standardized_summary(description: str, raw_description: str, feature_specificity: str):
    if feature_specificity == "not_provided":
        return "No version-specific update reason was provided by APKPure."

    if feature_specificity == "generic":
        return (
            "APKPure provides generic app or rollback text, but no clear version-specific "
            "reason for this update."
        )

    if description:
        return f"Version-specific note suggests: {description[:250]}"

    if raw_description:
        return f"Version note available but weakly structured: {raw_description[:250]}"

    return "No usable update summary available."


def classify_feature_specificity(raw_desc: str, clean_desc: str):
    if not raw_desc.strip():
        return "not_provided"

    if is_generic_description(raw_desc, clean_desc):
        return "generic"

    return "version_specific_or_actionable"


def enrich_row_with_detail(row, detail_text):
    detail = parse_detail_page_text(detail_text, row["version_number"])

    # Detail page metadata
    detail_meta_cols = [
        "detail_page_size",
        "detail_page_downloads",
        "detail_page_security_ratio",
        "detail_page_top_content_rating",
        "detail_page_top_update_date",
        "detail_page_android_os",
        "detail_page_download_format",
        "additional_app_latest_version",
        "uploaded_by",
        "requires_android",
        "available_on",
        "additional_app_category",
        "content_rating",
        "security_report_label",
        "security_scan_result",
        "security_scan_date",
        "security_check_completed",
        "same_as_package_name",
        "sha256",
        "verified_by",
    ]

    for col in detail_meta_cols:
        row[col] = detail.get(col, "")

    # What's New / update reason
    row["detail_page_version"] = detail["detail_page_version"]
    row["detail_page_update_date"] = detail["detail_page_update_date"]
    row["update_description_raw"] = detail["update_description_raw"]
    row["update_description"] = detail["update_description"]

    feature_specificity = classify_feature_specificity(
        raw_desc=row["update_description_raw"],
        clean_desc=row["update_description"],
    )

    row["feature_specificity"] = feature_specificity
    row["feature_text_sufficient_for_research"] = feature_specificity == "version_specific_or_actionable"

    row["standardized_update_categories"] = infer_update_categories(
        description=row["update_description"],
        raw_description=row["update_description_raw"],
    )

    row["standardized_summary"] = make_standardized_summary(
        description=row["update_description"],
        raw_description=row["update_description_raw"],
        feature_specificity=feature_specificity,
    )

    if not detail["parse_success"]:
        row["source_note"] += " Detail page What's New section could not be parsed."

    if row["detail_page_version"] and row["detail_page_version"] != row["version_number"]:
        row["source_note"] += (
            f" Detail page version {row['detail_page_version']} does not match "
            f"displayed version {row['version_number']}."
        )

    # Prefer Additional APP Information content rating if available.
    if not row["content_rating"] and row["detail_page_top_content_rating"]:
        row["content_rating"] = row["detail_page_top_content_rating"]

    # Fill apk_format from detail page if versions page did not expose it.
    if not row["apk_format"] and row.get("detail_page_download_format"):
        row["apk_format"] = row["detail_page_download_format"]

    return row


def limit_rows(rows, max_versions):
    if max_versions is None:
        return rows

    return rows[:max_versions]


def collect_from_web(max_versions=100, max_detail=100, sleep_seconds=1.0):
    print(f"Collecting versions page: {VERSIONS_URL}")
    html = fetch_html(VERSIONS_URL)

    rows_all = parse_versions_from_html(html)

    if not rows_all:
        print("No rows found from href-based HTML parser. Trying text fallback from fetched HTML.")
        rows_all = parse_versions_from_text(soup_text(html))

    rows = limit_rows(rows_all, max_versions)

    print(f"Found {len(rows_all)} total versions")
    print(f"Keeping {len(rows)} version rows")

    if max_versions is not None and len(rows_all) < max_versions:
        print(f"Warning: requested up to {max_versions} version rows, but only {len(rows_all)} were found.")

    rows_to_detail = rows if max_detail is None else rows[:max_detail]

    for idx, row in enumerate(rows_to_detail, start=1):
        print(f"[{idx}/{len(rows_to_detail)}] {row['version_number']} -> {row['detail_source_url']}")

        try:
            detail_html = fetch_html(row["detail_source_url"])
            detail_text = soup_text(detail_html)
            enrich_row_with_detail(row, detail_text)
        except Exception as e:
            row["source_note"] += f" Detail page failed: {e}"
            row["feature_specificity"] = "not_provided"
            row["feature_text_sufficient_for_research"] = False
            row["standardized_update_categories"] = "Other"
            row["standardized_summary"] = "Detail page could not be accessed or parsed."

        time.sleep(sleep_seconds)

    return rows


def collect_from_local_text(
    versions_text_path,
    detail_text_dir=None,
    link_map_csv=None,
    max_versions=100,
    max_detail=100,
):
    versions_text = Path(versions_text_path).read_text(encoding="utf-8", errors="ignore")
    rows_all = parse_versions_from_text(versions_text)

    link_map = {}
    if link_map_csv:
        link_df = pd.read_csv(link_map_csv)

        for _, r in link_df.iterrows():
            link_map[str(r["version_number"])] = str(r["detail_source_url"])

        for row in rows_all:
            version = row["version_number"]

            if version in link_map:
                actual_url = link_map[version]
                row["detail_source_url"] = actual_url
                row["detail_url_source_method"] = "manual_link_map_csv"
                row["detail_url_version_slug"] = extract_version_from_url(actual_url)
                row["detail_url_matches_displayed_version"] = (
                    row["detail_url_version_slug"] == version
                )
                row["source_note"] += " Detail URL replaced using manual link map CSV."

                if not row["detail_url_matches_displayed_version"]:
                    row["source_note"] += (
                        f" Warning: displayed version {version} differs from detail URL slug "
                        f"{row['detail_url_version_slug']}."
                    )

    rows = limit_rows(rows_all, max_versions)

    print(f"Found {len(rows_all)} total versions from local text")
    print(f"Keeping {len(rows)} version rows")

    if max_versions is not None and len(rows_all) < max_versions:
        print(f"Warning: requested up to {max_versions} version rows, but only {len(rows_all)} were found in the local text.")

    rows_to_detail = rows if max_detail is None else rows[:max_detail]

    if detail_text_dir:
        detail_dir = Path(detail_text_dir)

        for row in rows_to_detail:
            version = row["version_number"]
            detail_file = detail_dir / f"{version}.txt"

            if not detail_file.exists():
                row["source_note"] += " Detail text file not provided."
                row["feature_specificity"] = "not_provided"
                row["feature_text_sufficient_for_research"] = False
                row["standardized_update_categories"] = "Other"
                row["standardized_summary"] = "No local detail page text was provided."
                continue

            detail_text = detail_file.read_text(encoding="utf-8", errors="ignore")
            enrich_row_with_detail(row, detail_text)

    return rows


def save_outputs(rows, output_csv):
    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError("No APKPure rows found. Check parser or source text.")

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
    print()
    print("Preview:")

    preview_cols = [
        "version_number",
        "version_release_date",
        "is_current_version",
        "initial_app_release_date",
        "apk_format",
        "file_size",
        "detail_page_size",
        "detail_page_security_ratio",
        "requires_android",
        "content_rating",
        "security_check_completed",
        "same_as_package_name",
        "feature_specificity",
        "standardized_update_categories",
        "standardized_summary",
    ]

    existing_preview_cols = [col for col in preview_cols if col in df.columns]
    print(df[existing_preview_cols].head(10).to_string(index=False))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path.",
    )

    parser.add_argument(
        "--max-versions",
        type=int,
        default=100,
        help="Maximum number of version rows to keep. Use -1 for all.",
    )

    parser.add_argument(
        "--max-detail",
        type=int,
        default=100,
        help="How many detail pages to visit. Use -1 for all. Use 0 to skip detail pages.",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds to wait between detail page requests.",
    )

    parser.add_argument(
        "--versions-text",
        default=None,
        help="Optional browser-copied APKPure versions page text file.",
    )

    parser.add_argument(
        "--detail-text-dir",
        default=None,
        help="Optional folder containing browser-copied detail pages named like 5.407.200.txt.",
    )

    parser.add_argument(
        "--link-map-csv",
        default=None,
        help="Optional CSV with version_number, detail_source_url for manual actual APKPure links.",
    )

    args = parser.parse_args()

    if args.max_versions < 0:
        max_versions = None
    else:
        max_versions = args.max_versions

    if args.max_detail < 0:
        max_detail = None
    else:
        max_detail = args.max_detail

    if args.versions_text:
        rows = collect_from_local_text(
            versions_text_path=args.versions_text,
            detail_text_dir=args.detail_text_dir,
            link_map_csv=args.link_map_csv,
            max_versions=max_versions,
            max_detail=max_detail,
        )
    else:
        rows = collect_from_web(
            max_versions=max_versions,
            max_detail=max_detail,
            sleep_seconds=args.sleep,
        )

    save_outputs(rows, args.output)


if __name__ == "__main__":
    main()
