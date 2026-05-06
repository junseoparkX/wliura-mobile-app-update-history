import argparse
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent

# Input: 10 iOS app-level CSV files
DEFAULT_INPUT_DIR = PROJECT_DIR / "data" / "raw" / "ios"

# Output: combined CSV, not inside raw folder
DEFAULT_OUTPUT = PROJECT_DIR / "data" / "processed" / "ios" / "ios_apptopia_all_apps_combined.csv"


def read_csv_safely(csv_path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, encoding="utf-8", dtype=str)


def clean_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df


def normalize_app_names(df: pd.DataFrame) -> pd.DataFrame:
    if "app_name" not in df.columns:
        return df

    app_name_map = {
        "Grab: Taxi Ride, Food Delivery": "Grab",
        "Grab Taxi & Food Delivery": "Grab",
        "Amazon": "Amazon Shopping",
        "Amazon Shopping": "Amazon Shopping",
    }

    df["app_name"] = df["app_name"].replace(app_name_map)
    return df


def fill_required_fields(df: pd.DataFrame) -> pd.DataFrame:
    required_defaults = {
        "platform": "iOS",
        "standardized_update_categories": "Other",
        "standardized_summary": "No version-specific update summary was available from the iOS source.",
        "update_description": "",
        "update_description_raw": "",
        "source_note": "Apptopia iOS version history source.",
        "version_history_source": "Apptopia",
    }

    for col, default_value in required_defaults.items():
        if col not in df.columns:
            df[col] = default_value
        else:
            df[col] = df[col].fillna("").astype(str).str.strip()
            df.loc[df[col] == "", col] = default_value

    return df


def mark_current_version_by_app(df: pd.DataFrame) -> pd.DataFrame:
    if "app_name" not in df.columns or "version_number" not in df.columns:
        return df

    df["is_current_version"] = "False"

    # Assumption:
    # Each app-level Apptopia CSV is already ordered newest to oldest.
    # The first version for each app is treated as the current version.
    for app_name, group in df.groupby("app_name", sort=False):
        first_index = group.index[0]
        df.loc[first_index, "is_current_version"] = "True"

    return df


def remove_ios_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    iOS usually has one row per version, but this prevents accidental duplicate rows
    if a file was copied twice or a script was rerun into raw/.
    """

    subset_cols = []

    for col in ["app_name", "platform", "version_number", "version_release_date"]:
        if col in df.columns:
            subset_cols.append(col)

    if len(subset_cols) < 4:
        return df.drop_duplicates()

    before = len(df)
    df = df.drop_duplicates(subset=subset_cols, keep="first")
    after = len(df)

    print(f"iOS version-level duplicate cleanup: {before} -> {after}")

    return df


def reorder_basic_columns_first(df: pd.DataFrame) -> pd.DataFrame:
    basic_cols = [
        "app_name",
        "platform",
        "developer_company",
        "app_category",
        "version_number",
        "version_release_date",
        "is_current_version",
        "initial_app_release_date",
        "update_description",
        "standardized_update_categories",
        "standardized_summary",
        "version_history_source",
        "version_history_source_url",
        "source_note",
        "source_csv_file",
    ]

    existing_basic_cols = [col for col in basic_cols if col in df.columns]
    other_cols = [col for col in df.columns if col not in existing_basic_cols]

    return df[existing_basic_cols + other_cols]


def combine_ios_csvs(input_dir: Path, output_csv: Path, expected_count: int = 10):
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)

    csv_files = sorted(input_dir.glob("*.csv"))

    # Prevent accidentally re-combining already combined files.
    csv_files = [
        f for f in csv_files
        if "combined" not in f.name.lower()
        and "all_apps" not in f.name.lower()
        and "integrated" not in f.name.lower()
        and "processed" not in f.name.lower()
    ]

    if not csv_files:
        raise RuntimeError(f"No CSV files found in: {input_dir}")

    print(f"Found {len(csv_files)} iOS CSV files in {input_dir}")

    if expected_count is not None and len(csv_files) != expected_count:
        print(
            f"Warning: expected {expected_count} CSV files, "
            f"but found {len(csv_files)} files."
        )

    dfs = []

    for csv_file in csv_files:
        print(f"Reading: {csv_file.name}")
        df = read_csv_safely(csv_file)
        df = clean_string_columns(df)

        # Traceability
        df["source_csv_file"] = csv_file.name

        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True, sort=False)

    combined = clean_string_columns(combined)
    combined = normalize_app_names(combined)
    combined = fill_required_fields(combined)

    combined = remove_ios_duplicates(combined)

    if "app_name" in combined.columns:
        combined = combined.sort_values(["app_name"], kind="stable").reset_index(drop=True)

    combined = mark_current_version_by_app(combined)
    combined = reorder_basic_columns_first(combined)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print()
    print(f"Saved combined iOS CSV: {output_csv}")
    print(f"Total rows saved: {len(combined)}")

    if "app_name" in combined.columns:
        print()
        print(f"Total apps: {combined['app_name'].nunique()}")
        print("Rows by app:")
        print(combined["app_name"].value_counts().to_string())

    if "is_current_version" in combined.columns:
        print()
        print("Current-version count by app:")
        print(
            combined[combined["is_current_version"] == "True"]["app_name"]
            .value_counts()
            .to_string()
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Folder containing the 10 iOS app-level CSV files.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output path for the combined iOS CSV file.",
    )

    parser.add_argument(
        "--expected-count",
        type=int,
        default=10,
        help="Expected number of iOS CSV files. Use -1 to skip this check.",
    )

    args = parser.parse_args()

    expected_count = None if args.expected_count < 0 else args.expected_count

    combine_ios_csvs(
        input_dir=Path(args.input_dir),
        output_csv=Path(args.output),
        expected_count=expected_count,
    )


if __name__ == "__main__":
    main()