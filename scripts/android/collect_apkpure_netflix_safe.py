import argparse
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


APP_NAME = "Netflix"
PLATFORM = "Android"
DEVELOPER_COMPANY = "Netflix, Inc."
APP_CATEGORY = "Entertainment"

# Exact first Android APK release date is not available from APKPure.
# Keep this conservative for research coding; update manually if you verify an official Android app launch date.
INITIAL_APP_RELEASE_DATE = "Unknown / not available from APKPure"

PACKAGE_NAME_FALLBACK = "com.netflix.mediaclient"

VERSIONS_URL = "https://apkpure.com/netflix-android-2025/com.netflix.mediaclient/versions"
BASE_URL = "https://apkpure.com"
FALLBACK_DETAIL_BASE_URL = "https://apkpure.com/netflix-android-2025/com.netflix.mediaclient/download/"

# If this script is in:
# project/code/collect_apkpure_netflix_safe.py
# then data will be saved to:
# project/data/raw/android/...
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "android" / "netflix_apkpure_versions_enriched.csv"

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
VERSION_PATTERN = r"\d+(?:\.\d+)+(?:\s+build\s+\d+\s+\d+)?"
SIZE_PATTERN = r"\d+(?:\.\d+)?\s*(?:MB|GB|KB)"
APK_FORMAT_PATTERN = r"(?:APK|XAPK|APKS)(?:\s+(?:APK|XAPK|APKS))*"

# Netflix APKPure rows can look like:
# Netflix 9.64.0 build 8 64229 / APK / 216.2 MB / Apr 29, 2026 / Download
# Netflix 9.62.0 build 8 64181 / APK / 176.0 MB / Apr 16, 2026 / Download
VERSION_CARD_RE = re.compile(
    rf"{APP_NAME}\s+(?P<version>{VERSION_PATTERN})\s*"
    r"(?:(?P<badge>Latest|Hot)\s*)?"
    rf"(?P<apk_format>{APK_FORMAT_PATTERN})?\s*"
    rf"(?P<size>{SIZE_PATTERN})\s*"
    rf"(?P<date>{DATE_PATTERN})\s*"
    r"Download",
    re.IGNORECASE | re.DOTALL,
)

