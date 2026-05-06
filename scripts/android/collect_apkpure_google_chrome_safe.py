import argparse
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, unquote

import pandas as pd
import requests
from bs4 import BeautifulSoup


APP_NAME = "Google Chrome"
APP_NAME_FULL = "Google Chrome"
PLATFORM = "Android"
DEVELOPER_COMPANY = "Google LLC"
APP_CATEGORY = "Communication"
INITIAL_APP_RELEASE_DATE = "February 7, 2012 (beta)"

VERSIONS_URL = "https://apkpure.com/google-chrome-fast-secure/com.android.chrome/versions"
BASE_URL = "https://apkpure.com"
FALLBACK_DETAIL_BASE_URL = "https://apkpure.com/google-chrome-fast-secure/com.android.chrome/download/"

# If this script is in:
# project/code/collect_apkpure_google_chrome_safe.py
# then data will be saved to:
# project/data/raw/android/...
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "raw" / "android" / "google_chrome_apkpure_versions_enriched.csv"

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
VERSION_PATTERN = r"\d+(?:\.\d+){2,}"
SIZE_PATTERN = r"\d+(?:\.\d+)?\s*(?:MB|GB|KB)"
FORMAT_PATTERN = r"(?:(?:APK|XAPK)\s*){0,4}"

# Supports both forms:
# Google Chrome 32.9.0.100 / 174.4 MB / Apr 29, 2026 / Download
# Google Chrome 32.8.2.100 / XAPK / 170.9 MB / Apr 21, 2026 / Download
VERSION_CARD_RE = re.compile(
    rf"(?:{re.escape(APP_NAME)}|{re.escape(APP_NAME_FULL)})\s+"
    rf"(?P<version>{VERSION_PATTERN})\s*"
    rf"(?P<apk_format>{FORMAT_PATTERN})"
    rf"(?P<size>{SIZE_PATTERN})\s*"
    rf"(?P<date>{DATE_PATTERN})\s*"
    r"Download",
    re.IGNORECASE | re.DOTALL,
)

WHATS_NEW_RE = re.compile(
    rf"What's New in(?: the Latest)? Version\s+(?P<version>{VERSION_PATTERN})\s*"
    rf"(?:Last updated on\s+)?(?P<date>{DATE_PATTERN})\s*"
    r"(?P<desc>.*?)"
    r"(?=Google Chrome Version Comparison|Download APK|Download XAPK|"
    r"0\s*/\s*\d+|Scan Result|All Variants|Other Versions of Google Chrome|"
    r"Google Chrome Screenshots|All Versions|Featured Reviews|Related Tags|Also available|"
    r"More Apps|Trending Apps|Google Chrome Articles|APKPure)",
    re.IGNORECASE | re.DOTALL,
)


KNOWN_LABELS = {
    "latest version", "uploaded by", "requires android", "available on", "category",
    "content rating", "security report", "report", "package name", "version",
    "update date", "size", "architecture", "signature", "google play app license",
    "downloads", "android os", "security", "scan result", "scan date", "verified by",
}


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


def normalize_apk_format(value: str) -> str:
    if not value:
        return ""
    tokens = re.findall(r"APK|XAPK", value.upper())
    return "; ".join(dict.fromkeys(tokens))


def extract_version_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    slug = unquote(slug)
    if re.fullmatch(VERSION_PATTERN, slug):
        return slug
    return slug


def build_detail_url_from_version(version: str) -> str:
    return FALLBACK_DETAIL_BASE_URL + quote(version, safe="")


def normalize_downloads(value: str) -> str:
    return value.strip() if value else ""


def find_value_after_label(lines, label):
    label_lower = label.lower().rstrip(":")
    for i, line in enumerate(lines):
        if line.lower().rstrip(":") == label_lower and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate.lower().rstrip(":") in KNOWN_LABELS:
                return ""
            return candidate
    return ""


def find_values_after_label(lines, label, max_values=2):
    label_lower = label.lower().rstrip(":")
    values = []
    for i, line in enumerate(lines):
        if line.lower().rstrip(":") == label_lower:
            for candidate in lines[i + 1 : i + 1 + max_values]:
                candidate = candidate.strip()
                if candidate.lower().rstrip(":") in KNOWN_LABELS:
                    break
                values.append(candidate)
            break
    return values


def find_value_before_label(lines, label):
    label_lower = label.lower()
    for i, line in enumerate(lines):
        if line.lower() == label_lower and i - 1 >= 0:
            return lines[i - 1].strip()
    return ""


