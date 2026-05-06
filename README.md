# WLIURA Mobile App Update History Dataset

This repository contains scripts, processed datasets, and a final Excel submission for the WLIURA S26 Research Assistant test task.

The goal of the task is to collect mobile app version and update history information for 10 popular apps and their matched iOS and Android versions. Each row in the final dataset represents one app-platform-version observation. The dataset is designed to support analysis of the timing, frequency, and nature of mobile app updates over time.

GitHub repository: https://github.com/junseoparkX/wliura-mobile-app-update-history

---

## Project Overview

This project collects version and update history data for 10 matched mobile apps across iOS and Android.

The final Excel workbook includes:

1. A summary sheet describing the collection approach, GitHub repository, observed patterns, and data quality limitations.
2. A combined iOS update history sheet.
3. A combined Android update history sheet.
4. A combined iOS + Android update history sheet.

The main goal is to turn messy public app-history sources into a structured spreadsheet with version numbers, release/update dates, update descriptions, standardized update categories, standardized summaries, source URLs, and notes about missing or lower-quality information.

---

## Selected Apps

| App | Main Category | iOS Source | Android Source |
|---|---|---|---|
| Amazon Shopping | Shopping | Apptopia | APKPure |
| Facebook | Social media | Apptopia | APKPure |
| Google Chrome | Browser / Productivity | Apptopia | APKPure |
| Google Docs | Productivity | Apptopia | APKPure |
| Grab | Transportation / Food delivery | Apptopia | APKPure |
| Instagram | Social media | Apptopia | APKPure |
| Netflix | Entertainment | Apptopia | APKPure |
| Spotify | Music / Entertainment | Apptopia | APKPure |
| TikTok | Social media / Entertainment | Apptopia | APKPure |
| YouTube | Video / Entertainment | Apptopia | APKPure |

---

## Repository Structure

```text
wliura-mobile-app-update-history/
├── data/
│   ├── final/
│   │   └── Junseo_Park_WLIURA_S26_Mobile_App_Update_History.xlsx
│   │
│   ├── ios_txt/
│   │   ├── amazon_shopping_apptopia_about.txt
│   │   ├── facebook_apptopia_about.txt
│   │   ├── google_chrome_apptopia_about.txt
│   │   ├── google_docs_apptopia_about.txt
│   │   ├── grab_apptopia_about.txt
│   │   ├── instagram_apptopia_about.txt
│   │   ├── netflix_apptopia_about.txt
│   │   ├── spotify_apptopia_about.txt
│   │   ├── tiktok_apptopia_about.txt
│   │   └── youtube_apptopia_about.txt
│   │
│   ├── processed/
│   │   ├── android/
│   │   │   └── android_apkpure_all_apps_combined.csv
│   │   ├── ios/
│   │   │   └── ios_apptopia_all_apps_combined.csv
│   │   └── summary_sheet_with_github_styled.xlsx
│   │
│   └── raw/
│
├── deep_research/
│   ├── batch1.docx
│   ├── batch2.docx
│   ├── batch3.docx
│   └── combined_app_update_history_all.csv
│
├── experiments/
│   ├── data/
│   ├── node_modules/
│   ├── output/
│   ├── scripts/
│   ├── package.json
│   ├── package-lock.json
│   ├── requirements.txt
│   └── RUN_COMMANDS.md
│
├── scripts/
│   ├── android/
│   └── ios/
│
├── README.md
└── requirements.txt
```

---

## Final Outputs

The main processed platform-level files are:

```text
data/processed/ios/ios_apptopia_all_apps_combined.csv
data/processed/android/android_apkpure_all_apps_combined.csv
```

The final submission workbook is:

```text
data/final/Junseo_Park_WLIURA_S26_Mobile_App_Update_History.xlsx
```

The final workbook is organized as:

| Sheet | Description |
|---|---|
| `Summary` | Data collection approach, GitHub repository, observed patterns, output files, and limitations |
| `iOS_Update_History` | Combined iOS version/update history observations |
| `Android_Update_History` | Combined Android version/update history observations |
| `All_Update_History` | Combined iOS and Android observations in one sheet |

---

## Data Collection Approach

### iOS

For iOS, I used Apptopia app pages as the main source. Since direct structured export was not always available, I saved browser-copied Apptopia page text into the `data/ios_txt/` folder and wrote Python scripts to parse the copied text.

