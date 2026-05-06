# Run order

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
```

Collect current Android metadata:

```bash
python scripts/collect_android.py --registry data/app_registry.csv --output data/raw/android_current_updates.csv
```

Collect current iOS metadata:

```bash
python scripts/collect_ios_current.py --registry data/app_registry.csv --output data/raw/ios_current_updates.csv
```

Optional but recommended for longer iOS version history:

```bash
npm install
node scripts/collect_ios_history.js data/app_registry.csv data/raw/ios_version_history.csv
```

Combine raw CSV files into one Excel workbook:

```bash
python scripts/build_excel_from_raw.py --raw-dir data/raw --output output/app_update_history_filled.xlsx
```

Categorize release notes:

```bash
python scripts/categorize_updates.py \
  --input output/app_update_history_filled.xlsx \
  --sheet "Update History" \
  --output output/app_update_history_categorized.xlsx
```

Final manual checks:

- Open `output/app_update_history_categorized.xlsx`.
- Check rows with missing version dates or missing release notes.
- Supplement Android historical rows from AppBrain/APKMirror where possible.
- Add final pattern summary to the `Summary` sheet.