def find_download_size(lines):
    for line in lines:
        match = re.search(r"Download\s+(?:APK|XAPK)?\s*\(([^)]+)\)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def is_android_requirement(value: str) -> bool:
    return bool(value and re.search(r"Android\s+\d|API\s*\d|\+", value, re.IGNORECASE))


def parse_prefixed_line(lines, prefix):
    prefix_lower = prefix.lower()
    for line in lines:
        if line.lower().startswith(prefix_lower):
            return line.split(":", 1)[1].strip() if ":" in line else line[len(prefix):].strip()
    return ""


def extract_table_values(lines, label, kind=None, max_values=2):
    # First handle the clean copied-text layout:
    # Label / value1 / value2
    values = find_values_after_label(lines, label, max_values=max_values)

    # Then handle tabular copied text like:
    # Update Date	Apr 30, 2026	Apr 29, 2026
    label_lower = label.lower()
    for line in lines:
        if not line.lower().startswith(label_lower):
            continue
        rest = line[len(label):].strip(" 	:")
        if not rest:
            continue

        if kind == "version":
            values = re.findall(VERSION_PATTERN, rest)
        elif kind == "date":
            values = re.findall(DATE_PATTERN, rest)
        elif kind == "size":
            values = re.findall(SIZE_PATTERN, rest)
        elif kind == "package":
            values = re.findall(r"[a-zA-Z][\w]*(?:\.[a-zA-Z][\w]*)+", rest)
        elif kind == "license":
            values = re.findall(r"Not Required|Required", rest, flags=re.IGNORECASE)
        else:
            values = [x.strip() for x in re.split(r"\t+|\s{2,}", rest) if x.strip()]
        break

    return values[:max_values]


def parse_old_version_comparison(lines):
    package_values = extract_table_values(lines, "Package Name", kind="package")
    version_values = extract_table_values(lines, "Version", kind="version")
    update_date_values = extract_table_values(lines, "Update Date", kind="date")
    size_values = extract_table_values(lines, "Size", kind="size")
    requires_values = extract_table_values(lines, "Requires Android")
    architecture_values = extract_table_values(lines, "Architecture")
    signature_values = extract_table_values(lines, "Signature")
    license_values = extract_table_values(lines, "Google Play App License", kind="license")

    return {
        "version_comparison_available": "Yes" if any("Version Comparison" in line for line in lines) else "",
        "comparison_package_name_displayed": package_values[0] if len(package_values) >= 1 else "",
        "comparison_package_name_latest": package_values[1] if len(package_values) >= 2 else "",
        "comparison_version_displayed": version_values[0] if len(version_values) >= 1 else "",
        "comparison_version_latest": version_values[1] if len(version_values) >= 2 else "",
        "comparison_update_date_displayed": update_date_values[0] if len(update_date_values) >= 1 else "",
        "comparison_update_date_latest": update_date_values[1] if len(update_date_values) >= 2 else "",
        "comparison_size_displayed": size_values[0] if len(size_values) >= 1 else "",
        "comparison_size_latest": size_values[1] if len(size_values) >= 2 else "",
        "comparison_requires_android_displayed": requires_values[0] if len(requires_values) >= 1 else "",
        "comparison_requires_android_latest": requires_values[1] if len(requires_values) >= 2 else "",
        "comparison_architecture_displayed": architecture_values[0] if len(architecture_values) >= 1 else "",
        "comparison_architecture_latest": architecture_values[1] if len(architecture_values) >= 2 else "",
        "comparison_signature_displayed": signature_values[0] if len(signature_values) >= 1 else "",
        "comparison_signature_latest": signature_values[1] if len(signature_values) >= 2 else "",
        "google_play_app_license_displayed": license_values[0] if len(license_values) >= 1 else "",
        "google_play_app_license_latest": license_values[1] if len(license_values) >= 2 else "",
        "same_as_package_name": parse_prefixed_line(lines, "Package Name:"),
        "sha256": parse_prefixed_line(lines, "SHA-256:"),
        "verified_by": find_value_after_label(lines, "Verified by"),
        "trusted_app_label": "Trusted App" if any(line.lower() == "trusted app" for line in lines) else "",
    }


def parse_top_detail_metadata(lines):
    detail_update_date = find_value_before_label(lines, "Update date")
    detail_security_ratio = find_value_before_label(lines, "Security")
    detail_downloads = find_value_before_label(lines, "Downloads")
    detail_size = find_download_size(lines) or find_value_before_label(lines, "Size")

    before_android_os = find_value_before_label(lines, "Android OS")
    detail_android_os = before_android_os if is_android_requirement(before_android_os) else ""

    top_content_rating = ""
    for i, line in enumerate(lines):
        if line.lower() == "android os":
            if i - 1 >= 0 and not is_android_requirement(lines[i - 1]):
                top_content_rating = lines[i - 1].strip()
            elif i - 2 >= 0:
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
    comparison = parse_old_version_comparison(lines)

    requires_android = find_value_after_label(lines, "Requires Android")
    if not requires_android:
        requires_android = comparison.get("comparison_requires_android_displayed", "")

    architecture = find_value_after_label(lines, "Architecture")
    if not architecture:
        architecture = comparison.get("comparison_architecture_displayed", "")

    package_name = find_value_after_label(lines, "Package Name")
    if not package_name:
        package_name = comparison.get("comparison_package_name_displayed", "") or "com.android.chrome"

    return {
        "additional_app_latest_version": find_value_after_label(lines, "Latest Version"),
        "uploaded_by": find_value_after_label(lines, "Uploaded by"),
        "package_name": package_name,
        "languages": "",
        "requires_android": requires_android,
        "content_rating": find_value_after_label(lines, "Content Rating"),
        "architecture": architecture,
        "app_permissions_count": find_value_after_label(lines, "App Permissions"),
        "additional_app_category": find_value_after_label(lines, "Category"),
        "license_required": "Yes" if any(line.lower() == "license required" for line in lines) else "",
        "security_report_label": find_value_after_label(lines, "Security Report"),
        **comparison,
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

    for _ in range(10):
        if node is None:
            break
        text = node.get_text("\n", strip=True)
        if VERSION_CARD_RE.search(text):
            if not best_text or len(text) < len(best_text):
                best_text = text
        node = node.parent

    return best_text


def parse_versions_from_html(html: str, max_versions=100):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # Best mode: read real hrefs when APKPure HTML exposes them.
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
        apk_format = normalize_apk_format(match.group("apk_format"))

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

        rows = dedupe_rows(rows)
        if max_versions is not None and len(rows) >= max_versions:
            return rows[:max_versions]

    # Fallback from HTML text if href traversal only sees visible rows.
    if not rows or (max_versions is not None and len(rows) < max_versions):
        text_rows = parse_versions_from_text(soup_text(html), max_versions=max_versions)
        rows = dedupe_rows(rows + text_rows)

    return rows[:max_versions] if max_versions is not None else rows


def parse_versions_from_text(text: str, max_versions=100):
    rows = []

    for match in VERSION_CARD_RE.finditer(text):
        version = match.group("version").strip()
        size = match.group("size").strip()
        update_date = match.group("date").strip()
        apk_format = normalize_apk_format(match.group("apk_format"))
        detail_url = build_detail_url_from_version(version)
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
                url_matches_version=(detail_url_version_slug == version),
            )
        )

        rows = dedupe_rows(rows)
        if max_versions is not None and len(rows) >= max_versions:
            break

    return rows[:max_versions] if max_versions is not None else rows


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
    elif url_source_method == "manual_link_map_csv":
        note += " Detail URL was provided using manual link map CSV."
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
        "additional_app_latest_version": "",
        "uploaded_by": "",
        "package_name": "com.android.chrome",
        "languages": "",
        "requires_android": "",
        "content_rating": "",
        "architecture": "",
        "app_permissions_count": "",
        "additional_app_category": "",
        "license_required": "",
        "security_report_label": "",

        # Old-version detail / Version Comparison fields, useful for Chrome APKPure pages
        "version_comparison_available": "",
        "comparison_package_name_displayed": "",
        "comparison_package_name_latest": "",
        "comparison_version_displayed": "",
        "comparison_version_latest": "",
        "comparison_update_date_displayed": "",
        "comparison_update_date_latest": "",
        "comparison_size_displayed": "",
        "comparison_size_latest": "",
        "comparison_requires_android_displayed": "",
        "comparison_requires_android_latest": "",
        "comparison_architecture_displayed": "",
        "comparison_architecture_latest": "",
        "comparison_signature_displayed": "",
        "comparison_signature_latest": "",
        "google_play_app_license_displayed": "",
        "google_play_app_license_latest": "",
        "same_as_package_name": "",
        "sha256": "",
        "verified_by": "",
        "trusted_app_label": "",

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
        key = (row["version_number"], row["version_release_date"], row["file_size"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def remove_apkpure_boilerplate(desc: str, version: str) -> str:
    desc = clean_text(desc)

    boilerplate_patterns = [
        rf"{APP_NAME} is a web browser app that helps you search and browse quickly\.?,?",
        rf"Download and install old versions of {APP_NAME}.*?features!?",
        r"Download the Latest Version\.?,?",
        rf"{APP_NAME} old version {re.escape(version)} was released on .*? by Google LLC\.?,?",
        r"The app download size is .*?\.?,?",
        r"\b\d+(?:\.\d+)?\s*(?:MB|GB|KB)\.?,?",
        rf"We recommend you download the latest version of {APP_NAME}.*?performance\.?,?",
        r"We recommend you.*",
        r"Check out the detailed comparison between the latest and old version of Google Chrome.*",
    ]

    cleaned = desc
    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    return clean_text(cleaned)


def parse_detail_page_text(text: str, expected_version: str):
    lines = text_to_lines(text)

    detail_metadata = {}
    detail_metadata.update(parse_top_detail_metadata(lines))
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
        "web browser app",
        "search and browse quickly",
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

    vague_but_real_release_notes = [
        "minor bug fixes and improvements",
        "bug fixes and improvements",
        "performance improvements",
        "stability improvements",
        "thanks for choosing chrome! this release includes stability and performance improvements.",
    ]

    if clean_lower in vague_but_real_release_notes:
        return False

    return False


def infer_update_categories(description: str, raw_description: str):
    text = f"{description} {raw_description}".lower()
    categories = []

    if any(x in text for x in ["bug", "fix", "crash", "stability", "performance", "improvement", "improvements"]):
        categories.append("Bug fixes / performance improvements")
    if any(x in text for x in ["ui", "design", "layout", "interface", "redesign", "visual"]):
        categories.append("UI / design changes")
    if any(x in text for x in ["privacy", "data policy", "consent", "tracking", "gdpr"]):
        categories.append("Privacy / data policy changes")
    if any(x in text for x in ["ai", "artificial intelligence", "generative", "recommendation", "personalized"]):
        categories.append("AI-related features")
    if any(x in text for x in ["payment", "checkout", "subscription", "premium", "monetization", "purchase", "ads"]):
        categories.append("Payments / monetization")
    if any(x in text for x in ["personalization", "recommendations", "recommended", "discover", "discovery", "search", "suggestions", "address bar"]):
        categories.append("Personalization / recommendations")
    if any(x in text for x in ["browser", "browsing", "tab", "tabs", "sync", "bookmarks", "password manager", "translate", "safe browsing"]):
        categories.append("Browser / browsing features")
    if any(x in text for x in ["security", "account safety", "login", "password", "two-factor", "2fa", "malware"]):
        categories.append("Security / account safety")
    if any(x in text for x in ["sdk", "api", "developer", "integration"]):
        categories.append("SDK / API / developer integration")
    if any(x in text for x in ["new feature", "introducing", "now you can", "added", "launch", "shortcut", "shortcuts", "tab groups", "voice search", "google lens"]):
        categories.append("New product feature")

    if not categories:
        categories.append("Other")

    return "; ".join(dict.fromkeys(categories))


def make_standardized_summary(description: str, raw_description: str, feature_specificity: str):
    if feature_specificity == "not_provided":
        return "No version-specific update reason was provided by APKPure."
    if feature_specificity == "generic":
        return "APKPure provides generic app or rollback text, but no clear version-specific reason for this update."
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
        "additional_app_latest_version",
        "uploaded_by",
        "package_name",
        "languages",
        "requires_android",
        "content_rating",
        "architecture",
        "app_permissions_count",
        "additional_app_category",
        "license_required",
        "security_report_label",
        "version_comparison_available",
        "comparison_package_name_displayed",
        "comparison_package_name_latest",
        "comparison_version_displayed",
        "comparison_version_latest",
        "comparison_update_date_displayed",
        "comparison_update_date_latest",
        "comparison_size_displayed",
        "comparison_size_latest",
        "comparison_requires_android_displayed",
        "comparison_requires_android_latest",
        "comparison_architecture_displayed",
        "comparison_architecture_latest",
        "comparison_signature_displayed",
        "comparison_signature_latest",
        "google_play_app_license_displayed",
        "google_play_app_license_latest",
        "same_as_package_name",
        "sha256",
        "verified_by",
        "trusted_app_label",
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
            f" Detail page version {row['detail_page_version']} does not match displayed version "
            f"{row['version_number']}."
        )

    if not row["content_rating"] and row["detail_page_top_content_rating"]:
        row["content_rating"] = row["detail_page_top_content_rating"]
    if not row["requires_android"] and row["detail_page_android_os"]:
        row["requires_android"] = row["detail_page_android_os"]

    return row


def apply_link_map(rows, link_map_csv):
    if not link_map_csv:
        return rows

    link_df = pd.read_csv(link_map_csv)
    link_map = {}
    for _, r in link_df.iterrows():
        link_map[str(r["version_number"])] = str(r["detail_source_url"])

    for row in rows:
        version = row["version_number"]
        if version in link_map:
            actual_url = link_map[version]
            row["detail_source_url"] = actual_url
            row["detail_url_source_method"] = "manual_link_map_csv"
            row["detail_url_version_slug"] = extract_version_from_url(actual_url)
            row["detail_url_matches_displayed_version"] = row["detail_url_version_slug"] == version
            row["source_note"] += " Detail URL replaced using manual link map CSV."
            if not row["detail_url_matches_displayed_version"]:
                row["source_note"] += (
                    f" Warning: displayed version {version} differs from detail URL slug "
                    f"{row['detail_url_version_slug']}."
                )
    return rows


def collect_from_web(max_versions=100, max_detail=100, sleep_seconds=1.0):
    print(f"Collecting versions page: {VERSIONS_URL}")
    html = fetch_html(VERSIONS_URL)
    rows = parse_versions_from_html(html, max_versions=max_versions)

    if not rows:
        print("No rows found from href-based HTML parser. Trying text fallback from fetched HTML.")
        rows = parse_versions_from_text(soup_text(html), max_versions=max_versions)

    print(f"Found {len(rows)} version rows")
    if max_versions is not None and len(rows) < max_versions:
        print(
            f"Warning: requested up to {max_versions} version rows, but only {len(rows)} were found in the available page text/HTML."
        )

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


def collect_from_local_text(versions_text_path, detail_text_dir=None, link_map_csv=None, max_versions=100, max_detail=100):
    versions_text = Path(versions_text_path).read_text(encoding="utf-8", errors="ignore")
    rows = parse_versions_from_text(versions_text, max_versions=max_versions)
    rows = apply_link_map(rows, link_map_csv)

    print(f"Found {len(rows)} version rows from local text")
    if max_versions is not None and len(rows) < max_versions:
        print(
            f"Warning: requested up to {max_versions} version rows, but only {len(rows)} were found in the local text."
        )

    rows_to_detail = rows if max_detail is None else rows[:max_detail]
    if detail_text_dir:
        detail_dir = Path(detail_text_dir)
        for idx, row in enumerate(rows_to_detail, start=1):
            version = row["version_number"]
            detail_file = detail_dir / f"{version}.txt"
            print(f"[{idx}/{len(rows_to_detail)}] local detail text: {detail_file.name}")

            if not detail_file.exists():
                row["source_note"] += " Detail text file not provided."
                row["feature_specificity"] = "not_provided"
                row["feature_text_sufficient_for_research"] = False
                row["standardized_update_categories"] = "Other"
                row["standardized_summary"] = "No local detail page text was provided."
                continue

            detail_text = detail_file.read_text(encoding="utf-8", errors="ignore")
            enrich_row_with_detail(row, detail_text)
    else:
        for row in rows_to_detail:
            row["feature_specificity"] = row["feature_specificity"] or "not_provided"
            row["feature_text_sufficient_for_research"] = False
            row["standardized_update_categories"] = row["standardized_update_categories"] or "Other"
            row["standardized_summary"] = row["standardized_summary"] or "No local detail page text was provided."

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
    print(f"Total rows saved: {len(df)}")
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
        "detail_page_android_os",
        "requires_android",
        "content_rating",
        "uploaded_by",
        "additional_app_category",
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
        help="Maximum number of version rows to save. Use -1 for all available rows.",
    )
    parser.add_argument(
        "--max-detail",
        type=int,
        default=100,
        help="How many detail pages to visit/enrich. Use -1 for all saved rows. Use 0 to skip detail pages.",
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
        help="Optional folder containing browser-copied detail pages named like 147.0.7727.137.txt.",
    )
    parser.add_argument(
        "--link-map-csv",
        default=None,
        help="Optional CSV with version_number, detail_source_url for manual actual APKPure links.",
    )

    args = parser.parse_args()

    max_versions = None if args.max_versions < 0 else args.max_versions
    max_detail = None if args.max_detail < 0 else args.max_detail

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