# Detail page can say either:
# What's New in the Latest Version 45.0.42
# Last updated on Apr 29, 2026
# Minor bug fixes...
#
# or old pages may say:
# What's New in Version 45.0.2
# Apr 29, 2026
# ...
WHATS_NEW_RE = re.compile(
    rf"What's New in (?:the Latest Version|Version)\s+(?P<version>{VERSION_PATTERN})\s*"
    rf"(?:Last updated on\s*)?(?P<date>{DATE_PATTERN})\s*"
    r"(?P<desc>.*?)"
    r"(?=Download\s+(?:APK|XAPK|APKS)|\d+\s*/\s*\d+|Scan Result|Old Versions of Netflix|Netflix Screenshots|All Versions|Featured Reviews|Related Tags|APKPure)",
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
    slug = unquote(path.split("/")[-1])
    if re.fullmatch(VERSION_PATTERN, slug, flags=re.IGNORECASE):
        return slug
    return ""


def normalize_downloads(value: str) -> str:
    if not value:
        return ""
    return value.strip()


def normalize_apk_format(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    parts = [p.upper() for p in value.split() if p.upper() in {"APK", "XAPK", "APKS"}]
    return "; ".join(dict.fromkeys(parts))


def find_value_after_label(lines, label):
    """
    Handles cases like:
    Requires Android
    Android 9.0+
    """
    label_lower = label.lower()

    for i, line in enumerate(lines):
        if line.lower() == label_lower and i + 1 < len(lines):
            return lines[i + 1].strip()

    return ""


def find_value_before_label(lines, label):
    """
    Handles cases like:
    Apr 29, 2026
    Update date

    Teen
    Android 9.0+
    Android OS
    """
    label_lower = label.lower()

    for i, line in enumerate(lines):
        if line.lower() == label_lower and i - 1 >= 0:
            return lines[i - 1].strip()

    return ""


def find_first_regex(text: str, pattern: str, group: int = 1) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return clean_text(match.group(group))


def parse_top_detail_metadata(lines, full_text):
    """
    Parses top summary area from APKPure detail page:
    9.64.0 build 8 64229
    8.2
    1.1k
    Reviews
    Apr 29, 2026
    Update date
    0/63
    Security
    Teen
    Android 9.0+
    Android OS
    Download APK (216.2 MB)
    """
    detail_size = find_first_regex(
        full_text,
        r"Download\s+(?:APK|XAPK|APKS)(?:\s+\w+)?\s*\(([^)]+)\)",
    )
    if not detail_size:
        detail_size = find_value_before_label(lines, "Size")

    detail_downloads = find_value_before_label(lines, "Downloads")
    detail_update_date = find_value_before_label(lines, "Update date")
    detail_security_ratio = find_value_before_label(lines, "Security")
    detail_android_os = find_value_before_label(lines, "Android OS")

    # In APKPure detail pages, Content Rating can appear before Android OS:
    # Security / Teen / Android 9.0+ / Android OS
    top_content_rating = ""
    for i, line in enumerate(lines):
        if line.lower() == "android os" and i - 2 >= 0:
            top_content_rating = lines[i - 2].strip()
            break

    return {
        "detail_page_size": detail_size,
        "detail_page_downloads": normalize_downloads(detail_downloads),
        "detail_page_top_content_rating": top_content_rating,
        "detail_page_top_update_date": detail_update_date,
        "detail_page_security_ratio": detail_security_ratio,
        "detail_page_android_os": detail_android_os,
    }


def parse_more_app_info(lines):
    """
    Parses Netflix Additional APP Information fields:
    Latest Version
    9.64.0 build 8 64229
    Uploaded by
    Google LLC
    Requires Android
    Android 9.0+
    Category
    Free Social App
    Content Rating
    Teen
    Security Report
    Check Now

    APKPure may not show Package Name or App Permissions on every Netflix detail page,
    so package_name falls back to the package in the URL.
    """
    package_name = find_value_after_label(lines, "Package Name") or PACKAGE_NAME_FALLBACK

    return {
        "package_name": package_name,
        "languages": find_value_after_label(lines, "Languages"),
        "requires_android": find_value_after_label(lines, "Requires Android"),
        "content_rating": find_value_after_label(lines, "Content Rating"),
        "architecture": find_value_after_label(lines, "Architecture"),
        "app_permissions_count": find_value_after_label(lines, "App Permissions"),
        "additional_app_latest_version": find_value_after_label(lines, "Latest Version"),
        "uploaded_by": find_value_after_label(lines, "Uploaded by"),
        "additional_app_category": find_value_after_label(lines, "Category"),
        "security_report_label": find_value_after_label(lines, "Security Report"),
    }


def parse_security_info(lines):
    scan_result = ""
    scan_date = ""

    for line in lines:
        lower = line.lower()

        if lower.startswith("scan result"):
            scan_result = line.replace("Scan Result:", "").strip()

        if lower.startswith("scan date"):
            scan_date = line.replace("Scan Date:", "").strip()

    return {
        "security_scan_result": scan_result,
        "security_scan_date": scan_date,
    }


def find_reasonable_card_text(anchor):
    best_text = ""

    node = anchor
    for _ in range(8):
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
        apk_format = normalize_apk_format(match.group("apk_format") or "")
        size = match.group("size").strip()
        update_date = match.group("date").strip()

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
        apk_format = normalize_apk_format(match.group("apk_format") or "")
        size = match.group("size").strip()
        update_date = match.group("date").strip()

        detail_url = FALLBACK_DETAIL_BASE_URL + quote(version)
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
        "detail_page_top_content_rating": "",
        "detail_page_top_update_date": "",
        "detail_page_security_ratio": "",
        "detail_page_android_os": "",

        # From Additional APP Information / More App Info
        "package_name": PACKAGE_NAME_FALLBACK,
        "languages": "",
        "requires_android": "",
        "content_rating": "",
        "architecture": "",
        "app_permissions_count": "",
        "additional_app_latest_version": "",
        "uploaded_by": "",
        "additional_app_category": "",
        "security_report_label": "",

        # Security / scan info
        "security_scan_result": "",
        "security_scan_date": "",

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
            row["apk_format"],
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
        rf"{APP_NAME} is a streaming app that delivers series, movies, documentaries, anime, and stand up on mobile\.?",
        rf"Download and install old versions of {APP_NAME} that suits your device model and enjoy your favorite features!?",
        rf"{APP_NAME} old version {re.escape(version)} was released on .*? by Netflix, Inc\. ?",
        r"The app download size is .*?\. ?",
        rf"We recommend you download the latest version of {APP_NAME} for the new features and better performance\. ?",
        r"Check out the detailed comparison between the latest and old version of Netflix.*",
    ]

    cleaned = desc

    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = clean_text(cleaned)
    return cleaned


def parse_detail_page_text(text: str, expected_version: str):
    lines = text_to_lines(text)

    detail_metadata = {}
    detail_metadata.update(parse_top_detail_metadata(lines, text))
    detail_metadata.update(parse_more_app_info(lines))
    detail_metadata.update(parse_security_info(lines))

    match = WHATS_NEW_RE.search(text)

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
        "social networking app",
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

    # This is vague, but still an actual update note from the detail page.
    vague_only = [
        "minor bug fixes and improvements",
        "minor bug fixes and improvements. install or update to the newest version to check it out!",
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

    if any(x in text for x in ["bug", "fix", "crash", "stability", "performance", "improvement"]):
        categories.append("Bug fixes / performance improvements")

    if any(x in text for x in ["ui", "design", "layout", "interface", "redesign", "visual"]):
        categories.append("UI / design changes")

    if any(x in text for x in ["privacy", "data policy", "consent", "tracking", "gdpr"]):
        categories.append("Privacy / data policy changes")

    if any(x in text for x in ["ai", "artificial intelligence", "generative", "recommendation", "personalized"]):
        categories.append("AI-related features")

    if any(x in text for x in ["payment", "checkout", "subscription", "monetization", "purchase", "ads", "shop", "shopping", "premium", "subscription", "membership"]):
        categories.append("Payments / monetization")

    if any(x in text for x in ["personalization", "recommendations", "recommended", "feed", "algorithm", "for you"]):
        categories.append("Personalization / recommendations")

    if any(x in text for x in ["security", "account safety", "login", "password", "two-factor", "2fa", "malware"]):
        categories.append("Security / account safety")

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
            "series",
            "movie",
            "documentary",
            "anime",
            "stand up",
            "offline",
            "download",
            "profile",
            "kids",
            "parental",
            "recommendation",
            "playback",
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

    detail_meta_cols = [
        "detail_page_size",
        "detail_page_downloads",
        "detail_page_top_content_rating",
        "detail_page_top_update_date",
        "detail_page_security_ratio",
        "detail_page_android_os",
        "package_name",
        "languages",
        "requires_android",
        "content_rating",
        "architecture",
        "app_permissions_count",
        "additional_app_latest_version",
        "uploaded_by",
        "additional_app_category",
        "security_report_label",
        "security_scan_result",
        "security_scan_date",
    ]

    for col in detail_meta_cols:
        row[col] = detail.get(col, "")

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

    # Prefer Android OS from top area if Requires Android is absent.
    if not row["requires_android"] and row["detail_page_android_os"]:
        row["requires_android"] = row["detail_page_android_os"]

    return row


def collect_from_web(max_detail=100, sleep_seconds=1.0):
    print(f"Collecting versions page: {VERSIONS_URL}")
    html = fetch_html(VERSIONS_URL)

    rows = parse_versions_from_html(html)

    if not rows:
        print("No rows found from href-based HTML parser. Trying text fallback from fetched HTML.")
        rows = parse_versions_from_text(soup_text(html))

    print(f"Found {len(rows)} versions")

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


def collect_from_local_text(versions_text_path, detail_text_dir=None, link_map_csv=None, max_detail=100):
    versions_text = Path(versions_text_path).read_text(encoding="utf-8", errors="ignore")
    rows = parse_versions_from_text(versions_text)

    link_map = {}
    if link_map_csv:
        link_df = pd.read_csv(link_map_csv)

        for _, r in link_df.iterrows():
            link_map[str(r["version_number"])] = str(r["detail_source_url"])

        for row in rows:
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

    print(f"Found {len(rows)} versions from local text")

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
        "detail_page_downloads",
        "requires_android",
        "content_rating",
        "architecture",
        "app_permissions_count",
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
        "--max-detail",
        type=int,
        default=100,
        help="How many detail pages to visit. Default is 100. Use -1 for all. Use 0 to skip detail pages.",
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
        help="Optional folder containing browser-copied detail pages named like 9.64.0 build 8 64229.txt.",
    )

    parser.add_argument(
        "--link-map-csv",
        default=None,
        help="Optional CSV with version_number, detail_source_url for manual actual APKPure links.",
    )

    args = parser.parse_args()

    if args.max_detail < 0:
        max_detail = None
    else:
        max_detail = args.max_detail

    if args.versions_text:
        rows = collect_from_local_text(
            versions_text_path=args.versions_text,
            detail_text_dir=args.detail_text_dir,
            link_map_csv=args.link_map_csv,
            max_detail=max_detail,
        )
    else:
        rows = collect_from_web(
            max_detail=max_detail,
            sleep_seconds=args.sleep,
        )

    save_outputs(rows, args.output)


if __name__ == "__main__":
    main()
