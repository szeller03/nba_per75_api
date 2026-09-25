
import sys
from pathlib import Path
import pandas as pd

p = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path("data/regular_career_sdi_v4_wowy_rts.csv")
df = pd.read_csv(p)
print("FILE:", p)
print("ROWS:", len(df))
for c in df.columns:
    if c.endswith("_Percentile"):
        x = pd.to_numeric(df[c], errors="coerce")
        print(f"{c}: nonnull={x.notna().sum()} min={x.min():.2f} max={x.max():.2f}")
print("\nNamed checks:")
for name in ["Tim Duncan","Hakeem Olajuwon","Rudy Gobert","Nikola Jokić","Michael Jordan"]:
    hits = df[df.astype(str).apply(lambda r: r.str.contains(name, case=False, regex=False).any(), axis=1)]
    if not hits.empty:
        print(hits.to_string(index=False))