The iOS pipeline extracts:

- app name
- platform
- developer/company
- app category
- version number
- version release date
- current-version indicator
- initial app release date where available
- update description/release notes
- standardized update categories
- standardized summaries
- source URL
- app-level metadata where available

The individual iOS records were combined into:

```text
data/processed/ios/ios_apptopia_all_apps_combined.csv
```

### Android

For Android, I used APKPure version history pages and detail pages as the main source. The Android scripts parse version cards, version numbers, release dates, APK/XAPK formats, file sizes, and available detail-page metadata.

The Android pipeline extracts:

- app name
- platform
- developer/company
- app category
- version number
- version release/update date
- current-version indicator
- initial app release date where available
- APK/XAPK format
- file size
- Android requirements
- content rating
- package name
- app permissions count where available
- update description/release notes where available
- standardized update categories
- standardized summaries
- APKPure source URLs
- source notes and data quality notes

The individual Android records were combined into:

```text
data/processed/android/android_apkpure_all_apps_combined.csv
```

---

## Why This Approach Was Used

I explored multiple possible approaches before choosing the final pipeline.

The initial idea was to use broad web search, LLM-assisted collection, app-store APIs, scraping tools, and public app-history platforms. However, this was not the best approach for collecting many row-level version observations because the output was difficult to verify, inconsistent across apps, and less reliable for source-by-source traceability.

I also tried a Deep Research / ChatGPT-assisted collection workflow and stored the exploratory outputs in the `deep_research/` folder. This was useful for understanding possible sources and app coverage, but it was not ideal for producing a large, structured, reproducible spreadsheet with many version-level observations. The main issue was that it was difficult to guarantee consistent historical coverage, exact version dates, and clickable source URLs for every row.

The `experiments/` folder contains additional exploratory attempts and alternative collection approaches. These were kept for transparency but are not the final pipeline.

The final approach was chosen because it is more reproducible and easier to audit:

1. Save or access source pages app by app.
2. Parse version records with Python scripts.
3. Standardize fields into a shared schema.
4. Combine individual app CSVs into platform-level datasets.
5. Merge the summary, iOS, Android, and combined sheets into one final Excel workbook.
6. Keep source URLs and source notes for traceability.
7. Mark missing or generic update descriptions explicitly.

---

## Standardized Update Categories

Release notes were mapped into standardized categories so that qualitative update descriptions can later be converted into variables for analysis.

The standardized categories include:

- Bug fixes / performance improvements
- UI / design changes
- Privacy / data policy changes
- AI-related features
- Payments / monetization
- Personalization / recommendations
- Security / account safety
- SDK / API / developer integration
- New product feature
- Other

The scripts use rule-based keyword matching and app-specific summary logic to classify updates. When no useful version-specific description is available, the scripts mark the update as `Other` or indicate that the release note was missing, generic, or not provided.

---

## Important Columns

The final datasets include the core fields requested in the task:

```text
app_name
platform
developer_company
app_category
version_number
version_release_date
is_current_version
initial_app_release_date
update_description
standardized_update_categories
standardized_summary
version_history_source
version_history_source_url
detail_source_url
source_note
source_csv_file
```

Additional platform-specific metadata fields are included when available.

Examples of iOS-specific metadata:

```text
ios_app_id
bundle_id
app_store_price
in_app_purchase
store_categories
file_size
os_compatibility
device_compatibility
age_rating
languages
permission_categories
permission_usage_keys
permission_count
description_feature_flags
```

Examples of Android-specific metadata:

```text
apk_format
file_size
package_name
requires_android
content_rating
architecture
app_permissions_count
detail_page_size
detail_page_downloads
detail_page_update_date
security_scan_result
security_scan_date
detail_url_source_method
detail_url_matches_displayed_version
```

---

## Reproduction Steps

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the iOS app-level collection scripts after saving Apptopia copied text files in `data/ios_txt/`:

