
import sys, shutil, json, re
from pathlib import Path
import pandas as pd
import numpy as np

CATEGORY_ALIASES = {
    "Scoring": ["Scoring", "Career_Scoring", "Regular_Scoring", "Playoff_Scoring"],
    "Efficiency": ["Efficiency", "Career_Efficiency", "Regular_Efficiency", "Playoff_Efficiency"],
    "Creation": ["Creation", "Career_Creation", "Regular_Creation", "Playoff_Creation"],
    "Rebounding": ["Rebounding", "Career_Rebounding", "Regular_Rebounding", "Playoff_Rebounding"],
    "Defense": ["Defense", "Career_Defense", "Regular_Defense", "Playoff_Defense"],
    "Impact": ["Impact", "Career_Impact", "Regular_Impact", "Playoff_Impact"],
    "Overall_SDI": ["Overall_SDI", "SDI_v4", "SDI_v4_WOWY", "Career_SDI_v4", "Regular_SDI_v4", "Playoff_SDI_v4"],
}

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def find_col(df, aliases):
    cols = list(df.columns)
    for a in aliases:
        na = norm(a)
        for c in cols:
            if norm(c) == na:
                return c
    return None

def is_qualified(df):
    # Prefer an explicit qualification column.
    for c in df.columns:
        n = norm(c)
        if n in {"qualifiedcareer", "qualified", "per75qualified", "qualifiedregular", "qualifiedplayoff"}:
            vals = df[c].astype(str).str.lower()
            mask = vals.isin(["true","1","yes","y"])
            if mask.any():
                return mask
    # Otherwise all non-null composite observations form the population.
    return pd.Series(True, index=df.index)

def percentile(series):
    """Higher raw SDI/category score = higher companion percentile."""
    x = pd.to_numeric(series, errors="coerce")
    valid = x.notna()
    out = pd.Series(np.nan, index=series.index, dtype=float)
    if valid.sum() == 0:
        return out
    ranks = x[valid].rank(method="average", ascending=True)
    n = len(ranks)
    if n == 1:
        out.loc[valid] = 100.0
    else:
        out.loc[valid] = 100.0 * (ranks - 1.0) / (n - 1)
    return out

def percentile_col_name(col):
    return f"{col}_Percentile"

def process_file(path, report):
    df = pd.read_csv(path)
    qmask = is_qualified(df)
    added = []
    found = {}

    # Only create a category companion when a matching numeric composite exists.
    for category, aliases in CATEGORY_ALIASES.items():
        col = find_col(df, aliases)
        if col is None:
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        pop = values.where(qmask)
        if pop.notna().sum() < 2:
            continue

        pct = percentile(pop)
        outcol = percentile_col_name(col)
        # Preserve an existing companion only if it already exists and is numeric;
        # otherwise create it. Recalculation is intentional so Route A companions
        # cannot drift from the current composite.
        df[outcol] = pct.round(6)
        added.append(outcol)
        found[category] = col

    if not added:
        return

    backup = path.with_suffix(path.suffix + ".route_a_backup")
    if not backup.exists():
        shutil.copy2(path, backup)

    df.to_csv(path, index=False)

    report.append({
        "file": str(path),
        "qualified_population": int(qmask.sum()),
        "added_columns": added,
        "source_composites": found,
        "backup": str(backup),
    })

def main():
    if len(sys.argv) != 2:
        print("Usage: python apply_route_a_companion_percentiles.py <WebsiteFolder>")
        raise SystemExit(2)

    site = Path(sys.argv[1]).expanduser().resolve()
    if not site.exists():
        raise SystemExit(f"Folder not found: {site}")

    data = site / "data"
    if not data.exists():
        raise SystemExit(f"data folder not found: {data}")

    # Prioritize the known Career SDI file, then discover related SDI files.
    candidates = []
    preferred = data / "regular_career_sdi_v4_wowy_rts.csv"
    if preferred.exists():
        candidates.append(preferred)

    patterns = [
        "*career*sdi*.csv",
        "*regular*5*year*sdi*.csv",
        "*regular*peak*sdi*.csv",
        "*playoff*career*sdi*.csv",
        "*playoff*5*year*sdi*.csv",
        "*playoff*peak*sdi*.csv",
    ]
    seen = {p.resolve() for p in candidates}
    for pat in patterns:
        for p in data.glob(pat):
            if p.resolve() not in seen:
                candidates.append(p)
                seen.add(p.resolve())

    report = []
    for p in candidates:
        try:
            process_file(p, report)
        except Exception as e:
            report.append({"file": str(p), "error": repr(e)})

    report_path = site / "route_a_companion_percentile_report.json"
    report_path.write_text(json.dumps({
        "route": "A",
        "primary_score_unchanged": True,
        "companion_percentile_added": True,
        "files": report
    }, indent=2), encoding="utf-8")

    print("=" * 72)
    print("ROUTE A — SDI COMPANION PERCENTILE INTEGRATION")
    print("=" * 72)
    print(f"Site: {site}")
    print(f"Files processed: {len(report)}")
    for item in report:
        if "error" in item:
            print(f"ERROR: {item['file']} -> {item['error']}")
        else:
            print(f"OK: {item['file']}")
            print(f"  Qualified population: {item['qualified_population']}")
            print(f"  Added: {', '.join(item['added_columns'])}")
    print(f"Report: {report_path}")

if __name__ == "__main__":
    main()
