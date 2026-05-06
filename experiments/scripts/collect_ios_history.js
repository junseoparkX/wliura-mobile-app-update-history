/*
Collect iOS App Store version history using the Node package app-store-scraper.

Setup:
    npm install

Usage:
    node scripts/collect_ios_history.js data/app_registry.csv data/raw/ios_version_history.csv

Notes:
    - This is the best first attempt for multi-year iOS version history.
    - If the package/API changes or a specific app fails, keep the current-only iOS rows
      and document the limitation in data_quality_notes.
*/

const fs = require("fs");
const path = require("path");
const store = require("app-store-scraper");

const OUTPUT_COLUMNS = [
  "app_name",
  "platform",
  "developer_company",
  "app_category",
  "version_number",
  "version_release_date",
  "is_current_version",
  "initial_app_release_date",
  "update_description_release_notes",
  "standardized_update_categories",
  "standardized_update_summary",
  "source_url",
  "data_quality_notes",
];

function parseSimpleCsv(filePath) {
  const text = fs.readFileSync(filePath, "utf8").trim();
  const lines = text.split(/\r?\n/);
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    const row = {};
    headers.forEach((h, i) => {
      row[h] = values[i] || "";
    });
    return row;
  });
}

function escapeCsv(value) {
  if (value === null || value === undefined) return "";
  const str = String(value).replace(/\r?\n/g, " ").trim();
  if (/[",\n]/.test(str)) return `"${str.replace(/"/g, '""')}"`;
  return str;
}

function toDateOnly(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toISOString().slice(0, 10);
}

async function collectHistoryForApp(row) {
  const appId = Number(row.ios_app_id);
  const sourceUrl = row.ios_url || `https://apps.apple.com/app/id${appId}`;

  try {
    const appInfo = await store.app({ id: appId });
    const history = await store.versionHistory({ id: appId });

    const sortedHistory = (history || []).sort((a, b) => {
      const da = new Date(a.releaseDate || a.date || 0).getTime();
      const db = new Date(b.releaseDate || b.date || 0).getTime();
      return db - da;
    });

    return sortedHistory.map((item, index) => {
      return {
        app_name: row.app_name,
        platform: "iOS",
        developer_company: appInfo.developer || appInfo.sellerName || "",
        app_category: row.app_category,
        version_number: item.version || "",
        version_release_date: toDateOnly(item.releaseDate || item.date || ""),
        is_current_version: index === 0 ? "Yes" : "No",
        initial_app_release_date: toDateOnly(appInfo.released || ""),
        update_description_release_notes: item.releaseNotes || item.notes || "",
        standardized_update_categories: "",
        standardized_update_summary: "",
        source_url: sourceUrl,
        data_quality_notes: "iOS version history collected with app-store-scraper. Coverage depends on public App Store version history availability.",
      };
    });
  } catch (err) {
    return [
      {
        app_name: row.app_name,
        platform: "iOS",
        developer_company: "",
        app_category: row.app_category,
        version_number: "",
        version_release_date: "",
        is_current_version: "",
        initial_app_release_date: "",
        update_description_release_notes: "",
        standardized_update_categories: "",
        standardized_update_summary: "",
        source_url: sourceUrl,
        data_quality_notes: `iOS history collection failed: ${err.message}`,
      },
    ];
  }
}

async function main() {
  const registryPath = process.argv[2] || "data/app_registry.csv";
  const outputPath = process.argv[3] || "data/raw/ios_version_history.csv";

  const registry = parseSimpleCsv(registryPath);
  let allRows = [];

  for (const row of registry) {
    console.log(`Collecting iOS history for ${row.app_name}...`);
    const rows = await collectHistoryForApp(row);
    allRows = allRows.concat(rows);
  }

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const lines = [
    OUTPUT_COLUMNS.join(","),
    ...allRows.map((row) => OUTPUT_COLUMNS.map((col) => escapeCsv(row[col])).join(",")),
  ];
  fs.writeFileSync(outputPath, lines.join("\n"), "utf8");
  console.log(`Saved ${allRows.length} iOS history rows to ${outputPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