```bash
python scripts/ios/collect_apptopia_amazon_shopping_ios_from_txt.py
python scripts/ios/collect_apptopia_facebook_ios_from_txt.py
python scripts/ios/collect_apptopia_google_chrome_ios_from_txt.py
python scripts/ios/collect_apptopia_google_docs_ios_from_txt.py
python scripts/ios/collect_apptopia_grab_ios_from_txt.py
python scripts/ios/collect_apptopia_instagram_ios_from_txt.py
python scripts/ios/collect_apptopia_netflix_ios_from_txt.py
python scripts/ios/collect_apptopia_spotify_ios_from_txt.py
python scripts/ios/collect_apptopia_tiktok_ios_from_txt.py
python scripts/ios/collect_apptopia_youtube_ios_from_txt.py
```

Combine the iOS app-level CSV files:

```bash
python scripts/ios/combine_ios_apptopia_csvs.py
```

Run the Android app-level collection scripts:

```bash
python scripts/android/collect_apkpure_amazon_shopping_safe.py
python scripts/android/collect_apkpure_facebook_safe.py
python scripts/android/collect_apkpure_google_chrome_safe.py
python scripts/android/collect_apkpure_google_docs_safe.py
python scripts/android/collect_apkpure_grab_safe.py
python scripts/android/collect_apkpure_instagram_safe.py
python scripts/android/collect_apkpure_netflix_safe.py
python scripts/android/collect_apkpure_spotify_safe.py
python scripts/android/collect_apkpure_tiktok_safe.py
python scripts/android/collect_apkpure_youtube_safe.py
```

Combine the Android app-level CSV files:

```bash
python scripts/android/combine_android_apkpure_csvs.py
```

The processed outputs are saved to:

```text
data/processed/ios/ios_apptopia_all_apps_combined.csv
data/processed/android/android_apkpure_all_apps_combined.csv
```

The final workbook is saved to:

```text
data/final/Junseo_Park_WLIURA_S26_Mobile_App_Update_History.xlsx
```

---

## Data Quality Notes

Several limitations should be considered when using this dataset.

First, iOS and Android version histories are not equally available. The iOS Apptopia pages generally provided longer and more consistent historical coverage, while Android historical update descriptions from APKPure were sometimes missing, generic, or repeated across versions.

Second, APKPure is a third-party Android source, not the official Google Play historical archive. It was useful for collecting version numbers, update dates, file sizes, APK/XAPK metadata, and detail-page URLs, but some release notes were limited or not version-specific.

Third, some Android apps list multiple APK or XAPK variants for the same displayed version. The combine scripts therefore check duplicates and standardize the data toward an app-platform-version structure.

Fourth, many release notes are generic, such as routine bug fixes or performance improvements. These observations are still useful for update-frequency analysis, but they are less informative for identifying specific product or policy changes.

Fifth, initial app release dates are not always consistently available across sources, so some initial release dates should be treated as approximate or source-dependent.

---

## Observed Patterns

The collected data suggest that popular consumer apps update frequently, often on a weekly or biweekly cycle. Many updates are routine maintenance releases focused on bug fixes, performance improvements, reliability, stability, and security.

Some updates are more feature-heavy and include changes related to:

- UI redesigns
- new product features
- personalization and recommendation systems
- payments or monetization
- account safety and security
- AI-related features
- platform or SDK integrations

Social media and entertainment apps tend to show frequent update cycles. Shopping, productivity, browser, and transportation apps often combine routine maintenance with occasional larger feature or integration updates.

---

## Notes on Exploratory Attempts

The `deep_research/` folder contains early exploratory outputs from a Deep Research / ChatGPT-assisted approach. These files were not used as the final source of truth because they were less suitable for collecting many structured, row-level observations with consistent source URLs and reproducible parsing.

The `experiments/` folder contains alternative or failed attempts, including earlier scraping/API-style workflows. These files are kept for transparency and should not be treated as the final dataset pipeline.

The final dataset should be based on:

```text
data/processed/ios/ios_apptopia_all_apps_combined.csv
data/processed/android/android_apkpure_all_apps_combined.csv
data/final/Junseo_Park_WLIURA_S26_Mobile_App_Update_History.xlsx
```

---

## Submission Format

The final submission is an Excel workbook with four sheets:

1. `Summary`
2. `iOS_Update_History`
3. `Android_Update_History`
4. `All_Update_History`

This format keeps the summary first, separates iOS and Android observations for readability, and also provides a combined platform-level sheet for easier analysis.

---

## Author

Junseo Park

WLIURA S26 Research Assistant Test Task  
UBC Sauder School of Business
