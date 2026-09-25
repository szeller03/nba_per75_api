
from __future__ import annotations

import json
import math
import re
import os
import sys
import threading
import subprocess
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote
from urllib.request import Request, urlopen

import pandas as pd
import numpy as np

# Production data lives outside the website source tree. Use the established
# NBA_Per75 directory first, with a nearby-folder fallback for copied projects.
_ESTABLISHED_ROOT = Path(os.environ.get("NBA_PER75_ROOT", r"C:\Users\szell\OneDrive\Desktop\NBA_Per75"))
_HERE = Path(__file__).resolve()
_ROOT_CANDIDATES = [
    _ESTABLISHED_ROOT,
    _HERE.parents[2] / "NBA_Per75",
    _HERE.parents[3] / "NBA_Per75",
]
ROOT = next(
    (p for p in _ROOT_CANDIDATES if (p / "data").exists()),
    _ESTABLISHED_ROOT,
)
# Website-local root. Team enrichment files live with the website build,
# while player/stat master data lives in the established NBA_Per75 root.
SITE_ROOT = _HERE.parents[1]
HOST = "127.0.0.1"
PORT = 8000

def _first_existing_file(candidates):
    for p in candidates:
        p=Path(p)
        if p.exists() and p.is_file():
            return p
    return Path(candidates[0]) if candidates else Path(".")

def _first_existing_dir(candidates):
    for p in candidates:
        p=Path(p)
        if p.exists() and p.is_dir():
            return p
    return Path(candidates[0]) if candidates else Path(".")

def _recursive_file(name_candidates):
    # Only used for known project filenames; this makes copied website builds
    # tolerant of the user's finalized data-folder organization.
    wanted={str(x).lower() for x in name_candidates}
    try:
        for p in ROOT.rglob("*.csv"):
            if p.name.lower() in wanted:
                return p
    except Exception:
        pass
    return None

def _recursive_dir(name_candidates):
    wanted={str(x).lower() for x in name_candidates}
    try:
        for p in ROOT.rglob("*"):
            if p.is_dir() and p.name.lower() in wanted:
                return p
    except Exception:
        pass
    return None

_master_file = _recursive_file([
    "nba_per75_master_v46.csv",
    "nba_per75_master_dreb_v2.csv",
    "nba_per75_master.csv",
])
_identity_dir = _recursive_dir(["player_website_identity_v1"])
_taxonomy_dir = _recursive_dir(["player_statistic_taxonomy_v1"])
_qualification_dir = _recursive_dir(["qualification_population_v1"])
_percentile_dir = _recursive_dir(["historical_percentiles_v2_1"])
_percentile_lookup_file = _recursive_file(["player_percentile_lookup_v1.csv"])
_headshot_dir = _recursive_dir(["player_headshots_final_v1"])
_aggregation_dir = _recursive_dir(["player_subcategory_aggregation_v1"])

PATHS = {
    "identity": _identity_dir or (ROOT / "player_website_identity_v1"),
    "profiles": ROOT / "player_profiles_v1",
    "master": _master_file or (ROOT / "data" / "nba_per75_master_v46.csv"),
    "qualification": _qualification_dir or (ROOT / "player_analytics_v1_2_dreb" / "qualification_population_v1"),
    "percentiles": _percentile_dir or (ROOT / "player_analytics_v1_2_dreb" / "historical_percentiles_v2_1"),
    "percentile_lookup": _percentile_lookup_file or (ROOT / "player_profiles_v1" / "player_percentile_lookup_v1.csv"),
    "headshots": _headshot_dir or (ROOT / "player_headshots_final_v1"),
    "taxonomy": _taxonomy_dir or (ROOT / "player_statistic_taxonomy_v1"),
    "aggregation_spec": _aggregation_dir or (ROOT / "player_subcategory_aggregation_v1"),
    "visualization": ROOT / "player_visualization_data_v1",
    "statistic_registry": _first_existing_file([
        ROOT / "data" / "statistic_registry_v3.csv",
        ROOT / "data" / "statistic_registry_v2.csv",
        ROOT / "data" / "statistic_registry.csv",
    ]),
    "dominance": ROOT / "player_statistical_dominance_v1",
    "playoff_46": ROOT / "data" / "nba_per75_playoff_46_stats_v1",
    "playoff_percentiles": ROOT / "data" / "nba_per75_playoff_46_stats_v1" / "percentiles_v1",
}
# Backward-compatible aliases: several older endpoints referenced these keys.
PATHS["stat_registry"]=PATHS["statistic_registry"]


CACHE = {}
TEAM_INDEX_CACHE = Path(__file__).resolve().parent / "cache" / "team_index_v2.json"
TEAM_ANALYTICS_CACHE = Path(__file__).resolve().parent / "cache" / "team_analytics_v3.json"
TEAM_BUILD_STATE = {"status":"idle","started_at":None,"finished_at":None,"error":None}
TEAM_BUILD_LOCK = threading.Lock()

def clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v.item() if hasattr(v, "item") else v

def find_csv(folder, terms):
    """Find a CSV by filename terms, recursively.

    Several finalized NBA_Per75 data builders intentionally place season,
    career, and percentile outputs in nested subdirectories. A non-recursive
    glob made the playoff Big Board silently see an empty source even though
    diagnostics reported the parent directory existed.
    """
    folder=Path(folder)
    if not folder.exists():
        return None
    files=list(folder.rglob("*.csv"))
    if not files:
        return None
    scored=[]
    for f in files:
        n=f.name.lower()
        score=sum(3 for t in terms if t.lower() in n)
        # Prefer an exact filename/stronger match and shallower path.
        depth=len(f.relative_to(folder).parts)
        scored.append((score,-depth,f))
    scored.sort(key=lambda x:(-x[0],-x[1],x[2].name.lower()))
    return scored[0][2]


# ---------------------------------------------------------------------------
# Global percentage-unit normalization (Website182)
# ---------------------------------------------------------------------------
# Canonical rule: every percentage statistic exposed by the API is stored as
# a 0-100 percentage value. Some source files encode percentages as fractions
# (0-1), while others already use 0-100. Normalize at ingestion so calculations,
# percentiles, comparisons, profiles, teams, and cached JSON all use one unit.
_PERCENT_FIELD_HINTS = {
    "fg_pct","2p_pct","3p_pct","ft_pct","ts_pct","efg_pct","tov_pct",
    "orb_pct","drb_pct","dreb_pct","oreb_pct","trb_pct","ast_pct",
    "stl_pct","blk_pct","usg_pct","ftr","3par","w_l_pct","win_pct",
    "opp_tov_pct","opp_efg_pct","opponent_tov_pct","opponent_efg_pct",
    "def_tov_pct","def_efg_pct","defensive_tov_pct","defensive_efg_pct",
}

_RELATIVE_PERCENT_POINT_FIELDS = {"rts", "relative_ts", "relative_ts_pct", "relativets", "relativetspct"}

def _relative_percent_point_field(name):
    raw=str(name).strip().lower()
    n=re.sub(r"[^a-z0-9]", "", raw)
    return n in _RELATIVE_PERCENT_POINT_FIELDS

def _percent_field_name(name):
    raw=str(name).strip().lower()
    n=re.sub(r"[^a-z0-9]", "_", raw).strip("_")
    if n in _PERCENT_FIELD_HINTS:
        return True
    # A literal percent sign is the strongest source-schema signal.
    # Exclude relative/percentile metrics because those are not ordinary
    # percentages even when their labels contain a percent sign.
    if "%" in raw and "percentile" not in raw and not raw.startswith(("rts", "relative_ts")):
        return True
    if "percentile" in n or n.startswith("rts") or n.startswith("relative_ts"):
        return False
    compact=n.replace("_", "")
    return compact in {x.replace("_", "") for x in _PERCENT_FIELD_HINTS}

def normalize_percentage_dataframe(df):
    """Normalize only known percentage / relative-percent-point columns.

    IMPORTANT: never coerce arbitrary columns to numeric here. The previous
    implementation converted names, seasons, player IDs, statistic labels,
    and team names to NaN because it ran to_numeric() on every column. That
    broke the Big Board (zero rows), statistic selectors, and Team lookups.
    """
    if df is None or getattr(df, "empty", False):
        return df
    for c in list(df.columns):
        if not (_relative_percent_point_field(c) or _percent_field_name(c)):
            continue
        vals=pd.to_numeric(df[c], errors="coerce")
        # Normalize per value rather than per column. Sources can contain
        # mixed-unit rows (e.g. rTS 0.11 beside rTS 11.0).
        # rTS is a percentage-point differential. Fractional source values
        # are normally well below 0.5 (e.g. 0.11 -> +11.0), while a value
        # such as 1.4964 is already a canonical +1.4964 and must not become
        # +149.64. Ordinary percentage fields retain the broader 0-1 rule.
        if _relative_percent_point_field(c):
            mask=vals.notna() & (vals.abs() <= 0.5)
        else:
            mask=vals.notna() & (vals.abs() <= 1.5)
        df[c]=vals.where(~mask, vals*100.0)
    return df

_PANDAS_READ_CSV = pd.read_csv

def read_csv(*args, **kwargs):
    """Project-wide CSV reader with percentage-unit normalization."""
    # Keep the original pandas reader under a distinct name; calling this
    # wrapper recursively was the cause of Website182 startup RecursionErrors.
    return normalize_percentage_dataframe(_PANDAS_READ_CSV(*args, **kwargs))

def load(key, terms):
    if key in CACHE:
        return CACHE[key]
    f = find_csv(PATHS[key], terms)
    if not f:
        raise FileNotFoundError(f"No CSV found for {key}: {PATHS[key]}")
    df = read_csv(f, low_memory=False)
    CACHE[key] = df
    return df

def col(df, candidates):
    norm = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in df.columns}
    for c in candidates:
        k = re.sub(r"[^a-z0-9]", "", c.lower())
        if k in norm:
            return norm[k]
    return None

def identity_cols(df):
    return {
        "id": col(df, ["Player_ID", "PlayerId", "PlayerID", "player_id"]),
        "name": col(df, ["Player_Name", "Player", "Name", "player_name"]),
        "season": col(df, ["Season", "season"]),
    }

def filter_player(df, requested):
    c = identity_cols(df)
    if c["id"]:
        m = df[c["id"]].astype(str).eq(str(requested))
        if m.any():
            return df.loc[m].copy()
    if c["name"]:
        m = df[c["name"]].astype(str).str.strip().str.casefold().eq(str(requested).strip().casefold())
        if m.any():
            return df.loc[m].copy()
    return df.iloc[0:0].copy()


def _headshot_url_for(player_id=None, player_name=None):
    """Return the canonical website headshot URL for a player."""
    key="__explorer_headshot_lookup_v1__"
    if key not in CACHE:
        try:
            hs=load("headshots",["headshot_registry","headshot"])
            hc=col(hs,["Verified_Headshot_URL","Headshot_URL","HeadshotUrl","NBA_Headshot_URL","CDN_URL","Image_URL"])
            hi=identity_cols(hs)
            lookup={}
            if hc:
                if hi.get("id"):
                    for _,r in hs.iterrows():
                        value=clean(r[hc])
                        if value:
                            lookup[("id",str(r[hi["id"]]).strip())]=value
                if hi.get("name"):
                    for _,r in hs.iterrows():
                        value=clean(r[hc])
                        if value:
                            lookup[("name",str(r[hi["name"]]).strip().casefold().replace("*",""))]=value
            CACHE[key]=lookup
        except Exception:
            CACHE[key]={}
    lookup=CACHE[key]
    if player_id is not None:
        value=lookup.get(("id",str(player_id).strip()))
        if value:return value
    if player_name is not None:
        return lookup.get(("name",str(player_name).strip().casefold().replace("*","")))
    return None


def _canonical_identity_registry():
    """Build one canonical website identity per public player name.

    Some historical source layers contain a regular-season identity and a
    separate playoff identity for the same person (e.g. ``Michael Jordan``
    and ``Michael Jordan*``).  The website must treat these as one player.
    Prefer the identity with a qualified profile, then the one with the most
    qualified seasons, then the cleanest non-asterisk name.
    """
    key="__canonical_identity_registry_v2__"
    if key in CACHE:
        return CACHE[key]
    df=load_exact_csv("identity", "website_player_identity_v1.csv")
    if df.empty:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]
    c=identity_cols(df)
    if not c.get("name"):
        CACHE[key]=df.copy()
        return CACHE[key]
    work=df.copy()
    work["__public_name"]=work[c["name"]].astype(str).str.replace(r"\*+", "", regex=True).str.strip()
    work["__public_key"]=(
        work["__public_name"].astype(str)
        .str.replace(r"[^a-z0-9]+"," ",regex=True)
        .str.replace(r"\s+"," ",regex=True)
        .str.strip()
        .str.casefold()
    )
    if c.get("qualified_profile"):
        work["__qualified_flag"]=work[c["qualified_profile"]].astype(str).str.casefold().isin({"true","1","yes","qualified"}).astype(int)
    else:
        work["__qualified_flag"]=0
    if c.get("qualified_seasons"):
        work["__qualified_seasons_num"]=pd.to_numeric(work[c["qualified_seasons"]],errors="coerce").fillna(0)
    else:
        work["__qualified_seasons_num"]=0
    work["__clean_name"]=~work[c["name"]].astype(str).str.contains(r"\*",regex=True,na=False)
    # Only collapse duplicate rows when they represent the same canonical
    # player ID. Never collapse two distinct IDs merely because their names
    # are identical (e.g. George King, born 1928 vs George King, born 1994).
    if c.get("id"):
        work["__identity_key"]=work[c["id"]].astype(str).str.strip()
    else:
        work["__identity_key"]=work["__public_key"]
    work=work.sort_values(["__public_key","__qualified_flag","__qualified_seasons_num","__clean_name"],
                          ascending=[True,False,False,False],kind="stable")
    work=work.drop_duplicates("__identity_key",keep="first").copy()

    # Some source layers created separate Player_IDs for the same historical
    # person (regular/playoff/source ingestion variants). Collapse same-name
    # IDs only when their season histories materially overlap. This deliberately
    # does NOT collapse distinct namesakes with disjoint careers.
    if c.get("id") and c.get("name"):
        try:
            ms=load_master_seasons()
            mpid=col(ms,["Player_ID","PlayerId","PlayerID","player_id"])
            mname=col(ms,["Player","Player_Name","Display_Name","player_name","Name"])
            mseason=col(ms,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
            if mpid and mname and mseason and not ms.empty:
                mh=ms[[mpid,mname,mseason]].copy()
                mh["__pk"]=(mh[mname].astype(str).str.replace(r"\*+","",regex=True)
                            .str.replace(r"[^a-z0-9]+"," ",regex=True)
                            .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
                mh["__sid"]=mh[mpid].astype(str).str.strip()
                mh["__sy"]=mh[mseason].map(_season_label_any)
                mh=mh.dropna(subset=["__sy"])
                season_sets=mh.groupby("__sid")["__sy"].agg(lambda x:set(x)).to_dict()
                master_ids=set(season_sets)
                alias={}
                for pk,g in work.groupby("__public_key",sort=False):
                    ids=[str(x).strip() for x in g["__identity_key"].tolist()]
                    active=[x for x in ids if x in master_ids]
                    if len(active)==1:
                        # All other same-name IDs are stale/source aliases for
                        # the only identity that actually has player-season
                        # records in the authoritative master table.
                        for stale in ids:
                            if stale != active[0]:
                                alias[stale]=active[0]
                        continue
                    ids=[str(x).strip() for x in g["__identity_key"].tolist()]
                    for ii in range(len(ids)):
                        for jj in range(ii+1,len(ids)):
                            a_id,b_id=ids[ii],ids[jj]
                            overlap=len(season_sets.get(a_id,set()) & season_sets.get(b_id,set()))
                            if overlap>=3:
                                # Work is sorted by qualification/season count,
                                # so the earlier row is the preferred canonical ID.
                                alias[b_id]=a_id
                if alias:
                    work["__identity_key"]=work["__identity_key"].astype(str).str.strip().map(
                        lambda x: alias.get(x,x)
                    )
                    work=work.sort_values(["__public_key","__qualified_flag","__qualified_seasons_num","__clean_name"],
                                          ascending=[True,False,False,False],kind="stable")
                    work=work.drop_duplicates("__identity_key",keep="first").copy()
        except Exception:
            pass

    name_counts=work["__public_key"].value_counts()
    work["__ambiguous_name"]=work["__public_key"].map(name_counts).gt(1)
    # Keep the clean display name, but make the lookup key ID-specific when a
    # name belongs to more than one distinct player.
    work["__lookup_key"]=np.where(
        work["__ambiguous_name"],
        work["__public_key"]+"|"+work["__identity_key"],
        work["__public_key"]
    )
    work[c["name"]]=work["__public_name"]
    work["Display_Name"]=work["__public_name"]
    CACHE[key]=work
    return work

def _canonical_player_id_for_name(name):
    reg=_canonical_identity_registry()
    if reg.empty or name is None:
        return None
    c=identity_cols(reg)
    if not c.get("id") or not c.get("name"):
        return None
    key=str(name).replace("*","").strip().casefold()
    m=reg.loc[reg["__public_key"].eq(key)].copy()
    if m.empty:
        return None
    if len(m)>1:
        try:
            master=load_master_seasons()
            pidc=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
            namec=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
            seac=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
            if pidc and namec and seac:
                wanted=key
                mm=master.loc[master[namec].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
                if not mm.empty:
                    mm["__pid"]=mm[pidc].astype(str).str.strip()
                    mm["__year"]=mm[seac].map(_season_end_year)
                    counts=mm.dropna(subset=["__year"]).groupby("__pid")["__year"].nunique()
                    best_pid=counts.idxmax()
                    hit=m.loc[m[c["id"]].astype(str).str.strip().eq(str(best_pid))]
                    if not hit.empty:
                        return clean(hit.iloc[0][c["id"]])
        except Exception:
            pass
    return clean(m.iloc[0][c["id"]])

def api_players(q):
    df=_canonical_identity_registry()
    c=identity_cols(df)
    if not c["name"]:
        raise ValueError("Identity source has no player-name column.")
    work=df.copy()
    if q:
        work=work.loc[work[c["name"]].astype(str).str.contains(q,case=False,na=False)].copy()

    # Final public-player boundary: collapse IDs that the authoritative master
    # identifies as the same historical person. This is intentionally done
    # AFTER all registry work so stale source duplicates cannot leak into search.
    cmap=_canonical_master_identity_map()
    if c.get("id") and cmap:
        work["__canon_id"]=work[c["id"]].astype(str).str.strip().map(lambda x:cmap.get(x,x))
        work=work.drop_duplicates("__canon_id",keep="first")
    else:
        work["__canon_id"]=work[c["id"]].astype(str).str.strip() if c.get("id") else work.index.astype(str)
        # Last-resort public-name dedupe only when no authoritative ID map exists.
        work["__name_key"]=(work[c["name"]].astype(str)
                            .str.replace(r"[^a-z0-9]+"," ",regex=True)
                            .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
        work=work.drop_duplicates("__name_key",keep="first")

    work=work.head(50)
    hc=col(work,["Headshot_URL","HeadshotUrl","Verified_Headshot_URL","CDN_URL","Image_URL"])
    out=[]
    for _,r in work.iterrows():
        pid=clean(r[c["id"]]) if c["id"] else None
        canon_pid=cmap.get(str(pid).strip(),pid) if pid else pid
        pname=clean(r[c["name"]])
        hurl=clean(r[hc]) if hc else None
        if not hurl:
            hurl=_headshot_url_for(canon_pid,pname)
        out.append({"player_id":canon_pid,"player_name":pname,"headshot_url":hurl})
    return out


def load_master_seasons():
    """Authoritative player-season universe: not restricted by percentile qualification."""
    f=PATHS["master"]
    if not f.exists():
        return pd.DataFrame()
    key="__master_seasons__"
    if key not in CACHE:
        CACHE[key]=read_csv(f,low_memory=False)
    return CACHE[key]

def load_qualification_population():
    folder=PATHS["qualification"]
    f=find_csv(folder,["regular_qualification_population","qualification_population"])
    if not f:
        return pd.DataFrame()
    key="__qualification_population__"
    if key not in CACHE:
        CACHE[key]=read_csv(f,low_memory=False)
    return CACHE[key]

def career_aggregation_registry():
    """Configurable career aggregation contract.

    This is deliberately a registry rather than a hidden one-size-fits-all rule.
    Until statistic-specific methodology is finalized, rate/value statistics
    default to arithmetic mean and counting/cumulative statistics default to sum.
    The website can consume the registry without changing the source data.
    """
    return {
        "default_rate": "mean",
        "default_cumulative": "sum",
        "default_percentage": "weighted_mean_if_denominator_available_else_mean",
        "default_context": "career",
        "qualification_required": True,
        "qualification_policy": "career_population_gate",
    }

def aggregate_career_series(df, stat_col, value_col):
    """Provisional configurable aggregation for the career framework."""
    work=df.copy()
    work["_v"]=pd.to_numeric(work[value_col],errors="coerce")
    work=work.dropna(subset=["_v"])
    stat=str(work[stat_col].iloc[0]) if not work.empty else ""
    s=stat.casefold()

    cumulative_tokens=("games","minutes","points","rebounds","assists","steals","blocks",
                       "turnovers","fouls","win shares","vorp","ows","dws")
    is_cumulative=any(t in s for t in cumulative_tokens) and not any(
        t in s for t in ("per 75","/75","percent","%","rate","ratio","true shooting","ts%")
    )
    return float(work["_v"].sum()) if is_cumulative else float(work["_v"].mean())

def build_career_percentiles(per, player_id=None, player_name=None):
    """Career percentiles with an explicit qualification gate.

    Raw career values are available for the full player universe. Career
    percentiles are only assigned to players who have at least one qualifying
    player-season in the existing qualification population. This keeps
    availability separate from percentile eligibility without inventing a new
    minimum-qualifier threshold.
    """
    df=per.copy()
    pc=identity_cols(df)
    stat_col=choose_col(df,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    value_col=choose_col(df,[
        "Value","value","Statistic_Value","statistic_value",
        "Stat_Value","Raw_Value","Value_Per75","Value_per75"
    ])
    season_col=choose_col(df,["Season","season"])
    if not stat_col or not value_col or not pc["player"]:
        return []

    df["_player_key"]=df[pc["player"]].astype(str).str.strip()
    df["_stat_key"]=df[stat_col].astype(str).str.strip()
    df["_value_num"]=pd.to_numeric(df[value_col],errors="coerce")
    df=df.dropna(subset=["_value_num"])

    # Existing regular qualification population supplies the eligibility gate.
    qual=load_qualification_population()
    qualified_players=set()
    if not qual.empty:
        qc=identity_cols(qual)
        if qc["id"]:
            qualified_players.update(qual[qc["id"]].dropna().astype(str).str.strip())
        if qc["name"]:
            qualified_players.update(qual[qc["name"]].dropna().astype(str).str.strip().casefold())

    target_key=str(player_id).strip() if player_id is not None else None
    target_name=str(player_name).strip().casefold() if player_name is not None else None

    # Career aggregation is performed by statistic, never by percentile.
    career_rows=[]
    for stat, g in df.groupby("_stat_key"):
        for player, pg in g.groupby("_player_key"):
            career_rows.append({
                "_player_key":player,
                "_stat_key":stat,
                "_career_value":aggregate_career_series(pg,"_stat_key","_value_num"),
            })
    career=pd.DataFrame(career_rows)
    if career.empty:
        return []

    # Qualification gate. Prefer exact player-ID membership; otherwise use names.
    if qualified_players:
        allowed=career["_player_key"].astype(str).isin(qualified_players)
        if not allowed.any():
            allowed=career["_player_key"].astype(str).str.casefold().isin(qualified_players)
        qualified_career=career.loc[allowed].copy()
    else:
        # Do not silently invent qualification if the source is unavailable.
        qualified_career=career.iloc[0:0].copy()

    qualified_career["Career_Percentile"]=qualified_career.groupby("_stat_key")["_career_value"].rank(
        method="average",pct=True
    )*100.0

    if target_key is not None:
        target=qualified_career.loc[qualified_career["_player_key"].eq(target_key)]
    else:
        target=qualified_career.iloc[0:0]
    if target.empty and target_name:
        target=qualified_career.loc[
            qualified_career["_player_key"].astype(str).str.casefold().eq(target_name)
        ]

    # Raw career values are still returned for the player even if unqualified.
    raw_target=career.iloc[0:0]
    if target_key is not None:
        raw_target=career.loc[career["_player_key"].eq(target_key)]
    if raw_target.empty and target_name:
        raw_target=career.loc[
            career["_player_key"].astype(str).str.casefold().eq(target_name)
        ]

    pct_map={
        str(r["_stat_key"]):clean(r["Career_Percentile"])
        for _,r in target.iterrows()
    }
    rows=[]
    for _,r in raw_target.iterrows():
        stat=str(r["_stat_key"])
        rows.append({
            "Statistic":stat,
            "Career_Value":clean(r["_career_value"]),
            "Career_Percentile":pct_map.get(stat),
            "Career_Percentile_Qualified":stat in pct_map,
        })
    return rows



def _regular_career_profile_rows(player_id=None, player_name=None):
    """Return one row per registered regular-season career statistic.

    Career spiders use the canonical regular-season career table and the
    established 400 G / 10,000 MP career gate. Identity matching falls back to
    the cleaned public name so legacy/source IDs cannot make the spider vanish.
    """
    career=_build_regular_career_table()
    if career.empty:
        return []

    target=pd.DataFrame()
    if player_id is not None and "Player_ID" in career.columns:
        target=career.loc[career["Player_ID"].astype(str).str.strip().eq(str(player_id).strip())].copy()
    if target.empty and player_name and "Player" in career.columns:
        key=str(player_name).replace("*","").strip().casefold()
        names=career["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        target=career.loc[names.eq(key)].copy()
    if target.empty:
        return []

    qualified=career.loc[career["Qualified_Career"].astype(bool)].copy() if "Qualified_Career" in career.columns else pd.DataFrame()
    target_row=target.iloc[0]
    target_id=str(target_row.get("Player_ID", player_id)).strip()

    # Regular-season career percentiles are built from the qualified career
    # population, never from individual season percentile rows.
    pct_map={}
    if not qualified.empty:
        for stat in REGULAR_STATS:
            if stat not in qualified.columns:
                continue
            vals=pd.to_numeric(qualified[stat],errors="coerce")
            valid=vals.notna()
            if not valid.any():
                continue
            higher=stat not in {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
            pct=_playoff_percentile(vals,higher=higher)
            for idx in qualified.index[valid]:
                pidkey=str(qualified.loc[idx,"Player_ID"]).strip()
                pct_map[(pidkey,stat)]=clean(pct.loc[idx])

    rows=[]
    for stat in REGULAR_STATS:
        if stat not in target.columns:
            continue
        rows.append({
            "Statistic":stat,
            "Career_Value":clean(target_row[stat]),
            "Career_Percentile":pct_map.get((target_id,stat)),
            "Career_Percentile_Qualified":(target_id,stat) in pct_map,
        })
    return rows


def find_playoff_source():
    """Find the canonical Basketball-Reference playoff source first.
    The final website uses B-Ref for every playoff season from 1952 through
    the current season; NBA Stats is intentionally not part of the final
    playoff source hierarchy.
    """
    canonical=ROOT / "data" / "nba_per75_playoffs_player_season_v1.csv"
    if canonical.exists():
        return canonical
    bref=ROOT / "data" / "nba_per75_playoffs_bref_v1.csv"
    if bref.exists():
        return bref

    # First, allow the master dataset itself to contain season-type rows.
    master_path=PATHS.get("master")
    if master_path and master_path.exists():
        try:
            cols=read_csv(master_path,nrows=0).columns.tolist()
            ctype=col(pd.DataFrame(columns=cols),["Season_Type","SeasonType","Season_Type_ID","Phase"])
            if ctype:
                key="__master_playoff__"
                if key not in CACHE:
                    m=read_csv(master_path,low_memory=False)
                    CACHE[key]=m.loc[m[ctype].astype(str).str.casefold().isin(
                        {"playoffs","playoff","postseason"}
                    )].copy()
                if not CACHE[key].empty:
                    return master_path
        except Exception:
            pass

    candidates=[]
    for f in ROOT.rglob("*.csv"):
        name=f.name.casefold()
        if "playoff" not in name and "postseason" not in name:
            continue
        try:
            cols=read_csv(f,nrows=0).columns.tolist()
        except Exception:
            continue
        norm={re.sub(r"[^a-z0-9]","",str(c).casefold()):c for c in cols}
        has_player=any(k in norm for k in ("player","playername","displayname","playerid"))
        has_season=any(k in norm for k in ("season","seasonid"))
        if has_player and has_season:
            candidates.append(f)
    candidates.sort(key=lambda p:(len(str(p)),str(p).casefold()))
    return candidates[0] if candidates else None

def load_playoff_source():
    discovery_key="__playoff_source_file__"
    if discovery_key in CACHE:
        f=CACHE[discovery_key]
    else:
        f=find_playoff_source()
        CACHE[discovery_key]=f
    if not f:
        return pd.DataFrame(), None
    if f == PATHS.get("master") and "__master_playoff__" in CACHE:
        return CACHE["__master_playoff__"], f
    key=f"__playoff_source__:{f}"
    if key not in CACHE:
        CACHE[key]=read_csv(f,low_memory=False)
    return CACHE[key], f

def build_playoff_rows(source, player_id=None, player_name=None, season=None):
    if source is None or source.empty:
        return []
    c_id=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    c_name=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    c_season=col(source,["Season","season","Season_ID"])
    if not c_id and not c_name:
        return []
    if player_id is not None and c_id:
        work=source.loc[source[c_id].astype(str).str.strip().eq(str(player_id).strip())].copy()
        if work.empty and player_name and c_name:
            key=str(player_name).replace("*","").strip().casefold()
            names=source[c_name].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
            work=source.loc[names.eq(key)].copy()
    elif player_name and c_name:
        key=str(player_name).replace("*","").strip().casefold()
        names=source[c_name].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        work=source.loc[names.eq(key)].copy()
    else:
        work=source.iloc[0:0].copy()
    if season and c_season:
        work=work.loc[work[c_season].astype(str).str.strip().eq(str(season).strip())]
    return [{k:clean(v) for k,v in r.items()} for r in work.to_dict("records")]



REGULAR_STATS = [
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75","2PA_per75",
    "FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75","AST_per75","STL_per75",
    "BLK_per75","TOV_per75","PF_per75","FG_pct","2P_pct","3P_pct","FT_pct","TS_pct",
    "FTr","3PAr","rTS","ORtg","DRtg","NRtg","Relative_ORtg","Relative_DRtg",
    "Relative_NRtg","PER","BPM","OBPM","DBPM","VORP","WS","OWS","DWS",
    "OREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct","AST_TOV","DREB_pct"
]

def normalize_requested_season(value):
    """Normalize season selectors to the canonical YYYY-YY label."""
    if value is None: return None
    s=str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}",s): return s
    if re.fullmatch(r"\d{4}",s):
        y=int(s); return f"{y-1}-{s[-2:]}"
    return s

PLAYOFF_STATS = [
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75","2PA_per75",
    "FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75","AST_per75","STL_per75",
    "BLK_per75","TOV_per75","PF_per75","FG_pct","2P_pct","3P_pct","FT_pct","TS_pct",
    "FTr","3PAr","rTS","ORtg","DRtg","NRtg","Relative_ORtg","Relative_DRtg",
    "Relative_NRtg","PER","BPM","OBPM","DBPM","VORP","WS","OWS","DWS",
    "OREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct","AST_TOV","DREB_pct"
]
PLAYOFF_PER75_STATS = {
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75","2PA_per75",
    "FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75","AST_per75","STL_per75",
    "BLK_per75","TOV_per75","PF_per75"
}
PLAYOFF_ADDITIVE_STATS = {"WS","OWS","DWS","VORP"}
PLAYOFF_LOWER_IS_BETTER = {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
PLAYOFF_STAT_ALIASES = {
    "WS_per48":["WS_per48","WS/48"],
    "USG_pct":["USG_pct","USG%"],
    "TRB_pct":["TRB_pct","TRB%"],
    "OREB_pct":["OREB_pct","ORB%"],
    "DREB_pct":["DREB_pct","DRB%"],
    "AST_pct":["AST_pct","AST%"],
    "STL_pct":["STL_pct","STL%"],
    "BLK_pct":["BLK_pct","BLK%"],
    "TOV_pct":["TOV_pct","TOV%"],
    "AST_TOV":["AST_TOV","AST/TOV"],
    "NRtg":["NRtg"],
    "Relative_NRtg":["Relative_NRtg"],
}

def _playoff_source_column(df, stat):
    return col(df, PLAYOFF_STAT_ALIASES.get(stat, [stat]))

def _season_label_any(v):
    s=str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}",s):
        return s
    try:
        y=int(float(s))
        return f"{y-1}-{str(y)[-2:]}"
    except Exception:
        return s

def _season_end_year(v):
    s=str(v).strip()
    m=re.match(r"^(\d{4})-(\d{2})$",s)
    if m:
        return int(m.group(1))+1
    try: return int(float(s))
    except Exception: return None

ERA_DEFINITIONS = [
    ("1951-52_to_1969-70", 1952, 1970, "1951-52 → 1969-70"),
    ("1970-71_to_1979-80", 1971, 1980, "1970-71 → 1979-80"),
    ("1980-81_to_1989-90", 1981, 1990, "1980-81 → 1989-90"),
    ("1990-91_to_1999-00", 1991, 2000, "1990-91 → 1999-00"),
    ("2000-01_to_2009-10", 2001, 2010, "2000-01 → 2009-10"),
    ("2010-11_to_2019-20", 2011, 2020, "2010-11 → 2019-20"),
    ("2020-21_to_2025-26", 2021, 2026, "2020-21 → 2025-26"),
]

def _era_key(year):
    y=_season_end_year(year)
    if y is None: return None
    for key,a,b,_label in ERA_DEFINITIONS:
        if a <= y <= b: return key
    return None

def _era_label(year):
    key=_era_key(year)
    for k,_a,_b,label in ERA_DEFINITIONS:
        if k == key: return label
    return "Unresolved"

def _era_options():
    return [{"value":k,"label":label} for k,_a,_b,label in ERA_DEFINITIONS]

def _playoff_era(year):
    try: y=int(year)
    except Exception: return "UNRESOLVED"
    bands=[
        ("1951-52_to_1969-70",1952,1970),("1970-71_to_1979-80",1971,1980),
        ("1980-81_to_1989-90",1981,1990),("1990-91_to_1999-00",1991,2000),
        ("2000-01_to_2009-10",2001,2010),("2010-11_to_2019-20",2011,2020),
        ("2020-21_to_2025-26",2021,2026),
    ]
    for label,a,b in bands:
        if a<=y<=b: return label
    return "UNRESOLVED"

def _playoff_percentile(series, higher=True):
    x=pd.to_numeric(series,errors="coerce")
    out=pd.Series(np.nan,index=series.index,dtype=float)
    valid=x.notna(); n=int(valid.sum())
    if n==0: return out
    if n==1:
        out.loc[valid]=100.0
        return out
    ranks=x.loc[valid].rank(method="average",ascending=not higher)
    out.loc[valid]=100.0*(n-ranks)/(n-1)
    return out

def load_authoritative_playoff_master():
    key="__authoritative_playoff_master__"
    if key in CACHE:
        return CACHE[key]
    candidates=[
        ROOT/"data"/"nba_per75_master_v46.csv",
        ROOT/"data"/"nba_per75_master_dreb_v2.csv",
        ROOT/"data"/"nba_per75_master.csv",
    ]
    source=None
    for path in candidates:
        if not path.exists(): continue
        try:
            probe=read_csv(path,nrows=5,low_memory=False)
            st=col(probe,["Season_Type","SeasonType","Season_Type_ID","Phase"])
            if st:
                # The file is a combined regular-season/playoff master; do not
                # inspect only the first five rows because they may all be
                # regular-season rows.
                source=path
                break
        except Exception:
            continue
    if source is None:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]

    raw=read_csv(source,low_memory=False)
    season_type=col(raw,["Season_Type","SeasonType","Season_Type_ID","Phase"])
    if season_type:
        raw=raw.loc[raw[season_type].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()
    if raw.empty:
        CACHE[key]=raw
        return raw

    pid_col=col(raw,["Player_ID","PlayerId","PlayerID","player_id"])
    pname_col=col(raw,["Player","Player_Name","Display_Name","player_name","Name"])
    if not pname_col:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]

    if not pid_col:
        try:
            ident=load_exact_csv("identity","website_player_identity_v1.csv")
            ic=identity_cols(ident)
            if ic["id"] and ic["name"]:
                mp=ident[[ic["name"],ic["id"]]].drop_duplicates()
                mp.columns=["__player_name_key","__player_id"]
                raw["__player_name_key"]=raw[pname_col].astype(str).str.strip().str.casefold()
                mp["__player_name_key"]=mp["__player_name_key"].astype(str).str.strip().str.casefold()
                raw=raw.merge(mp,on="__player_name_key",how="left",validate="many_to_one")
                raw["__player_id_final"]=raw["__player_id"]
            else:
                raw["__player_id_final"]=raw[pname_col].astype(str).str.strip()
        except Exception:
            raw["__player_id_final"]=raw[pname_col].astype(str).str.strip()
    else:
        raw["__player_id_final"]=raw[pid_col]

    season_col=col(raw,["Season","season","Season_ID"])
    mp_col=col(raw,["MP","Minutes","minutes"])
    team_col=col(raw,["Team","Tm","team"])
    if not season_col:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]

    raw["__season_label"]=raw[season_col].map(_season_label_any)
    raw["__mp_num"]=pd.to_numeric(raw[mp_col],errors="coerce") if mp_col else np.nan
    gcol=col(raw,["G","Games","games"])

    groups=[]
    keys=["__player_id_final",pname_col,"__season_label"]
    for (pid,name,season),g in raw.groupby(keys,dropna=False,sort=False):
        row={"Player_ID":clean(pid),"Player":clean(name),"Season":season,"Season_Type":"Playoffs"}
        row["G"]=pd.to_numeric(g[gcol],errors="coerce").sum(min_count=1) if gcol else np.nan
        row["MP"]=g["__mp_num"].sum(min_count=1)
        for stat in PLAYOFF_STATS:
            sc=_playoff_source_column(g,stat)
            vals=pd.to_numeric(g[sc],errors="coerce") if sc else pd.Series(np.nan,index=g.index)
            if stat in PLAYOFF_PER75_STATS:
                x=pd.DataFrame({"v":vals,"mp":g["__mp_num"]}).dropna()
                x=x[x["mp"]>0]
                row[stat]=float((x["v"]*x["mp"]).sum()/x["mp"].sum()) if not x.empty else np.nan
            elif stat in PLAYOFF_ADDITIVE_STATS:
                row[stat]=float(vals.sum(min_count=1)) if vals.notna().any() else np.nan
            else:
                chosen=vals
                if team_col and team_col in g.columns:
                    tv=vals[g[team_col].astype(str).str.upper().eq("TOT")]
                    chosen=tv if tv.notna().any() else vals
                chosen=chosen.dropna()
                row[stat]=float(chosen.iloc[0]) if not chosen.empty else np.nan
        groups.append(row)
    canonical=pd.DataFrame(groups)
    CACHE[key]=canonical
    CACHE["__authoritative_playoff_source_path__"]=source
    return canonical

def _load_final_playoff_46_file(career=False):
    """Load the finalized 46-stat playoff layer, not a reconstructed master."""
    folder=PATHS["playoff_46"]
    if not folder.exists():
        return pd.DataFrame()
    terms = (
        ["nba_per75_playoffs_career_46_stats_v1"]
        if career else ["nba_per75_playoffs_46_stats_v1"]
    )
    f=find_csv(folder,terms)
    exact = (
        "nba_per75_playoffs_career_46_stats_v1.csv"
        if career else "nba_per75_playoffs_46_stats_v1.csv"
    )
    if not f:
        hits=list(folder.rglob(exact)) if folder.exists() else []
        f=hits[0] if hits else None
    # Final fallback: search the entire NBA_Per75 data tree for the exact
    # finalized builder output. This handles copied/renamed parent folders.
    if not f:
        hits=list((ROOT/"data").rglob(exact)) if (ROOT/"data").exists() else []
        f=hits[0] if hits else None
    if not f:
        return pd.DataFrame()
    key=f"__final_playoff_46__:{f}"
    if key not in CACHE:
        CACHE[key]=read_csv(f,low_memory=False)
    return CACHE[key].copy()

def _load_corrected_playoff_season_from_master():
    """Build the canonical playoff website season layer from nba_per75_master_v46."""
    key="__corrected_playoff_master_season_v1__"
    if key in CACHE: return CACHE[key]
    master_path=PATHS.get("master")
    if not master_path or not Path(master_path).exists():
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    df=read_csv(master_path,low_memory=False)
    stype=col(df,["Season_Type","Season Type","season_type"])
    if not stype:
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    df=df.loc[df[stype].astype(str).str.strip().str.casefold().isin({"playoffs","playoff","postseason"})].copy()
    player_col=col(df,["Player","Player_Name","Display_Name","player_name","Name"])
    season_col=col(df,["SeasonEndYear","Season_End_Year","Season","season","Season_ID"])
    if df.empty or not player_col or not season_col:
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    out=pd.DataFrame()
    out["Player"]=df[player_col].astype(str).str.strip()
    out["Season"]=pd.to_numeric(df[season_col],errors="coerce")
    out["Season_Type"]="Playoffs"
    for src,target in [("G","G"),("GS","GS"),("MP","MP")]:
        c=col(df,[src]); out[target]=pd.to_numeric(df[c],errors="coerce") if c else np.nan
    raw_map={"FG":"FG_raw","FGA":"FGA_raw","3P":"3P_raw","3PA":"3PA_raw","2P":"2P_raw","2PA":"2PA_raw","FT":"FT_raw","FTA":"FTA_raw","ORB":"ORB_raw","DRB":"DRB_raw","TRB":"TRB_raw","AST":"AST_raw","STL":"STL_raw","BLK":"BLK_raw","TOV":"TOV_raw","PF":"PF_raw","PTS":"PTS_raw"}
    for target,src in raw_map.items():
        c=col(df,[src,target]); out[target]=pd.to_numeric(df[c],errors="coerce") if c else np.nan
    pc=col(df,["Estimated_Possessions","Estimated_Player_Possessions","Player_Possessions","Possessions"])
    out["Estimated_Player_Possessions"]=pd.to_numeric(df[pc],errors="coerce") if pc else np.nan
    stat_sources={
        "PTS_per75":"PTS_per75","FG_per75":"FG_per75","FGA_per75":"FGA_per75","3P_per75":"3P_per75","3PA_per75":"3PA_per75","2P_per75":"2P_per75","2PA_per75":"2PA_per75","FT_per75":"FT_per75","FTA_per75":"FTA_per75","ORB_per75":"ORB_per75","DRB_per75":"DRB_per75","TRB_per75":"TRB_per75","AST_per75":"AST_per75","STL_per75":"STL_per75","BLK_per75":"BLK_per75","TOV_per75":"TOV_per75","PF_per75":"PF_per75",
        "FG_pct":"FG_pct","2P_pct":"2P_pct","3P_pct":"3P_pct","FT_pct":"FT_pct","TS_pct":"TS_pct","FTr":"FTr","3PAr":"3PAr","rTS":"rTS","ORtg":"ORtg","DRtg":"DRtg","NRtg":"NRtg","Relative_ORtg":"Relative_ORtg","Relative_DRtg":"Relative_DRtg","Relative_NRtg":"Relative_NRtg","PER":"PER","BPM":"BPM","OBPM":"OBPM","DBPM":"DBPM","VORP":"VORP","WS":"WS","OWS":"OWS","DWS":"DWS","OREB_pct":"OREB_pct","AST_pct":"AST_pct","STL_pct":"STL_pct","BLK_pct":"BLK_pct","TOV_pct":"TOV_pct","AST_TOV":"AST_TOV","DREB_pct":"DREB_pct"}
    for target,src in stat_sources.items():
        c=col(df,[src]); out[target]=pd.to_numeric(df[c],errors="coerce") if c else np.nan
    try:
        identity=_canonical_identity_registry(); ic=identity_cols(identity)
        if ic.get("id") and ic.get("name"):
            im=identity[[ic["id"],ic["name"]]].copy()
            im["__name_key"]=im[ic["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
            im=im.drop_duplicates("__name_key",keep="first")
            out["__name_key"]=out["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
            out=out.merge(im[[ic["id"],"__name_key"]],on="__name_key",how="left")
            out=out.rename(columns={ic["id"]:"Player_ID"}).drop(columns=["__name_key"],errors="ignore")
    except Exception: pass
    if "Player_ID" not in out.columns: out["Player_ID"]=np.nan
    CACHE[key]=out; CACHE["__playoff_web_season_source__"]="nba_per75_master_v46_playoffs"; return out

def load_playoff_46_season():
    """Canonical playoff player-season layer using validated v46 master values."""
    return _load_corrected_playoff_season_from_master()

def load_playoff_46_career():
    """Fast, corrected playoff career aggregation from the validated master layer."""
    key="__corrected_playoff_master_career_v1__"
    if key in CACHE: return CACHE[key]
    season=load_playoff_46_season().copy()
    if season.empty: CACHE[key]=pd.DataFrame(); return CACHE[key]
    pid=col(season,["Player_ID","PlayerId","PlayerID","player_id"]); player=col(season,["Player","Player_Name","Display_Name","player_name","Name"])
    if not player: CACHE[key]=pd.DataFrame(); return CACHE[key]
    if not pid:
        season["Player_ID"]=season[player].astype(str).str.strip().str.casefold(); pid="Player_ID"
    keys=[pid,player]
    season["__MPW"]=pd.to_numeric(season["MP"],errors="coerce").clip(lower=0)
    season["__POSSW"]=pd.to_numeric(season["Estimated_Player_Possessions"],errors="coerce").clip(lower=0)
    g=season.groupby(keys,dropna=False,sort=False)
    out=g[[c for c in ["G","GS","MP","FG","FGA","3P","3PA","2P","2PA","FT","FTA","ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS","Estimated_Player_Possessions"] if c in season.columns]].sum(min_count=1).reset_index()
    out=out.rename(columns={pid:"Player_ID",player:"Player"})
    per75=set(PLAYOFF_PER75_STATS)
    pct_denoms={"FG_pct":"FGA","2P_pct":"2PA","3P_pct":"3PA","FT_pct":"FTA","TS_pct":"FGA","FTr":"FGA","3PAr":"FGA"}
    additive={"WS","OWS","DWS","VORP"}
    # Precompute common denominators once.
    poss_num=g["__POSSW"].sum(min_count=1).reset_index(name="__poss")
    mp_num=g["__MPW"].sum(min_count=1).reset_index(name="__mp")
    out=out.merge(poss_num,on=keys,how="left").merge(mp_num,on=keys,how="left")
    for stat in PLAYOFF_STATS:
        if stat not in season.columns:
            out[stat]=np.nan; continue
        vals=pd.to_numeric(season[stat],errors="coerce")
        tmp=season[keys].copy(); tmp["__v"]=vals
        if stat in per75:
            tmp["__num"]=vals*season["__POSSW"]
            z=tmp.groupby(keys,dropna=False)["__num"].sum(min_count=1).reset_index()
            z=z.merge(poss_num,on=keys,how="left"); z[stat]=z["__num"]/z["__poss"].replace(0,np.nan)
        elif stat in additive:
            z=tmp.groupby(keys,dropna=False)["__v"].sum(min_count=1).reset_index().rename(columns={"__v":stat})
        elif stat in pct_denoms and pct_denoms[stat] in season.columns:
            den=pd.to_numeric(season[pct_denoms[stat]],errors="coerce")
            tmp["__num"]=vals*den; tmp["__den"]=den
            z=tmp.groupby(keys,dropna=False)[["__num","__den"]].sum(min_count=1).reset_index(); z[stat]=z["__num"]/z["__den"].replace(0,np.nan)
        else:
            tmp["__num"]=vals*season["__MPW"]
            z=tmp.groupby(keys,dropna=False)["__num"].sum(min_count=1).reset_index(); z=z.merge(mp_num,on=keys,how="left"); z[stat]=z["__num"]/z["__mp"].replace(0,np.nan)
        out=out.merge(z[keys+[stat]],on=keys,how="left")
    out["Season_Type"]="Playoffs"
    out=out.drop(columns=["__poss","__mp"],errors="ignore")
    CACHE[key]=out; CACHE["__playoff_web_career_source__"]="nba_per75_master_v46_playoffs_aggregated"; return out

def _playoff_long_percentiles(source, career=False):
    if source is None or source.empty: return pd.DataFrame()
    stats=[s for s in PLAYOFF_STATS if s in source.columns]; pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"]); player=col(source,["Player","Player_Name","Display_Name","player_name","Name"]); season_col=col(source,["Season","season","Season_ID"]); gcol=col(source,["G","Games","games"]); mpcol=col(source,["MP","Minutes","minutes"])
    if not player: return pd.DataFrame()
    q=(pd.to_numeric(source[gcol],errors="coerce")>=50)&(pd.to_numeric(source[mpcol],errors="coerce")>=1500) if career else ((pd.to_numeric(source[gcol],errors="coerce")>=3)&(pd.to_numeric(source[mpcol],errors="coerce")>=75))
    def ep(y):
        try:y=int(y)
        except:return "UNRESOLVED"
        for label,a,b in [("1951-52_to_1969-70",1952,1970),("1970-71_to_1979-80",1971,1980),("1980-81_to_1989-90",1981,1990),("1990-91_to_1999-00",1991,2000),("2000-01_to_2009-10",2001,2010),("2010-11_to_2019-20",2011,2020),("2020-21_to_2025-26",2021,2026)]:
            if a<=y<=b:return label
        return "UNRESOLVED"
    def pct(v,higher=True):
        x=pd.to_numeric(v,errors="coerce"); valid=x.notna(); out=pd.Series(np.nan,index=x.index,dtype=float); n=int(valid.sum())
        if n==1: out.loc[valid]=100.; return out
        if n==0:return out
        ranks=x.loc[valid].rank(method="average",ascending=not higher); out.loc[valid]=100*(n-ranks)/(n-1); return out
    lower={"TOV_pct","PF_per75","TOV_per75","DRtg","Relative_DRtg"}; parts=[]
    for stat in stats:
        b=pd.DataFrame({"Player_ID":source[pid] if pid else source[player],"Player":source[player],"Season":source[season_col] if season_col else np.nan,"G":source[gcol],"MP":source[mpcol],"Statistic":stat,"Value":pd.to_numeric(source[stat],errors="coerce"),"Qualified":q})
        b["Era"]=b["Season"].map(ep); higher=stat not in lower
        if career:
            b["Career_Percentile"]=np.nan; m=q&b.Value.notna(); b.loc[m,"Career_Percentile"]=pct(b.loc[m,"Value"],higher)
        else:
            for c in ["Season_Percentile","Era_Percentile","Historical_Percentile"]: b[c]=np.nan
            m=q&b.Value.notna()
            if m.any():
                b.loc[m,"Season_Percentile"]=b.loc[m].groupby("Season")["Value"].transform(lambda z:pct(z,higher)); b.loc[m,"Era_Percentile"]=b.loc[m].groupby("Era")["Value"].transform(lambda z:pct(z,higher)); b.loc[m,"Historical_Percentile"]=pct(b.loc[m,"Value"],higher)
        parts.append(b)
    return pd.concat(parts,ignore_index=True)

def _load_final_playoff_percentile_long(career=False):
    # Old files are deliberately ignored because they were generated from the broken Per-75 layer.
    return pd.DataFrame()

def load_playoff_percentile_long(career=False):
    key=f"__corrected_playoff_long_pct__:{career}"
    if key in CACHE: return CACHE[key]
    source=load_playoff_46_career() if career else load_playoff_46_season()
    out=_playoff_long_percentiles(source,career=career) if not source.empty else pd.DataFrame()
    CACHE[key]=out
    return out

def _playoff_player_match(df,pid=None,pname=None):
    if df is None or df.empty:
        return pd.DataFrame()
    cpid=col(df,["Player_ID","PlayerId","PlayerID","player_id"])
    cp=col(df,["Player","Player_Name","Display_Name","player_name","Name"])
    if pid is not None and cpid:
        m=df.loc[df[cpid].astype(str).str.strip().eq(str(pid).strip())].copy()
        if not m.empty: return m
    # Playoff source layers may retain a legacy/source ID or an asterisk on the
    # name. Once identity resolution maps to the canonical ID, always allow a
    # cleaned public-name fallback so the same person still resolves correctly.
    if pname is not None and cp:
        key=str(pname).replace("*","").strip().casefold()
        names=df[cp].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        return df.loc[names.eq(key)].copy()
    return df.iloc[0:0].copy()

def _canonical_master_identity_map():
    """Return source Player_ID -> canonical Player_ID using authoritative seasons."""
    key="__master_identity_map_v1__"
    if key in CACHE:
        return CACHE[key]
    master=load_master_seasons()
    if master.empty:
        CACHE[key]={}
        return CACHE[key]
    pid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    name=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    season=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    if not pid or not name or not season:
        CACHE[key]={}
        return CACHE[key]
    x=master[[pid,name,season]].copy()
    x["__pid"]=x[pid].astype(str).str.strip()
    x["__nk"]=(x[name].astype(str).str.replace(r"\*+","",regex=True)
               .str.replace(r"[^a-z0-9]+"," ",regex=True)
               .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
    x["__yr"]=x[season].map(_season_end_year)
    x=x.dropna(subset=["__yr"]).drop_duplicates(["__pid","__yr"])
    sig=x.groupby(["__nk","__pid"])["__yr"].agg(
        years=lambda s:set(s), seasons="count", start="min", end="max"
    ).reset_index()
    mapping={}
    for nk,g in sig.groupby("__nk",sort=False):
        rows=g.to_dict("records")
        # Build overlap clusters. IDs with substantial overlap are source
        # aliases for the same historical player.
        clusters=[]
        unused=set(range(len(rows)))
        while unused:
            i=unused.pop()
            cluster={i}
            changed=True
            while changed:
                changed=False
                for j in list(unused):
                    overlap_any=False
                    for k in cluster:
                        aa,bb=rows[k],rows[j]
                        ov=len(aa["years"] & bb["years"])
                        smaller=max(1,min(len(aa["years"]),len(bb["years"])))
                        if ov>=3 or ov/smaller>=0.50:
                            overlap_any=True
                            break
                    if overlap_any:
                        cluster.add(j); unused.remove(j); changed=True
            clusters.append(cluster)
        for cluster in clusters:
            best=max((rows[i] for i in cluster),
                     key=lambda r:(r["seasons"],r["end"]-r["start"],-r["start"],r["__pid"]))
            for i in cluster:
                mapping[rows[i]["__pid"]]=best["__pid"]
    CACHE[key]=mapping
    return mapping

def resolve_player_identity(requested):
    """Resolve either a canonical ID or any legacy/source ID to one public identity."""
    identity=_canonical_identity_registry()
    ic=identity_cols(identity)
    req=str(requested).strip()

    # Canonical ID lookup.
    if not identity.empty and ic.get("id"):
        m=identity.loc[identity[ic["id"]].astype(str).str.strip().eq(req)]
        if not m.empty:
            # The Players endpoint already returns the canonical public ID.
            # Do not rebuild the expensive master-season identity map during
            # every profile request; that map is only needed to collapse search
            # results and stale source aliases.
            return clean(m.iloc[0][ic["id"]]), clean(m.iloc[0][ic["name"]])

    # IMPORTANT: the raw identity source can contain a second/source-only ID
    # for the same person (e.g. Michael Jordan*). If a user follows an old
    # bookmark or a stale search result to that ID, map it through the cleaned
    # public name back to the canonical registry instead of opening a second
    # profile.
    raw_identity=load_exact_csv("identity", "website_player_identity_v1.csv")
    ric=identity_cols(raw_identity)
    if not raw_identity.empty and ric.get("id") and ric.get("name"):
        raw_match=raw_identity.loc[raw_identity[ric["id"]].astype(str).str.strip().eq(req)]
        if not raw_match.empty:
            raw_name=str(raw_match.iloc[0][ric["name"]]).replace("*","").strip().casefold()
            if not identity.empty and ic.get("id") and "__public_key" in identity.columns:
                cm=identity.loc[identity["__public_key"].eq(raw_name)]
                if len(cm)==1:
                    return clean(cm.iloc[0][ic["id"]]), clean(cm.iloc[0][ic["name"]])
                # Ambiguous names (e.g. two distinct players named George King)
                # must never be resolved to whichever row happens to sort first.
                # Preserve the source identity rather than creating a duplicate
                # profile under the wrong person's canonical ID.
                if len(cm)>1:
                    return req, str(raw_match.iloc[0][ric["name"]]).replace("*","").strip()

    # Public-name lookup.
    if not identity.empty and ic.get("name"):
        key=re.sub(r"[^a-z0-9]+"," ",req.replace("*",""),flags=re.I).strip().casefold()
        m=identity.loc[identity["__public_key"].eq(key)]
        if len(m)==1:
            return clean(m.iloc[0][ic["id"]]) if ic.get("id") else None, clean(m.iloc[0][ic["name"]])
        if len(m)>1:
            # Do not silently choose between distinct people who share a name.
            return None, req.replace("*","").strip()

    # Fallback to the authoritative master for names/IDs not yet represented
    # in the website identity registry.
    master=load_master_seasons()
    if not master.empty:
        mc=identity_cols(master)
        if mc.get("id"):
            m=master.loc[master[mc["id"]].astype(str).eq(req)]
            if not m.empty:
                return clean(m.iloc[0][mc["id"]]), clean(m.iloc[0][mc["name"]])
        if mc.get("name"):
            key=req.replace("*","").strip().casefold()
            m=master.loc[master[mc["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(key)]
            if not m.empty:
                return clean(m.iloc[0][mc["id"]]) if mc.get("id") else None, clean(m.iloc[0][mc["name"]])
    return None, req.replace("*","").strip()

def api_playoff_profile(requested, season):
    pid,pname=resolve_player_identity(requested)
    if pid is None and (not pname or pname.casefold() == str(requested).casefold()):
        # A name-only master row can still be valid; continue with name lookup.
        pass

    season_df=load_playoff_46_season()
    if season_df.empty:
        return {"found":True,"player":{"player_id":pid,"player_name":pname},
                "seasons":[],"profile":None,"percentiles":[],"playoff_available":False,
                "season_type":"Playoffs"}

    season_col=col(season_df,["Season","season","Season_ID"])
    # Preserve EVERY playoff season in the finalized season layer, regardless
    # of percentile qualification.
    player_rows=_playoff_player_match(season_df,pid,pname)
    # The playoff source stores seasons as the starting year (e.g. 1985),
    # while the profile UI uses the canonical YYYY-YY label (1985-86). Keep
    # one display/selection format and normalize back to the raw source only
    # when matching rows.
    seasons=sorted(
        {_season_label_any(x) for x in player_rows[season_col].dropna().astype(str).tolist()},
        key=lambda x:_season_end_year(x) or 0
    ) if season_col and not player_rows.empty else []

    requested_view=normalize_requested_season(season) if season else (seasons[-1] if seasons else None)
    is_career=bool(requested_view and requested_view.casefold()=="career")

    if is_career:
        # Career aggregation is only needed for the explicit Career view.
        # Avoid building the full playoff career table for every normal
        # player-season profile request.
        career_df=load_playoff_46_career()
        cm=_playoff_player_match(career_df,pid,pname)
        profile={k:clean(v) for k,v in (cm.iloc[0].to_dict().items() if not cm.empty else [])}
        profile["Season"]="Career"
        per=_playoff_long_percentiles(career_df,career=True)
        # Prefer finalized percentile file when available.
        final_long=_load_final_playoff_percentile_long(True)
        if not final_long.empty:
            per=final_long
        pm=_playoff_player_match(per,pid,pname)
        percentiles=[{k:clean(v) for k,v in r.items()} for r in pm.to_dict("records")]
        context_avail={"Season":False,"Era":False,"Historical":False,"Career":True}
        raw_rows=cm
    else:
        sm=player_rows.loc[player_rows[season_col].map(_season_label_any).eq(str(requested_view))].copy() if season_col else player_rows.iloc[0:0]
        profile={k:clean(v) for k,v in (sm.iloc[0].to_dict().items() if not sm.empty else [])}
        final_long=_load_final_playoff_percentile_long(False)
        per=final_long if not final_long.empty else _playoff_long_percentiles(season_df,career=False)
        ps=_playoff_player_match(per,pid,pname)
        if not ps.empty and "Season" in ps.columns:
            ps=ps.loc[ps["Season"].map(_season_label_any).eq(str(requested_view))].copy()
        percentiles=[{k:clean(v) for k,v in r.items()} for r in ps.to_dict("records")]
        context_avail={"Season":True,"Era":True,"Historical":True,"Career":False}
        raw_rows=sm

    # Build the 46-stat raw-value map through normalized source-column lookup,
    # so punctuation/case aliases such as USG% cannot make a valid statistic
    # disappear from the profile.
    stat_values={}
    if not raw_rows.empty:
        raw=raw_rows.iloc[0]
        for stat in PLAYOFF_STATS:
            sc=_playoff_source_column(raw_rows,stat)
            stat_values[stat]=clean(raw[sc]) if sc else None

    headshot=None
    try:
        hs=load("headshots",["headshot_registry","headshot"])
        hm=filter_player(hs,pid if pid is not None else pname)
        if hm.empty: hm=filter_player(hs,pname)
        if not hm.empty:
            hc=col(hm,["Verified_Headshot_URL","Headshot_URL","HeadshotUrl","NBA_Headshot_URL","CDN_URL","Image_URL"])
            if hc: headshot=clean(hm.iloc[0][hc])
    except Exception:
        pass

    profile_sdi = _v21_profile_sdi_for_player(
        pid=pid, pname=pname, season=requested_view if not is_career else None, playoff=True
    ) if not is_career else {}

    return {
        "found":True,
        "view":requested_view,
        "is_career":is_career,
        "player":{"player_id":pid,"player_name":pname,"headshot_url":headshot},
        "seasons":seasons,
        "profile":profile,
        "playoff_statistics":stat_values,
        "percentiles":percentiles,
        "sdi_categories":profile_sdi,
        "playoff_available":True,
        "playoff_source":str(CACHE.get("__final_playoff_46_source_path__",PATHS["playoff_46"])),
        "season_type":"Playoffs",
        "available_contexts":context_avail,
        "statistic_registry":PLAYOFF_STATS,
        "career_note":(
            "Career playoff values come from the finalized playoff career 46-stat layer. "
            "Career percentiles require G >= 50 and MP >= 1,500. Single-season playoff percentiles require G >= 3 and MP >= 75."
            if is_career else None
        ),
    }



def _load_sdi_v4_spec():
    """Load the locked NEW SDI v4 formula used by Player Profile peaks."""
    key="__sdi_v4_spec__"
    if key in CACHE:
        return CACHE[key]
    candidates=[
        ROOT/"config"/"statistical_index_v4_locked.json",
        ROOT/"data"/"statistical_index_v4_locked.json",
    ]
    spec={}
    for p in candidates:
        if p.exists():
            try:
                spec=json.loads(p.read_text(encoding="utf-8"))
                break
            except Exception:
                pass
    CACHE[key]=spec
    return spec

def _compute_sdi_v4_from_percentile_rows(rows):
    """Compute one season's NEW SDI v4 from season percentiles.

    Formula:
      1. weighted statistic percentile -> subgroup score
      2. weighted subgroup score -> category score
      3. equal-weight the six top-level categories
    """
    if rows is None or rows.empty:
        return np.nan

    stat_col=choose_col(rows,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    pct_col=percentile_column(rows,"Season")
    if not stat_col or not pct_col:
        return np.nan

    spec=_load_sdi_v4_spec()
    if not spec:
        return np.nan

    vals=(rows.assign(__stat=rows[stat_col].astype(str).str.strip(),
                      __pct=pd.to_numeric(rows[pct_col],errors="coerce"))
          .dropna(subset=["__pct"])
          .drop_duplicates("__stat",keep="first")
          .set_index("__stat")["__pct"].to_dict())

    category_scores=[]
    for category, groups in spec.items():
        if category=="peak_rules" or not isinstance(groups,dict):
            continue
        group_scores=[]
        for group_name, group_spec in groups.items():
            if not isinstance(group_spec,dict):
                continue
            stats=group_spec.get("statistics",{})
            if not isinstance(stats,dict):
                continue
            usable=[(float(vals[s]),float(w)) for s,w in stats.items()
                    if s in vals and pd.notna(vals[s]) and pd.notna(w)]
            if not usable:
                continue
            den=sum(w for _,w in usable)
            if den<=0:
                continue
            group_score=sum(v*w for v,w in usable)/den
            group_scores.append((group_score,float(group_spec.get("weight",1.0))))
        if not group_scores:
            continue
        den=sum(w for _,w in group_scores)
        if den<=0:
            continue
        category_scores.append(sum(v*w for v,w in group_scores)/den)

    if len(category_scores)!=6:
        return np.nan
    return float(np.mean(category_scores))

def _load_regular_sdi_v4_player_seasons():
    """Load/cache the compact NEW SDI v4 player-season index.

    The expensive percentile CSV is read once. The persisted compact file is
    then used on every subsequent API start. This replaces the old
    player_statistical_dominance_v1 dependency for regular 5-Year Peak.
    """
    key="__regular_sdi_v4_player_seasons__"
    if key in CACHE:
        return CACHE[key]

    cache_path=ROOT/"local_api"/"cache"/"regular_sdi_v4_player_seasons.csv"
    if cache_path.exists():
        try:
            d=read_csv(cache_path,low_memory=False)
            CACHE[key]=d
            return d
        except Exception:
            pass

    per=load("percentiles",["player_season_percentiles_long"])
    if per.empty:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]

    pc=identity_cols(per)
    stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    season_col=choose_col(per,["Season","season","Season_ID"])
    pct_col=percentile_column(per,"Season")
    if not pc.get("id") and not pc.get("player"):
        CACHE[key]=pd.DataFrame()
        return CACHE[key]
    if not stat_col or not season_col or not pct_col:
        CACHE[key]=pd.DataFrame()
        return CACHE[key]

    # Restrict to the six-category formula's statistics before grouping.
    spec=_load_sdi_v4_spec()
    wanted=[]
    for category, groups in spec.items():
        if category=="peak_rules" or not isinstance(groups,dict): continue
        for gs in groups.values():
            if isinstance(gs,dict):
                wanted.extend(gs.get("statistics",{}).keys())
    wanted=set(wanted)

    d=per.copy()
    d["__stat"]=d[stat_col].astype(str).str.strip()
    d=d.loc[d["__stat"].isin(wanted)].copy()
    d["__pct"]=pd.to_numeric(d[pct_col],errors="coerce")
    d=d.dropna(subset=["__pct"])
    d["__season"]=d[season_col].map(_season_end_year)
    d=d.dropna(subset=["__season"]).copy()
    d["__season"]=d["__season"].astype(int)
    if pc.get("id"):
        d["__pid"]=d[pc["id"]].astype(str).str.strip()
    else:
        d["__pid"]=d[pc["player"]].astype(str).str.replace(r"\*+","",regex=True).str.strip()

    # Map each statistic to its exact nested v4 weights.
    mapping=[]
    for category, groups in spec.items():
        if category=="peak_rules" or not isinstance(groups,dict): continue
        for group_name, gs in groups.items():
            if not isinstance(gs,dict): continue
            for stat, sw in gs.get("statistics",{}).items():
                mapping.append((category,group_name,stat,float(sw),float(gs.get("weight",1.0))))
    wm=pd.DataFrame(mapping,columns=["__cat","__group","__stat","__sw","__gw"])
    d=d.merge(wm,on="__stat",how="inner")

    # Compute subgroup scores, then category scores, then equal-weight SDI.
    d["__num"]=d["__pct"]*d["__sw"]
    gcols=["__pid","__season","__cat","__group"]
    g=d.groupby(gcols,sort=False,dropna=False).agg(
        __num=("__num","sum"), __sw=("__sw","sum"), __gw=("__gw","first")
    ).reset_index()
    g["__group_score"]=g["__num"]/g["__sw"].replace(0,np.nan)
    c=g.groupby(["__pid","__season","__cat"],sort=False,dropna=False).apply(
        lambda x: np.average(x["__group_score"],weights=x["__gw"]) if x["__gw"].sum()>0 else np.nan
    ).reset_index(name="__category_score")
    s=c.groupby(["__pid","__season"],sort=False,dropna=False)["__category_score"].mean().reset_index(name="SDI_v4")
    s["Season"]=s["__season"].map(_season_label_any)
    s=s[["__pid","Season","__season","SDI_v4"]].copy()

    cache_path.parent.mkdir(parents=True,exist_ok=True)
    s.to_csv(cache_path,index=False)
    CACHE[key]=s
    return s

def _new_sdi_v4_for_player(match, requested_pid=None, requested_name=None):
    """Return season -> NEW SDI v4 for one player.

    Prefer the compact cached player-season index. If that index has not been
    built yet (the normal startup path), compute SDI v4 only for this player
    from the existing season-percentile rows. This keeps profile requests
    functional without rebuilding the entire league index.
    """
    idx=_load_regular_sdi_v4_player_seasons()

    pid=str(requested_pid).strip() if requested_pid is not None else None
    if not idx.empty:
        if pid:
            m=idx.loc[idx["__pid"].astype(str).str.strip().eq(pid)].copy()
        else:
            m=pd.DataFrame()

        if m.empty and requested_name:
            master=load_master_seasons()
            pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
            pidcol=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
            if pcol and pidcol:
                wanted=str(requested_name).replace("*","").strip().casefold()
                mm=master.loc[
                    master[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted),
                    pidcol
                ].dropna().astype(str).str.strip().unique().tolist()
                if mm:
                    m=idx.loc[idx["__pid"].astype(str).str.strip().isin(mm)].copy()

        if not m.empty:
            return dict(zip(m["__season"].astype(int),pd.to_numeric(m["SDI_v4"],errors="coerce")))

    # Live single-player fallback. The cache is deliberately optional at
    # startup, so a missing compact index must not make every 5-Year Peak
    # profile report "No matching player."
    try:
        per=load("percentiles",["player_season_percentiles_long"])
        if per.empty:
            return {}
        pc=identity_cols(per)
        stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
        season_col=choose_col(per,["Season","season","Season_ID"])
        pct_col=percentile_column(per,"Season")
        if not stat_col or not season_col or not pct_col:
            return {}

        pkey=None
        if pc.get("id") and pid:
            pkey=pid
            rows=per.loc[per[pc["id"]].astype(str).str.strip().eq(pid)].copy()
        else:
            rows=pd.DataFrame()

        if rows.empty and requested_name and pc.get("player"):
            wanted=str(requested_name).replace("*","").strip().casefold()
            rows=per.loc[
                per[pc["player"]].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)
            ].copy()

        # If the percentile source uses a different player ID, map through the
        # name in the already matched master rows.
        if rows.empty and requested_name and pc.get("id"):
            master=load_master_seasons()
            pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
            mpid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
            if pcol and mpid:
                wanted=str(requested_name).replace("*","").strip().casefold()
                master_ids=master.loc[
                    master[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted), mpid
                ].dropna().astype(str).str.strip().unique().tolist()
                if master_ids:
                    rows=per.loc[per[pc["id"]].astype(str).str.strip().isin(master_ids)].copy()

        if rows.empty:
            return {}

        wanted_stats=set()
        spec=_load_sdi_v4_spec()
        for category, groups in spec.items():
            if category=="peak_rules" or not isinstance(groups,dict):
                continue
            for gs in groups.values():
                if isinstance(gs,dict):
                    wanted_stats.update(gs.get("statistics",{}).keys())
        rows["__stat"]=rows[stat_col].astype(str).str.strip()
        rows=rows.loc[rows["__stat"].isin(wanted_stats)].copy()
        rows["__season"]=rows[season_col].map(_season_end_year)
        rows=rows.dropna(subset=["__season"]).copy()
        rows["__season"]=rows["__season"].astype(int)
        out={}
        for year, grp in rows.groupby("__season",sort=False):
            score=_compute_sdi_v4_from_percentile_rows(grp)
            if pd.notna(score):
                out[int(year)]=float(score)
        return out
    except Exception:
        return {}

def _load_profile_dominance_index():
    """Load a tiny persistent SDI index for Player Profile peak windows.

    The source dominance table can be very large. Profile peak rendering only
    needs Player_ID/name, season, and SDI, so persist just those fields once.
    """
    cache_key="__profile_dominance_index_v1__"
    if cache_key in CACHE:
        return CACHE[cache_key]
    cache_path=ROOT/"data"/"cache"/"profile_dominance_index_v1.csv"
    if cache_path.exists():
        try:
            d=read_csv(cache_path,low_memory=False)
            CACHE[cache_key]=d
            return d
        except Exception:
            pass

    dfile=find_recursive_csv(ROOT,["player_statistical_dominance_v1","dominance_index"])
    if not dfile:
        CACHE[cache_key]=pd.DataFrame()
        return CACHE[cache_key]

    try:
        # Read only columns needed for peak-window selection.
        header=read_csv(dfile,nrows=0)
        dpid=col(header,["Player_ID","PlayerId","PlayerID","player_id"])
        dname=col(header,["Player","Player_Name","Display_Name","player_name","Name"])
        dseason=col(header,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        dscore=col(header,["Dominance_Index","dominance_index","Index_Score","Index"])
        use=[x for x in [dpid,dname,dseason,dscore] if x]
        if not dscore or not dseason:
            CACHE[cache_key]=pd.DataFrame()
            return CACHE[cache_key]
        d=read_csv(dfile,usecols=use,low_memory=False)
        if dpid: d=d.rename(columns={dpid:"Player_ID"})
        if dname: d=d.rename(columns={dname:"Player"})
        d=d.rename(columns={dseason:"Season",dscore:"SDI"})
        if "Player_ID" in d.columns:
            d["Player_ID"]=d["Player_ID"].astype(str).str.strip()
        if "Player" in d.columns:
            d["Player"]=d["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip()
        d["__year"]=d["Season"].map(_season_end_year)
        d["SDI"]=pd.to_numeric(d["SDI"],errors="coerce")
        d=d.dropna(subset=["__year","SDI"]).copy()
        d["__year"]=d["__year"].astype(int)
        cache_path.parent.mkdir(parents=True,exist_ok=True)
        d.to_csv(cache_path,index=False)
        CACHE[cache_key]=d
        return d
    except Exception:
        CACHE[cache_key]=pd.DataFrame()
        return CACHE[cache_key]


def _regular_peak_resolved_name(requested_pid=None, requested_name=None):
    """Resolve the actual canonical player name for regular 5-Year Peak.

    The profile identity resolver returns (public_id, data_id). The regular
    peak path also needs the display/name identity for name-based fallback.
    """
    reg=_canonical_identity_registry()
    if not reg.empty:
        ic=identity_cols(reg)
        if ic.get("id") and ic.get("name"):
            targets=[]
            if requested_pid is not None:
                targets.append(str(requested_pid).strip())
            if requested_name:
                targets.append(str(requested_name).replace("*","").strip())
            for target in targets:
                m=reg.loc[reg[ic["id"]].astype(str).str.strip().eq(target)]
                if not m.empty:
                    return str(m.iloc[0][ic["name"]]).replace("*","").strip()
    raw=str(requested_name or "").replace("*","").strip()
    # Preserve an actual multi-word name if one was supplied directly.
    if " " in raw or any(ch.isalpha() and ch not in "abcdef" for ch in raw):
        return raw
    return None

def _canonical_five_year_peak_profile(requested_pid=None, requested_name=None):
    resolved_name=_regular_peak_resolved_name(requested_pid, requested_name) or (str(requested_name or "").replace("*","").strip() or None)
    request_key=("__regular_5yr_profile_v3__",
                 str(requested_pid).strip() if requested_pid is not None else "",
                 str(resolved_name or "").casefold())
    if request_key in CACHE:
        return CACHE[request_key]
    """Return the player's single canonical 5-Year Peak.

    Fast profile path: identify the requested player's qualifying windows
    directly from master data, then select the window with the highest mean
    season-level SDI. This avoids rebuilding the entire league peak population
    merely to render one player's profile.
    

    The canonical window is the valid five-season window with the highest
    average Statistical Dominance Index across its five included seasons.
    All profile statistics are then aggregated over that same window.
    """
    # ---- FAST SINGLE-PLAYER PATH ------------------------------------------------
    # Profile requests should never have to construct every player's peak just
    # to display one player. Resolve the requested player and evaluate only
    # that player's valid windows.
    try:
        master=load_master_seasons()
        pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
        pidcol=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
        scol=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        stcol=col(master,["Season_Type","SeasonType","season_type","Phase"])
        gcol=col(master,["G","Games","games"])
        mpcol=col(master,["MP","Minutes","minutes"])
        if pcol and scol and gcol and mpcol:
            work=master.copy()
            if stcol:
                work=work.loc[work[stcol].astype(str).str.strip().str.casefold().isin(
                    {"regular season","regular","reg season"})].copy()
            # Prefer the requested canonical ID, but NEVER let a stale/aliased
            # public ID prevent a valid name-based match. This is especially
            # important for the 5-Year Peak route because the canonical search
            # registry and the season master can legitimately use different
            # source IDs for the same player.
            match=pd.DataFrame()
            if pidcol and requested_pid is not None:
                match=work.loc[work[pidcol].astype(str).str.strip().eq(str(requested_pid).strip())].copy()
            if match.empty and resolved_name:
                wanted=str(resolved_name).replace("*","").strip().casefold()
                match=work.loc[
                    work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)
                ].copy()
            if not match.empty:
                match["__season_year"]=match[scol].map(_season_end_year)
                match["__G"]=pd.to_numeric(match[gcol],errors="coerce")
                match["__MP"]=pd.to_numeric(match[mpcol],errors="coerce")
                match=match.dropna(subset=["__season_year"]).copy()
                match["__season_year"]=match["__season_year"].astype(int)
                match=match.sort_values(["__season_year","__MP"],ascending=[True,False]).drop_duplicates(["__season_year"],keep="first")

                schedule=match.groupby("__season_year")["__G"].max().dropna().to_dict()
                qualified=[]
                for _,rr in match.iterrows():
                    sched=float(schedule.get(int(rr["__season_year"]),82) or 82)
                    if float(rr["__G"])>=math.ceil(.60*sched) and float(rr["__MP"])>=1400:
                        qualified.append(rr)
                q=pd.DataFrame(qualified) if qualified else pd.DataFrame()
                candidates=[]
                for i in range(max(0,len(q)-4)):
                    cand=q.iloc[i:i+5].copy()
                    if len(cand)==5 and int(cand["__season_year"].iloc[-1])-int(cand["__season_year"].iloc[0])<=5:
                        candidates.append(cand)

                if candidates:
                    # Prefer an SDI field already present in the player's master
                    # rows. Only fall back to the dominance file if necessary.
                    # NEW SDI v4: use the locked six-category/equal-top-level
                    # formula from config/statistical_index_v4_locked.json.
                    sdi_map=_new_sdi_v4_for_player(
                        match, requested_pid=requested_pid, requested_name=resolved_name
                    )
                    match["__sdi"]=match["__season_year"].map(sdi_map)

                    # A canonical window is valid only when ALL FIVE included
                    # qualifying seasons have a real SDI v4 score.  Missing SDI
                    # must invalidate the candidate; treating an incomplete
                    # window as score 0.0 can select a false peak.
                    valid_candidates=[]
                    # `candidates` were sliced from match before __sdi was
                    # attached, so each slice needs an explicit season->SDI
                    # mapping.  Without this, cand["__sdi"] raises KeyError,
                    # the outer guard swallows it, and the profile returns
                    # "No matching player".
                    sdi_by_year=(match.dropna(subset=["__season_year"])
                                      .drop_duplicates("__season_year",keep="first")
                                      .set_index("__season_year")["__sdi"]
                                      .to_dict())
                    for cand in candidates:
                        cand=cand.copy()
                        cand["__sdi"]=cand["__season_year"].map(sdi_by_year)
                        scores=pd.to_numeric(cand["__sdi"],errors="coerce")
                        if len(scores)!=FIVE_YEAR_PEAK_N or scores.isna().any():
                            continue
                        score=float(scores.mean())
                        valid_candidates.append((score,cand))
                    if valid_candidates:
                        # Primary selection is the highest five-season average
                        # SDI. Use the later-ending window only as a deterministic
                        # tie-breaker when averages are effectively identical.
                        best=max(
                            valid_candidates,
                            key=lambda item:(round(item[0],12), int(item[1]["__season_year"].max()))
                        )
                        cand=best[1]
                        stats=[str(x) for x in REGULAR_STATS if str(x) in cand.columns]
                        row={"Player_ID":str(requested_pid or ""), "Player":str(resolved_name or cand[pcol].iloc[0]),
                             "Season":"5-Year Peak",
                             "Peak_Start_Year":int(cand["__season_year"].min()),
                             "Peak_End_Year":int(cand["__season_year"].max()),
                             "Peak_Seasons":[_season_label_any(y) for y in cand["__season_year"].tolist()],
                             "Peak_Era":_era_key(int(cand["__season_year"].min())),
                             "Peak_SDI":best[0]}
                        for stat in stats:
                            row[stat]=clean(_era_average_statistic(cand,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS))

                        # Peak percentiles are populated from the already-built
                        # Big Board statistic populations when available; if not,
                        # return the values immediately and let the UI render them.
                        pcts=[]
                        for stat in stats:
                            pcts.append({"Statistic":stat,"Value":row.get(stat),"Peak_Value":row.get(stat),
                                         "Peak_Percentile":None})
                        result={"found":True,"available":True,
                                "player":{"player_id":requested_pid,"player_name":row["Player"]},
                                "profile":row,"statistic_values":{k:row.get(k) for k in stats},
                                "percentiles":pcts,"seasons":["5-Year Peak"],
                                "season":"5-Year Peak","season_type":"Regular Season",
                                "is_five_year_peak":True,
                                "peak":{"start":row["Peak_Start_Year"],"end":row["Peak_End_Year"],
                                        "seasons":row["Peak_Seasons"],"era":row["Peak_Era"],"sdi":best[0]}}
                        CACHE[request_key]=result
                        return result
    except Exception:
        pass

    # Legacy all-player peak reconstruction is intentionally disabled.
    # Regular Player Profile 5-Year Peak is now exclusively selected from the
    # NEW SDI v4 season index above. This prevents accidental fallback to the
    # obsolete dominance-index source and avoids multi-minute request-time work.
    return {"found":False,"available":False}

    target=None
    req_id=str(requested_pid).strip() if requested_pid is not None else None
    req_name=str(requested_name or "").replace("*","").strip().casefold()
    for item in population:
        if req_id and item["player_id"]==req_id:
            target=item; break
    if target is None and req_name:
        for item in population:
            if item["player"].replace("*","").strip().casefold()==req_name:
                target=item; break
    if target is None:
        return {"found":False,"available":False}

    cand=target["rows"]
    stats=[str(x) for x in REGULAR_STATS if str(x) in cand.columns]
    row={"Player_ID":target["player_id"],"Player":target["player"],
         "Season":"5-Year Peak",
         "Peak_Start_Year":int(min(target["years"])),
         "Peak_End_Year":int(max(target["years"])),
         "Peak_Seasons":[_season_label_any(y) for y in target["years"]],
         "Peak_Era":_era_key(int(min(target["years"]))),
         "Peak_SDI":target["sdi"]}
    for stat in stats:
        row[stat]=clean(_era_average_statistic(cand,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS))

    # Compute statistic-specific percentiles across canonical player peaks.
    # The percentile context is the population of one canonical peak per player.
    population_rows=[]
    for item in population:
        c=item["rows"]
        vals={}
        for stat in stats:
            vals[stat]=_era_average_statistic(c,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
        population_rows.append(vals)
    pct={}
    for stat in stats:
        vals=pd.to_numeric(pd.Series([r.get(stat) for r in population_rows]),errors="coerce")
        target_val=pd.to_numeric(pd.Series([row.get(stat)]),errors="coerce").iloc[0]
        valid=vals.dropna()
        if pd.notna(target_val) and len(valid):
            rank=float((valid <= target_val).sum())
            pct[stat]=100.0*rank/len(valid)
        else:
            pct[stat]=None

    return {
        "found":True,"available":True,
        "player":{"player_id":target["player_id"],"player_name":target["player"]},
        "profile":row,
        "statistic_values":{k:row.get(k) for k in stats},
        "percentiles":[{"Statistic":stat,"Value":row.get(stat),"Peak_Value":row.get(stat),
                        "Career_Percentile":pct.get(stat),"Peak_Percentile":pct.get(stat)}
                       for stat in stats],
        "seasons":["5-Year Peak"],
        "season":"5-Year Peak",
        "season_type":"Regular Season",
        "is_five_year_peak":True,
        "peak":{"start":int(min(target["years"])),"end":int(max(target["years"])),
                "seasons":[_season_label_any(y) for y in target["years"]],
                "era":_era_key(int(min(target["years"]))),
                "sdi":target["sdi"]},
        "note":"Canonical 5-Year Peak is the valid five-season window with the highest average Statistical Dominance Index. All displayed statistics use that same window."
    }


def _playoff_season_index_table(source):
    """Compute a season-level six-category index from the current playoff
    percentile population. Used only to select a canonical playoff peak."""
    long=_playoff_long_percentiles(source,career=False)
    if long.empty:
        return pd.DataFrame()
    statc=col(long,["Statistic","statistic","Stat"])
    pidc=col(long,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(long,["Player","Player_Name","Display_Name","player_name","Name"])
    seac=col(long,["Season","season","Season_ID"])
    pctc="Historical_Percentile" if "Historical_Percentile" in long.columns else None
    if not statc or not namec or not seac or not pctc: return pd.DataFrame()
    spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
    scat=choose_col(spec,["Category"]); sgrp=choose_col(spec,["Group_ID","Group","Group_Id"])
    sstat=choose_col(spec,["Statistic","Stat"]); ssw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    sgw=choose_col(spec,["Group_Weight"])
    if not all([scat,sgrp,sstat,ssw,sgw]): return pd.DataFrame()
    allowed={"Scoring Volume","Scoring Efficiency","Creation & Playmaking","Rebounding","Defense","Impact & Value"}
    w=spec.loc[spec[scat].astype(str).str.strip().isin(allowed)].copy()
    w["_stat_key"]=w[sstat].astype(str).str.strip()
    w["_sw"]=pd.to_numeric(w[ssw],errors="coerce"); w["_gw"]=pd.to_numeric(w[sgw],errors="coerce")
    w=w.dropna(subset=["_sw","_gw"])
    long=long.copy()
    long["_stat_key"]=long[statc].astype(str).str.strip()
    long["_pct_num"]=pd.to_numeric(long[pctc],errors="coerce")
    pieces=[]
    base=[c for c in [pidc,namec,seac] if c]
    for (category,group),g in w.groupby([scat,sgrp],sort=False):
        m=long.merge(g[["_stat_key","_sw"]],on="_stat_key",how="inner").dropna(subset=["_pct_num"])
        if m.empty: continue
        gs=m.groupby(base,dropna=False).apply(lambda z: np.average(z["_pct_num"],weights=z["_sw"]),include_groups=False).reset_index(name="_group_score")
        gs["_gw"]=float(g["_gw"].iloc[0]); gs["_category"]=str(category); pieces.append(gs)
    if not pieces:return pd.DataFrame()
    groups=pd.concat(pieces,ignore_index=True)
    out=(groups.assign(_w=groups["_group_score"]*groups["_gw"])
         .groupby(base,dropna=False).agg(_weighted=("_w","sum"),_gw=("_gw","sum")).reset_index())
    out["SDI"]=out["_weighted"]/out["_gw"].replace(0,np.nan)
    return out



PLAYOFF_PEAK_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "playoff_peak_v2.json"

def _load_precomputed_playoff_peak_population():
    """Load the one-time playoff 5-Year Peak calculation from disk."""
    try:
        if not PLAYOFF_PEAK_CACHE_PATH.exists():
            return None
        with PLAYOFF_PEAK_CACHE_PATH.open("r", encoding="utf-8") as f:
            payload=json.load(f)
        rows=payload.get("rows") if isinstance(payload,dict) else None
        if not isinstance(rows,list) or not rows:
            return None
        result={}
        for row in rows:
            if not isinstance(row,dict):
                continue
            pid=str(row.get("player_id","")).strip()
            name=str(row.get("player_name","")).replace("*","").strip().casefold()
            if pid or name:
                result[(pid,name)]=row
        if not result:
            return None
        return _hydrate_playoff_peak_percentiles(result)
    except Exception:
        # A bad/stale cache must never prevent the API from starting.
        return None


def _hydrate_playoff_peak_percentiles(rows_by_key):
    """Fast percentile hydration for an already-precomputed peak cache.

    This deliberately operates only on the 322-ish cached peak rows. It never
    rebuilds playoff season windows or scans the full playoff season source.
    """
    if not rows_by_key:
        return rows_by_key

    rows=list(rows_by_key.values())
    changed=False

    # If the cache already contains complete percentile maps, leave it alone.
    complete=True
    for r in rows:
        stats=r.get("statistics") or {}
        pcts=r.get("percentiles") or {}
        if any(k not in pcts for k,v in stats.items() if v is not None):
            complete=False
            break
    if complete and all(r.get("sdi_percentile") is not None for r in rows):
        return rows_by_key

    for stat in PLAYOFF_STATS:
        vals=[]
        for r in rows:
            v=(r.get("statistics") or {}).get(stat)
            try:
                v=float(v)
            except (TypeError,ValueError):
                continue
            if np.isfinite(v):
                vals.append(v)
        if not vals:
            continue
        s=pd.Series(vals,dtype="float64")
        lower=stat in PLAYOFF_LOWER_IS_BETTER
        ranks=s.rank(method="average",ascending=lower)
        pct_values=(100.0 if len(s)==1 else 100.0*(len(s)-ranks)/(len(s)-1)).tolist()
        j=0
        for r in rows:
            v=(r.get("statistics") or {}).get(stat)
            try:
                valid=np.isfinite(float(v))
            except (TypeError,ValueError):
                valid=False
            if valid:
                r.setdefault("percentiles",{})[stat]=float(pct_values[j])
                j+=1

    sdi_vals=[]
    for r in rows:
        try:
            v=float(r.get("sdi"))
            if np.isfinite(v):
                sdi_vals.append(v)
        except (TypeError,ValueError):
            pass
    if sdi_vals:
        s=pd.Series(sdi_vals,dtype="float64")
        ranks=s.rank(method="average",ascending=False)
        pcts=(100.0 if len(s)==1 else 100.0*(len(s)-ranks)/(len(s)-1)).tolist()
        j=0
        for r in rows:
            try:
                valid=np.isfinite(float(r.get("sdi")))
            except (TypeError,ValueError):
                valid=False
            if valid:
                r["sdi_percentile"]=float(pcts[j])
                j+=1

    for key,r in rows_by_key.items():
        rows_by_key[key]=r
    return rows_by_key


def _playoff_peak_population():
    """Build the canonical playoff 5-Year Peak population once and cache it.

    Selection rule is locked by the project specification:
    - exactly five consecutive playoff appearances;
    - every appearance >= 3 games and >= 75 minutes;
    - five appearances total >= 35 games;
    - player-profile window is selected by the highest five-season average
      season-level playoff SDI;
    - all statistics are aggregated over that selected five-appearance window.

    The resulting population is used only for Peak-context percentiles.
    """
    key="__playoff_peak_population_v1__"
    if key in CACHE:
        return CACHE[key]

    precomputed=_load_precomputed_playoff_peak_population()
    if precomputed is not None:
        CACHE[key]=precomputed
        return precomputed

    source=load_playoff_46_season()
    if source.empty:
        CACHE[key]={}
        return {}

    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pidcol=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID"])
    if not pcol or not scol:
        CACHE[key]={}
        return {}

    idx_table=_playoff_season_index_table(source)
    rows=[]

    if pidcol:
        groups=source.groupby([pidcol,pcol],dropna=False,sort=False)
    else:
        groups=source.groupby([pcol],dropna=False,sort=False)

    for keyvals,g in groups:
        candidates=_playoff_five_year_peak_candidates(g)
        if not candidates:
            continue

        best=None
        for cand in candidates:
            scores=[]
            if not idx_table.empty:
                for _,r in cand.iterrows():
                    y=_season_label_any(r[scol])
                    m=idx_table.copy()
                    idx_pid=col(idx_table,["Player_ID","PlayerId","PlayerID","player_id"])
                    idx_name=col(idx_table,["Player","Player_Name","Display_Name","player_name","Name"])
                    idx_season=col(idx_table,["Season","season","Season_ID"])
                    if idx_pid and pidcol:
                        target=str(r[pidcol]).strip()
                        m=m.loc[m[idx_pid].astype(str).str.strip().eq(target)]
                    elif idx_name:
                        target=str(r[pcol]).replace("*","").strip().casefold()
                        m=m.loc[m[idx_name].astype(str).str.replace("*","",regex=False).str.strip().str.casefold().eq(target)]
                    if idx_season:
                        m=m.loc[m[idx_season].map(_season_label_any).eq(y)]
                    if not m.empty and "SDI" in m.columns and pd.notna(m.iloc[0]["SDI"]):
                        scores.append(float(m.iloc[0]["SDI"]))
            score=float(np.mean(scores)) if len(scores)==5 else 0.0

            if best is None or score > best["sdi"]:
                best={"sdi":score,"rows":cand.copy(),"years":cand["__year"].astype(int).tolist()}

        if best is None:
            continue

        cand=best["rows"]
        stats={}
        for stat in PLAYOFF_STATS:
            sc=_playoff_source_column(cand,stat)
            stats[stat]=clean(
                _era_average_statistic(
                    cand,stat,ERA_AVERAGE_PER75_REGULAR,
                    ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS
                )
            ) if sc else None

        pid_value=clean(cand.iloc[0][pidcol]) if pidcol else None
        player_value=clean(cand.iloc[0][pcol])
        rows.append({
            "player_id":pid_value,
            "player_name":player_value,
            "start":min(best["years"]),
            "end":max(best["years"]),
            "seasons":[_season_label_any(y) for y in best["years"]],
            "era":_playoff_era(min(best["years"])),
            "sdi":float(best["sdi"]),
            "statistics":stats,
        })

    # Percentile population: higher is better for every peak statistic except
    # the established lower-is-better defensive/turnover/foul metrics.
    result={}
    for row in rows:
        result[(str(row["player_id"]).strip(), str(row["player_name"]).replace("*","").strip().casefold())]=row

    for stat in PLAYOFF_STATS:
        vals=[r["statistics"].get(stat) for r in rows if r["statistics"].get(stat) is not None]
        if not vals:
            continue
        s=pd.Series(vals,dtype="float64")
        lower=stat in PLAYOFF_LOWER_IS_BETTER
        ranks=s.rank(method="average",ascending=lower)
        pct_values=(100.0 if len(s)==1 else 100.0*(len(s)-ranks)/(len(s)-1)).tolist()
        j=0
        for r in rows:
            if r["statistics"].get(stat) is not None:
                r.setdefault("percentiles",{})[stat]=float(pct_values[j])
                j+=1

    # SDI percentile is also a Peak-context percentile.
    s=pd.Series([r["sdi"] for r in rows],dtype="float64")
    ranks=s.rank(method="average",ascending=False)
    sdi_pcts=(100.0 if len(s)==1 else 100.0*(len(s)-ranks)/(len(s)-1)).tolist()
    for i,r in enumerate(rows):
        r["sdi_percentile"]=float(sdi_pcts[i])

    CACHE[key]=result
    return result

def _canonical_playoff_five_year_peak_profile(requested_pid=None, requested_name=None):
    population=_playoff_peak_population()
    if not population:
        return {"found":False,"available":False}

    wanted_id=str(requested_pid).strip() if requested_pid is not None else ""
    wanted_name=str(requested_name or "").replace("*","").strip().casefold()
    hit=None
    for row in population.values():
        if wanted_id and str(row.get("player_id","")).strip()==wanted_id:
            hit=row
            break
    if hit is None and wanted_name:
        for row in population.values():
            if str(row.get("player_name","")).replace("*","").strip().casefold()==wanted_name:
                hit=row
                break

    if hit is None:
        return {"found":False,"available":False}

    stat_values=dict(hit.get("statistics",{}) or {})
    # V75: expose the canonical cached Peak percentile values explicitly.
    # The frontend must not infer Peak percentiles from raw values.
    cached_percentiles=dict(hit.get("percentiles",{}) or {})
    percentiles=[]
    for stat in PLAYOFF_STATS:
        if stat not in stat_values:
            continue
        value=stat_values.get(stat)
        pct=cached_percentiles.get(stat)
        percentiles.append({
            "Statistic":stat,
            "Value":value,
            "Peak_Value":value,
            "Peak_Percentile":pct,
            "Percentile":pct,
        })
    percentiles.append({
        "Statistic":"SDI",
        "Value":hit.get("sdi"),
        "Peak_Value":hit.get("sdi"),
        "Peak_Percentile":hit.get("sdi_percentile"),
        "Percentile":hit.get("sdi_percentile"),
    })

    row={
        "Player_ID":hit.get("player_id"),
        "Player":hit.get("player_name"),
        "Season":"5-Year Peak",
        "Peak_Start_Year":hit.get("start"),
        "Peak_End_Year":hit.get("end"),
        "Peak_Seasons":hit.get("seasons",[]),
        "Peak_Era":hit.get("era"),
        "Peak_SDI":hit.get("sdi"),
        "Peak_SDI_Percentile":hit.get("sdi_percentile"),
    }
    row.update(stat_values)

    return {
        "found":True,
        "available":True,
        "playoff_available":True,
        "player":{"player_id":hit.get("player_id"),"player_name":hit.get("player_name")},
        "profile":row,
        "statistic_values":stat_values,
        "playoff_statistics":stat_values,
        "percentiles":percentiles,
        "peak_percentiles":cached_percentiles,
        "seasons":["5-Year Peak"],
        "season":"5-Year Peak",
        "season_type":"Playoffs",
        "is_five_year_peak":True,
        "peak":{
            "start":hit.get("start"),
            "end":hit.get("end"),
            "seasons":hit.get("seasons",[]),
            "era":hit.get("era"),
            "sdi":hit.get("sdi"),
            "sdi_percentile":hit.get("sdi_percentile"),
        },
        "source":"canonical_playoff_peak_population_v1",
        "peak_spider": _playoff_peak_spider_from_profile({
            "found": True,
            "available": True,
            "player": {"player_id": hit.get("player_id"), "player_name": hit.get("player_name")},
            "peak": {
                "sdi": hit.get("sdi"),
                "sdi_percentile": hit.get("sdi_percentile"),
            },
            "percentiles": percentiles,
        }),
    }


def _load_precomputed_regular_peak_profile(requested_pid=None, requested_name=None):
    """Read one precomputed regular-season 5-Year Peak profile.

    This is intentionally a read-only fast path. The expensive peak/window/
    percentile work is performed by build_precomputed_5_year_peaks.py.
    """
    path=ROOT / "data" / "precomputed_5_year_peak" / "regular_profile_peaks_v2.json"
    if not path.exists():
        return None
    try:
        cache_key="__precomputed_regular_peak_profiles_v2__"
        if cache_key in CACHE:
            payload=CACHE[cache_key]
        else:
            payload=json.loads(path.read_text(encoding="utf-8"))
            CACHE[cache_key]=payload
        players=payload.get("players",[])
        wanted_id=str(requested_pid).strip() if requested_pid is not None else ""
        wanted_name=str(requested_name or "").replace("*","").strip().casefold()
        hit=None
        if wanted_id:
            for p in players:
                if str(p.get("player_id","")).strip()==wanted_id:
                    hit=p; break
        if hit is None and wanted_name:
            for p in players:
                if str(p.get("player_name","")).replace("*","").strip().casefold()==wanted_name:
                    hit=p; break
        if hit is None:
            return None

        stats=hit.get("statistics",{}) or {}
        statistic_values={}
        percentiles=[]
        for key,value in stats.items():
            if key.endswith("__percentile"):
                continue
            statistic_values[key]=clean(value)
            percentiles.append({
                "Statistic":key,
                "Value":clean(value),
                "Peak_Value":clean(value),
                "Peak_Percentile":clean(stats.get(f"{key}__percentile")),
            })

        row={
            "Player_ID":hit.get("player_id"),
            "Player":hit.get("player_name"),
            "Season":"5-Year Peak",
            "Peak_Start_Year":hit.get("peak_start_year"),
            "Peak_End_Year":hit.get("peak_end_year"),
            "Peak_Seasons":hit.get("peak_seasons",[]),
            "Peak_Era":hit.get("peak_era"),
            "Peak_SDI":hit.get("peak_sdi"),
        }
        row.update(statistic_values)

        return {
            "found":True,
            "available":True,
            "player":{"player_id":hit.get("player_id"),"player_name":hit.get("player_name")},
            "profile":row,
            "statistic_values":statistic_values,
            "percentiles":percentiles,
            "seasons":["5-Year Peak"],
            "season":"5-Year Peak",
            "season_type":"Regular Season",
            "is_five_year_peak":True,
            "peak":{
                "start":hit.get("peak_start_year"),
                "end":hit.get("peak_end_year"),
                "seasons":hit.get("peak_seasons",[]),
                "era":hit.get("peak_era"),
                "sdi":hit.get("peak_sdi"),
            },
            "source":"precomputed_5_year_peak",
        }
    except Exception as e:
        return {"found":False,"available":False,"error":f"Precomputed peak dataset could not be read: {e}"}


def _profile_data_identity(requested_pid, requested_name):
    """Return (public_pid, data_pid) for profile-backed source tables."""
    public_pid=str(requested_pid).strip() if requested_pid is not None else None
    name_key=re.sub(r"[^a-z0-9]+"," ",str(requested_name or "").replace("*",""),
                    flags=re.I).strip().casefold()

    # Prefer the requested canonical ID when it has actual master rows.
    master=load_master_seasons()
    mpid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    mname=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    if mpid and not master.empty and public_pid:
        if master[mpid].astype(str).str.strip().eq(public_pid).any():
            return public_pid, public_pid

    # If the canonical ID is a source alias without usable rows, select the
    # strongest same-name ID from the authoritative master.
    candidates=[]
    if mpid and mname and not master.empty:
        mm=master.copy()
        mm["__pid"]=mm[mpid].astype(str).str.strip()
        mm["__nk"]=(mm[mname].astype(str).str.replace(r"\*+","",regex=True)
                    .str.replace(r"[^a-z0-9]+"," ",regex=True)
                    .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
        mm=mm.loc[mm["__nk"].eq(name_key)]
        if not mm.empty:
            candidates=mm.groupby("__pid").size().sort_values(ascending=False).index.tolist()

    # Profile source can be richer than master; use it if needed.
    profiles=load("profiles",["player_season_profiles","season_profiles"])
    ppid=col(profiles,["Player_ID","PlayerId","PlayerID","player_id"])
    pname=col(profiles,["Player","Player_Name","Display_Name","player_name","Name"])
    if ppid and not profiles.empty:
        if public_pid and profiles[ppid].astype(str).str.strip().eq(public_pid).any():
            return public_pid, public_pid
        if pname:
            pp=profiles.copy()
            pp["__pid"]=pp[ppid].astype(str).str.strip()
            pp["__nk"]=(pp[pname].astype(str).str.replace(r"\*+","",regex=True)
                        .str.replace(r"[^a-z0-9]+"," ",regex=True)
                        .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
            counts=pp.loc[pp["__nk"].eq(name_key)].groupby("__pid").size().sort_values(ascending=False)
            for candidate in counts.index.tolist():
                if candidate not in candidates:
                    candidates.append(candidate)

    return public_pid, (candidates[0] if candidates else public_pid)


# ---------------------------------------------------------------------------
# v21 — LOCKED PLAYER-PROFILE SDI SEASON CACHES
# ---------------------------------------------------------------------------
# These caches are intentionally isolated from the legacy canonical SDI CSV.
# Player Profile season SDI must be derived from the current percentile layer
# and the locked profile specification.  No UI/data-source paths are changed.

_V21_SDI_CATEGORY_ORDER = [
    "Scoring Volume",
    "Scoring Efficiency",
    "Creation & Playmaking",
    "Rebounding",
    "Defense",
    "Impact & Value",
]
_V21_PLAYOFF_SDI_CATEGORIES = [
    "Scoring Volume",
    "Scoring Efficiency",
    "Creation & Playmaking",
    "Rebounding",
]


def _v21_stat_percentile_column(df, context="Season"):
    return percentile_column(df, context)


def _v21_rank_by_season(values, lower_is_better=False):
    """Rank already-directional composite values within each season."""
    out=pd.Series(np.nan,index=values.index,dtype=float)
    work=pd.to_numeric(values,errors="coerce")
    for season,g in work.groupby(values.index if False else work.index):
        pass
    return out


def _v21_load_aggregation_spec():
    """Load the authoritative player subcategory specification."""
    try:
        spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
        if spec is not None and not spec.empty:
            return spec
    except Exception:
        pass
    return pd.DataFrame()


def _v21_percentile_rank_series(s, ascending=False):
    s=pd.to_numeric(s,errors="coerce")
    valid=s.notna()
    out=pd.Series(np.nan,index=s.index,dtype=float)
    n=int(valid.sum())
    if n==0:
        return out
    if n==1:
        out.loc[valid]=100.0
        return out
    ranks=s.loc[valid].rank(method="average",ascending=ascending)
    out.loc[valid]=100.0*(n-ranks)/(n-1)
    return out


def _v21_build_category_scores(long, season_col, player_cols, pct_col, categories,
                               playoff=False):
    """Build player-season category composites from authoritative percentile rows.

    For v21, Scoring Efficiency is explicitly locked to:
      65% rTS + 35% component efficiency;
      component = 50% 2P%, 40% 3P%, 10% FT%.

    Other categories use the current authoritative subcategory specification.
    Playoffs use only the four retained categories and remove any WOWY Offense
    group before proportionally renormalizing the remaining Creation groups.
    """
    if long is None or long.empty or not pct_col or not season_col:
        return pd.DataFrame()

    spec=_v21_load_aggregation_spec()
    if spec.empty:
        return pd.DataFrame()

    sc=choose_col(spec,["Category"])
    sg=choose_col(spec,["Group_ID","Group","Group_Id"])
    ss=choose_col(spec,["Statistic","Stat"])
    sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    gw=choose_col(spec,["Group_Weight"])
    if not all([sc,sg,ss,sw,gw]):
        return pd.DataFrame()

    statc=choose_col(long,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not statc:
        return pd.DataFrame()

    base=[c for c in player_cols if c and c in long.columns]
    if not base:
        return pd.DataFrame()

    d=long[base+[season_col,statc,pct_col]].copy()
    d["__stat"]=d[statc].astype(str).str.strip()
    d["__season"]=d[season_col].map(_season_end_year)
    d["__pct"]=pd.to_numeric(d[pct_col],errors="coerce")
    d=d.dropna(subset=["__season","__pct"]).copy()
    d["__season"]=d["__season"].astype(int)
    d=d.drop_duplicates(base+["__season","__stat"],keep="first")

    w=spec.copy()
    w["__category"]=w[sc].astype(str).str.strip()
    w["__group"]=w[sg].astype(str).str.strip()
    w["__stat"]=w[ss].astype(str).str.strip()
    w["__sw"]=pd.to_numeric(w[sw],errors="coerce")
    w["__gw"]=pd.to_numeric(w[gw],errors="coerce")
    w=w.dropna(subset=["__sw","__gw"])
    w=w.loc[w["__category"].isin(categories)].copy()

    if playoff:
        # The locked playoff construction removes WOWY Offense from Creation.
        w=w.loc[~w["__group"].str.casefold().str.contains("wowy offense",na=False)].copy()
        # Re-normalize Creation group weights after the removal.
        for category in categories:
            m=w["__category"].eq(category)
            if not m.any():
                continue
            total=w.loc[m,"__gw"].drop_duplicates().sum()
            if total>0:
                # Group weights may be repeated once per statistic. Use the
                # first weight per group and normalize at aggregation time.
                pass

    # The authoritative CSV may contain duplicate rows for a statistic across
    # versions. Keep one specification row per category/group/statistic.
    w=w.drop_duplicates(["__category","__group","__stat"],keep="first")
    d=d.merge(w[["__category","__group","__stat","__sw","__gw"]],on="__stat",how="inner")
    if d.empty:
        return pd.DataFrame()

    # v21 locked Scoring Efficiency. This intentionally bypasses any legacy
    # SDI_scoring_efficiency field and any stale efficiency weights in the CSV.
    if "Scoring Efficiency" in categories:
        eff_stats={"rTS","2P_pct","3P_pct","FT_pct"}
        eff=d.loc[d["__stat"].isin(eff_stats)].copy()
        if not eff.empty:
            # A statistic is a percentile value already direction-corrected.
            piv=(eff.pivot_table(index=base+["__season"],columns="__stat",
                                 values="__pct",aggfunc="first")
                   .reset_index())
            required=["rTS","2P_pct","3P_pct","FT_pct"]
            if all(x in piv.columns for x in required):
                piv["__category_score__eff"]=(
                    0.65*piv["rTS"]+
                    0.35*(0.50*piv["2P_pct"]+0.40*piv["3P_pct"]+0.10*piv["FT_pct"])
                )
                eff_out=piv[base+["__season","__category_score__eff"]].copy()
                eff_out["__category"]="Scoring Efficiency"
            else:
                eff_out=pd.DataFrame()
        else:
            eff_out=pd.DataFrame()
    else:
        eff_out=pd.DataFrame()

    # Remove Efficiency from generic aggregation because v21 has its own
    # locked formula above.
    generic=d.loc[d["__category"].ne("Scoring Efficiency")].copy()
    pieces=[]
    if not generic.empty:
        generic["__num"]=generic["__pct"]*generic["__sw"]
        # Subcategory score.
        g=(generic.groupby(base+["__season","__category","__group"],sort=False,dropna=False)
             .agg(__num=("__num","sum"),__sw=("__sw","sum"),__gw=("__gw","first"))
             .reset_index())
        g["__group_score"]=g["__num"]/g["__sw"].replace(0,np.nan)
        # Category score. For playoff Creation, the removed WOWY group simply
        # disappears and the remaining group weights are normalized by sum.
        c=(g.groupby(base+["__season","__category"],sort=False,dropna=False)
             .apply(lambda x: np.average(x["__group_score"],weights=x["__gw"])
                    if x["__gw"].sum()>0 else np.nan)
             .reset_index(name="__category_score"))
        pieces.append(c)

    if not eff_out.empty:
        pieces.append(eff_out.rename(columns={"__category_score__eff":"__category_score"})[
            base+["__season","__category","__category_score"]
        ])

    if not pieces:
        return pd.DataFrame()
    out=pd.concat(pieces,ignore_index=True)
    return out


def _v21_build_profile_sdi_cache(playoff=False):
    key="__v21_playoff_profile_sdi__" if playoff else "__v21_regular_profile_sdi__"
    if key in CACHE:
        return CACHE[key]

    try:
        if playoff:
            source=load_playoff_46_season()
            long=load_playoff_percentile_long(False)
        else:
            long=load("percentiles",["player_season_percentiles_long"])
            source=None
        if long is None or long.empty:
            CACHE[key]=pd.DataFrame()
            return CACHE[key]

        ic=identity_cols(long)
        pid=ic.get("id")
        pname=ic.get("player")
        season_col=ic.get("season") or choose_col(long,["Season","season","Season_ID"])
        pct_col=_v21_stat_percentile_column(long,"Season")
        if not season_col or not pct_col or (not pid and not pname):
            CACHE[key]=pd.DataFrame()
            return CACHE[key]

        player_cols=[x for x in [pid,pname] if x]
        cats=_V21_PLAYOFF_SDI_CATEGORIES if playoff else _V21_SDI_CATEGORY_ORDER
        scores=_v21_build_category_scores(
            long,season_col,player_cols,pct_col,cats,playoff=playoff
        )
        if scores.empty:
            CACHE[key]=pd.DataFrame()
            return CACHE[key]

        # Canonical player identity fields.
        if pid:
            scores["Player_ID"]=scores[pid].astype(str).str.strip()
        else:
            scores["Player_ID"]=None
        if pname:
            scores["Player"]=scores[pname].astype(str).str.replace(r"\*+","",regex=True).str.strip()
        else:
            scores["Player"]=""

        # Category percentile is ranked against the PLAYER-SEASON population
        # for that exact season, not against a legacy all-time SDI population.
        scores["Category_Percentile"]=np.nan
        for category,g in scores.groupby("__category",sort=False):
            scores.loc[g.index,"Category_Percentile"]=(
                g.groupby("__season")["__category_score"]
                 .transform(lambda s:_v21_percentile_rank_series(s,ascending=False))
            )

        scores["Season"]=scores["__season"].map(_season_label_any)
        out=scores[["Player_ID","Player","Season","__season","__category",
                    "__category_score","Category_Percentile"]].copy()
        out=out.rename(columns={"__category":"Category","__category_score":"Category_Score"})
        out["Category_Score"]=pd.to_numeric(out["Category_Score"],errors="coerce")
        out["Category_Percentile"]=pd.to_numeric(out["Category_Percentile"],errors="coerce")
        CACHE[key]=out
        return out
    except Exception as e:
        print(("Playoff" if playoff else "Regular")+" individual-season SDI cache build failed:",repr(e))
        CACHE[key]=pd.DataFrame()
        return CACHE[key]


def _v21_profile_sdi_for_player(pid=None,pname=None,season=None,playoff=False):
    cache=_v21_build_profile_sdi_cache(playoff=playoff)
    if cache is None or cache.empty:
        return {}
    m=cache.copy()
    if pid is not None:
        mm=m.loc[m["Player_ID"].astype(str).str.strip().eq(str(pid).strip())].copy()
    else:
        mm=pd.DataFrame()
    if mm.empty and pname:
        key=str(pname).replace("*","").strip().casefold()
        mm=m.loc[m["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(key)].copy()
    if season and str(season).casefold()!="career":
        requested=_season_label_any(season)
        mm=mm.loc[mm["Season"].map(_season_label_any).eq(str(requested))].copy()
    result={}
    for _,r in mm.iterrows():
        result[str(r["Category"])]= {
            "score":clean(r["Category_Score"]),
            "percentile":clean(r["Category_Percentile"]),
        }
    return result

def api_profile(requested, season, season_type="Regular Season"):
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
            pid,pname=resolve_player_identity(requested)
            return _canonical_playoff_five_year_peak_profile(pid,pname)
        return api_playoff_profile(requested, season)
    if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        pid,pname=resolve_player_identity(requested)

        # V67: profiles read the precomputed dataset first. No league-wide or
        # player-level peak calculation occurs during the request.
        precomputed=_load_precomputed_regular_peak_profile(pid,pname)
        if precomputed is not None:
            return precomputed

        try:
            return _canonical_five_year_peak_profile(pid,pname)
        except Exception as e:
            # Do not let one malformed historical row take down the profile.
            # Fall back to a direct player-season peak calculation.
            try:
                master=load_master_seasons()
                pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
                pidcol=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
                scol=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
                if pcol and scol:
                    work=master.copy()
                    stc=col(work,["Season_Type","SeasonType","season_type","Phase"])
                    if stc:
                        work=work.loc[work[stc].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
                    if pidcol and pid is not None:
                        work=work.loc[work[pidcol].astype(str).str.strip().eq(str(pid).strip())].copy()
                    elif pname:
                        work=work.loc[work[pcol].astype(str).str.replace("*","",regex=False).str.strip().str.casefold().eq(str(pname).replace("*","").strip().casefold())].copy()
                    qids,qnames=_regular_qualified_season_keys(master)
                    cands=_five_year_peak_candidates(work,qids,qnames)
                    if cands:
                        # Deterministic fallback: latest valid window. The normal
                        # canonical path remains SDI-selected when available.
                        cand=cands[-1]
                        row={"Player_ID":str(pid or ""), "Player":str(pname or ""),
                             "Season":"5-Year Peak",
                             "Peak_Start_Year":int(cand["__season_year"].min()),
                             "Peak_End_Year":int(cand["__season_year"].max()),
                             "Peak_Seasons":[_season_label_any(y) for y in cand["__season_year"].tolist()],
                             "Peak_Era":_era_key(int(cand["__season_year"].min()))}
                        stats=[x for x in REGULAR_STATS if x in cand.columns]
                        for stat in stats:
                            row[stat]=clean(_era_average_statistic(cand,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS))
                        return {"found":True,"available":True,
                                "player":{"player_id":pid,"player_name":pname},
                                "profile":row,"statistic_values":{k:row.get(k) for k in stats},
                                "percentiles":[],"seasons":["5-Year Peak"],
                                "season":"5-Year Peak","season_type":"Regular Season",
                                "is_five_year_peak":True,
                                "peak":{"start":row["Peak_Start_Year"],"end":row["Peak_End_Year"],
                                        "seasons":row["Peak_Seasons"],"era":row["Peak_Era"]},
                                "note":"Fallback peak window used because the canonical SDI population could not be loaded."}
            except Exception:
                pass
            return {"found":False,"available":False,"error":"Unable to compute 5-Year Peak for this player."}

    pid,pname=resolve_player_identity(requested)
    public_pid,data_pid=_profile_data_identity(pid,pname)
    # Profile routes should operate on a canonical ID. Ambiguous name-only
    # requests are not allowed to silently select one of multiple people.
    if pid is None and requested and str(requested).strip().casefold() != str(pname).strip().casefold():
        return {"found":False,"available":False,"error":"Player identity could not be resolved uniquely."}

    playoff_source, playoff_source_path = load_playoff_source()

    profiles = load("profiles", ["player_season_profiles", "season_profiles"])
    pm = filter_player(profiles, data_pid) if pid is not None else pd.DataFrame()
    if pm.empty and pname:
        pm = filter_player(profiles, pname)
    pc = identity_cols(profiles)

    # FULL PLAYER-SEASON UNIVERSE: the authoritative master controls the
    # regular-season season list. Percentile qualification never removes a
    # season. If the canonical ID is a source alias, retry the master by name
    # so a profile cannot silently collapse to the smaller qualified profile
    # table.
    master=load_master_seasons()
    mm=filter_player(master, data_pid) if (not master.empty and pid is not None) else pd.DataFrame()
    if mm.empty and not master.empty and pname:
        mm=filter_player(master,pname)
    mc=identity_cols(master) if not master.empty else {}

    is_playoffs = str(season_type).casefold() in {"playoffs","playoff","postseason"}

    if is_playoffs and not playoff_source.empty:
        # Playoff source is filtered to THIS PLAYER before both the season
        # selector and the selected-season row are built. This prevents the
        # profile from exposing league-wide seasons or accidentally returning
        # another player's first row.
        psc=col(playoff_source,["Season","season","Season_ID"])
        player_rows=_playoff_player_match(playoff_source,pid,pname)
        season_source=player_rows
        sc=psc
        seasons=sorted(
            {_season_label_any(x) for x in player_rows[psc].dropna().astype(str).tolist()},
            key=lambda x:_season_end_year(x) or 0
        ) if psc and not player_rows.empty else []
    else:
        # Use the full master season universe whenever available. Only fall
        # back to player_season_profiles when the master truly has no rows.
        season_source=mm if not mm.empty else pm
        sc=mc.get("season") if mc else pc["season"]
        seasons=sorted(
            {_season_label_any(x) for x in season_source[sc].dropna().astype(str).tolist()},
            key=lambda x:_season_end_year(x) or 0
        ) if sc and not season_source.empty else []

    requested_view = normalize_requested_season(season) if season else (seasons[-1] if seasons else None)
    is_career = requested_view == "Career"

    if is_career:
        current=season_source.copy()
        chosen="Career"
    else:
        chosen=requested_view
        # Match by canonical season label rather than raw source formatting
        # (e.g. 2021, 2021-22, or 2021/22 all resolve to the same season).
        if sc and chosen and not season_source.empty:
            current=season_source.loc[
                season_source[sc].map(_season_label_any).eq(str(chosen))
            ].copy()
        else:
            current=season_source.head(0)

        if is_playoffs:
            # player_rows above is already restricted to the requested player.
            current=season_source.loc[
                season_source[sc].map(_season_label_any).eq(str(chosen))
            ].copy() if sc and chosen and not season_source.empty else season_source.head(0)
        else:
            # Prefer the enriched regular-season profile row for qualified
            # seasons, but retain the master row for valid unqualified seasons.
            if chosen and pc["season"] and not pm.empty:
                enriched=pm.loc[
                    pm[pc["season"]].map(_season_label_any).eq(str(chosen))
                ].copy()
                if not enriched.empty:
                    current=enriched

    headshot = None
    try:
        hs = load("headshots", ["headshot_registry", "headshot"])
        hm = filter_player(hs, pid if pid is not None else pname)
        if hm.empty:
            hm = filter_player(hs, pname)
        if not hm.empty:
            hc = col(hm, [
                "Verified_Headshot_URL", "Headshot_URL", "HeadshotUrl",
                "NBA_Headshot_URL", "CDN_URL", "Image_URL"
            ])
            if hc:
                headshot = clean(hm.iloc[0][hc])
    except Exception:
        pass

    profile = None
    if not current.empty:
        if is_career:
            # Career is a true aggregation, not an arithmetic mean of season
            # rows. For regular season use the canonical career table; playoff
            # profiles are handled by api_playoff_profile above.
            career_table=_build_regular_career_table()
            cm=career_table.loc[career_table["Player_ID"].astype(str).eq(str(data_pid))] if not career_table.empty and pid is not None else pd.DataFrame()
            if cm.empty and not career_table.empty:
                cm=career_table.loc[career_table["Player"].astype(str).str.casefold().eq(str(pname).casefold())]
            career={k:clean(v) for k,v in (cm.iloc[0].to_dict().items() if not cm.empty else [])}
            career["Season"]="Career"
            career["Career_Seasons_Represented"]=int(cm.shape[0]) if not cm.empty else int(len(current))
            career["Career_Qualification"]=("G >= 400 AND MP >= 10,000")
            profile=career
        else:
            if is_playoffs:
                # One canonical player-season row is expected after identity
                # integration. If an unintegrated raw source is used, preserve
                # its first row rather than silently combining identities here.
                profile={k:clean(v) for k,v in current.iloc[0].to_dict().items()}
            else:
                profile={k:clean(v) for k,v in current.iloc[0].to_dict().items()}

    # 46-stat rows: season-specific rows for a normal view. Career returns a
    # descriptive mean of the available season values; percentile columns are
    # omitted because averaging percentiles would be statistically misleading.
    percentile_rows = []
    try:
        if not is_playoffs:
            per = load("percentiles", ["player_season_percentiles_long"])
            if is_career:
                percentile_rows = _regular_career_profile_rows(
                    player_id=pid,
                    player_name=pname,
                )
            else:
                per_match = filter_player(per, pid if pid is not None else pname)
                if per_match.empty:
                    per_match = filter_player(per, pname)
                per_c = identity_cols(per)
                if per_c["season"] and chosen:
                    per_match = per_match.loc[
                        per_match[per_c["season"]].astype(str).eq(chosen)
                    ]
                percentile_rows = [
                    {k: clean(v) for k, v in row.items()}
                    for row in per_match.to_dict("records")
                ]
    except Exception:
        pass

    # Always expose the canonical 46-stat values from the master season row as
    # a fallback. This matters for valid but percentile-unqualified seasons
    # (for example Jordan 1985-86 and other small-sample seasons).
    statistic_values={}
    if not current.empty:
        raw=current.iloc[0]
        for stat in REGULAR_STATS:
            source_col=col(current,[stat])
            statistic_values[stat]=clean(raw[source_col]) if source_col else None

    profile_sdi = _v21_profile_sdi_for_player(
        pid=pid, pname=pname, season=chosen if not is_career else None, playoff=False
    ) if not is_career else {}

    return {
        "found": True,
        "view": chosen,
        "is_career": is_career,
        "player": {
            "player_id": pid,
            "player_name": pname,
            "headshot_url": headshot,
        },
        "seasons": seasons,
        "profile": profile,
        "statistic_values": statistic_values,
        "percentiles": percentile_rows,
        "sdi_categories": profile_sdi,
        "playoff_available": not playoff_source.empty,
        "playoff_source": str(playoff_source_path) if playoff_source_path else None,
        "playoff_statistics": (
            build_playoff_rows(
                playoff_source,
                player_id=pid,
                player_name=pname,
                season=chosen if not is_career else None,
            ) if is_playoffs else []
        ),
        "season_type": "Playoffs" if is_playoffs else "Regular Season",
        "career_note": (
            "Career view summarizes the available season-profile/statistical "
            "records. Career percentiles are not fabricated by averaging "
            "percentiles."
            if is_career else None
        ),
    }


def load_exact_csv(folder_key, filename):
    path = PATHS[folder_key] / filename
    if not path.exists():
        raise FileNotFoundError(str(path))
    key = f"{folder_key}:{filename}"
    if key not in CACHE:
        CACHE[key] = read_csv(path, low_memory=False)
    return CACHE[key]


def choose_col(df, candidates):
    return col(df, candidates)



def percentile_column(df, context):
    normalized = {
        re.sub(r"[^a-z0-9]", "", str(c).lower()): c
        for c in df.columns
    }
    aliases = {
        "Season": ["Season_Percentile", "SeasonPercentile", "Season_Pctl", "SeasonPctl"],
        "Era": ["Era_Percentile", "EraPercentile", "Era_Pctl", "EraPctl"],
        "Historical": ["Historical_Percentile", "HistoricalPercentile", "Historical_Pctl", "HistoricalPctl"],
    }
    for candidate in aliases.get(context, aliases["Historical"]):
        k=re.sub(r"[^a-z0-9]","",candidate.lower())
        if k in normalized:
            return normalized[k]
    ctx=re.sub(r"[^a-z0-9]","",context.lower())
    for k, original in normalized.items():
        if ctx in k and ("percentile" in k or "pctl" in k):
            return original
    return None


def _playoff_spider_from_percentiles(pm, pid, pname, season, context, stats):
    if pm.empty:
        return {"found":True,"player":{"player_id":pid,"player_name":pname},
                "season":season,"context":context,"available_contexts":{},
                "category_axes":[],"stat_axes":[]}

    stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not stat_col:
        return {"found":True,"player":{"player_id":pid,"player_name":pname},
                "season":season,"context":context,"available_contexts":{},
                "category_axes":[],"stat_axes":[]}

    pct_col = "Career_Percentile" if context=="Career" else percentile_column(pm,context)
    if pct_col is None:
        return {"found":True,"player":{"player_id":pid,"player_name":pname},
                "season":season,"context":context,"available_contexts":{},
                "category_axes":[],"stat_axes":[]}

    pm=pm.copy()
    pm["_stat_key"]=pm[stat_col].astype(str).str.strip()
    pm[pct_col]=pd.to_numeric(pm[pct_col],errors="coerce")
    vals=(pm.dropna(subset=[pct_col]).drop_duplicates("_stat_key")
          .set_index("_stat_key")[pct_col].to_dict())

    spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
    cat=choose_col(spec,["Category"]); grp=choose_col(spec,["Group_ID","Group","Group_Id"])
    st=choose_col(spec,["Statistic","Stat"])
    sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    gw=choose_col(spec,["Group_Weight"])
    axes=[]
    dominance_categories={
        "Scoring Volume","Scoring Efficiency","Creation & Playmaking",
        "Rebounding","Defense","Impact & Value"
    }
    if all([cat,grp,st,sw,gw]):
        w=spec.loc[spec[cat].astype(str).str.strip().isin(dominance_categories)].copy()
        w["_stat_key"]=w[st].astype(str).str.strip()
        w["_sv"]=w["_stat_key"].map(vals)
        w["_sw"]=pd.to_numeric(w[sw],errors="coerce")
        w["_gw"]=pd.to_numeric(w[gw],errors="coerce")
        w=w.dropna(subset=["_sv","_sw","_gw"])
        groups=[]
        for (category,group),g in w.groupby([cat,grp],sort=False):
            den=g["_sw"].sum()
            if den:
                groups.append((str(category),str(group),
                               float((g["_sv"]*g["_sw"]).sum()/den),
                               float(g["_gw"].iloc[0])))
        for category in list(dict.fromkeys(x[0] for x in groups)):
            gs=[x for x in groups if x[0]==category]
            den=sum(x[3] for x in gs)
            axes.append({"axis":category,
                         "value":float(sum(x[2]*x[3] for x in gs)/den) if den else None})

    requested=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
    stat_axes=[{"axis":s,"value":vals.get(s)} for s in requested]
    return {"found":True,"player":{"player_id":pid,"player_name":pname},
            "season":season,"context":context,
            "available_contexts":{"Season":context=="Season","Era":context=="Era",
                                  "Historical":context=="Historical","Career":context=="Career"},
            "category_axes":axes,"stat_axes":stat_axes}

def _playoff_peak_spider_from_profile(peak, stats=None):
    if not peak.get("found") or not peak.get("available"):
        return {
            "found": True,
            "season": "5-Year Peak",
            "context": "Peak",
            "available_contexts": {"Peak": False},
            "category_axes": [],
            "stat_axes": [],
        }

    rows=peak.get("percentiles",[]) or []
    vals={}
    for row in rows:
        stat=str(row.get("Statistic") or row.get("statistic") or "").strip()
        pct=row.get("Peak_Percentile", row.get("Percentile"))
        if stat and pct is not None:
            try:
                vals[stat]=float(pct)
            except Exception:
                pass

    stat_names=stats or PLAYOFF_STATS
    stat_axes=[{"axis":stat,"value":vals.get(stat)} for stat in stat_names if vals.get(stat) is not None]

    # Use the canonical aggregation specification for the six dominance axes.
    spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
    scat=choose_col(spec,["Category"])
    sgrp=choose_col(spec,["Group_ID","Group","Group_Id"])
    sstat=choose_col(spec,["Statistic","Stat"])
    ssw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    sgw=choose_col(spec,["Group_Weight"])

    allowed=[
        "Scoring Volume","Scoring Efficiency","Creation & Playmaking",
        "Rebounding","Defense","Impact & Value"
    ]
    category_axes=[]
    if all([scat,sgrp,sstat,ssw,sgw]):
        w=spec.copy()
        w=w.loc[w[scat].astype(str).str.strip().isin(allowed)].copy()
        w["_stat_key"]=w[sstat].astype(str).str.strip()
        w["_sw"]=pd.to_numeric(w[ssw],errors="coerce")
        w["_gw"]=pd.to_numeric(w[sgw],errors="coerce")
        w=w.dropna(subset=["_sw","_gw"])
        for category in allowed:
            cg=w.loc[w[scat].astype(str).str.strip().eq(category)]
            group_scores=[]
            for group,g in cg.groupby(sgrp,sort=False):
                usable=g.loc[g["_stat_key"].isin(vals)].copy()
                if usable.empty:
                    continue
                sw=usable["_sw"].to_numpy(dtype=float)
                scores=[vals[s] for s in usable["_stat_key"].astype(str)]
                within=float(np.average(scores,weights=sw)) if sw.sum()>0 else float(np.mean(scores))
                gw=float(usable["_gw"].iloc[0])
                group_scores.append((within,gw))
            if group_scores:
                total=sum(gw for _,gw in group_scores)
                value=sum(score*gw for score,gw in group_scores)/total if total>0 else float(np.mean([x[0] for x in group_scores]))
                category_axes.append({"axis":category,"value":float(value)})

    return {
        "found":True,
        "player":peak.get("player"),
        "season":"5-Year Peak",
        "context":"Peak",
        "available_contexts":{"Season":False,"Era":False,"Historical":False,"Career":False,"Peak":True},
        "category_axes":category_axes,
        "stat_axes":stat_axes,
        "peak_sdi":peak.get("peak",{}).get("sdi"),
        "peak_sdi_percentile":peak.get("peak",{}).get("sdi_percentile"),
    }

def api_playoff_spider(requested,season=None,context="Historical",stats=None):
    pid,pname=resolve_player_identity(requested)
    if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        return _playoff_peak_spider_from_profile(_canonical_playoff_five_year_peak_profile(pid,pname), stats)
    if pid is None and not pname: return {"found":False}

    context="Career" if str(season).casefold()=="career" else (
        context if context in {"Season","Era","Historical"} else "Historical"
    )
    pm=_load_final_playoff_percentile_long(context=="Career")
    if pm.empty:
        pm=load_playoff_percentile_long(context=="Career")
    pm=_playoff_player_match(pm,pid,pname)
    if context!="Career":
        cs=col(pm,["Season","season","Season_ID"])
        if cs and season:
            requested=normalize_requested_season(season)
            pm=pm.loc[pm[cs].map(_season_label_any).eq(str(requested))].copy()
    if context == "Season" and str(season).strip():
        cached=_v21_profile_sdi_for_player(
            pid=pid, pname=pname, season=season, playoff=True
        )
        if cached:
            vals={}
            if not pm.empty:
                sc=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
                pc=percentile_column(pm,"Season")
                if sc and pc:
                    vals=(pm.assign(__s=pm[sc].astype(str).str.strip())
                          .dropna(subset=[pc]).drop_duplicates("__s")
                          .set_index("__s")[pc].to_dict())
            axes=[{"axis":k,"value":v.get("percentile"),
                   "score":v.get("score")} for k,v in cached.items()]
            requested_stats=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
            stat_axes=[{"axis":st,"value":vals.get(st)} for st in requested_stats]
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":season,"context":context,"available_contexts":available,
                    "category_axes":axes,"stat_axes":stat_axes,
                    "sdi_categories":cached}
    return _playoff_spider_from_percentiles(pm,pid,pname,season,context,stats)

def api_spider(requested, season=None, context="Historical", stats=None, season_type="Regular Season"):
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        return api_playoff_spider(requested,season,context,stats)
    pid,pname=resolve_player_identity(requested)
    public_pid,data_pid=_profile_data_identity(pid,pname)
    if pid is None and not pname: return {"found":False}

    context=context if context in {"Season","Era","Historical","Career"} else "Historical"

    # Canonical 5-Year Peak spider: all axes use the same SDI-selected
    # five-season window and the peak-specific percentile population.
    if str(season).casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        peak=_canonical_five_year_peak_profile(pid,pname)
        if not peak.get("found") or not peak.get("available"):
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":"5-Year Peak","context":"Peak","available_contexts":{"Peak":False},
                    "category_axes":[],"stat_axes":[]}
        pm=pd.DataFrame(peak.get("percentiles",[]))
        stat_col="Statistic"
        pct="Peak_Percentile"
        available={"Season":False,"Era":False,"Historical":False,"Career":False,"Peak":True}
    # Career spider uses the canonical career percentile population directly.
    # Season percentile tables do not contain a Career row, so filtering them
    # by season="Career" necessarily produced an empty spider.
    elif str(season).casefold()=="career" or context=="Career":
        career_rows=_regular_career_profile_rows(player_id=data_pid, player_name=pname)
        if not career_rows:
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":"Career","context":"Career","available_contexts":{"Career":False},
                    "category_axes":[],"stat_axes":[]}
        pm=pd.DataFrame(career_rows)
        stat_col="Statistic"
        pct="Career_Percentile"
        available={"Season":False,"Era":False,"Historical":False,"Career":True}
    else:
        per=load("percentiles",["player_season_percentiles_long"])
        pm=filter_player(per,data_pid if data_pid is not None else pname)
        if pm.empty: pm=filter_player(per,pname)
        pc=identity_cols(per)
        if pc["season"] and season:
            pm=pm.loc[pm[pc["season"]].astype(str).eq(str(season))]
        pct=percentile_column(pm,context)
        stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
        available={c: percentile_column(pm,c) is not None for c in ("Season","Era","Historical")}
        if not pct or not stat_col:
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":season,"context":context,"available_contexts":available,
                    "category_axes":[],"stat_axes":[]}

    pm=pm.copy()
    pm["_stat_key"]=pm[stat_col].astype(str).str.strip()
    pm[pct]=pd.to_numeric(pm[pct],errors="coerce")
    vals=(pm.dropna(subset=[pct]).drop_duplicates("_stat_key")
            .set_index("_stat_key")[pct].to_dict())

    # v21: Player Profile Season SDI comes from the dedicated locked cache,
    # not from the legacy aggregation/SDI CSV path. Keep other contexts and
    # custom stat axes unchanged.
    if context == "Season" and str(season).casefold() != "career" and str(season).strip():
        cached=_v21_profile_sdi_for_player(
            pid=pid, pname=pname, season=season, playoff=False
        )
        if cached:
            axes=[{"axis":k,"value":v.get("percentile"),
                   "score":v.get("score")} for k,v in cached.items()]
            requested_stats=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
            stat_axes=[{"axis":st,"value":vals.get(st)} for st in requested_stats]
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":season,"context":context,"available_contexts":available,
                    "category_axes":axes,"stat_axes":stat_axes,
                    "sdi_categories":cached}

    spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
    cat=choose_col(spec,["Category"]); grp=choose_col(spec,["Group_ID","Group","Group_Id"])
    st=choose_col(spec,["Statistic","Stat"])
    sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    gw=choose_col(spec,["Group_Weight"])
    axes=[]
    # The Dominance spider is intentionally limited to the six Dominance
    # categories. Context categories are exposed only by the Context spider.
    dominance_categories = {
        "Scoring Volume", "Scoring Efficiency", "Creation & Playmaking",
        "Rebounding", "Defense", "Impact & Value"
    }
    if all([cat,grp,st,sw,gw]):
        w=spec.copy()
        if cat:
            w=w.loc[w[cat].astype(str).str.strip().isin(dominance_categories)].copy()
        w["_stat_key"]=w[st].astype(str).str.strip()
        w["_sv"]=w["_stat_key"].map(vals)
        w["_sw"]=pd.to_numeric(w[sw],errors="coerce")
        w["_gw"]=pd.to_numeric(w[gw],errors="coerce")
        w=w.dropna(subset=["_sv","_sw","_gw"])
        groups=[]
        for (category,group),g in w.groupby([cat,grp],sort=False):
            d=g["_sw"].sum()
            if d:
                groups.append((str(category),str(group),
                               float((g["_sv"]*g["_sw"]).sum()/d),
                               float(g["_gw"].iloc[0])))
        for category in list(dict.fromkeys(x[0] for x in groups)):
            gs=[x for x in groups if x[0]==category]
            d=sum(x[3] for x in gs)
            axes.append({"axis":category,"value":float(sum(x[2]*x[3] for x in gs)/d) if d else None})

    requested_stats=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
    stat_axes=[{"axis":st,"value":vals.get(st)} for st in requested_stats]
    return {"found":True,"player":{"player_id":pid,"player_name":pname},
            "season":season,"context":context,"available_contexts":available,
            "category_axes":axes,"stat_axes":stat_axes}


def api_playoff_context_profile(requested,season=None,context="Historical"):
    pid,pname=resolve_player_identity(requested)
    if pid is None and not pname: return {"found":False}

    is_career=str(season).casefold()=="career"
    pm=_load_final_playoff_percentile_long(is_career)
    if pm.empty:
        pm=load_playoff_percentile_long(is_career)
    pm=_playoff_player_match(pm,pid,pname)
    if not is_career:
        cs=col(pm,["Season","season","Season_ID"])
        if cs and season:
            pm=pm.loc[pm[cs].astype(str).str.strip().eq(str(season).strip())].copy()
    stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    pct_col="Career_Percentile" if is_career else percentile_column(pm,context)
    if not stat_col or not pct_col:
        return {"found":True,"available":False,"categories":[],"stat_values":{}}

    pm["_stat_key"]=pm[stat_col].astype(str).str.strip()
    pm[pct_col]=pd.to_numeric(pm[pct_col],errors="coerce")
    vals=(pm.dropna(subset=[pct_col]).drop_duplicates("_stat_key")
          .set_index("_stat_key")[pct_col].to_dict())

    taxonomy=load_exact_csv("taxonomy","player_statistic_taxonomy_v1.csv")
    tc=choose_col(taxonomy,["Statistic","Stat"])
    tcat=choose_col(taxonomy,["Category"])
    tdom=choose_col(taxonomy,["Domain"])
    if not tc or not tcat:
        return {"found":True,"available":True,"categories":[],"stat_values":vals}

    tx=taxonomy.copy()
    if tdom:
        tx=tx.loc[tx[tdom].astype(str).str.casefold().eq("context")]
    context_categories={"Offensive Role / Usage","Shot Profile","Availability / Foul Context"}
    tx=tx.loc[tx[tcat].astype(str).str.strip().isin(context_categories)]
    cats=[]
    for category,g in tx.groupby(tcat,sort=False):
        scores=[vals[s] for s in g[tc].astype(str).str.strip() if s in vals]
        if scores:
            cats.append({"axis":str(category),"value":float(sum(scores)/len(scores))})
    return {"found":True,"available":True,"context":"Career" if is_career else context,
            "categories":cats,"stat_values":vals}

def api_context_profile(requested, season=None, context="Historical", season_type="Regular Season"):
    if str(season_type).casefold() not in {"playoffs","playoff","postseason"} and str(season).casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        pid,pname=resolve_player_identity(requested)
        peak=_canonical_five_year_peak_profile(pid,pname)
        if not peak.get("found") or not peak.get("available"):
            return {"found":True,"available":False,"categories":[],"stat_values":{}}
        vals={str(r.get("Statistic")):r.get("Peak_Percentile") for r in peak.get("percentiles",[])}
        taxonomy=load_exact_csv("taxonomy","player_statistic_taxonomy_v1.csv")
        tc=choose_col(taxonomy,["Statistic","Stat"]); tcat=choose_col(taxonomy,["Category"]); tdom=choose_col(taxonomy,["Domain"])
        if not tc or not tcat:
            return {"found":True,"available":True,"context":"Peak","categories":[],"stat_values":vals}
        tx=taxonomy.copy()
        if tdom:
            tx=tx.loc[tx[tdom].astype(str).str.casefold().eq("context")]
        context_categories={"Offensive Role / Usage","Shot Profile","Availability / Foul Context"}
        tx=tx.loc[tx[tcat].astype(str).str.strip().isin(context_categories)]
        cats=[]
        for category,g in tx.groupby(tcat,sort=False):
            scores=[vals[s] for s in g[tc].astype(str).str.strip() if s in vals and vals[s] is not None]
            if scores:
                cats.append({"axis":str(category),"value":float(sum(scores)/len(scores))})
        return {"found":True,"available":True,"context":"Peak","categories":cats,"stat_values":vals}

    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        return api_playoff_context_profile(requested,season,context)
    pid,pname=resolve_player_identity(requested)
    public_pid,data_pid=_profile_data_identity(pid,pname)
    if pid is None and not pname: return {"found":False}

    per=load("percentiles",["player_season_percentiles_long"])
    pm=filter_player(per,data_pid if data_pid is not None else pname)
    if pm.empty: pm=filter_player(per,pname)
    pc=identity_cols(per)
    if pc["season"] and season and str(season)!="Career":
        pm=pm.loc[pm[pc["season"]].astype(str).eq(str(season))]
    context=context if context in {"Season","Era","Historical"} else "Historical"
    pct=percentile_column(pm,context)
    stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not pct or not stat_col:
        return {"found":True,"available":False,"categories":[]}

    taxonomy=load_exact_csv("taxonomy","player_statistic_taxonomy_v1.csv")
    tc=choose_col(taxonomy,["Statistic","Stat"])
    tcat=choose_col(taxonomy,["Category"])
    tdom=choose_col(taxonomy,["Domain"])
    if not tc or not tcat:
        return {"found":True,"available":False,"categories":[]}

    pm["_stat_key"]=pm[stat_col].astype(str).str.strip()
    pm[pct]=pd.to_numeric(pm[pct],errors="coerce")
    vals=pm.dropna(subset=[pct]).drop_duplicates("_stat_key").set_index("_stat_key")[pct].to_dict()

    context_cats=[]
    # Only taxonomy rows in Context domain belong here.
    tx=taxonomy.copy()
    if tdom:
        tx=tx.loc[tx[tdom].astype(str).str.casefold().eq("context")]
    context_categories = {
        "Offensive Role / Usage", "Shot Profile", "Availability / Foul Context"
    }
    if tcat:
        tx=tx.loc[tx[tcat].astype(str).str.strip().isin(context_categories)]
    for category,g in tx.groupby(tcat,sort=False):
        scores=[]
        for stat in g[tc].astype(str).str.strip():
            if stat in vals: scores.append(vals[stat])
        if scores:
            context_cats.append({"axis":str(category),"value":float(sum(scores)/len(scores))})
    return {"found":True,"available":True,"context":context,
            "categories":context_cats,
            "stat_values":vals}



def find_recursive_csv(root, filename_terms):
    """Find a data file once, then reuse the resolved path."""
    if not root.exists():
        return None
    cache_key="__path__::" + str(root) + "::" + "|".join(sorted(str(x).lower() for x in filename_terms))
    if cache_key in CACHE:
        return CACHE[cache_key]
    candidates=[]
    for f in root.rglob("*.csv"):
        name=f.name.lower()
        score=sum(5 for t in filename_terms if t.lower() in name)
        if score:
            candidates.append((score, len(str(f)), f))
    candidates.sort(key=lambda x:(-x[0], x[1], x[2].name))
    result=candidates[0][2] if candidates else None
    CACHE[cache_key]=result
    return result

def load_canonical_percentiles():
    f=find_recursive_csv(
        ROOT,
        ["player_season_percentiles_long_v2_1.csv",
         "player_season_percentiles_long",
         "percentiles_long"]
    )
    if not f:
        return load("percentiles", ["player_season_percentiles_long"])
    key="__canonical_percentiles__"
    if key not in CACHE:
        # The Big Board and regular percentile endpoints only need identity,
        # season/statistic, value and percentile columns. Avoid loading large
        # auxiliary columns from the long canonical table on first tab load.
        header=read_csv(f,nrows=0)
        wanted_exact={
            "Player_ID","PlayerId","PlayerID","player_id",
            "Player","Player_Name","Display_Name","Name","player_name",
            "Season","season","Season_ID","SeasonEndYear","Season_End_Year","Year",
            "Statistic","statistic","Stat","Statistic_Name","stat_name",
            "Value","value","Statistic_Value","statistic_value","Stat_Value",
            "Raw_Value","Value_Per75","Value_per75","Stat_Value_Per75",
            "Statistic_Value_Per75","Metric_Value","stat_value",
            "Season_Percentile","SeasonPercentile","Season_Pctl","SeasonPctl",
            "Percentile_Season","Pctl_Season",
            "Era_Percentile","EraPercentile","Era_Pctl","EraPctl",
            "Percentile_Era","Pctl_Era",
            "Historical_Percentile","HistoricalPercentile","Historical_Pctl",
            "HistoricalPctl","Percentile_Historical","Pctl_Historical",
            "Percentile","percentile","Pctl","pctl","Percentile_Value","percentile_value"
        }
        use=[c for c in header.columns if str(c) in wanted_exact]
        # Safety fallback: if an unexpected schema is encountered, retain the
        # old full-table behavior rather than breaking the endpoint.
        if len(use) >= 5:
            CACHE[key]=read_csv(f,usecols=use,low_memory=False)
        else:
            CACHE[key]=read_csv(f,low_memory=False)
    return CACHE[key]

def season_display_label(value):
    s=str(value).strip()
    m=re.match(r"^(\\d{4})-(\\d{2}|\\d{4})$",s)
    if m:
        start=int(m.group(1))
        end=m.group(2)
        if len(end)==4:
            return end
        end2=int(end)
        start2=start % 100
        century=start // 100
        end_year=(century*100+end2) if end2 > start2 else ((century+1)*100+end2)
        return str(end_year)
    return s



def _playoff_season_list(df):
    cs=col(df,["Season","season","Season_ID"])
    if not cs or df.empty:
        return []
    vals=df[cs].dropna().astype(str).str.strip().unique().tolist()
    return sorted(vals,key=lambda x:_season_end_year(x) or 0)


ERA_AVERAGE_REGULAR_MIN_GAMES = 250
ERA_AVERAGE_REGULAR_MIN_MINUTES = 6000
ERA_AVERAGE_PLAYOFF_MIN_GAMES = 40
ERA_AVERAGE_PLAYOFF_MIN_MINUTES = 1250
ERA_AVERAGE_PARTICIPATION = 0.40

ERA_AVERAGE_PER75_REGULAR = {s for s in PLAYOFF_STATS if s.endswith("_per75")}
ERA_AVERAGE_PER75_PLAYOFF = set(PLAYOFF_PER75_STATS)
ERA_AVERAGE_ADDITIVE = {"WS","OWS","DWS","VORP"}
ERA_AVERAGE_LOWER = {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
ERA_AVERAGE_DENOMS = {
    "FG_pct":"FGA", "2P_pct":"2PA", "3P_pct":"3PA", "FT_pct":"FTA",
    "TS_pct":"FGA", "FTr":"FGA", "3PAr":"FGA", "AST_TOV":"TOV"
}

def _era_average_statistic(rows, statistic, per75_stats, additive_stats, denom_map):
    """Aggregate a player's qualifying player-season rows across one era.

    Per-75 rates are possession-weighted, additive value statistics are summed,
    shooting/ratio statistics use their natural denominators where available,
    and remaining rate/impact statistics are minute-weighted. This avoids
    averaging season averages and preserves the weighting logic used elsewhere
    in the PER-75 project.
    """
    if rows.empty or statistic not in rows.columns:
        return np.nan
    vals=pd.to_numeric(rows[statistic],errors="coerce")
    if statistic in additive_stats:
        return float(vals.sum(min_count=1)) if vals.notna().any() else np.nan
    if statistic == "WS/48":
        ws=col(rows,["WS"]); mp=col(rows,["MP","Minutes","minutes"])
        if ws and mp:
            w=pd.to_numeric(rows[ws],errors="coerce"); m=pd.to_numeric(rows[mp],errors="coerce")
            return float(48*w.sum(min_count=1)/m.sum()) if m.notna().any() and m.sum()>0 and w.notna().any() else np.nan
    if statistic in per75_stats:
        poss=col(rows,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
        if poss:
            w=pd.to_numeric(rows[poss],errors="coerce")
        else:
            w=pd.Series(np.nan,index=rows.index)
        if w.isna().all():
            mp=col(rows,["MP","Minutes","minutes"])
            w=pd.to_numeric(rows[mp],errors="coerce")*2.0 if mp else pd.Series(np.nan,index=rows.index)
        x=pd.DataFrame({"v":vals,"w":w}).dropna(); x=x[x.w>0]
        return float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan
    if statistic in denom_map:
        den_col=denom_map[statistic]
        dc=col(rows,[den_col, den_col.replace("_raw","")])
        if dc:
            d=pd.to_numeric(rows[dc],errors="coerce")
            x=pd.DataFrame({"v":vals,"w":d}).dropna(); x=x[x.w>0]
            if not x.empty: return float((x.v*x.w).sum()/x.w.sum())
    mp=col(rows,["MP","Minutes","minutes"])
    w=pd.to_numeric(rows[mp],errors="coerce") if mp else pd.Series(np.nan,index=rows.index)
    x=pd.DataFrame({"v":vals,"w":w}).dropna(); x=x[x.w>0]
    return float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan

def _era_average_qualified_rows(source, season_type, era_key):
    """Return one aggregated era row per player after the agreed eligibility gate.

    Era-average aggregation is cached by dataset + era because the same
    population is reused for every statistic, sort direction, and search.
    """
    cache_key=f"__era_average_rows_v2__:{season_type}:{era_key}"
    if cache_key in CACHE:
        cached, meta = CACHE[cache_key]
        return cached.copy(), dict(meta)
    if source is None or source.empty or not era_key:
        return pd.DataFrame(), {"players_considered":0,"players_qualified":0}
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    gcol=col(source,["G","Games","games"])
    mpcol=col(source,["MP","Minutes","minutes"])
    if not pcol or not scol or not gcol or not mpcol:
        return pd.DataFrame(), {"players_considered":0,"players_qualified":0}
    bounds=next(((aa,bb) for k,aa,bb,_label in ERA_DEFINITIONS if k==era_key),(None,None))
    if bounds[0] is None:
        return pd.DataFrame(), {"players_considered":0,"players_qualified":0}
    # Avoid mapping _era_key over the entire master/playoff source on every new era.
    # Only rows whose season end year lies in the selected era are needed.
    years=pd.to_numeric(source[scol].map(_season_end_year),errors="coerce")
    work=source.loc[years.between(bounds[0],bounds[1],inclusive="both")].copy()
    work["__year"]=years.loc[work.index].astype("Int64")
    if season_type.casefold().startswith("regular"):
        st=col(work,["Season_Type","SeasonType","season_type","Phase"])
        if st: work=work.loc[work[st].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
    else:
        st=col(work,["Season_Type","SeasonType","season_type","Phase"])
        if st: work=work.loc[work[st].astype(str).str.strip().str.casefold().isin({"playoffs","playoff","postseason"})].copy()
    era_rows=work.copy()
    if era_rows.empty:
        return pd.DataFrame(), {"players_considered":0,"players_qualified":0}
    era_rows["__year"]=era_rows["__year"]
    work["__Gnum"]=pd.to_numeric(work[gcol],errors="coerce").fillna(0)
    work["__MPnum"]=pd.to_numeric(work[mpcol],errors="coerce").fillna(0)
    era_rows["__Gnum"]=pd.to_numeric(era_rows[gcol],errors="coerce").fillna(0)
    era_rows["__MPnum"]=pd.to_numeric(era_rows[mpcol],errors="coerce").fillna(0)
    # Use the established player-season qualification definitions for the
    # participation numerator, then apply the new era-level aggregate floor.
    if season_type.casefold().startswith("regular"):
        try:
            q=load_qualification_population()
            qp=col(q,["Player","Player_Name","Display_Name","player_name","Name"])
            qs=col(q,["Season","season","Season_ID"])
            qg=col(q,["G","Games","games"]); qm=col(q,["MP","Minutes","minutes"])
            if qp and qs and qg and qm:
                qset=set(zip(q[qp].astype(str).str.strip().str.casefold(), q[qs].astype(str).str.strip()))
                era_rows["__qualified_season"]=list(zip(era_rows[pcol].astype(str).str.strip().str.casefold(),era_rows[scol].astype(str).str.strip())).copy()
                era_rows["__qualified_season"]=era_rows["__qualified_season"].map(lambda x:x in qset)
            else:
                era_rows["__qualified_season"]=(era_rows["__Gnum"]>=7)&(era_rows["__MPnum"]>=1400)
        except Exception:
            era_rows["__qualified_season"]=(era_rows["__Gnum"]>=7)&(era_rows["__MPnum"]>=1400)
    else:
        era_rows["__qualified_season"]=(era_rows["__Gnum"]>=7)&(era_rows["__MPnum"]>=125)
    rows=[]
    for key,g in era_rows.groupby([pid,pcol] if pid else [pcol],dropna=False,sort=False):
        name=key[1] if pid else key[0]; pidv=key[0] if pid else name
        # Player's eligible seasons are the seasons between first and last
        # season in which they appear in the selected season type, clipped to
        # the selected era. This prevents pre-entry/post-retirement years from
        # penalizing the participation rate.
        allp=work.loc[work[pcol].astype(str).str.strip().str.casefold().eq(str(name).strip().casefold())]
        years=pd.to_numeric(allp["__year"],errors="coerce").dropna().astype(int).tolist()
        a,b=next(((aa,bb) for k,aa,bb,l in ERA_DEFINITIONS if k==era_key),(None,None))
        if not years or a is None: continue
        lo=max(a,min(years)); hi=min(b,max(years)); eligible=max(0,hi-lo+1)
        qualified_seasons=int(g["__qualified_season"].sum())
        participation=(qualified_seasons/eligible) if eligible else 0.0
        games=float(g["__Gnum"].sum()); minutes=float(g["__MPnum"].sum())
        min_games=ERA_AVERAGE_REGULAR_MIN_GAMES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_GAMES
        min_minutes=ERA_AVERAGE_REGULAR_MIN_MINUTES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_MINUTES
        if participation + 1e-12 < ERA_AVERAGE_PARTICIPATION or games < min_games or minutes < min_minutes:
            continue
        row={"Player_ID":clean(pidv),"Player":clean(name),"Era":era_key,
             "Era_Eligible_Seasons":eligible,"Era_Qualified_Seasons":qualified_seasons,
             "Era_Participation":participation,"G":games,"MP":minutes}
        stats=PLAYOFF_STATS
        per75=ERA_AVERAGE_PER75_REGULAR if season_type.casefold().startswith("regular") else ERA_AVERAGE_PER75_PLAYOFF
        for stat in stats:
            row[stat]=_era_average_statistic(g,stat,per75,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
        rows.append(row)
    result=pd.DataFrame(rows)
    meta={"players_considered":int(era_rows[pcol].nunique()),"players_qualified":len(rows)}
    CACHE[cache_key]=(result.copy(), dict(meta))
    return result, meta

def _era_average_percentile(rows, statistic, higher=True):
    vals=pd.to_numeric(rows[statistic],errors="coerce")
    out=pd.Series(np.nan,index=rows.index,dtype=float)
    valid=vals.notna()
    if valid.sum()==0: return out
    ranks=vals.loc[valid].rank(method="average",ascending=not higher)
    n=int(valid.sum())
    if n==1: out.loc[valid]=100.0
    else: out.loc[valid]=100.0*(n-ranks)/(n-1)
    return out

def api_era_average_big_board(season_type="Regular Season",era=None,statistic=None,sort_direction="desc",search=None,limit=100):
    era_key=str(era or "").strip()
    if not era_key:
        return {"rows":[],"count":0,"scope":"era_average","season_type":season_type,
                "era":None,"note":"Select an era to calculate an Era Average."}
    source=load_master_seasons() if season_type.casefold().startswith("regular") else load_playoff_46_season()
    rows,meta=_era_average_qualified_rows(source,season_type,era_key)
    if rows.empty or not statistic or statistic not in rows.columns:
        return {"rows":[],"count":0,"scope":"era_average","career_scope":False,
                "historical_scope":False,"context":"Era","season":"Era Average",
                "season_type":season_type,"era":era_key,"statistic":statistic or "Statistical Dominance Index",
                "note":"Era Average requires a selected statistic. The Statistical Dominance Index is intentionally deferred for this build.","qualification":{
                    "participation":ERA_AVERAGE_PARTICIPATION,"min_games":ERA_AVERAGE_REGULAR_MIN_GAMES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_GAMES,
                    "min_minutes":ERA_AVERAGE_REGULAR_MIN_MINUTES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_MINUTES},"meta":meta}
    higher=statistic not in ERA_AVERAGE_LOWER
    pct_cache_key=f"__era_average_pct_v2__:{season_type}:{era_key}:{statistic}"
    if pct_cache_key in CACHE:
        ranked=CACHE[pct_cache_key].copy()
    else:
        ranked=rows.copy()
        ranked["_value_num"]=pd.to_numeric(ranked[statistic],errors="coerce")
        ranked=ranked.dropna(subset=["_value_num"]).copy()
        ranked["_pct"]=_era_average_percentile(ranked,statistic,higher=higher)
        CACHE[pct_cache_key]=ranked.copy()
    if search:
        ranked=ranked.loc[ranked["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
    rows=ranked
    rows=rows.sort_values("_pct",ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
    out=[]
    for rank,(_,r) in enumerate(rows.iterrows(),1):
        out.append({"rank":rank,"player_id":clean(r.get("Player_ID")),"player_name":clean(r.get("Player")),
                    "season":"Era Average","season_label":"Era Average","statistic":statistic,
                    "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"context":"Era",
                    "headshot_url":_headshot_url_for(clean(r.get("Player_ID")),clean(r.get("Player"))),
                    "era":era_key,"era_participation":clean(r["Era_Participation"]),
                    "era_qualified_seasons":clean(r["Era_Qualified_Seasons"]),
                    "era_eligible_seasons":clean(r["Era_Eligible_Seasons"]),
                    "era_games":clean(r["G"]),"era_minutes":clean(r["MP"])})
    return {"rows":out,"count":len(out),"scope":"era_average","career_scope":False,
            "historical_scope":False,"context":"Era","season":"Era Average","season_type":season_type,
            "era":era_key,"statistic":statistic,"qualification":{
                "participation":ERA_AVERAGE_PARTICIPATION,"min_games":ERA_AVERAGE_REGULAR_MIN_GAMES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_GAMES,
                "min_minutes":ERA_AVERAGE_REGULAR_MIN_MINUTES if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MIN_MINUTES},"meta":meta,
            "note":"Era Average aggregates qualified player-seasons across the selected era. Per-75 rates are possession-weighted; cumulative stats are summed; percentage/rate stats use their natural denominator when available."}


PLAYOFF_SINGLE_MIN_GAMES = 3
PLAYOFF_SINGLE_MIN_MINUTES = 75
PLAYOFF_FIVE_YEAR_MIN_GAMES = 35

def _playoff_five_year_peak_candidates(source):
    """Return valid five-consecutive-playoff-appearance windows.

    Each appearance must meet the single-season playoff percentile threshold
    (3 G + 75 MP), and the five appearances must total at least 35 games.
    """
    if source is None or source.empty:
        return []
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID"])
    gcol=col(source,["G","Games","games"])
    mpcol=col(source,["MP","Minutes","minutes"])
    if not pcol or not scol or not gcol or not mpcol:
        return []
    work=source.copy()
    work["__year"]=work[scol].map(_season_end_year)
    work["__g"]=pd.to_numeric(work[gcol],errors="coerce")
    work["__mp"]=pd.to_numeric(work[mpcol],errors="coerce")
    work=work.dropna(subset=["__year"]).copy()
    work["__year"]=work["__year"].astype(int)
    work["__qualified"]=(work["__g"]>=PLAYOFF_SINGLE_MIN_GAMES)&(work["__mp"]>=PLAYOFF_SINGLE_MIN_MINUTES)
    work=work.sort_values("__year",kind="stable").drop_duplicates(["__year"],keep="first")
    q=work.loc[work["__qualified"]].sort_values("__year").reset_index(drop=True)
    if len(q)<5: return []
    candidates=[]
    for i in range(len(q)-4):
        g=q.iloc[i:i+5].copy()
        years=g["__year"].astype(int).tolist()
        # "Consecutive playoff appearances": no missing postseason between
        # the five selected appearances.
        if years[-1]-years[0] != 4:
            continue
        if float(g["__g"].sum()) < PLAYOFF_FIVE_YEAR_MIN_GAMES:
            continue
        candidates.append(g)
    return candidates

def _playoff_five_year_peak_board(era=None,statistic=None,sort_direction="desc",search=None,limit=100):
    source=load_playoff_46_season()
    if source.empty:
        return {"rows":[],"count":0,"scope":"five_year_peak","season_type":"Playoffs","era":era or None}
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID"])
    if not pcol or not scol: return {"rows":[],"count":0,"scope":"five_year_peak","season_type":"Playoffs"}
    st=col(source,["Season_Type","SeasonType","season_type","Phase"])
    if st:
        source=source.loc[source[st].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()
    lower=PLAYOFF_LOWER_IS_BETTER
    rows=[]
    for key,g in source.groupby([pid,pcol],dropna=False,sort=False) if pid else source.groupby([pcol],dropna=False,sort=False):
        candidates=_playoff_five_year_peak_candidates(g)
        for cand in candidates:
            start=int(cand["__year"].min())
            peak_era=_playoff_era(start)
            if era and peak_era != era: continue
            stat=statistic or "PTS_per75"
            sc=_playoff_source_column(cand,stat)
            if not sc: continue
            val=_era_average_statistic(cand,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
            if pd.isna(val): continue
            name=str(cand.iloc[0][pcol])
            pidv=str(cand.iloc[0][pid]) if pid else name
            rows.append({"Player_ID":pidv,"Player":name,"Peak_Start_Year":start,
                         "Peak_End_Year":int(cand["__year"].max()),"Peak_Era":peak_era,
                         "Peak_Seasons":[_season_label_any(y) for y in cand[scol].tolist()],
                         "_value_num":float(val),"Total_Games":int(cand["__g"].sum())})
    if not rows:
        return {"rows":[],"count":0,"scope":"five_year_peak","season_type":"Playoffs","era":era or None,"statistic":statistic}
    df=pd.DataFrame(rows)
    higher=stat not in lower
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").drop_duplicates(["Player_ID","Player"],keep="first").copy()
    vals=df["_value_num"]; n=len(vals)
    ranks=vals.rank(method="average",ascending=not higher)
    df["_pct"]=100.0 if n==1 else 100.0*(n-ranks)/(n-1)
    if search:
        df=df.loc[df["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").head(int(limit)).reset_index(drop=True)
    out=[]
    for i,r in df.iterrows():
        out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
                    "season":clean(r["Peak_Start_Year"]),
                    "season_label":f"{r['Peak_Seasons'][0]} → {r['Peak_Seasons'][-1]}",
                    "peak_seasons":r["Peak_Seasons"],"peak_era":clean(r["Peak_Era"]),
                    "total_games":clean(r["Total_Games"]),"value":clean(r["_value_num"]),
                    "percentile":clean(r["_pct"])})
    return {"rows":out,"count":len(out),"scope":"five_year_peak","season_type":"Playoffs",
            "era":era or None,"statistic":stat,
            "note":"Playoff 5-Year Peak = five consecutive playoff appearances; each appearance must meet 3 G + 75 MP, and the five appearances must total at least 35 games."}

def api_playoff_big_board(season=None,context="Historical",statistic=None,
                          sort_direction="desc",search=None,limit=100,scope="single",era=None):
    if str(scope).casefold() in {"five_year_peak","5-year peak","5 year peak","5year_peak","peak"}:
        return _playoff_five_year_peak_board(era,statistic,sort_direction,search,limit)
    is_career=str(scope).casefold()=="career" or str(season).casefold()=="career"

    raw=load_playoff_46_career() if is_career else load_playoff_46_season()
    if raw.empty:
        return {"seasons":[],"season_options":[],"season":"Career" if is_career else "Historical Percentile",
                "rows":[],"count":0,"season_type":"Playoffs"}

    c_pid=col(raw,["Player_ID","PlayerId","PlayerID","player_id"])
    c_player=col(raw,["Player","Player_Name","Display_Name","player_name","Name"])
    c_season=col(raw,["Season","season","Season_ID"])
    if not c_player:
        raise ValueError("Finalized playoff source lacks player-name column.")

    # Season selector comes from the COMPLETE raw playoff season layer, not
    # the qualified percentile population.
    raw_seasons=[] if is_career else _playoff_season_list(raw)
    era_key=str(era or "").strip()
    if era_key and not is_career:
        raw_seasons=[s for s in raw_seasons if _era_key(s) == era_key]
    options=[{"value":s,"label":_season_label_any(s)} for s in raw_seasons] if not is_career else [{"value":"Career","label":"Career"}]

    requested=str(season or "").strip()
    historical=(not is_career) and requested.casefold() in {"","historical","historical percentile","all","all seasons"}

    # Load finalized percentile long data separately. It intentionally excludes
    # non-qualified percentile rows, but never removes the raw value.
    pct=_load_final_playoff_percentile_long(is_career)
    if pct.empty:
        pct=_playoff_long_percentiles(raw,career=is_career)

    p_pid=col(pct,["Player_ID","PlayerId","PlayerID","player_id"])
    p_player=col(pct,["Player","Player_Name","Display_Name","player_name","Name"])
    p_season=col(pct,["Season","season","Season_ID"])
    p_stat=col(pct,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    p_value=col(pct,["Value","value","Career_Value","Raw_Value","Statistic_Value"])

    if is_career:
        work=raw.copy()
        if search:
            work=work.loc[work[c_player].astype(str).str.contains(str(search),case=False,na=False)]
        if statistic:
            sc=_playoff_source_column(work,statistic)
            if not sc:
                work=work.iloc[0:0]
            else:
                work["_value_num"]=pd.to_numeric(work[sc],errors="coerce")
        else:
            work["_value_num"]=np.nan

        if not statistic:
            # Career Dominance requires percentile values. Build it from the
            # finalized career percentile layer only for qualified careers.
            pm=pct.copy()
            pc_stat=p_stat
            pct_col="Career_Percentile" if "Career_Percentile" in pm.columns else col(pm,["Career_Percentile","Percentile"])
            if not pc_stat or not pct_col:
                rows=[]
            else:
                pm["_pct_num"]=pd.to_numeric(pm[pct_col],errors="coerce")
                pm["_stat_key"]=pm[pc_stat].astype(str).str.strip()
                spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
                scat=choose_col(spec,["Category"]); sgrp=choose_col(spec,["Group_ID","Group","Group_Id"])
                sstat=choose_col(spec,["Statistic","Stat"]); ssw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
                sgw=choose_col(spec,["Group_Weight"])
                pieces=[]
                if all([scat,sgrp,sstat,ssw,sgw]):
                    w=spec.loc[spec[scat].astype(str).str.strip().isin({
                        "Scoring Volume","Scoring Efficiency","Creation & Playmaking",
                        "Rebounding","Defense","Impact & Value"
                    })].copy()
                    w["_stat_key"]=w[sstat].astype(str).str.strip()
                    w["_sw"]=pd.to_numeric(w[ssw],errors="coerce")
                    w["_gw"]=pd.to_numeric(w[sgw],errors="coerce")
                    w=w.dropna(subset=["_sw","_gw"])
                    base=[c for c in [p_pid,p_player] if c]
                    for (category,group),g in w.groupby([scat,sgrp],sort=False):
                        m=pm.merge(g[["_stat_key","_sw"]],on="_stat_key",how="inner")
                        m=m.dropna(subset=["_pct_num"])
                        if m.empty: continue
                        gs=m.groupby(base,dropna=False).apply(
                            lambda z: np.average(z["_pct_num"],weights=z["_sw"]),
                            include_groups=False
                        ).reset_index(name="_group_score")
                        gs["_gw"]=float(g["_gw"].iloc[0]); gs["_category"]=str(category)
                        pieces.append(gs)
                    if pieces:
                        groups=pd.concat(pieces,ignore_index=True)
                        cats=(groups.assign(_w=groups["_group_score"]*groups["_gw"])
                              .groupby(base,dropna=False)
                              .agg(_weighted=("_w","sum"),_gw=("_gw","sum"))
                              .reset_index())
                        cats["_index_value"]=cats["_weighted"]/cats["_gw"].replace(0,np.nan)
                        cats["_index_pct"]=_playoff_percentile(cats["_index_value"],higher=True)
                        cats=cats.sort_values("_index_pct",ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
                        rows=[]
                        for rank,(_,r) in enumerate(cats.iterrows(),1):
                            rows.append({
                                "rank":rank,"player_id":clean(r[p_pid]) if p_pid else None,
                                "player_name":clean(r[p_player]),"season":"Career","season_label":"Career",
                                "statistic":"Statistical Dominance Index",
                                "value":clean(r["_index_value"]),"percentile":clean(r["_index_pct"]),
                                "context":"Career","headshot_url":_headshot_url_for(clean(r[p_pid]) if p_pid else None,clean(r[p_player]))
                            })
                return {"seasons":["Career"],"season_options":options,"season":"Career",
                        "historical_scope":False,"career_scope":True,"context":"Career",
                        "statistic":"Statistical Dominance Index","rows":rows,
                        "count":len(rows),"season_type":"Playoffs"}

        # Merge career percentile by player/statistic.
        if statistic and not pct.empty and p_stat and p_pid:
            psc=_playoff_source_column(work,statistic)
            if psc:
                pct_stat=pct.loc[pct[p_stat].astype(str).str.strip().str.casefold().eq(str(statistic).strip().casefold())].copy()
                pct_col="Career_Percentile" if "Career_Percentile" in pct_stat.columns else col(pct_stat,["Career_Percentile"])
                if pct_col:
                    right=pct_stat[[c for c in [p_pid,p_player,pct_col] if c]].copy()
                    right=right.rename(columns={pct_col:"_pct_num"})
                    if p_player and c_player:
                        right["__name_key"]=right[p_player].astype(str).str.strip().str.casefold()
                        right=right.drop_duplicates("__name_key",keep="first")
                        work["__name_key"]=work[c_player].astype(str).str.strip().str.casefold()
                        work=work.merge(right[["__name_key","_pct_num"]],on="__name_key",how="left")
                    elif p_pid and c_pid:
                        right=right.drop_duplicates(p_pid,keep="first")
                        work=work.merge(right[[p_pid,"_pct_num"]],left_on=c_pid,right_on=p_pid,how="left")
        if "_pct_num" not in work: work["_pct_num"]=np.nan
        work=work.dropna(subset=["_value_num"])
        work=work.sort_values(["_pct_num","_value_num"],ascending=[sort_direction=="asc",sort_direction=="asc"],na_position="last").head(int(limit))
        rows=[{"rank":i,"player_id":clean(r[c_pid]) if c_pid else None,"player_name":clean(r[c_player]),
               "season":"Career","season_label":"Career","statistic":statistic,
               "value":clean(r["_value_num"]),"percentile":clean(r["_pct_num"]),
               "context":"Career"} for i,(_,r) in enumerate(work.iterrows(),1)]
        return {"seasons":["Career"],"season_options":options,"season":"Career",
                "historical_scope":False,"career_scope":True,"context":"Career",
                "statistic":statistic,"rows":rows,"count":len(rows),"season_type":"Playoffs"}

    # SINGLE-SEASON BOARD: retain every raw season and merge percentile data.
    work=raw.copy()
    if era_key and not is_career and c_season:
        work=work.loc[work[c_season].map(_era_key).eq(era_key)].copy()
    if not historical and c_season:
        work=work.loc[work[c_season].astype(str).str.strip().eq(requested)].copy()
    if search:
        work=work.loc[work[c_player].astype(str).str.contains(str(search),case=False,na=False)]
    if not statistic:
        # Default dominance board: use finalized percentile rows only, since
        # the index itself is a percentile-based construct.
        pm=pct.copy()
        pct_col=percentile_column(pm,context)
        if pct_col and p_stat:
            pm["_pct_num"]=pd.to_numeric(pm[pct_col],errors="coerce")
            pm["_stat_key"]=pm[p_stat].astype(str).str.strip()
            spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
            scat=choose_col(spec,["Category"]); sgrp=choose_col(spec,["Group_ID","Group","Group_Id"])
            sstat=choose_col(spec,["Statistic","Stat"]); ssw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
            sgw=choose_col(spec,["Group_Weight"])
            pieces=[]
            if all([scat,sgrp,sstat,ssw,sgw]):
                w=spec.loc[spec[scat].astype(str).str.strip().isin({
                    "Scoring Volume","Scoring Efficiency","Creation & Playmaking",
                    "Rebounding","Defense","Impact & Value"
                })].copy()
                w["_stat_key"]=w[sstat].astype(str).str.strip()
                w["_sw"]=pd.to_numeric(w[ssw],errors="coerce")
                w["_gw"]=pd.to_numeric(w[sgw],errors="coerce")
                w=w.dropna(subset=["_sw","_gw"])
                base=[c for c in [p_pid,p_player,p_season] if c]
                for (category,group),g in w.groupby([scat,sgrp],sort=False):
                    m=pm.merge(g[["_stat_key","_sw"]],on="_stat_key",how="inner").dropna(subset=["_pct_num"])
                    if m.empty: continue
                    gs=m.groupby(base,dropna=False).apply(
                        lambda z: np.average(z["_pct_num"],weights=z["_sw"]),
                        include_groups=False
                    ).reset_index(name="_group_score")
                    gs["_gw"]=float(g["_gw"].iloc[0]); gs["_category"]=str(category)
                    pieces.append(gs)
                if pieces:
                    groups=pd.concat(pieces,ignore_index=True)
                    cats=(groups.assign(_w=groups["_group_score"]*groups["_gw"])
                          .groupby(base,dropna=False)
                          .agg(_weighted=("_w","sum"),_gw=("_gw","sum"))
                          .reset_index())
                    cats["_index_value"]=cats["_weighted"]/cats["_gw"].replace(0,np.nan)
                    cats["_index_pct"]=_playoff_percentile(cats["_index_value"],higher=True)
                    cats=cats.sort_values("_index_pct",ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
                    rows=[]
                    for rank,(_,r) in enumerate(cats.iterrows(),1):
                        rows.append({"rank":rank,"player_id":clean(r[p_pid]) if p_pid else None,
                                     "player_name":clean(r[p_player]),"season":clean(r[p_season]),
                                     "season_label":_season_label_any(r[p_season]),
                                     "statistic":"Statistical Dominance Index",
                                     "value":clean(r["_index_value"]),"percentile":clean(r["_index_pct"]),
                                     "context":context,"headshot_url":_headshot_url_for(clean(r[p_pid]) if p_pid else None,clean(r[p_player]))})
                    return {"seasons":raw_seasons,"season_options":options,
                            "season":"Historical Percentile" if historical else requested,
                            "historical_scope":historical,"career_scope":False,
                            "context":context,"statistic":"Statistical Dominance Index",
                            "rows":rows,"count":len(rows),"season_type":"Playoffs"}

    # Explicit statistic: raw values come from the complete season layer;
    # percentile is merged only where qualification produced one.
    sc=_playoff_source_column(work,statistic) if statistic else None
    if not sc:
        work["_value_num"]=np.nan
    else:
        work["_value_num"]=pd.to_numeric(work[sc],errors="coerce")

    if not pct.empty and statistic and p_stat and c_pid and p_pid:
        ps=pct.loc[pct[p_stat].astype(str).str.strip().str.casefold().eq(str(statistic).strip().casefold())].copy()
        pct_col=percentile_column(ps,context)
        if pct_col:
            right=ps[[c for c in [p_pid,p_player,p_season,pct_col] if c]].copy()
            right=right.rename(columns={pct_col:"_pct_num"})
            if p_player and p_season and c_player and c_season:
                right["__name_key"]=right[p_player].astype(str).str.strip().str.casefold()
                right["__season_key"]=right[p_season].astype(str).str.strip()
                right=right.drop_duplicates(["__name_key","__season_key"],keep="first")
                work["__name_key"]=work[c_player].astype(str).str.strip().str.casefold()
                work["__season_key"]=work[c_season].astype(str).str.strip()
                work=work.merge(right[["__name_key","__season_key","_pct_num"]],
                                 on=["__name_key","__season_key"],how="left")
            elif p_pid and p_season and c_pid and c_season:
                right=right.drop_duplicates([p_pid,p_season],keep="first")
                work=work.merge(right[[p_pid,p_season,"_pct_num"]],
                                 left_on=[c_pid,c_season],right_on=[p_pid,p_season],how="left")
    if "_pct_num" not in work:
        work["_pct_num"]=np.nan

    work=work.dropna(subset=["_value_num"])
    # Percentile first; raw value is the fallback ordering for non-qualified
    # seasons, which remain visible.
    work["_sort_pct"]=work["_pct_num"].fillna(-np.inf if sort_direction!="asc" else np.inf)
    work["_sort_value"]=work["_value_num"]
    work=work.sort_values(["_sort_pct","_sort_value"],
                          ascending=[sort_direction=="asc",sort_direction=="asc"],
                          na_position="last")
    work=work.drop_duplicates([c for c in [c_pid,c_player,c_season] if c],keep="first").head(int(limit))

    rows=[]
    for rank,(_,r) in enumerate(work.iterrows(),1):
        rows.append({
            "rank":rank,"player_id":clean(r[c_pid]) if c_pid else None,
            "player_name":clean(r[c_player]),"season":clean(r[c_season]),
            "season_label":_season_label_any(r[c_season]),
            "statistic":statistic,"value":clean(r["_value_num"]),
            "percentile":clean(r["_pct_num"]),"context":context
        })
    return {"seasons":raw_seasons,"season_options":options,
            "season":"Historical Percentile" if historical else requested,
            "historical_scope":historical,"career_scope":False,"context":context,
            "statistic":statistic,"rows":rows,"count":len(rows),"season_type":"Playoffs"}

def _career_qualified_mask(df):
    if df.empty: return pd.Series(False,index=df.index)
    g=pd.to_numeric(df.get("G",np.nan),errors="coerce")
    mp=pd.to_numeric(df.get("MP",np.nan),errors="coerce")
    return g.ge(400) & mp.ge(10000)


def _rebuild_career_rts_from_seasons(career_df):
    """Reconstruct career rTS from raw player-season shooting totals.

    rTS is a percentage-point differential, so mixed source units cannot be
    safely repaired with a single numeric threshold. The canonical career
    value is instead rebuilt from the same underlying quantities that define
    TS%: player TS% minus that season's league TS%, weighted by the player's
    true-shooting-attempt denominator across seasons.

    This is used only for the Regular Season career rTS Big Board/profile.
    If the season source is unavailable or lacks the required raw totals, the
    existing career rTS column is retained as a fallback.
    """
    if career_df is None or career_df.empty:
        return career_df
    try:
        profiles=load("profiles",["player_season_profiles","season_profiles"])
    except Exception:
        return career_df
    if profiles is None or profiles.empty:
        return career_df

    pc=col(profiles,["Player_ID","PlayerId","PlayerID","player_id"])
    pn=col(profiles,["Player","Player_Name","Display_Name","player_name","Name"])
    sc=col(profiles,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    pts=col(profiles,["PTS","Points","PTS_raw","Points_raw"])
    fga=col(profiles,["FGA","FGA_raw","Field_Goal_Attempts"])
    fta=col(profiles,["FTA","FTA_raw","Free_Throw_Attempts"])
    if not sc or not pts or not fga or not fta or (not pc and not pn):
        return career_df

    work=profiles.copy()
    work["__season"] = work[sc].map(_season_label_any).astype(str).str.strip()
    work["__pts"] = pd.to_numeric(work[pts],errors="coerce")
    work["__fga"] = pd.to_numeric(work[fga],errors="coerce")
    work["__fta"] = pd.to_numeric(work[fta],errors="coerce")
    work=work.dropna(subset=["__season","__pts","__fga","__fta"])
    work["__tsa"] = work["__fga"] + 0.44*work["__fta"]
    work=work[work["__tsa"]>0].copy()
    if work.empty:
        return career_df

    # Collapse multi-team stints to one player-season before constructing the
    # league totals, preventing 2TM/3TM duplication.
    pkey=(work[pc].astype(str).str.strip() if pc else work[pn].astype(str).str.strip().str.casefold())
    nkey=(work[pn].astype(str).str.strip().str.casefold() if pn else pkey)
    work["__pkey"]=pkey
    work["__namekey"]=nkey
    grouped=work.groupby(["__pkey","__namekey","__season"],dropna=False,sort=False)[["__pts","__fga","__fta","__tsa"]].sum().reset_index()
    grouped["__ts"] = grouped["__pts"]/(2.0*grouped["__tsa"])*100.0

    league=grouped.groupby("__season",sort=False)[["__pts","__tsa"]].sum()
    league["__league_ts"] = league["__pts"]/(2.0*league["__tsa"])*100.0
    grouped=grouped.join(league["__league_ts"],on="__season")
    grouped["__rts"] = grouped["__ts"]-grouped["__league_ts"]

    # Weighted by the player's own TSA across seasons. This is equivalent to
    # aggregating the player's TS differential with the natural denominator.
    career_rts=grouped.groupby("__pkey").apply(
        lambda g: float((g["__rts"]*g["__tsa"]).sum()/g["__tsa"].sum()),
        include_groups=False
    )
    career_name_rts=grouped.groupby("__namekey").apply(
        lambda g: float((g["__rts"]*g["__tsa"]).sum()/g["__tsa"].sum()),
        include_groups=False
    )

    out=career_df.copy()
    if "Player_ID" in out.columns:
        ids=out["Player_ID"].astype(str).str.strip()
        out["rTS_rebuilt"]=ids.map(career_rts)
    else:
        out["rTS_rebuilt"]=np.nan
    if "Player" in out.columns:
        names=out["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        fallback=names.map(career_name_rts)
        out["rTS_rebuilt"]=out["rTS_rebuilt"].where(out["rTS_rebuilt"].notna(),fallback)
    out["rTS"]=out["rTS_rebuilt"].where(out["rTS_rebuilt"].notna(),pd.to_numeric(out.get("rTS"),errors="coerce"))
    out.drop(columns=["rTS_rebuilt"],inplace=True)
    return out

def _build_regular_career_table():
    """Build career values from the canonical regular-season master.

    Per-75 statistics are weighted by estimated possessions (derived from raw
    PTS / Per-75 when an explicit possession column is unavailable). Additive
    value statistics are summed; percentage/rate/index statistics are weighted
    by MP or their natural attempt denominator where available.
    """
    # Prefer the finalized canonical career layer. The previous implementation
    # rebuilt a career table by grouping season rows, which was both slow and
    # semantically wrong for career Big Board values.
    career_file=find_csv(ROOT / "data", ["nba_per75_career_v2"])
    if career_file is not None:
        cache_key=f"__regular_career_canonical__:{career_file}"
        if cache_key in CACHE:
            return CACHE[cache_key]
        career=read_csv(career_file,low_memory=False)
        if "rTS" in career.columns:
            career=_rebuild_career_rts_from_seasons(career)
        # The canonical career file contains separate Regular Season and
        # Playoffs rows. The regular-season board must expose only Regular Season.
        stc=col(career,["Season_Type","SeasonType","season_type","Phase"])
        if stc:
            vals=career[stc].astype(str).str.strip().str.casefold()
            if vals.isin({"regular season","regular","reg season"}).any():
                career=career.loc[vals.isin({"regular season","regular","reg season"})].copy()
        player_col=col(career,["Player","Player_Name","Display_Name","player_name","Name"])
        if player_col:
            out=pd.DataFrame({"Player":career[player_col].astype(str).str.strip()})
            # Copy all career metrics before identity mapping. A merge can change
            # row order; assigning metric columns after a merge would silently
            # attach one player's values to another player's identity.
            gcol=col(career,["Career_G","G","Games","games"])
            mpcol=col(career,["Career_MP","MP","Minutes","minutes"])
            out["G"]=pd.to_numeric(career[gcol],errors="coerce") if gcol else np.nan
            out["MP"]=pd.to_numeric(career[mpcol],errors="coerce") if mpcol else np.nan
            lcol=col(career,["League","league","League_Name","LeagueName"])
            out["League"]=career[lcol].astype(str).str.strip() if lcol else "NBA"
            # Preserve the raw career totals needed by BRef percentage
            # qualification. The percentage itself remains the canonical
            # statistic shown/ranked by the Big Board.
            for raw in ["FG","FGA","FT","FTA","3P","3PA","TSA","PTS","TRB","AST","STL","BLK","TOV"]:
                rc=col(career,[raw,raw+"_raw",raw+"s"])
                if rc:
                    out[raw]=pd.to_numeric(career[rc],errors="coerce")
            for stat in PLAYOFF_STATS:
                if stat in career.columns:
                    out[stat]=pd.to_numeric(career[stat],errors="coerce")
            # Map the canonical player identity ID without changing row order.
            try:
                # Preserve an authoritative Player_ID already present in the
                # canonical career layer. Falling back to a name lookup is only
                # safe when the clean name is unique.
                career_pid=col(career,["Player_ID","PlayerId","PlayerID","player_id"])
                if career_pid:
                    out["Player_ID"]=career[career_pid].astype(str).str.strip()
                else:
                    ident=load_exact_csv("identity","website_player_identity_v1.csv")
                    ic=identity_cols(ident)
                    if ic["id"] and ic["name"]:
                        mp=ident[[ic["id"],ic["name"]]].copy()
                        mp["__name"]=mp[ic["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip()
                        mp=mp.drop_duplicates("__name",keep=False)
                        id_map=dict(zip(mp["__name"],mp[ic["id"]]))
                        out["Player_ID"]=out["Player"].map(id_map)
                    else:
                        out["Player_ID"]=out["Player"]
            except Exception:
                out["Player_ID"]=out["Player"]
            out["Qualified_Career"]=_career_qualified_mask(out)
            CACHE[cache_key]=out
            return out

    master=load_master_seasons()
    if master.empty: return pd.DataFrame()
    st=col(master,["Season_Type","SeasonType","Season_Type_ID","Phase"])
    if st:
        master=master.loc[master[st].astype(str).str.casefold().eq("regular season")].copy()
    pid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    player=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    if not pid or not player: return pd.DataFrame()
    # Prefer canonical player-season rows. If multiple rows remain, collapse by ID/name/season.
    season=col(master,["Season","season","Season_ID"])
    if not season: return pd.DataFrame()
    work=master.copy()
    work["__G"]=pd.to_numeric(work[col(work,["G","Games","games"])],errors="coerce") if col(work,["G","Games","games"]) else np.nan
    work["__MP"]=pd.to_numeric(work[col(work,["MP","Minutes","minutes"])],errors="coerce") if col(work,["MP","Minutes","minutes"]) else np.nan
    per75=set(PLAYOFF_PER75_STATS)
    # Regular season registry has the same canonical 46 stat names in the master.
    stat_sources={stat:col(work,[stat]) for stat in PLAYOFF_STATS}
    # Explicit possessions if available.
    poss_col=col(work,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
    work["__poss"]=pd.to_numeric(work[poss_col],errors="coerce") if poss_col else np.nan
    if work["__poss"].isna().all():
        pts_col=stat_sources.get("PTS_per75")
        raw_pts=col(work,["PTS","PTS_raw","Points"])
        if pts_col and raw_pts:
            pp=pd.to_numeric(work[pts_col],errors="coerce")
            pts=pd.to_numeric(work[raw_pts],errors="coerce")
            work["__poss"]=pts/(pp/75.0).replace(0,np.nan)
    if work["__poss"].isna().all():
        work["__poss"]=work["__MP"].clip(lower=0)*2.0

    rows=[]
    keys=[pid,player,season]
    for key,g in work.groupby(keys,dropna=False,sort=False):
        pidv,name,sv=key
        row={"Player_ID":clean(pidv),"Player":clean(name),"Season":clean(sv),"G":g["__G"].sum(min_count=1),"MP":g["__MP"].sum(min_count=1)}
        poss=pd.to_numeric(g["__poss"],errors="coerce")
        mp=pd.to_numeric(g["__MP"],errors="coerce")
        for stat in PLAYOFF_STATS:
            sc=stat_sources.get(stat)
            if not sc:
                row[stat]=np.nan; continue
            vals=pd.to_numeric(g[sc],errors="coerce")
            if stat in per75:
                x=pd.DataFrame({"v":vals,"w":poss}).dropna(); x=x[x["w"]>0]
                row[stat]=float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan
            elif stat in {"WS","OWS","DWS","VORP"}:
                row[stat]=float(vals.sum(min_count=1)) if vals.notna().any() else np.nan
            elif stat in {"FG_pct","2P_pct","3P_pct","FT_pct","TS_pct","FTr","3PAr"}:
                # Weighted by attempts when possible.
                den_map={"FG_pct":"FGA","2P_pct":"2PA","3P_pct":"3PA","FT_pct":"FTA","TS_pct":"FGA","FTr":"FGA","3PAr":"FGA"}
                dc=col(g,[den_map[stat]]) if stat in den_map else None
                if dc:
                    d=pd.to_numeric(g[dc],errors="coerce"); x=pd.DataFrame({"v":vals,"w":d}).dropna(); x=x[x.w>0]
                    row[stat]=float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan
                else:
                    x=pd.DataFrame({"v":vals,"w":mp}).dropna(); row[stat]=float((x.v*x.w).sum()/x.w.sum()) if not x.empty and x.w.sum()>0 else np.nan
            else:
                x=pd.DataFrame({"v":vals,"w":mp}).dropna(); row[stat]=float((x.v*x.w).sum()/x.w.sum()) if not x.empty and x.w.sum()>0 else np.nan
        rows.append(row)
    out=pd.DataFrame(rows)
    if out.empty: return out
    out["Qualified_Career"]=_career_qualified_mask(out)
    return out

def _regular_career_big_board(statistic, sort_direction="desc", search=None, limit=100):
    career=_build_regular_career_table()
    if career.empty or not statistic: return []
    if search:
        career=career.loc[career["Player"].astype(str).str.contains(str(search),case=False,na=False)]
    career["_value_num"]=pd.to_numeric(career[statistic],errors="coerce") if statistic in career.columns else np.nan
    career=career.dropna(subset=["_value_num"])
    qualified=career.loc[career["Qualified_Career"]].copy()

    # Career percentage statistics retain BRef's statistic-specific career
    # attempt minimums. Per-75 career boards additionally require 15,000 MP.
    league_col="League" if "League" in career.columns else None
    if statistic in BREF_PERCENT_STATS:
        def _career_pct_ok(r):
            league=str(r[league_col]).upper() if league_col else "NBA"
            league="ABA" if "ABA" in league else "NBA"
            rule=BREF_CAREER_PERCENT[league][statistic]
            return _bref_number(r,[rule[0],rule[0]+"_raw"])>=rule[1]
        qualified=qualified.loc[qualified.apply(_career_pct_ok,axis=1)].copy()
    if statistic in BREF_BASIC_STATS and statistic.endswith("_per75"):
        qualified=qualified.loc[pd.to_numeric(qualified["MP"],errors="coerce").ge(BREF_CAREER_PER75_MP)].copy()
    higher=statistic not in {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
    # Percentile qualification is G>=400 and MP>=10000. Non-qualified careers
    # remain available but receive no percentile.
    qualified["_pct"]=_playoff_percentile(qualified["_value_num"],higher=higher)
    pct_map=dict(zip(qualified["Player_ID"].astype(str),qualified["_pct"]))
    career["_pct"]=career["Player_ID"].astype(str).map(pct_map)
    # Big Board qualification is a hard inclusion rule. Do not leave
    # sub-threshold careers in the ranked result merely because they lack a
    # percentile. This is what previously allowed players such as Randy
    # Holcomb and Mel Peterson onto the career FG% board.
    career=qualified.copy()
    career["_pct"]=career["Player_ID"].astype(str).map(pct_map)
    # Big Board rank is determined by the actual statistic value. Percentile is
    # a descriptive field, not the primary ordering key; rounded/tied
    # percentiles previously caused values to appear out of order.
    career=career.sort_values("_value_num",ascending=(sort_direction=="asc"),kind="stable",na_position="last")
    career=career.head(int(limit))
    rows=[]
    for rank,(_,r) in enumerate(career.iterrows(),1):
        rows.append({"rank":rank,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
                     "season":"Career","season_label":"Career","statistic":statistic,
                     "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"context":"Career",
                     "career_games":clean(r["G"]),"career_minutes":clean(r["MP"]),
                     "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))})
    return rows


FIVE_YEAR_PEAK_MAX_SPAN = 5  # max end-year - start-year: six calendar seasons
FIVE_YEAR_PEAK_N = 5

def _regular_qualified_season_keys(master):
    """Return the authoritative regular-season qualifying player/season keys.

    Prefer the finalized qualification population. If its legacy IDs do not
    line up with the canonical master identity layer, derive the same
    qualification gate directly from the master rows using the established
    rule: at least 60% of that season's league schedule and at least 1,400
    minutes. This keeps the peak engine independent of source-ID drift.
    """
    q=load_qualification_population()
    ids=set(); names=set()
    if not q.empty:
        qp=col(q,["Player_ID","PlayerId","PlayerID","player_id"])
        qn=col(q,["Player","Player_Name","Display_Name","player_name","Name"])
        qs=col(q,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        if qs:
            seasons=q[qs].map(_season_label_any).astype(str).str.strip()
            if qp:
                ids=set(zip(q[qp].astype(str).str.strip(), seasons))
            if qn:
                names=set(zip(q[qn].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold(), seasons))

    # Validate that the qualification keys actually intersect the master.
    # A stale/source-only ID table otherwise makes every peak appear empty.
    pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    gcol=col(master,["G","Games","games"])
    mpcol=col(master,["MP","Minutes","minutes"])
    if not pcol or not scol:
        return ids,names

    master_keys=set()
    seasons=master[scol].map(_season_label_any)
    if pid:
        master_keys.update(zip(master[pid].astype(str).str.strip(),seasons))
    master_names=set(zip(master[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold(),seasons))

    if (ids and ids & master_keys) or (names and names & master_names):
        return ids,names

    # Fallback: derive the qualification directly from the season rows.
    # Schedule is inferred from the maximum player G in each season, which is
    # robust to shortened historical schedules and avoids hard-coding 82.
    work=master.copy()
    work["__season_label"]=work[scol].map(_season_label_any)
    work["__g_num"]=pd.to_numeric(work[gcol],errors="coerce") if gcol else np.nan
    work["__mp_num"]=pd.to_numeric(work[mpcol],errors="coerce") if mpcol else np.nan
    schedule=work.groupby("__season_label")["__g_num"].max().to_dict()
    for _,r in work.iterrows():
        season=str(r["__season_label"])
        sched=float(schedule.get(season,82) or 82)
        games=float(r["__g_num"]) if pd.notna(r["__g_num"]) else 0
        minutes=float(r["__mp_num"]) if pd.notna(r["__mp_num"]) else 0
        if games >= math.ceil(0.60*sched) and minutes >= 1400:
            ident=str(r[pid]).strip() if pid else ""
            name=str(r[pcol]).replace("*","").strip().casefold()
            if ident: ids.add((ident,season))
            names.add((name,season))
    return ids,names


def _five_year_peak_candidates(player_rows, qualified_ids, qualified_names):
    """Return all valid five-qualifying-season peak windows for one player.

    Five qualifying seasons must fit inside at most six calendar seasons. A
    single skipped/non-qualifying season is therefore allowed; two consecutive
    skipped seasons are not.
    """
    if player_rows.empty:
        return []
    rows=player_rows.copy()
    scol=col(rows,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    pcol=col(rows,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(rows,["Player_ID","PlayerId","PlayerID","player_id"])
    if not scol:
        return []
    rows["__season_year"]=rows[scol].map(_season_end_year)
    rows=rows.dropna(subset=["__season_year"]).copy()
    rows["__season_year"]=rows["__season_year"].astype(int)

    # Deduplicate to one player-season row if an upstream source ever contains
    # duplicate records for the same identity/season.
    dedup_cols=["__season_year"]
    if pid and pid in rows.columns:
        rows=rows.sort_values(["__season_year"],kind="stable").drop_duplicates(dedup_cols,keep="first")
    else:
        rows=rows.sort_values(["__season_year"],kind="stable").drop_duplicates(dedup_cols,keep="first")

    qflags=[]
    gcol=col(rows,["G","Games","games"])
    mpcol=col(rows,["MP","Minutes","minutes"])
    rows["__Gnum"]=pd.to_numeric(rows[gcol],errors="coerce") if gcol else np.nan
    rows["__MPnum"]=pd.to_numeric(rows[mpcol],errors="coerce") if mpcol else np.nan

    # Build a conservative schedule lookup from the full qualification layer
    # when possible. The established regular-season gate is the authoritative
    # 60% participation + 1,400 MP rule.
    schedule_by_year={}
    try:
        qsrc=load_qualification_population()
        qs=col(qsrc,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        qg=col(qsrc,["G","Games","games"])
        if qs and qg:
            qtmp=qsrc.copy()
            qtmp["__qyear"]=qtmp[qs].map(_season_end_year)
            qtmp["__qg"]=pd.to_numeric(qtmp[qg],errors="coerce")
            schedule_by_year=qtmp.groupby("__qyear")["__qg"].max().dropna().to_dict()
    except Exception:
        schedule_by_year={}

    for _,r in rows.iterrows():
        y=int(r["__season_year"])
        season_raw=_season_label_any(r[scol])
        ident=str(r[pid]).strip() if pid else ""
        name=str(r[pcol]).replace("*","").strip().casefold() if pcol else ""
        key_match=((ident,season_raw) in qualified_ids) or ((name,season_raw) in qualified_names)

        games=float(r["__Gnum"]) if pd.notna(r["__Gnum"]) else 0.0
        minutes=float(r["__MPnum"]) if pd.notna(r["__MPnum"]) else 0.0
        schedule=float(schedule_by_year.get(y,82) or 82)
        direct_match=(games >= math.ceil(0.60*schedule) and minutes >= 1400)

        qflags.append(bool(key_match or direct_match))
    rows["__qualified"]=qflags
    q=rows.loc[rows["__qualified"]].sort_values("__season_year").reset_index(drop=True)
    if len(q) < FIVE_YEAR_PEAK_N:
        return []

    candidates=[]
    for i in range(len(q)-FIVE_YEAR_PEAK_N+1):
        g=q.iloc[i:i+FIVE_YEAR_PEAK_N].copy()
        years=g["__season_year"].astype(int).tolist()
        if years[-1]-years[0] <= FIVE_YEAR_PEAK_MAX_SPAN:
            candidates.append(g)
    return candidates

def _five_year_peak_board(season_type="Regular Season", era=None, statistic=None,
                          sort_direction="desc", search=None, limit=100):
    """Build the 5-Year Peak Big Board directly from master season rows."""
    is_playoff=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    source=load_playoff_46_season() if is_playoff else load_master_seasons()
    if source.empty:
        return {"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,"era":era or None}

    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    gcol=col(source,["G","Games","games"])
    mpcol=col(source,["MP","Minutes","minutes"])
    if not pcol or not scol or not gcol or not mpcol:
        return {"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,"era":era or None}

    work=source.copy()
    st=col(work,["Season_Type","SeasonType","season_type","Phase"])
    if st and not is_playoff:
        work=work.loc[work[st].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()

    work["__year"]=work[scol].map(_season_end_year)
    work["__g"]=pd.to_numeric(work[gcol],errors="coerce")
    work["__mp"]=pd.to_numeric(work[mpcol],errors="coerce")
    work=work.dropna(subset=["__year"]).copy()
    work["__year"]=work["__year"].astype(int)

    if pid:
        work["__pid"]=work[pid].astype(str).str.strip()
    else:
        work["__pid"]=work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip()
    work["__name"]=work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip()

    identity=_canonical_identity_registry()
    if not identity.empty:
        ic=identity_cols(identity)
        if ic.get("id") and ic.get("name"):
            id_to_name=dict(zip(identity[ic["id"]].astype(str).str.strip(),
                                identity[ic["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip()))
            work["__canonical_name"]=work["__pid"].map(id_to_name).fillna(work["__name"])
        else:
            work["__canonical_name"]=work["__name"]
    else:
        work["__canonical_name"]=work["__name"]

    stat=statistic or "PTS_per75"
    available_stats=PLAYOFF_STATS if is_playoff else REGULAR_STATS
    if stat not in available_stats and stat not in source.columns:
        stat="PTS_per75"

    schedule={} if is_playoff else work.groupby("__year")["__g"].max().dropna().to_dict()
    rows=[]

    for canonical_name,g in work.groupby("__canonical_name",dropna=False,sort=False):
        g=g.sort_values(["__year","__mp"],ascending=[True,False],kind="stable")
        g=g.drop_duplicates(["__year"],keep="first")

        if is_playoff:
            q=g.loc[(g["__g"]>=3)&(g["__mp"]>=75)].copy()
            windows=[]
            if len(q)>=5:
                # Five rows must represent five consecutive playoff appearances.
                # Since the playoff dataset contains one row per postseason
                # appearance, five adjacent rows are the appearance sequence.
                for i in range(len(q)-4):
                    cand=q.iloc[i:i+5].copy()
                    if float(cand["__g"].sum())>=35:
                        windows.append(cand)
        else:
            qualified=[]
            for _,r in g.iterrows():
                sched=float(schedule.get(int(r["__year"]),82) or 82)
                if float(r["__g"])>=math.ceil(0.60*sched) and float(r["__mp"])>=1400:
                    qualified.append(r)
            q=pd.DataFrame(qualified) if qualified else pd.DataFrame()
            windows=[]
            for i in range(max(0,len(q)-4)):
                cand=q.iloc[i:i+5].copy()
                if len(cand)==5 and int(cand["__year"].iloc[-1])-int(cand["__year"].iloc[0])<=5:
                    windows.append(cand)

        for cand in windows:
            start_year=int(cand["__year"].min())
            end_year=int(cand["__year"].max())
            peak_era=_era_key(start_year)
            if era and peak_era!=era:
                continue
            val=_era_average_statistic(
                cand,stat,
                ERA_AVERAGE_PER75_PLAYOFF if is_playoff else ERA_AVERAGE_PER75_REGULAR,
                ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS
            )
            if pd.isna(val):
                continue
            labels=[_season_label_any(x) for x in cand[scol].tolist()]
            rows.append({
                "Player_ID":str(cand["__pid"].iloc[0]),
                "Player":str(canonical_name),
                "Peak_Start_Year":start_year,
                "Peak_End_Year":end_year,
                "Peak_Era":peak_era,
                "Peak_Seasons":labels,
                "_value_num":float(val),
            })

    if not rows:
        return {"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,"era":era or None,"statistic":stat}

    df=pd.DataFrame(rows)
    lower={"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
    higher=stat not in lower
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").drop_duplicates(["Player"],keep="first")
    vals=df["_value_num"]
    ranks=vals.rank(method="average",ascending=not higher)
    n=len(vals)
    df["_pct"]=100.0 if n==1 else 100.0*(n-ranks)/(n-1)
    if search:
        df=df.loc[df["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").head(int(limit)).reset_index(drop=True)

    out=[]
    for i,r in df.iterrows():
        labels=[str(x) for x in r["Peak_Seasons"]]
        years=[_season_end_year(x) for x in labels]
        skipped=[]
        if not is_playoff:
            full=list(range(min(years),max(years)+1))
            skipped=[_season_label_any(y) for y in full if y not in years]
        out.append({
            "rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
            "season":clean(r["Peak_Start_Year"]),
            "season_label":f"{labels[0]} → {labels[-1]}",
            "peak_seasons":labels,"skipped_seasons":skipped,
            "peak_era":clean(r["Peak_Era"]),"value":clean(r["_value_num"]),
            "percentile":clean(r["_pct"])
        })

    return {
        "rows":out,"count":len(out),"scope":"five_year_peak","season_type":season_type,
        "era":era or None,"statistic":stat,
        "note":(
            "Playoff 5-Year Peak = five consecutive qualifying playoff appearances, each ≥3 G and ≥75 MP, with ≥35 total games."
            if is_playoff else
            "Regular-season 5-Year Peak = five qualifying seasons within a maximum six-calendar-season span. One skipped/non-qualifying season is allowed; two consecutive skipped seasons are not. Each included season must meet ≥60% schedule participation and ≥1,400 minutes."
        )
    }



# ---------------------------------------------------------------------------
# Big Board qualification layer
# ---------------------------------------------------------------------------
# IMPORTANT: These rules are eligibility gates only. They NEVER replace the
# statistic being ranked. If the Big Board requests PTS_per75, the value
# displayed/ranked remains PTS_per75.
#
# The canonical percentile table remains the Big Board's population source.
# We use the season master only to determine whether a player-season satisfies
# the supplied Basketball-Reference-style minimum.
BREF_BASIC_GAMES = {
    1947:40, 1948:32, 1949:40, 1950:46, 1951:46, 1952:44,
    **{y:48 for y in range(1953,1958)},
    1958:55,1959:55,1960:60,1961:55,
    **{y:65 for y in range(1962,1970)},
    **{y:70 for y in range(1970,1975)},
    **{y:70 for y in range(1975,1999)},
    1999:43,
    **{y:70 for y in range(2000,2012)},
    2012:56,
    **{y:70 for y in range(2013,2019)},
    **{y:58 for y in range(2019,2022)},
    **{y:58 for y in range(2022,2035)},
}
BREF_ADV_MP = {
    1952:1207,1953:1280,**{y:1317 for y in range(1954,1960)},
    1960:1372,1961:1445,**{y:1463 for y in range(1962,1966)},
    1966:1482,**{y:1500 for y in range(1967,1999)},
    1999:915,**{y:1500 for y in range(2000,2012)},
    2012:1207,**{y:1500 for y in range(2013,2019)},
    **{y:1500 for y in range(2019,2022)},**{y:1500 for y in range(2022,2035)},
}
# Percentage thresholds are season-specific where the supplied BRef table
# differs; otherwise the modern/current threshold is used.
BREF_FG = {}
# NBA / BAA season-specific FG qualification (made FGs unless explicitly FGA).
for y in range(1947,1950): BREF_FG[y]=("FG",200)
for y in range(1950,1952): BREF_FG[y]=("FG",200)
for y in range(1952,1956): BREF_FG[y]=("FG",210)
for y in range(1956,1960): BREF_FG[y]=("FG",230)
BREF_FG[1960]=("FG",190)
for y in range(1961,1963): BREF_FG[y]=("FG",200)
for y in range(1963,1965): BREF_FG[y]=("FG",210)
BREF_FG[1965]=("FG",220)
BREF_FG[1966]=("FG",210)
for y in range(1967,1969): BREF_FG[y]=("FG",220)
BREF_FG[1969]=("FG",230)
BREF_FG[1970]=("G_FGA",(70,700))
for y in range(1971,1973): BREF_FG[y]=("FGA",700)
for y in range(1973,1975): BREF_FG[y]=("FGA",560)
for y in range(1975,1999): BREF_FG[y]=("FG",300)
BREF_FG[1999]=("FG",183)
for y in range(2000,2012): BREF_FG[y]=("FG",300)
BREF_FG[2012]=("FG",241)
for y in range(2013,2022): BREF_FG[y]=("FG",300)
for y in range(2022,2035): BREF_FG[y]=("FG",300)

BREF_FT = {}
for y in range(1947,1949): BREF_FT[y]=("FT",125)
BREF_FT[1949]=("FT",150)
for y in range(1950,1952): BREF_FT[y]=("FT",170)
for y in range(1952,1956): BREF_FT[y]=("FT",180)
for y in range(1956,1960): BREF_FT[y]=("FT",190)
BREF_FT[1960]=("FT",185)
for y in range(1961,1963): BREF_FT[y]=("FT",200)
for y in range(1963,1967): BREF_FT[y]=("FT",210)
for y in range(1967,1969): BREF_FT[y]=("FT",220)
BREF_FT[1969]=("FT",230)
BREF_FT[1970]=("G_FTA",(70,350))
for y in range(1971,1973): BREF_FT[y]=("FTA",350)
for y in range(1973,1975): BREF_FT[y]=("FTA",160)
for y in range(1975,1999): BREF_FT[y]=("FT",125)
BREF_FT[1999]=("FT",76)
for y in range(2000,2012): BREF_FT[y]=("FT",125)
BREF_FT[2012]=("FT",100)
for y in range(2013,2022): BREF_FT[y]=("FT",125)
for y in range(2022,2035): BREF_FT[y]=("FT",125)

BREF_3P = {}
for y in range(1980,1990): BREF_3P[y]=25
for y in range(1990,1994): BREF_3P[y]=50
for y in range(1994,1997): BREF_3P[y]=82
BREF_3P[1997]=55
BREF_3P[1998]=34
for y in range(2000,2012): BREF_3P[y]=55
BREF_3P[2012]=44
BREF_3P[2013]=55
for y in range(2014,2022): BREF_3P[y]=82
for y in range(2022,2035): BREF_3P[y]=82

BREF_TSA = {}
BREF_TSA[1947]=366
BREF_TSA[1948]=293
BREF_TSA[1949]=366
for y in range(1950,1952): BREF_TSA[y]=581
BREF_TSA[1952]=564
BREF_TSA[1953]=598
for y in range(1954,1960): BREF_TSA[y]=415
BREF_TSA[1960]=457
BREF_TSA[1961]=482
for y in range(1962,1966): BREF_TSA[y]=488
BREF_TSA[1966]=494
for y in range(1967,1999): BREF_TSA[y]=500
BREF_TSA[1999]=305
for y in range(2000,2012): BREF_TSA[y]=500
BREF_TSA[2012]=402
for y in range(2013,2022): BREF_TSA[y]=500
for y in range(2022,2035): BREF_TSA[y]=500

# Career minimums for percentage/statistic qualification.
BREF_CAREER_PERCENT = {
    "NBA":{"FG_pct":("FG",2000),"FT_pct":("FT",1200),
           "3P_pct":("3P",250),"TS_pct":("TSA",5000)},
    "ABA":{"FG_pct":("FG",1000),"FT_pct":("FT",600),
           "3P_pct":("3P",125),"TS_pct":("TSA",2500)},
}
BREF_CAREER_PER75_MP=15000
BREF_BASIC_STATS = {
    "MP","MIN","MIN_per_game","PTS","PTS_per75","TRB","TRB_per75",
    "AST","AST_per75","STL","STL_per75","BLK","BLK_per75"
}
BREF_PERCENT_STATS = {"FG_pct","FT_pct","3P_pct","TS_pct"}
BREF_ADV_STATS = {
    "PER","ORB_pct","DRB_pct","TRB_pct","AST_pct","STL_pct","BLK_pct",
    "TOV_pct","USG_pct","WS/48","WS_48"
}
BREF_ORTG_STATS = {"ORtg","Relative_ORtg","rORTG","Relative ORtg"}

BREF_BASIC_STATS = {
    "MP","MIN","MIN_per_game","PTS","PTS_per75","TRB","TRB_per75",
    "AST","AST_per75","STL","STL_per75","BLK","BLK_per75"
}
BREF_PERCENT_STATS = {"FG_pct","FT_pct","3P_pct","TS_pct"}
BREF_ADV_STATS = {
    "PER","ORB_pct","DRB_pct","TRB_pct","AST_pct","STL_pct","BLK_pct",
    "TOV_pct","USG_pct","DRtg","WS/48","WS_48"
}
BREF_ORTG_STATS = {"ORtg","Relative_ORtg","rORTG","Relative ORtg"}

def _bref_year(v):
    y=_season_end_year(v)
    return int(y) if y is not None else None

def _bref_col(df,names):
    return col(df,names)

def _bref_number(row,names):
    c=_bref_col(row.to_frame().T,names)
    if not c: return 0.0
    v=pd.to_numeric(row[c],errors="coerce")
    return float(v) if pd.notna(v) else 0.0

def _bref_league(row):
    c=_bref_col(row.to_frame().T,["League","league","League_Name","LeagueName"])
    if not c: return "NBA"
    s=str(row[c]).strip().upper()
    return "ABA" if "ABA" in s else ("BAA" if "BAA" in s else "NBA")

def _bref_basic_ok(row,year,league):
    g=_bref_number(row,["G","Games","games"])
    mp=_bref_number(row,["MP","Minutes","minutes"])
    if league=="ABA":
        # Supplied ABA season rules are cumulative. Use the strongest
        # applicable production route for the basic-stat family.
        if year==1967: return g>=40
        thresholds={
            1968:(2048,1000,500,250),1969:(2048,1200,750,325),
            1970:(2048,1000,650,275),1971:(2048,1000,700,335),
            1972:(2048,1000,600,250),1973:(2048,1000,500,200),
            1974:(2048,1000,600,250),1975:(2048,1000,600,250)}
        t=thresholds.get(year)
        if not t: return g>=40
        mpv,pts,trb,ast=t
        return mp>=mpv and _bref_number(row,["PTS","PTS_raw","Points"])>=pts and \
               _bref_number(row,["TRB","TRB_raw","REB","Rebounds"])>=trb and \
               _bref_number(row,["AST","AST_raw","Assists"])>=ast
    games_req=BREF_BASIC_GAMES.get(year,58 if year and year>=2021 else 70)
    if g>=games_req: return True
    # BRef's alternative cumulative routes for the seasons where supplied.
    if year and 1975<=year<=1998 or year and 2000<=year<=2012 or year and year>=2013:
        mp_req=2000 if year not in {1999,2012} else (1220 if year==1999 else 1610)
        pts_req=1400 if year not in {1999,2012} else (854 if year==1999 else 1127)
        trb_req=800 if year not in {1999,2012} else (488 if year==1999 else 644)
        ast_req=400 if year not in {1999,2012} else (244 if year==1999 else 321)
        return (_bref_number(row,["MP","Minutes","minutes"])>=mp_req and
                _bref_number(row,["PTS","PTS_raw","Points"])>=pts_req)
    return False

def _bref_percent_ok(row,stat,year,league):
    if stat=="FG_pct":
        if league=="ABA":
            if year in {1968,1969,1970,1971,1972,1973}: req=("FGA",560)
            elif year==1974: req=("FGA",560)
            else: req=("FG",300)
        else:
            req=BREF_FG.get(year)
        if not req: return True
        if req[0]=="G_FGA":
            return (_bref_number(row,["G","Games","games"])>=req[1][0] and
                    _bref_number(row,["FGA","FGA_raw"])>=req[1][1])
        c=["FGA","FGA_raw"] if req[0]=="FGA" else ["FG","FG_raw","Field_Goals"]
        return _bref_number(row,c)>=req[1]
    if stat=="FT_pct":
        if league=="ABA":
            req=("FTA",200 if year>=1975 else 160)
        else:
            req=BREF_FT.get(year)
        if not req: return True
        if req[0]=="G_FTA":
            return (_bref_number(row,["G","Games","games"])>=req[1][0] and
                    _bref_number(row,["FTA","FTA_raw"])>=req[1][1])
        c=["FTA","FTA_raw"] if req[0]=="FTA" else ["FT","FT_raw","Free_Throws"]
        return _bref_number(row,c)>=req[1]
    if stat=="3P_pct":
        req=BREF_3P.get(year)
        if league=="ABA":
            req={1968:35,1969:40,1970:50,1971:35,1972:40,1973:28,1974:20,1975:27,1976:20}.get(year)
        return True if req is None else _bref_number(row,["3P","3P_raw","3PM"])>=req
    if stat=="TS_pct":
        req=BREF_TSA.get(year)
        if league=="ABA":
            req=476 if year in {1968,1969} else 512
        return True if req is None else _bref_number(row,["TSA","TSA_raw","True_Shooting_Attempts"])>=req
    return True

def _bref_master_eligibility(statistic, season_type="Regular Season"):
    """Return (ids, names, seasons) for qualified regular player-seasons.

    This function is intentionally separate from the canonical percentile
    population. It is a gate only; it never supplies ranking values.
    """
    if not str(season_type).casefold().startswith("regular"):
        return None
    cache_key=f"__bref_gate__::{str(statistic).strip()}::{str(season_type).strip().casefold()}"
    if cache_key in CACHE:
        return CACHE[cache_key]
    master=load_master_seasons()
    if master.empty:
        CACHE[cache_key]=None
        return None
    p=_bref_col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=_bref_col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    s=_bref_col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    if not p or not s: return None
    ids=set(); names=set(); seasons=set()
    for _,r in master.iterrows():
        season=r[s]; y=_bref_year(season)
        if y is None: continue
        league=_bref_league(r)
        st=str(statistic or "").strip()
        if st in BREF_PERCENT_STATS:
            ok=_bref_percent_ok(r,st,y,league)
        elif st in BREF_ORTG_STATS:
            ok=_bref_number(r,["Possessions","Poss","Player_Possessions","Estimated_Player_Possessions"]) >= BREF_ORtg_POSS.get(y,500)
        elif st in BREF_ADV_STATS or st in {"rTS","Relative_TS","Relative_TS%"}:
            ok=_bref_number(r,["MP","Minutes","minutes"]) >= BREF_ADV_MP.get(y,1500)
        else:
            ok=_bref_basic_ok(r,y,league)
        if ok:
            ss=_season_label_any(season)
            seasons.add(ss)
            if pid: ids.add((str(r[pid]).strip(),ss))
            names.add((str(r[p]).replace("*","").strip().casefold(),ss))
    result=(ids,names,seasons)
    CACHE[cache_key]=result
    return result

def _apply_bref_big_board_gate(work, statistic, c_season, c_pid, c_player, season_type):
    """Filter canonical Big Board rows without changing their statistic/value."""
    gate=_bref_master_eligibility(statistic,season_type)
    if gate is None or work.empty:
        return work
    ids,names,_=gate
    ss=work[c_season].map(_season_label_any)
    if c_pid:
        key=list(zip(work[c_pid].astype(str).str.strip(),ss))
        mask=pd.Series(key,index=work.index).isin(ids)
    else:
        mask=pd.Series(
            list(zip(work[c_player].astype(str).str.replace(r"\\*+","",regex=True).str.strip().str.casefold(),ss)),
            index=work.index
        ).isin(names)
    return work.loc[mask].copy()


def _regular_ast_tov_rows():
    """Build single-season AST:TOV from raw regular-season totals.

    Turnovers were not consistently recorded before 1977-78, so a season is
    only eligible when TOV is actually present. The BRef basic-stat
    qualification (including its historical games/production alternatives)
    is then applied to the season. AST:TOV itself remains AST / TOV.
    """
    master=load_master_seasons()
    if master.empty: return pd.DataFrame()
    pcol=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    astc=col(master,["AST","AST_raw","Assists","assists"])
    tovc=col(master,["TOV","TOV_raw","Turnovers","turnovers"])
    gcol=col(master,["G","Games","games"])
    mpcol=col(master,["MP","Minutes","minutes"])
    lcol=col(master,["League","league","League_Name","LeagueName"])
    if not pcol or not scol or not astc or not tovc:
        return pd.DataFrame()
    work=master.copy()
    work["__season"] = work[scol].map(_season_label_any)
    work["__year"] = work["__season"].map(_season_end_year)
    work["__ast"] = pd.to_numeric(work[astc],errors="coerce")
    work["__tov"] = pd.to_numeric(work[tovc],errors="coerce")
    work["__g"] = pd.to_numeric(work[gcol],errors="coerce") if gcol else np.nan
    work["__mp"] = pd.to_numeric(work[mpcol],errors="coerce") if mpcol else np.nan
    keys=[pcol,"__season"]
    if pid: keys=[pid,pcol,"__season"]
    rows=[]
    for key,g in work.groupby(keys,dropna=False,sort=False):
        if pid:
            pv,pname,season=key
        else:
            pname,season=key; pv=pname
        year=_season_end_year(season)
        if year is None or year < 1978:
            continue
        # Collapse traded/team rows. Games/minutes are additive; AST/TOV are
        # additive when present.
        ast=g["__ast"].sum(min_count=1)
        tov=g["__tov"].sum(min_count=1)
        games=g["__g"].sum(min_count=1)
        minutes=g["__mp"].sum(min_count=1)
        if pd.isna(tov) or tov <= 0 or pd.isna(ast):
            continue
        # Apply the same BRef basic-stat qualification used by the other
        # single-season boards. Build a minimal row for the existing rule.
        rr=pd.Series({
            "G":games,"MP":minutes,"PTS":pd.to_numeric(g.get("__pts",pd.Series(dtype=float)),errors="coerce").sum(min_count=1)
                   if "__pts" in g else np.nan,
            "TRB":np.nan,"AST":ast,"STL":np.nan,"BLK":np.nan,
            "League":str(g[lcol].iloc[0]) if lcol else "NBA"
        })
        # For AST:TOV, the BRef basic threshold is applied to games and the
        # AST production alternative where applicable. The existing helper
        # accepts the same row-level fields; supplement AST explicitly.
        league=_bref_league(rr)
        basic_ok=_bref_basic_ok(rr,year,league)
        # For seasons with no qualifying game count, use the BRef AST
        # alternative where supplied (400 AST / 321 in 2011-12 / etc.).
        if not basic_ok:
            ast_req=400
            if year==1999: ast_req=244
            elif year==2012: ast_req=321
            basic_ok=float(ast)>=ast_req
        if not basic_ok:
            continue
        ratio=float(ast)/float(tov)
        rows.append({"Player_ID":clean(pv),"Player":clean(pname),"Season":clean(season),
                     "AST_raw":clean(ast),"TOV_raw":clean(tov),"G":clean(games),
                     "MP":clean(minutes),"AST_TOV":ratio})
    return pd.DataFrame(rows)


def _regular_ast_tov_big_board(season=None, context="Historical", sort_direction="desc",
                               search=None, limit=100, era=None, career=False):
    season_rows=_regular_ast_tov_rows()
    if season_rows.empty: return []
    if career:
        # Career AST:TOV uses ONLY seasons in which turnovers were recorded.
        # BRef career basic qualification is enforced on the resulting career
        # sample: 400 games (and the site's existing 10,000-MP percentile gate).
        sr=season_rows.copy()
        groups=[]
        for (pid,pname),g in sr.groupby(["Player_ID","Player"],dropna=False,sort=False):
            games=pd.to_numeric(g["G"],errors="coerce").sum(min_count=1)
            minutes=pd.to_numeric(g["MP"],errors="coerce").sum(min_count=1)
            ast=pd.to_numeric(g["AST_raw"],errors="coerce").sum(min_count=1)
            tov=pd.to_numeric(g["TOV_raw"],errors="coerce").sum(min_count=1)
            if pd.isna(games) or games < 400 or pd.isna(minutes) or minutes < 10000:
                continue
            if pd.isna(ast) or pd.isna(tov) or tov <= 0:
                continue
            groups.append({"Player_ID":clean(pid),"Player":clean(pname),
                           "G":games,"MP":minutes,"AST_TOV":float(ast)/float(tov)})
        out=pd.DataFrame(groups)
        if out.empty: return []
        if search:
            out=out.loc[out["Player"].astype(str).str.contains(str(search),case=False,na=False)]
        out["_pct"]=_playoff_percentile(out["AST_TOV"],higher=True)
        out=out.sort_values("_pct" if out["_pct"].notna().any() else "AST_TOV",
                            ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
        return [{"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
                 "season":"Career","season_label":"Career","statistic":"AST_TOV",
                 "value":clean(r["AST_TOV"]),"percentile":clean(r["_pct"]),
                 "context":"Career","career_games":clean(r["G"]),"career_minutes":clean(r["MP"]),
                 "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))}
                for i,(_,r) in enumerate(out.iterrows())]

    if era:
        season_rows=season_rows.loc[season_rows["Season"].map(_era_key).eq(str(era))].copy()
    requested=str(season or "").strip()
    historical=requested.casefold() in {"","historical","historical percentile","all","all seasons"}
    if not historical:
        season_rows=season_rows.loc[season_rows["Season"].astype(str).eq(requested)].copy()
    if search:
        season_rows=season_rows.loc[season_rows["Player"].astype(str).str.contains(str(search),case=False,na=False)]
    season_rows=season_rows.dropna(subset=["AST_TOV"]).copy()
    if season_rows.empty: return []
    season_rows["_pct"]=_playoff_percentile(season_rows["AST_TOV"],higher=True)
    season_rows=season_rows.sort_values("_pct" if season_rows["_pct"].notna().any() else "AST_TOV",
                                        ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
    return [{"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
             "season":clean(r["Season"]),"season_label":season_display_label(r["Season"]),
             "statistic":"AST_TOV","value":clean(r["AST_TOV"]),"percentile":clean(r["_pct"]),
             "context":context,"career_games":clean(r["G"]),"career_minutes":clean(r["MP"]),
             "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))}
            for i,(_,r) in enumerate(season_rows.iterrows())]

def api_big_board(season=None, context="Historical", statistic=None,
                  sort_direction="desc", search=None, limit=100, scope="single",
                  season_type="Regular Season", era=None):
    """Canonical season-wide Big Board.

    The season selector has one Historical Percentile scope covering every
    player-season, followed by one option for every season in the database.
    """
    scope_key=str(scope).casefold()
    if scope_key in {"era_average","era average","era"}:
        return api_era_average_big_board(season_type,era,statistic,sort_direction,search,limit)
    if scope_key in {"career","career_average","career average"}:
        if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
            return api_playoff_big_board(
                season="Career", context=context, statistic=statistic,
                sort_direction=sort_direction, search=search, limit=limit,
                scope="career", era=era
            )
        if str(statistic or "").strip().casefold() == "ast_tov":
            rows=_regular_ast_tov_big_board(career=True, sort_direction=sort_direction,
                                            search=search, limit=limit)
        else:
            rows=_regular_career_big_board(statistic,sort_direction,search,limit)
        return {"seasons":[],"season_options":[{"value":"Career","label":"Career"}],
                "season":"Career","historical_scope":False,"career_scope":True,
                "context":"Career","statistic":statistic,"rows":rows,
                "count":len(rows),"season_type":"Regular Season"}
    if scope_key in {"five_year_peak","5-year peak","5 year peak","5year_peak","peak"}:
        return _five_year_peak_board(season_type,era,statistic,sort_direction,search,limit)
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        return api_playoff_big_board(season,context,statistic,sort_direction,search,limit,scope,era)

    # AST:TOV is derived from raw regular-season AST/TOV because older
    # percentile files may not contain the ratio as a canonical row.
    if str(statistic or "").strip().casefold() == "ast_tov":
        rows=_regular_ast_tov_big_board(
            season=season, context=context, sort_direction=sort_direction,
            search=search, limit=limit, era=era, career=False
        )
        return {"seasons":[],"season_options":[],"season":season or "Historical Percentile",
                "historical_scope":str(season or "").casefold() in {"","historical","historical percentile"},
                "career_scope":False,"context":context,"statistic":"AST_TOV",
                "rows":rows,"count":len(rows),"season_type":"Regular Season"}

    source=load_canonical_percentiles()
    if source.empty:
        return {"seasons":[],"season_options":[],"season":"Historical Percentile",
                "rows":[],"count":0}

    c_season=col(source,["Season","season","Season_ID"])
    c_pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    c_player=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    c_stat=col(source,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    c_value=col(source,[
        "Value","value","Statistic_Value","statistic_value","Stat_Value",
        "Raw_Value","Value_Per75","Value_per75","Stat_Value_Per75",
        "Statistic_Value_Per75","Metric_Value","stat_value"
    ])
    if not c_season or not c_player or not c_stat:
        raise ValueError("Canonical percentile source must contain Season, Player, and Statistic columns.")

    raw_seasons=source[c_season].dropna().astype(str).str.strip().unique().tolist()
    raw_seasons.sort(key=lambda x: int(season_display_label(x)) if season_display_label(x).isdigit() else 0)
    era_key=str(era or "").strip()
    if era_key:
        raw_seasons=[s for s in raw_seasons if _era_key(s) == era_key]
    season_options=[{"value":s,"label":season_display_label(s)} for s in raw_seasons]

    requested=str(season or "").strip()
    career_scope=str(scope).casefold() == "career" or requested.casefold() == "career"
    historical_scope=(not career_scope) and requested.casefold() in {
        "", "historical", "historical percentile", "all", "all seasons"
    }
    chosen=None if historical_scope else requested

    work=source.copy()
    if era_key and not career_scope:
        work=work.loc[work[c_season].map(_era_key).eq(era_key)].copy()
    if chosen is not None:
        work=work.loc[work[c_season].astype(str).str.strip().eq(chosen)].copy()
    if search:
        work=work.loc[work[c_player].astype(str).str.contains(str(search),case=False,na=False)]
    if statistic:
        work=work.loc[work[c_stat].astype(str).str.strip().str.casefold()
                       .eq(str(statistic).strip().casefold())]

    # BRef qualification is an eligibility gate only. The canonical row's
    # requested statistic remains the ranking/display value.
    if statistic and not career_scope:
        work=_apply_bref_big_board_gate(work, statistic, c_season, c_pid, c_player, season_type)

    # CAREER BOARD: use the canonical regular-season career aggregation,
    # not an average of percentile rows. This branch must run before percentile
    # column discovery because the career response is not sourced from the
    # season percentile table.
    if career_scope:
        rows=_regular_career_big_board(statistic,sort_direction,search,limit) if statistic else []
        return {"seasons":raw_seasons,"season_options":[{"value":"Career","label":"Career"}],
                "season":"Career","historical_scope":False,"career_scope":True,
                "context":"Career","statistic":statistic or "Statistical Dominance Index",
                "rows":rows,"count":len(rows),
                "note":"Career values are aggregated from the canonical regular-season career layer; career percentiles require G >= 400 and MP >= 10,000."}

    pct_candidates={
        "Season":["Season_Percentile","SeasonPercentile","Season_Pctl","SeasonPctl","Percentile_Season","Pctl_Season"],
        "Era":["Era_Percentile","EraPercentile","Era_Pctl","EraPctl","Percentile_Era","Pctl_Era"],
        "Historical":["Historical_Percentile","HistoricalPercentile","Historical_Pctl","HistoricalPctl","Percentile_Historical","Pctl_Historical"],
    }
    pct_col=col(work,pct_candidates.get("Historical" if historical_scope else context,[]))
    if pct_col is None:
        pct_col=col(work,["Percentile","percentile","Pctl","pctl","Percentile_Value","percentile_value"])
    if pct_col is None:
        raise ValueError("Canonical percentile source has no usable percentile column.")

    # Dominance Index board.
    if not statistic:
        idx_file=find_recursive_csv(ROOT,["player_statistical_dominance_v1","dominance_index"])
        if idx_file:
            d=read_csv(idx_file,low_memory=False)
            dc_season=col(d,["Season","season"])
            dc_pid=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
            dc_player=col(d,["Player","Player_Name","Display_Name","player_name","Name"])
            dc_idx=col(d,["Dominance_Index","dominance_index","Index_Score","Index"])
            if dc_idx:
                if chosen is not None and dc_season:
                    d=d.loc[d[dc_season].astype(str).str.strip().eq(chosen)]
                if search and dc_player:
                    d=d.loc[d[dc_player].astype(str).str.contains(str(search),case=False,na=False)]
                d["_rank_value"]=pd.to_numeric(d[dc_idx],errors="coerce")
                d=d.dropna(subset=["_rank_value"]).sort_values("_rank_value",ascending=(sort_direction!="desc")).head(int(limit))
                rows=[]
                for rank,(_,r) in enumerate(d.iterrows(),1):
                    rows.append({
                        "rank":rank,
                        "player_id":clean(r[dc_pid]) if dc_pid else None,
                        "player_name":clean(r[dc_player]) if dc_player else None,
                        "season":clean(r[dc_season]) if dc_season else None,
                        "season_label":season_display_label(r[dc_season]) if dc_season else None,
                        "statistic":"Statistical Dominance Index",
                        "value":clean(r["_rank_value"]),
                        "percentile":None,
                        "headshot_url":_headshot_url_for(clean(r[dc_pid]) if dc_pid else None,clean(r[dc_player]) if dc_player else None),
                        "context":context
                    })
                return {"seasons":raw_seasons,"season_options":season_options,
                        "season":"Historical Percentile" if historical_scope else chosen,
                        "historical_scope":historical_scope,"context":context,
                        "statistic":"Statistical Dominance Index","rows":rows,"count":len(rows)}

    # Statistic board: raw VALUE and PERCENTILE are taken from the same row.
    work["_rank_value"]=pd.to_numeric(work[pct_col],errors="coerce")
    work=work.dropna(subset=["_rank_value"]).sort_values(
        "_rank_value",ascending=(sort_direction!="desc")
    ).copy()

    if not historical_scope:
        work=work.drop_duplicates(c_pid if c_pid else c_player,keep="first")

    work=work.head(int(limit))
    rows=[]
    for rank,(_,r) in enumerate(work.iterrows(),1):
        rows.append({
            "rank":rank,
            "player_id":clean(r[c_pid]) if c_pid else None,
            "player_name":clean(r[c_player]),
            "season":clean(r[c_season]),
            "season_label":season_display_label(r[c_season]),
            "statistic":clean(r[c_stat]),
            "value":clean(r[c_value]) if c_value and pd.notna(r[c_value]) else None,
            "percentile":clean(r[pct_col]),
            "headshot_url":_headshot_url_for(clean(r[c_pid]) if c_pid else None,clean(r[c_player])),
            "context":"Historical" if historical_scope else context
        })

    return {"seasons":raw_seasons,"season_options":season_options,
            "season":"Historical Percentile" if historical_scope else chosen,
            "historical_scope":historical_scope,
            "context":"Historical" if historical_scope else context,
            "statistic":statistic or "Statistical Dominance Index",
            "rows":rows,"count":len(rows)}




def _comparison_percentile_source(is_playoffs=False):
    """Load the exact percentile population used by the website.

    Regular-season comparisons use player_percentile_lookup_v1.csv first.
    Playoff comparisons use the finalized playoff percentile population.
    """
    key="__comparison_percentile_source_playoff_v4__" if is_playoffs else "__comparison_percentile_source_regular_v4__"
    if key in CACHE:
        return CACHE[key]

    candidates=[]
    if is_playoffs:
        for base in [PATHS.get("playoff_percentiles"), PATHS.get("percentiles"), PATHS.get("visualization")]:
            if base and Path(base).exists():
                candidates.extend(Path(base).rglob("*.csv"))
    else:
        exact=PATHS.get("percentile_lookup")
        if exact and Path(exact).exists():
            candidates.append(Path(exact))
        for base in [PATHS.get("visualization"), PATHS.get("percentiles"), PATHS.get("profiles")]:
            if base and Path(base).exists():
                candidates.extend(Path(base).rglob("*.csv"))

    seen=set(); unique=[]
    for f in candidates:
        f=Path(f)
        s=str(f.resolve())
        if s not in seen:
            seen.add(s); unique.append(f)

    def score(f):
        n=f.name.lower()
        score=0
        if n=="player_percentile_lookup_v1.csv": score+=1000
        if "season_percentile_big_board_long" in n: score+=500
        if "season_percentile_big_board" in n: score+=400
        if "percentile" in n: score+=100
        try:
            cols=[str(c).lower() for c in read_csv(f,nrows=2,low_memory=False).columns]
            if any("percentile" in c for c in cols): score+=100
            if any(c.replace("_","") in {"playerid","player_id"} for c in cols): score+=50
            if "season" in cols or "season_id" in cols: score+=50
        except Exception:
            pass
        return score

    unique.sort(key=score,reverse=True)
    for f in unique:
        try:
            df=read_csv(f,low_memory=False)
            if any("percentile" in str(c).lower() for c in df.columns):
                CACHE[key]=df
                CACHE[key+"__path__"]=str(f)
                return df
        except Exception:
            continue
    raise FileNotFoundError("No canonical percentile CSV found")


def _comparison_percentile_lookup(pctdf, player_id, player_name, years, stat, context):
    if pctdf is None or pctdf.empty:
        return pd.Series(np.nan,index=years,dtype=float)

    pidc=col(pctdf,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(pctdf,["Player","Player_Name","Display_Name","Name","player_name"])
    seac=col(pctdf,["Season","season","Season_ID","SeasonEndYear","Season_End_Year","Year"])
    wanted_name=str(player_name or "").replace("*","").strip().casefold()

    # ID match first, then public-name match. If the canonical lookup uses a
    # different historical ID, the name fallback keeps the percentile layer
    # connected to the same public player.
    qdf=pd.DataFrame()
    if pidc and player_id is not None:
        qdf=pctdf.loc[pctdf[pidc].astype(str).str.strip().eq(str(player_id).strip())].copy()
    if qdf.empty and namec:
        names=pctdf[namec].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        qdf=pctdf.loc[names.eq(wanted_name)].copy()
    if qdf.empty or not seac:
        return pd.Series(np.nan,index=years,dtype=float)

    qdf["__pct_year"]=qdf[seac].map(_season_end_year)
    qdf=qdf.dropna(subset=["__pct_year"]).copy()
    if qdf.empty:
        return pd.Series(np.nan,index=years,dtype=float)
    qdf["__pct_year"]=qdf["__pct_year"].astype(int)
    qdf=qdf.drop_duplicates("__pct_year",keep="first").set_index("__pct_year")

    # IMPORTANT: the finalized percentile registry historically exposes Era
    # and Historical percentile families, while some versions expose Season.
    # For comparison's default Season context, use Season if available, then
    # fall back to Era, then Historical rather than returning null.
    context_order={
        "Season":["Season_Percentile_","Era_Percentile_","Historical_Percentile_","Percentile_"],
        "Era":["Era_Percentile_","Season_Percentile_","Historical_Percentile_","Percentile_"],
        "Historical":["Historical_Percentile_","Era_Percentile_","Season_Percentile_","Percentile_"],
    }.get(context,["Season_Percentile_","Era_Percentile_","Historical_Percentile_","Percentile_"])

    aliases={
        "TS_pct":["TS_pct","TS%","TS"],
        "FG_pct":["FG_pct","FG%"],
        "2P_pct":["2P_pct","2P%"],
        "3P_pct":["3P_pct","3P%"],
        "FT_pct":["FT_pct","FT%"],
    }
    stat_names=[stat]+aliases.get(stat,[])
    norm_cols={re.sub(r"[^a-z0-9]","",str(c).lower()):c for c in qdf.columns}
    pctcol=None
    for pref in context_order:
        for sn in stat_names:
            key=re.sub(r"[^a-z0-9]","",(pref+sn).lower())
            if key in norm_cols:
                pctcol=norm_cols[key]; break
        if pctcol: break

    # Also support Stat_Percentile naming.
    if not pctcol:
        for sn in stat_names:
            snn=re.sub(r"[^a-z0-9]","",sn.lower())
            for c in qdf.columns:
                cn=re.sub(r"[^a-z0-9]","",str(c).lower())
                if snn in cn and "percentile" in cn:
                    pctcol=c; break
            if pctcol: break

    if not pctcol:
        return pd.Series(np.nan,index=years,dtype=float)
    return pd.to_numeric(qdf[pctcol].reindex(years),errors="coerce")


def _comparison_canonical_regular_percentiles(player_id, player_name, years, stat, context):
    """Read regular-season percentiles from the same long-format source used
    by player profiles and spider/category endpoints.

    The canonical table is one row per player-season-statistic. Its percentile
    is selected by `percentile_column`, so there is no wide-column naming
    ambiguity.
    """
    try:
        per=load_canonical_percentiles()
    except Exception:
        per=load("percentiles",["player_season_percentiles_long"])
    if per is None or per.empty:
        return pd.Series(np.nan,index=years,dtype=float)

    pidc=col(per,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(per,["Player","Player_Name","Display_Name","Name","player_name"])
    seac=col(per,["Season","season","Season_ID","SeasonEndYear","Season_End_Year","Year"])
    statc=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not seac or not statc:
        return pd.Series(np.nan,index=years,dtype=float)

    q=pd.DataFrame()
    if pidc and player_id is not None:
        q=per.loc[per[pidc].astype(str).str.strip().eq(str(player_id).strip())].copy()
    if q.empty and namec:
        wanted=str(player_name or "").replace("*","").strip().casefold()
        names=per[namec].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        q=per.loc[names.eq(wanted)].copy()
    if q.empty:
        return pd.Series(np.nan,index=years,dtype=float)

    wanted_stat=str(stat).strip().casefold()
    # Handle common display/source aliases without altering canonical statistic names.
    aliases={
        "ts_pct":{"ts_pct","ts%","ts"},
        "fg_pct":{"fg_pct","fg%"},
        "2p_pct":{"2p_pct","2p%"},
        "3p_pct":{"3p_pct","3p%"},
        "ft_pct":{"ft_pct","ft%"},
    }
    statset=aliases.get(wanted_stat,{wanted_stat})
    q=q.loc[q[statc].astype(str).str.strip().str.casefold().isin(statset)].copy()
    if q.empty:
        return pd.Series(np.nan,index=years,dtype=float)

    q["__pct_year"]=q[seac].map(_season_end_year)
    q=q.dropna(subset=["__pct_year"]).copy()
    if q.empty:
        return pd.Series(np.nan,index=years,dtype=float)
    q["__pct_year"]=q["__pct_year"].astype(int)

    pctcol=percentile_column(q,context)
    if not pctcol:
        # The canonical table may expose Era/Historical rather than Season.
        for fallback in (["Era","Historical"] if context=="Season" else
                         ["Season","Historical"] if context=="Era" else
                         ["Era","Season"]):
            pctcol=percentile_column(q,fallback)
            if pctcol: break
    if not pctcol:
        return pd.Series(np.nan,index=years,dtype=float)

    q["__pct"]=pd.to_numeric(q[pctcol],errors="coerce")
    q=q.drop_duplicates("__pct_year",keep="first").set_index("__pct_year")
    return q["__pct"].reindex([int(y) for y in years])

def _comparison_stat_percentile_columns(df, stat, context):
    prefixes = {
        "Season": ["Season_Percentile_", "Percentile_"],
        "Era": ["Era_Percentile_", "Season_Percentile_", "Percentile_"],
        "Historical": ["Historical_Percentile_", "Percentile_"],
    }.get(context, ["Season_Percentile_", "Percentile_"])
    normalized={re.sub(r"[^a-z0-9]","",str(c).lower()):c for c in df.columns}
    for prefix in prefixes:
        key=re.sub(r"[^a-z0-9]","",(prefix+stat).lower())
        if key in normalized:
            return normalized[key]
    return None


def _comparison_player_rows(source, requested, start_year, end_year):
    if source is None or source.empty:
        return pd.DataFrame(), None, None
    pidcol=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    scol=col(source,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    if not scol:
        return pd.DataFrame(), None, None

    target_id, target_name = resolve_player_identity(requested)
    work=source.copy()
    mask=pd.Series(False,index=work.index)
    if pidcol and target_id is not None:
        mask=work[pidcol].astype(str).str.strip().eq(str(target_id).strip())
    if not mask.any() and pcol:
        wanted=str(target_name or requested).replace("*","").strip().casefold()
        mask=work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)
    work=work.loc[mask].copy()
    if work.empty:
        return work, target_id, target_name

    work["__comparison_year"]=work[scol].map(_season_end_year)
    work=work.dropna(subset=["__comparison_year"]).copy()
    work["__comparison_year"]=work["__comparison_year"].astype(int)
    if start_year is not None:
        work=work.loc[work["__comparison_year"]>=start_year].copy()
    if end_year is not None:
        work=work.loc[work["__comparison_year"]<=end_year].copy()
    return work,target_id,target_name


def api_compare_players(player_a, player_b, start_a=None, end_a=None, start_b=None, end_b=None,
                        season_type="Regular Season", context="Season"):
    """Compare two players across an inclusive season range.

    Rate statistics use the same possession/minute/denominator weighting logic
    used by the canonical profile/era aggregation code. Additive value stats
    are summed. Season percentile columns are weighted by the same minutes
    available for each selected season.
    """
    def parse_year(v):
        if v in (None,"","Career"): return None
        s=str(v).strip()
        if re.fullmatch(r"\d{4}",s): return int(s)
        return _season_end_year(s)

    ranges=[]
    for s,e in [(start_a,end_a),(start_b,end_b)]:
        sy,ey=parse_year(s),parse_year(e)
        if sy is not None and ey is not None and sy>ey:
            sy,ey=ey,sy
        ranges.append((sy,ey))

    is_playoffs=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    source = load_playoff_source()[0] if is_playoffs else load("profiles",["player_season_profiles","season_profiles"])
    stats = PLAYOFF_STATS if is_playoffs else REGULAR_STATS
    per75 = PLAYOFF_PER75_STATS if is_playoffs else ERA_AVERAGE_PER75_REGULAR
    additive = PLAYOFF_ADDITIVE_STATS if is_playoffs else ERA_AVERAGE_ADDITIVE
    denom = ERA_AVERAGE_DENOMS

    rows_out=[]
    for player_index, requested in enumerate([player_a,player_b]):
        sy,ey=ranges[player_index]
        rows,pid,name=_comparison_player_rows(source,requested,sy,ey)
        if rows.empty:
            return {"found":False,"error":f"Could not find selected seasons for {requested}.","season_type":season_type}
        # If no range supplied, use the full available range for this player.
        actual_years=sorted(rows["__comparison_year"].unique().tolist())
        if not actual_years:
            return {"found":False,"error":f"No seasons available for {name or requested}.","season_type":season_type}

        stat_values={}
        stat_percentiles={}
        weight_col=col(rows,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
        if not weight_col:
            weight_col=col(rows,["MP","Minutes","minutes"])
        weights=pd.to_numeric(rows[weight_col],errors="coerce") if weight_col else pd.Series(1.0,index=rows.index)
        weights=weights.where(weights>0,1.0)

        for stat in stats:
            if stat not in rows.columns and _playoff_source_column(rows,stat) is None:
                continue
            scol=_playoff_source_column(rows,stat) if is_playoffs else stat
            if scol not in rows.columns:
                continue
            temp=rows.copy()
            if scol != stat:
                temp[stat]=temp[scol]
            value=_era_average_statistic(temp,stat,per75,additive,denom)
            stat_values[stat]=clean(value)

            pct_series=None
            try:
                years=rows["__comparison_year"].astype(int).tolist()
                if not is_playoffs:
                    pct_series=_comparison_canonical_regular_percentiles(
                        pid,name,years,stat,context
                    )
                else:
                    pctdf=_comparison_percentile_source(True)
                    pct_series=_comparison_percentile_lookup(
                        pctdf,pid,name,years,stat,context
                    )
                pct_series.index=rows.index
            except Exception:
                # Profile-source fallback if the dedicated percentile source
                # is unavailable.
                fc=col(rows,[
                    ("Season_Percentile_"+stat),
                    ("Era_Percentile_"+stat),
                    ("Historical_Percentile_"+stat),
                    ("Percentile_"+stat),
                ])
                if fc:
                    pct_series=pd.to_numeric(rows[fc],errors="coerce")

            if pct_series is not None:
                x=pd.DataFrame({"v":pct_series,"w":weights}).dropna()
                x=x[x.w>0]
                stat_percentiles[stat]=clean(
                    float((x.v*x.w).sum()/x.w.sum())
                ) if not x.empty else None
            else:
                stat_percentiles[stat]=None

        # Store selected season labels for transparency.
        season_labels=[_season_label_any(y) for y in actual_years]
        rows_out.append({
            "player_id":str(pid) if pid is not None else None,
            "player_name":name or str(requested),
            "seasons":season_labels,
            "start_season":season_labels[0],
            "end_season":season_labels[-1],
            "season_count":len(season_labels),
            "statistics":stat_values,
            "percentiles":stat_percentiles,
        })

    return {
        "found":True,
        "season_type":"Playoffs" if is_playoffs else "Regular Season",
        "percentile_context":context,
        "requested_start":_season_label_any(sy) if sy else "All selected seasons",
        "requested_end":_season_label_any(ey) if ey else "All selected seasons",
        "players":rows_out,
        "weighting":{
            "per75":"Possession-weighted when possession estimates exist; otherwise minute-weighted.",
            "additive":"Summed across selected seasons.",
            "percentages":"Weighted by their natural attempt denominator.",
            "impact":"Minute-weighted when no natural denominator exists.",
            "percentiles":"Weighted by available minutes/possessions for the selected seasons.",
        },
        "statistics":stats,
    }


def api_stat_registry():
    canonical=PATHS.get("statistic_registry")
    if canonical and canonical.exists():
        registry=read_csv(canonical,low_memory=False)
    else:
        try:
            registry=load_exact_csv("stat_registry","player_statistic_registry_v1.csv")
        except Exception:
            try:
                registry=load_exact_csv("taxonomy","player_statistic_taxonomy_v1.csv")
            except Exception:
                # The finalized v3 registry is already the canonical source.
                # If the configured file is absent, synthesize the registry
                # directly from the 46-stat contract used by the website.
                registry=pd.DataFrame({"Statistic": PLAYOFF_STATS})
    # AST:TOV is part of the canonical 46-stat contract. Older registry CSVs
    # may predate it, so expose it as a selectable Big Board statistic while
    # leaving the canonical value untouched.
    stat_col=col(registry,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    existing=set(registry[stat_col].astype(str).str.strip()) if stat_col else set()
    if "AST_TOV" not in existing:
        registry=pd.concat([registry, pd.DataFrame([{"Statistic":"AST_TOV","Description":"Assist-to-turnover ratio"}])],
                           ignore_index=True)
    out=[]
    for r in registry.to_dict("records"):
        x={k:clean(v) for k,v in r.items()}
        x["statistic"]=x.get("Statistic") or x.get("Stat") or x.get("Statistic_ID") or x.get("Name")
        out.append(x)
    return {"statistics":out}


def _team_columns(df):
    return {
        "team": col(df, ["Team","Team_Abbreviation","TeamAbbreviation","Tm","TeamID","Franchise","Team_Name"]),
        "season": col(df, ["Season","season"]),
        "player": col(df, ["Player_Name","Player","Name","player_name"]),
        "pid": col(df, ["Player_ID","PlayerId","PlayerID","player_id"]),
        "mp": col(df, ["MP","Minutes","Minutes_Played"]),
        "pts": col(df, ["PTS","Points"]),
        "wins": col(df, ["W","Wins"]),
        "losses": col(df, ["L","Losses"]),
    }

def _build_team_index_background():
    """Build the compact team cache without blocking the HTTP request."""
    global TEAM_BUILD_STATE
    with TEAM_BUILD_LOCK:
        if TEAM_BUILD_STATE["status"]=="building":
            return
        TEAM_BUILD_STATE={"status":"building","started_at":time.time(),"finished_at":None,"error":None}
    try:
        # Execute the same canonical precompute script in-process so it uses
        # this API's resolved NBA_PER75_ROOT and does not spawn another server.
        script=Path(__file__).resolve().parent / "precompute_team_index_v1.py"
        ns={"__name__":"__team_precompute_background__","__file__":str(script)}
        code=script.read_text(encoding="utf-8")
        exec(compile(code,str(script),"exec"),ns,ns)
        TEAM_BUILD_STATE={"status":"ready","started_at":TEAM_BUILD_STATE["started_at"],
                          "finished_at":time.time(),"error":None}
    except Exception as exc:
        TEAM_BUILD_STATE={"status":"error","started_at":TEAM_BUILD_STATE.get("started_at"),
                          "finished_at":time.time(),"error":f"{type(exc).__name__}: {exc}"}

def _ensure_team_index_build():
    if _read_team_index_cache("Regular Season") is not None:
        return "ready"
    with TEAM_BUILD_LOCK:
        status=TEAM_BUILD_STATE["status"]
    if status=="idle":
        threading.Thread(target=_build_team_index_background,daemon=True).start()
        return "building"
    return status

def _read_team_index_cache(season_type="Regular Season"):
    """Read the compact precomputed Team index. This must be fast."""
    path=TEAM_INDEX_CACHE
    if not path.exists():
        return None
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload,dict) and payload.get("version")==2:
            by_type=payload.get("season_types",{})
            return by_type.get(season_type)
    except Exception:
        return None
    return None

def _restore_team_opponent_data_from_prior_builds():
    """Recover the most populated Team data from prior Website builds."""
    marker=CACHE.get("__team_opponent_restore_v2__")
    if marker is not None: return marker
    canonical=SITE_ROOT / "data" / "nba_per75_team_master_enriched.csv"
    if not canonical.exists(): canonical=SITE_ROOT / "team_data" / "nba_per75_team_master.csv"
    if not canonical.exists(): CACHE["__team_opponent_restore_v2__"]="no_canonical"; return "no_canonical"
    try: cur=pd.read_csv(canonical,low_memory=False)
    except Exception: CACHE["__team_opponent_restore_v2__"]="read_failed"; return "read_failed"
    needed=["Opponent_TOV%","Opponent_eFG%","Logo_ID","Logo_File","Logo_Source","Logo_Source_URL"]
    for c in needed:
        if c not in cur.columns: cur[c]=np.nan
    def score(df):
        a=int(pd.to_numeric(df.get("Opponent_TOV%",pd.Series(dtype=float)),errors="coerce").notna().sum())
        b=int(pd.to_numeric(df.get("Opponent_eFG%",pd.Series(dtype=float)),errors="coerce").notna().sum())
        logos=int(df.get("Logo_ID",pd.Series(dtype=object)).notna().sum())
        return a+b,logos
    best=None; best_score=(-1,-1); best_path=None
    roots=[ROOT.parent,ROOT.parent.parent,ROOT.parent.parent.parent]
    seen=set()
    for base in roots:
        if not base.exists(): continue
        try: dirs=[d for d in base.rglob("*") if d.is_dir() and re.search(r"website(17[7-9]|18[0-5])$",d.name,re.I)]
        except Exception: dirs=[]
        for d in dirs:
            try:
                key=str(d.resolve())
                if key in seen or d.resolve()==ROOT.resolve(): continue
                seen.add(key)
            except Exception: pass
            for cand in [d/"data"/"nba_per75_team_master_enriched.csv",d/"team_data"/"nba_per75_team_master.csv"]:
                if not cand.exists(): continue
                try: df=pd.read_csv(cand,low_memory=False)
                except Exception: continue
                if not {"Season","Team"}.issubset(df.columns): continue
                sc=score(df)
                if sc>best_score: best,best_score,best_path=df,sc,cand
    if best is None or best_score[0]<=0:
        CACHE["__team_opponent_restore_v2__"]="none_found"; return "none_found"
    key_cols=[c for c in ["Season","Team","Season_Type"] if c in cur.columns and c in best.columns]
    if not key_cols: key_cols=["Season","Team"]
    b=best.copy()
    for c in key_cols: b[c]=b[c].astype(str).str.strip(); cur[c]=cur[c].astype(str).str.strip()
    keep=key_cols+[c for c in needed if c in b.columns]
    b=b[keep].drop_duplicates(key_cols,keep="last")
    merged=cur.merge(b,on=key_cols,how="left",suffixes=("","__prior"))
    for c in needed:
        prior=f"{c}__prior"
        if prior not in merged.columns: continue
        if c in {"Logo_ID","Logo_File","Logo_Source","Logo_Source_URL"}:
            merged[c]=merged[c].where(merged[c].notna() & (merged[c].astype(str).str.strip()!=""),merged[prior])
        else:
            old=pd.to_numeric(merged[c],errors="coerce"); new=pd.to_numeric(merged[prior],errors="coerce")
            merged[c]=old.where(old.notna(),new)
        merged.drop(columns=[prior],inplace=True)
    merged.to_csv(canonical,index=False)
    mirror=SITE_ROOT/"team_data"/"nba_per75_team_master.csv"
    try: merged.to_csv(mirror,index=False)
    except Exception: pass
    result=f"restored {best_score[0]} opponent cells / {best_score[1]} logo IDs from {best_path}"
    CACHE["__team_opponent_restore_v2__"]=result; return result


def _repair_logo_metadata_fast():
    """Repair Logo_ID/Logo_File using one historical franchise metadata fetch."""
    master=SITE_ROOT/"data"/"nba_per75_team_master_enriched.csv"
    if not master.exists(): return "no_master"
    try: df=pd.read_csv(master,low_memory=False)
    except Exception as exc: return f"read_failed:{exc}"
    for c in ["Logo_ID","Logo_File","Logo_Source","Logo_Source_URL"]:
        if c not in df.columns: df[c]=np.nan
    if int(df["Logo_ID"].notna().sum())>=len(df)*0.95 and not df["Logo_ID"].astype(str).str.startswith("nba-").any():
        return f"existing ({int(df['Logo_ID'].notna().sum())} logo IDs)"
    url="https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/franchises.json"
    try:
        req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req,timeout=30) as r: franchises=json.loads(r.read().decode("utf-8","ignore"))
    except Exception as exc: return f"metadata_fetch_failed:{exc}"
    def norm_logo(x): return re.sub(r"[^a-z0-9]+","",str(x).replace("*","").lower())
    mapping={}; base={}
    for fr in franchises:
        if fr.get("id"): base[norm_logo(fr.get("name"))]=fr.get("id")
        for team in fr.get("teams",[]):
            if team.get("league")=="NBA" and team.get("id") and team.get("year"):
                mapping[(norm_logo(team.get("name")),int(team.get("year")))]=team.get("id")
    matched=0
    for i,r in df.iterrows():
        season=str(r.get("Season","")); m=re.match(r"^(\d{4})-(\d{2})$",season); year=int(m.group(1))+1 if m else None
        name=norm_logo(r.get("Team","")); fid=mapping.get((name,year)) if year else None
        if not fid and year:
            # Conservative city/franchise prefix fallback.
            t=norm_logo(r.get("Team",""))
            cand=[v for (n,y),v in mapping.items() if y==year and (n.startswith(t[:6]) or t.startswith(n[:6]))]
            if len(set(cand))==1: fid=cand[0]
        if not fid: fid=base.get(name)
        if fid:
            df.at[i,"Logo_ID"]=fid
            df.at[i,"Logo_File"]=f"team-logos/{fid}.png"
            df.at[i,"Logo_Source"]="TGOlson/nba-logos"
            df.at[i,"Logo_Source_URL"]="https://github.com/TGOlson/nba-logos"
            matched+=1
    df.to_csv(master,index=False)
    try: df.to_csv(SITE_ROOT/"team_data"/"nba_per75_team_master.csv",index=False)
    except Exception: pass
    return f"logo metadata matched {matched}/{len(df)}"

def _apply_brescou_opponent_factors():
    """Fast bulk restore of Opponent TOV% / Opponent eFG%.

    Uses Brescou's single regular-season Four Factors CSV (1996-97 through
    2022-23). The source stores percentages as fractions (0-1); the project
    canonical Team master stores percentages as 0-100. Existing non-null Team
    values always win, so this is a fill-only repair and never overwrites a
    previously working value.
    """
    master=SITE_ROOT/"data"/"nba_per75_team_master_enriched.csv"
    if not master.exists(): return "no_master"
    try:
        df=pd.read_csv(master,low_memory=False)
    except Exception as exc:
        return f"read_failed:{exc}"
    for c in ["Opponent_TOV%","Opponent_eFG%"]:
        if c not in df.columns: df[c]=np.nan

    # If both opponent columns already have meaningful coverage, do nothing.
    existing_tov=int(pd.to_numeric(df["Opponent_TOV%"],errors="coerce").notna().sum())
    existing_efg=int(pd.to_numeric(df["Opponent_eFG%"],errors="coerce").notna().sum())
    if existing_tov>100 and existing_efg>100:
        return f"existing ({existing_tov} TOV, {existing_efg} eFG)"

    cache_dir=SITE_ROOT/"local_api"/"cache"/"team_sources"
    cache_dir.mkdir(parents=True,exist_ok=True)
    src=cache_dir/"brescou_team_stats_four_factors_rs.csv"
    url="https://raw.githubusercontent.com/Brescou/NBA-dataset-stats-player-team/main/team/team_stats_four_factors_rs.csv"
    try:
        if not src.exists() or src.stat().st_size<1000:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 NBA-PER75"})
            with urlopen(req,timeout=30) as r: src.write_bytes(r.read())
    except Exception as exc:
        if not src.exists(): return f"brescou_download_failed:{type(exc).__name__}: {exc}"

    try:
        b=pd.read_csv(src,low_memory=False)
    except Exception as exc:
        return f"brescou_read_failed:{type(exc).__name__}: {exc}"
    required={"TEAM_NAME","SEASON","OPP_EFG_PCT","OPP_TOV_PCT"}
    if not required.issubset(b.columns):
        return "brescou_missing_columns"

    def norm_name(x):
        x=str(x).replace("*","").strip().casefold()
        x=re.sub(r"[^a-z0-9]","",x)
        aliases={
            "newjerseynets":"newjerseynets",
            "newyorkknicks":"newyorkknicks",
            "seattlesupersonics":"seattlesupersonics",
            "washingtonbullets":"washingtonbullets",
            "washingtonwizards":"washingtonwizards",
            "charlottebobcats":"charlottebobcats",
            "charlottehornets":"charlottehornets",
            "neworleanshornets":"neworleanshornets",
            "neworleanspelicans":"neworleanspelicans",
            "oklahomacitythunder":"oklahomacitythunder",
            "vancouvergrizzlies":"vancouvergrizzlies",
            "memphisgrizzlies":"memphisgrizzlies",
            "sanantoniospurs":"sanantoniospurs",
            "goldenstatewarriors":"goldenstatewarriors",
            "losangelesclippers":"losangelesclippers",
            "losangeleslakers":"losangeleslakers",
            "sacramento":"sacramentokings",
            "kings":"sacramentokings",
        }
        return aliases.get(x,x)

    # Canonical season/team key. Preserve the site's season labels exactly.
    b["__team_key"]=b["TEAM_NAME"].map(norm_name)
    b["__season_key"]=b["SEASON"].astype(str).str.strip()
    b=b.drop_duplicates(["__team_key","__season_key"],keep="last")
    d=df.copy()
    d["__team_key"]=d["Team"].map(norm_name)
    d["__season_key"]=d["Season"].astype(str).str.strip()
    # Merge instead of relying on MultiIndex.map; this is deterministic and
    # preserves the Team master row order.
    patch=b[["__team_key","__season_key","OPP_TOV_PCT","OPP_EFG_PCT"]].copy()
    patch["OPP_TOV_PCT"]=pd.to_numeric(patch["OPP_TOV_PCT"],errors="coerce")*100.0
    patch["OPP_EFG_PCT"]=pd.to_numeric(patch["OPP_EFG_PCT"],errors="coerce")*100.0
    d=d.merge(patch,on=["__team_key","__season_key"],how="left",suffixes=("","__b"))
    old_tov=pd.to_numeric(d["Opponent_TOV%"],errors="coerce")
    old_efg=pd.to_numeric(d["Opponent_eFG%"],errors="coerce")
    d["Opponent_TOV%"]=old_tov.where(old_tov.notna(),pd.to_numeric(d["OPP_TOV_PCT"],errors="coerce"))
    d["Opponent_eFG%"]=old_efg.where(old_efg.notna(),pd.to_numeric(d["OPP_EFG_PCT"],errors="coerce"))
    d.drop(columns=[x for x in ["__team_key","__season_key","OPP_TOV_PCT","OPP_EFG_PCT"] if x in d.columns],inplace=True)
    d.to_csv(master,index=False)
    try: d.to_csv(SITE_ROOT/"team_data"/"nba_per75_team_master.csv",index=False)
    except Exception: pass
    nt=int(pd.to_numeric(d["Opponent_TOV%"],errors="coerce").notna().sum())
    ne=int(pd.to_numeric(d["Opponent_eFG%"],errors="coerce").notna().sum())
    return f"Brescou bulk fill: {nt} TOV, {ne} eFG"

def _ensure_team_data_fast():
    """Restore Team opponent stats quickly, without BRef/RealGM scraping."""
    master=SITE_ROOT/"data"/"nba_per75_team_master_enriched.csv"
    if not master.exists(): return "no_master"
    try:
        df=pd.read_csv(master,low_memory=False)
    except Exception as exc: return f"read_failed:{exc}"
    for c in ["Opponent_TOV%","Opponent_eFG%","Logo_ID","Logo_File","Logo_Source","Logo_Source_URL"]:
        if c not in df.columns: df[c]=np.nan
    before=(int(pd.to_numeric(df["Opponent_TOV%"],errors="coerce").notna().sum()),
            int(pd.to_numeric(df["Opponent_eFG%"],errors="coerce").notna().sum()))
    try:
        result=_apply_brescou_opponent_factors()
    except Exception as exc:
        result=f"Brescou fill failed: {type(exc).__name__}: {exc}"
    try:
        df2=pd.read_csv(master,low_memory=False)
        after=(int(pd.to_numeric(df2["Opponent_TOV%"],errors="coerce").notna().sum()),
               int(pd.to_numeric(df2["Opponent_eFG%"],errors="coerce").notna().sum()))
    except Exception:
        after=before
    return f"{result}; coverage {before[0]}/{before[1]} -> {after[0]}/{after[1]}"


def _load_team_source():
    """Fallback only for the precompute script / team detail.

    The Team index endpoint itself never calls this function. This prevents a
    missing cache from turning a page request into a multi-second/full-file
    pandas load.
    """
    key="__team_source_v3__"
    if key in CACHE:return CACHE[key]
    f=find_csv(PATHS["master"],["nba_per75_master","master"])
    if not f: raise FileNotFoundError(f"No master CSV found: {PATHS['master']}")
    header=read_csv(f,nrows=0,low_memory=False)
    c=_team_columns(header)
    if not c["team"] or not c["season"]:
        CACHE[key]=None;return None
    wanted=list(dict.fromkeys([x for x in [c["team"],c["season"],c["player"],c["pid"],c["mp"],c["pts"],c["wins"],c["losses"]] if x]))
    CACHE[key]=read_csv(f,usecols=wanted,low_memory=False)
    return CACHE[key]


TEAM_ANALYTICS_STATS = [
    ("rDRtg","rDRtg","lower"),
    ("rORtg","rORtg","higher"),
    ("NRtg","NRtg","higher"),
    ("Pace","Pace","higher"),
    ("rPace","rPace","higher"),
    ("ORtg","ORtg","higher"),
    ("DRtg","DRtg","lower"),
    ("PTS/100","PTS_per100","higher"),
    ("TS%","TS_pct","higher"),
    ("eFG%","eFG_pct","higher"),
    ("3PAr","3PAr","higher"),
    ("TOV%","TOV_pct","lower"),
    ("ORB%","ORB_pct","higher"),
    ("FTr","FTr","higher"),
    ("Opp TOV%","Opp_TOV_pct","higher"),
    ("Opp eFG%","Opp_eFG_pct","higher"),
]

def _norm_col(s):
    return re.sub(r"[^a-z0-9]","",str(s).lower())

def _find_col(cols, names):
    mp={_norm_col(c):c for c in cols}
    for n in names:
        if _norm_col(n) in mp:return mp[_norm_col(n)]
    return None

def _find_team_analytics_source(season_type="Regular Season"):
    """Find the best genuine team-season source, preferring populated opponent data.

    The enriched Team master was working before the global-unit changes. The
    regression came from always preferring the bundled (blank) copy over the
    user's already-enriched canonical Team file. Compare all legitimate
    candidates and select the one with the most populated opponent fields.
    """
    base=Path(os.environ.get("NBA_PER75_ROOT", str(ROOT)))
    nba_per75_root=Path(os.environ.get("NBA_PER75_ROOT", str(base.parent/"NBA_Per75")))
    candidates=[]
    seen=set()

    def add_candidate(p):
        p=Path(p)
        try: key=str(p.resolve())
        except Exception: key=str(p)
        if not p.exists() or key in seen: return
        seen.add(key); candidates.append(p)

    # 1. Bundled copy, established external NBA_Per75 canonical copy, and
    #    the ordinary team_data mirror.
    add_candidate(Path(__file__).resolve().parents[1]/"data"/"nba_per75_team_master_enriched.csv")
    add_candidate(nba_per75_root/"data"/"nba_per75_team_master_enriched.csv")
    add_candidate(nba_per75_root/"team_data"/"nba_per75_team_master.csv")
    add_candidate(Path(__file__).resolve().parents[1]/"team_data"/"nba_per75_team_master.csv")

    # 2. Nearby Website builds can contain the enriched copy produced by the
    #    Team repair script. Never prefer them merely because they are newer.
    for root in [Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[3]]:
        try:
            for d in root.rglob("*"):
                if d.is_dir() and re.search(r"website(17[7-9]|18[0-6])$", d.name, re.I):
                    add_candidate(d/"data"/"nba_per75_team_master_enriched.csv")
                    add_candidate(d/"team_data"/"nba_per75_team_master.csv")
        except Exception:
            pass

    # 3. Other genuine team-season CSVs as fallback.
    try:
        for p in base.rglob("*.csv"):
            n=p.name.lower()
            if any(x in n for x in ("nba_per75_master","player_","percentile","profile","identity","taxonomy","qualification","visualization","comparison")):
                continue
            if any(x in n for x in ("team","teams","standings","franchise")):
                add_candidate(p)
    except Exception:
        pass

    def inspect(p):
        try:
            h=_PANDAS_READ_CSV(p,nrows=0,low_memory=False)
            cols=list(h.columns)
            tc=_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
            sc=_find_col(cols,["Season","season"])
            stc=_find_col(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"])
            oc=_find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"])
            dc=_find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"])
            pc=_find_col(cols,["Pace","PACE"])
            if not (tc and sc and oc and dc and pc): return None
            if season_type=="Playoffs" and stc is None and not re.search(r"playoff|postseason",p.name,re.I): return None
            ot=_find_col(cols,["Opp_TOV_pct","Opp TOV%","Opponent_TOV_pct","Opponent TOV%","Opponent_TOV%","OppTOV%","Def_TOV_pct","Def TOV%","Defensive_TOV_pct","Defensive TOV%","TOV%.1","TOV_pct.1"])
            oe=_find_col(cols,["Opp_eFG_pct","Opp eFG%","Opponent_eFG_pct","Opponent eFG%","Opponent_eFG%","OppeFG%","Def_eFG_pct","Def eFG%","Defensive_eFG_pct","Defensive eFG%","eFG%.1","eFG_pct.1","EFG_PCT.1"])
            logo=_find_col(cols,["Logo_ID","LogoID","logo_id"])
            # Only inspect these small columns; this does not run enrichment.
            use=[tc,sc]+[x for x in [ot,oe,logo] if x]
            d=_PANDAS_READ_CSV(p,usecols=list(dict.fromkeys(use)),low_memory=False)
            opp=0
            if ot: opp+=pd.to_numeric(d[ot],errors="coerce").notna().sum()
            if oe: opp+=pd.to_numeric(d[oe],errors="coerce").notna().sum()
            logos=int(d[logo].notna().sum()) if logo else 0
            return (int(opp),logos,tc,sc,stc,ot,oe,p)
        except Exception:
            return None

    inspected=[x for p in candidates if (x:=inspect(p)) is not None]
    if not inspected: return None
    # Opponent coverage is the first priority. Logos are second. Stable
    # preference for the bundled/external canonical source breaks ties.
    inspected.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return inspected[0][-1]


def _team_metric_columns(cols):
    mapping={
        "team":_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"]),
        "season":_find_col(cols,["Season","season"]),
        "season_type":_find_col(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"]),
        "ortg":_find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"]),
        "drtg":_find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"]),
        "pace":_find_col(cols,["Pace","PACE"]),
        "rpace":_find_col(cols,["rPace","RPace","Relative_Pace","RelativePace"]),
        "rortg":_find_col(cols,["rORtg","rORTG","Relative_ORtg","Relative_ORTG"]),
        "rdrtg":_find_col(cols,["rDRtg","rDRTG","Relative_DRtg","Relative_DRTG"]),
        "nrtg":_find_col(cols,["NRtg","NRTG","Net_Rtg","NetRtg","NetRating"]),
        "pts100":_find_col(cols,["PTS_per100","PTS/100","PTS_per_100","Points_per100","ORtg","ORTG"]),
        "tspct":_find_col(cols,["TS_pct","TS%","TS_PCT"]),
        "efgpct":_find_col(cols,["eFG_pct","eFG%","EFG_PCT"]),
        "threepar":_find_col(cols,["3PAr","3PA_rate","ThreePA_Rate"]),
        "tovpct":_find_col(cols,["TOV_pct","TOV%","TOV_PCT"]),
        "orbpct":_find_col(cols,["ORB_pct","ORB%","ORB_PCT"]),
        "ftr":_find_col(cols,["FTr","FT_Rate","FTR"]),
        "logo_id":_find_col(cols,["Logo_ID","LogoID","logo_id"]),
        "logo_file":_find_col(cols,["Logo_File","LogoFile","logo_file"]),
        "logo_source":_find_col(cols,["Logo_Source","LogoSource","logo_source"]),
        "opp_tovpct":_find_col(cols,[
            "Opp_TOV_pct","Opp TOV%","Opponent_TOV_pct","Opponent TOV%","OppTOV%",
            "Opponent_TOV%","Opponent TOV Pct","Opponent_TOV_PCT","Opp TOV Pct","TOV_pct_Opp",
            "TOV%_Opp","Opp_TOV_PCT","OppTOV_pct","OpponentTOV_pct",
            "OpponentTurnoverPct","Opponent_Turnover_Percentage"
        ]),
        "opp_efgpct":_find_col(cols,[
            "Opp_eFG_pct","Opp eFG%","Opponent_eFG_pct","Opponent eFG%","OppeFG%",
            "Opponent_eFG%","Opponent eFG Pct","Opponent_eFG_PCT","Opp eFG Pct","eFG_pct_Opp",
            "eFG%_Opp","Opp_eFG_PCT","OppeFG_pct","OpponentEFG_pct",
            "OpponentEffectiveFGPct","Opponent_Effective_FG_Percentage","eFG%.1","eFG_pct.1","EFG_PCT.1",
            "Def_eFG_pct","Def eFG%","Defensive_eFG_pct","Defensive eFG%",
            "Defensive_eFG%","DefeFG%","Opp eFG%"
        ]),
    }
    norm={_norm_col(c):c for c in cols}
    for n,cname in norm.items():
        if not mapping["opp_tovpct"] and "opp" in n and "tov" in n and ("pct" in n or "percent" in n):
            mapping["opp_tovpct"]=cname
        if not mapping["opp_efgpct"] and "opp" in n and "efg" in n and ("pct" in n or "percent" in n):
            mapping["opp_efgpct"]=cname
    return mapping


def _num(v):
    try:
        x=float(v)
        return None if not np.isfinite(x) else x
    except Exception:return None

def _build_team_analytics_cache():
    """Build team analytics only from genuine team-season records.

    Never aggregate player-season ratings into team ratings. If the project
    does not contain a team-season source, fail explicitly instead of creating
    false values (e.g. a bogus +14.63 Pacers NRtg).
    """
    season_types={}
    source_report={}
    for requested in ("Regular Season","Playoffs"):
        path=_find_team_analytics_source(requested)
        source_report[requested]=str(path) if path else None
        if not path:
            continue

        h=read_csv(path,nrows=0,low_memory=False)
        c=_team_metric_columns(h.columns)
        if not (c["team"] and c["season"] and c["ortg"] and c["drtg"] and c["pace"]):
            continue
        wanted=list(dict.fromkeys([x for x in c.values() if x]))
        d=read_csv(path,usecols=wanted,low_memory=False)
        d[c["team"]]=d[c["team"]].astype(str).str.strip()

        # Remove aggregate player/team labels permanently.
        d=d[~d[c["team"]].str.upper().str.match(
            r"^(?:2TM|3TM|4TM|TOT|TOTAL)(?:$|[\s_-])",na=False
        )].copy()

        # Separate playoff/regular records when source contains season type.
        if c.get("season_type"):
            st=d[c["season_type"]].astype(str).str.lower()
            is_po=st.str.contains("playoff|postseason",regex=True,na=False)
            if requested=="Playoffs":
                if is_po.any(): d=d[is_po]
            else:
                if is_po.any(): d=d[~is_po]

        for key,colname in c.items():
            if colname and key not in ("team","season","season_type"):
                d[colname]=pd.to_numeric(d[colname],errors="coerce")

        rows=[]
        for (tm,se),g in d.groupby([c["team"],c["season"]],sort=False):
            # A genuine team source should have one team-season record. If it
            # has duplicate rows, use the first complete team-season record,
            # never an average of player rows.
            g=g.dropna(subset=[c["ortg"],c["drtg"],c["pace"]])
            if g.empty: continue
            rec=g.iloc[0]
            r={"team":str(tm),"season":str(se),"season_type":requested,
               "source":str(path)}
            # Historical logo identity travels with the same team-season row.
            if c.get("logo_id") and pd.notna(rec[c["logo_id"]]):
                r["logo_id"]=str(rec[c["logo_id"]])
            else:
                safe=re.sub(r"[^a-z0-9]+","-",str(tm).lower()).strip("-")
                yr=re.search(r"(\d{4})$",str(se))
                r["logo_id"]=f"nba-{safe}-{yr.group(1) if yr else se}"
            if c.get("logo_file") and pd.notna(rec[c["logo_file"]]):
                r["logo_file"]=str(rec[c["logo_file"]])
            if c.get("logo_source") and pd.notna(rec[c["logo_source"]]):
                r["logo_source"]=str(rec[c["logo_source"]])
            for key,colname in c.items():
                if key in ("team","season","season_type") or not colname: continue
                v=rec[colname]
                if pd.notna(v): r[key]=float(v)

            # Guard against accidentally ingesting a player-level source.
            if r.get("nrtg") is not None:
                implied=r["ortg"]-r["drtg"]
                if abs(implied-r["nrtg"])>0.15:
                    r["nrtg"]=implied
            else:
                r["nrtg"]=r["ortg"]-r["drtg"]
            rows.append(r)

        # Correct relative metrics within each season. If the source already
        # provides them, retain them only if they agree with team-level values.
        by={}
        for r in rows: by.setdefault(r["season"],[]).append(r)
        for rs in by.values():
            # League/team mean is used as the baseline. The team source itself
            # is the population; no player-level weighting is involved.
            ov=[r["ortg"] for r in rs if r.get("ortg") is not None]
            dv=[r["drtg"] for r in rs if r.get("drtg") is not None]
            pv=[r["pace"] for r in rs if r.get("pace") is not None]
            mo=sum(ov)/len(ov) if ov else None
            md=sum(dv)/len(dv) if dv else None
            mp=sum(pv)/len(pv) if pv else None
            for r in rs:
                r["nrtg"]=r["ortg"]-r["drtg"]
                if mo is not None:r["rortg"]=r["ortg"]-mo
                if md is not None:r["rdrtg"]=r["drtg"]-md
                if mp is not None:r["rpace"]=r["pace"]-mp

        season_types[requested]={
            "rows":rows,
            "seasons":sorted({r["season"] for r in rows},reverse=True),
            "source":str(path)
        }

    if not season_types:
        raise FileNotFoundError(
            "No genuine team-season source found. Expected Team, Season, "
            "ORtg, DRtg and Pace. The player master is intentionally rejected."
        )

    all_rows=[r for v in season_types.values() for r in v["rows"]]
    payload={
        "version":18,
        "season_types":season_types,
        "rows":all_rows,
        "seasons":sorted({r["season"] for r in all_rows},reverse=True),
        "source_report":source_report,
        "opponent_columns":{
            st:{k:v for k,v in _team_metric_columns(
                read_csv(Path(src),nrows=0,low_memory=False).columns
            ).items() if k in ("opp_tovpct","opp_efgpct")}
            for st,src in source_report.items() if src
        },
        "stats":[
            {"label":label,"key":key,"direction":direction}
            for label,key,direction in TEAM_ANALYTICS_STATS
        ]
    }
    TEAM_ANALYTICS_CACHE.parent.mkdir(parents=True,exist_ok=True)
    TEAM_ANALYTICS_CACHE.write_text(json.dumps(payload,separators=(",",":")),encoding="utf-8")
    return payload


def _team_analytics_payload():
    if TEAM_ANALYTICS_CACHE.exists():
        try:
            p=json.loads(TEAM_ANALYTICS_CACHE.read_text(encoding="utf-8"))
            if p.get("version")==18 and p.get("season_types"):
                return p
        except Exception:
            pass
    return _build_team_analytics_cache()



_TEAM_STAT_KEY_MAP = {
    "rDRtg":"rdrtg","rORtg":"rortg","NRtg":"nrtg","Pace":"pace","rPace":"rpace",
    "ORtg":"ortg","DRtg":"drtg","PTS/100":"pts100","TS%":"tspct",
    "eFG%":"efgpct","3PAr":"threepar","TOV%":"tovpct","ORB%":"orbpct","FTr":"ftr","Opp TOV%":"opp_tovpct","Opp eFG%":"opp_efgpct",
    "rdrtg":"rdrtg","rortg":"rortg","nrtg":"nrtg","pace":"pace","rpace":"rpace","ortg":"ortg","drtg":"drtg",
    "pts100":"pts100","tspct":"tspct","efgpct":"efgpct","threepar":"threepar",
    "tovpct":"tovpct","orbpct":"orbpct","ftr":"ftr","opp_tovpct":"opp_tovpct","opp_efgpct":"opp_efgpct"
}
_TEAM_DISPLAY_STATS = [
    ("rDRtg","Relative DRtg","lower"),("rORtg","Relative ORtg","higher"),
    ("NRtg","NRtg","higher"),("Pace","Pace","higher"),("rPace","Relative Pace","higher"),("ORtg","ORtg","higher"),
    ("DRtg","DRtg","lower"),("PTS/100","PTS/100","higher"),("TS%","TS%","higher"),
    ("eFG%","eFG%","higher"),("3PAr","3PAr","higher"),("TOV%","TOV%","lower"),
    ("ORB%","ORB%","higher"),("FTr","FTr","higher"),
    ("Opp TOV%","Opponent TOV%","higher"),("Opp eFG%","Opponent eFG%","lower")
]

def _is_multi_team_label(team):
    s=str(team or "").strip().upper()
    return bool(re.fullmatch(r"[234]TM", s) or re.fullmatch(r"[234][- ]?TEAM", s))

def _team_clean_rows(rows):
    return [r for r in rows if not _is_multi_team_label(r.get("team"))]

def _team_percentile(value, population, higher=True):
    vals=pd.to_numeric(pd.Series(population),errors="coerce").dropna()
    try:x=float(value)
    except Exception:return None
    if vals.empty:return None
    if len(vals)==1:return 100.0
    # Percentile is the percentage of qualified team-seasons at or below the
    # value when higher is better; invert for lower-is-better statistics.
    if higher:
        return float((vals < x).sum() + 0.5*(vals == x).sum()) / float(len(vals)-1) * 100.0
    return float((vals > x).sum() + 0.5*(vals == x).sum()) / float(len(vals)-1) * 100.0

def _team_year_number(season):
    return _season_end_year(season)

def _team_era_key(season):
    return _era_key(season)

_TEAM_DISPLAY_NAMES = {
    # Current / commonly used abbreviations
    "ATL":"Atlanta Hawks","BOS":"Boston Celtics","BKN":"Brooklyn Nets",
    "BRK":"Brooklyn Nets","CHA":"Charlotte Hornets","CHH":"Charlotte Hornets",
    "CHI":"Chicago Bulls","CLE":"Cleveland Cavaliers","DAL":"Dallas Mavericks",
    "DEN":"Denver Nuggets","DET":"Detroit Pistons","GSW":"Golden State Warriors",
    "GS":"Golden State Warriors","HOU":"Houston Rockets","IND":"Indiana Pacers",
    "LAC":"Los Angeles Clippers","LAL":"Los Angeles Lakers","MEM":"Memphis Grizzlies",
    "MIA":"Miami Heat","MIL":"Milwaukee Bucks","MIN":"Minnesota Timberwolves",
    "NOP":"New Orleans Pelicans","NOH":"New Orleans Hornets","NYK":"New York Knicks",
    "NY":"New York Knicks","OKC":"Oklahoma City Thunder","ORL":"Orlando Magic",
    "PHI":"Philadelphia 76ers","PHX":"Phoenix Suns","PHO":"Phoenix Suns",
    "POR":"Portland Trail Blazers","SAC":"Sacramento Kings","SAS":"San Antonio Spurs",
    "SA":"San Antonio Spurs","TOR":"Toronto Raptors","UTA":"Utah Jazz",
    "WAS":"Washington Wizards","WSH":"Washington Wizards",
    # Historical franchise abbreviations / legacy labels
    "SEA":"Seattle SuperSonics","NJN":"New Jersey Nets","VAN":"Vancouver Grizzlies",
    "CHH":"Charlotte Hornets","NO":"New Orleans Pelicans","NOK":"New Orleans/Oklahoma City Hornets",
    "KCK":"Kansas City Kings","KCO":"Kansas City-Omaha Kings","CIN":"Cincinnati Royals",
    "SDC":"San Diego Clippers","SD":"San Diego Clippers","BUF":"Buffalo Braves",
    "BAL":"Baltimore Bullets","CAP":"Capital Bullets","WSB":"Washington Bullets",
    "FTW":"Fort Wayne Pistons","SYR":"Syracuse Nationals","ROC":"Rochester Royals",
    "STL":"St. Louis Hawks","MLH":"Milwaukee Hawks","TRI":"Tri-Cities Blackhawks",
    "PHW":"Philadelphia Warriors","SFW":"San Francisco Warriors","CHZ":"Chicago Zephyrs",
    "CHP":"Chicago Packers","BLB":"Baltimore Bullets","INO":"Indianapolis Olympians",
    "WAT":"Waterloo Hawks",
}

def _clean_team_name(name):
    s=str(name or "").strip()
    s=re.sub(r"\s*\*$","",s).strip()
    return _TEAM_DISPLAY_NAMES.get(s.upper(),s)

def api_team_profile(team, season="", season_type="Regular Season", scope="season"):
    p=_team_analytics_payload()
    types=p.get("season_types",{})
    if types:
        typed=types.get(season_type,{"rows":[],"seasons":[]})
        all_rows=_team_clean_rows(list(typed.get("rows",[])))
    else:
        all_rows=_team_clean_rows(list(p.get("rows",[])))

    all_rows=[r for r in all_rows
              if not re.match(r"^(?:2TM|3TM|4TM|TOT|TOTAL)(?:$|[\s_-])",
                              str(r.get("team","")).strip(),re.I)]
    for r in all_rows:
        r["team"]=_clean_team_name(r.get("team"))

    target=_clean_team_name(team)
    target_key=_team_match_key(target)
    matches=[r for r in all_rows if _team_match_key(r.get("team"))==target_key]
    if season:
        matches=[r for r in matches if str(r.get("season"))==str(season)]
    if not matches:
        return {"ready":False,"error":f"Team-season not found: {target} {season}",
                "team":target,"season":season}

    row=matches[0]
    target_season=str(row.get("season",""))
    era=_team_era_key(target_season)
    populations={
        "season":[r for r in all_rows if str(r.get("season"))==target_season],
        "historical":all_rows,
        "era":[r for r in all_rows if _team_era_key(r.get("season"))==era] if era else []
    }
    stats=[]
    for key,label,direction in _TEAM_DISPLAY_STATS:
        raw=_TEAM_STAT_KEY_MAP[key]
        value=row.get(raw)
        item={"key":key,"label":label,"value":value,"direction":direction,"percentiles":{}}
        for scope_name,pop in populations.items():
            item["percentiles"][scope_name]=_team_percentile(
                value,[r.get(raw) for r in pop],higher=(direction=="higher")
            )
        stats.append(item)
    return {"ready":True,"team":target,"season":target_season,
            "season_type":season_type,"era":era,"era_label":_era_label(target_season),
            "stats":stats,"row":row,
            "population_sizes":{k:len(v) for k,v in populations.items()}}


def api_team_analytics(search="",season="",season_type="Regular Season",
                       statistic="rDRtg",direction="desc",limit=100,era=""):
    try:p=_team_analytics_payload()
    except Exception as exc:
        return {"rows":[],"total":0,"seasons":[],"stats":TEAM_ANALYTICS_STATS,
                "statistic":statistic,"direction":direction,"ready":False,
                "error":f"{type(exc).__name__}: {exc}"}
    types=p.get("season_types",{})
    if types:
        typed=types.get(season_type,{"rows":[],"seasons":[]})
        rows=_team_clean_rows(list(typed.get("rows",[])))
        rows=[r for r in rows if not re.match(r"^(?:2TM|3TM|4TM)(?:$|[\s_-])",str(r.get("team","")).strip(),re.I)]; seasons=typed.get("seasons",[])
    else:
        rows=_team_clean_rows(list(p.get("rows",[]))); rows=[r for r in rows if not re.match(r"^(?:2TM|3TM|4TM)(?:$|[\s_-])",str(r.get("team","")).strip(),re.I)]; seasons=p.get("seasons",[])
    for r in rows:
        r["team"]=_clean_team_name(r.get("team"))
    if season and season not in ("All","all"):
        rows=[r for r in rows if str(r.get("season"))==str(season)]
    if era and era not in ("All","all"):
        rows=[r for r in rows if _era_key(r.get("season"))==str(era)]
    if search:
        q=str(search).casefold(); rows=[r for r in rows if q in str(r.get("team","")).casefold()]
    key=_TEAM_STAT_KEY_MAP.get(statistic,"rdrtg")
    # For a franchise search the Team Database must remain exhaustive. Do not
    # discard historical team-seasons merely because the selected statistic
    # is unavailable; return the row with a null value so the UI can display
    # the season and a dash for that statistic.
    if not search:
        rows=[r for r in rows if r.get(key) is not None]
    if statistic in ("rDRtg","DRtg"):
        effective_direction=(direction or "asc").lower()
    else:
        effective_direction=(direction or "desc").lower()
    reverse=effective_direction in ("desc","high","highest")
    if search:
        rows.sort(key=lambda r: (r.get(key) is None, float(r.get(key,0) or 0)),
                  reverse=reverse)
    else:
        rows.sort(key=lambda r:float(r.get(key,-1e99)),reverse=reverse)
    # Provide the selected display key directly on each row so the frontend
    # cannot accidentally look up the normalized cache key incorrectly.
    for r in rows:
        r[statistic]=r.get(key)
    display_limit=(len(rows) if search else min(50,len(rows)))
    return {"rows":rows[:display_limit],"total":len(rows),"displayed":display_limit,
            "top_limit":50 if not search else None,"search_mode":bool(search),
            "seasons":seasons,"stats":p.get("stats",[]),"statistic":statistic,
            "statistic_key":key,"direction":direction,"source":p.get("source"),
            "ready":True,"season_type":season_type,"era":era,
            "eras":[{"value":k,"label":label} for k,_a,_b,label in ERA_DEFINITIONS]}


def _team_match_key(name):
    s=_clean_team_name(name).casefold()
    s=re.sub(r"[^a-z0-9]+","",s)
    aliases={
        "okc":"oklahomacitythunder",
        "seattle":"seattlesupersonics",
        "nj":"brooklynnets",
        "newjersey":"brooklynnets",
        "la":"losangeles",
        "lac":"losangelesclippers",
        "lal":"losangeleslakers",
        "gs":"goldenstatewarriors",
        "gsw":"goldenstatewarriors",
        "ny":"newyorkknicks",
        "nyk":"newyorkknicks",
        "phx":"phoenixsuns",
        "pho":"phoenixsuns",
        "sas":"sanantoniospurs",
        "sa":"sanantoniospurs",
        "utah":"utahjazz",
        "uta":"utahjazz",
        "den":"denvernuggets",
        "mil":"milwaukeebucks",
        "bos":"bostonceltics",
        "chi":"chicagobulls",
        "cle":"clevelandcavaliers",
        "dal":"dallasmavericks",
        "hou":"houstonrockets",
        "mem":"memphisgrizzlies",
        "mia":"miamiheat",
        "min":"minnesotatimberwolves",
        "orl":"orlandomagic",
        "phi":"philadelphia76ers",
        "por":"portlandtrailblazers",
        "sac":"sacramentokings",
        "tor":"torontoraptors",
        "was":"washingtonwizards",
        "atl":"atlantahawks",
        "cha":"charlottehornets",
        "det":"detroitpistons",
        "ind":"indianapacers",
        "nop":"neworleanspelicans",
        "oklahomacity":"oklahomacitythunder",
    }
    return aliases.get(s,s)

def api_teams(search="", season=None, season_type="Regular Season", era="", statistic="rDRtg", direction="asc"):
    status=_ensure_team_index_build()
    cached=_read_team_index_cache(season_type)
    if cached is None:
        return {"rows":[],"count":0,"seasons":[],"season":season or "All",
                "ready":False,"building":status=="building","status":status,
                "error":TEAM_BUILD_STATE.get("error") if status=="error" else None}
    rows=list(cached.get("rows",[]))
    # The database is an exhaustive historical team-season index, not a
    # qualified-statistic population.
    rows=[r for r in rows if not re.match(
        r"^(?:2TM|3TM|4TM|TOT|TOTAL)(?:$|[\s_-])",
        str(r.get("team","")).strip(),re.I)]
    for r in rows:
        r["team"]=_clean_team_name(r.get("team"))
    if season and season not in {"All","all","Historical Percentile"}:
        rows=[r for r in rows if str(r["season"])==str(season)]
    if search:
        q=str(search).casefold().strip()
        rows=[r for r in rows
              if q in str(r.get("team","")).casefold()
              or q in _team_match_key(r.get("team")).casefold()]
    if era and era not in {"All","all"}:
        rows=[r for r in rows if _era_key(r.get("season"))==str(era)]

    # Enrich exhaustive database rows with every available team-season
    # statistic from the analytics dataset. The two sources can use different
    # team labels, so match on normalized franchise identity + season.
    try:
        payload=_team_analytics_payload()
        typed=payload.get("season_types",{}).get(season_type,{"rows":[]})
        analytic_rows=_team_clean_rows(list(typed.get("rows",[])))
        lookup={}
        for ar in analytic_rows:
            if re.match(r"^(?:2TM|3TM|4TM|TOT|TOTAL)(?:$|[\s_-])",
                        str(ar.get("team","")).strip(),re.I):
                continue
            lookup[(_team_match_key(ar.get("team")),str(ar.get("season")))] = ar
        for r in rows:
            ar=lookup.get((_team_match_key(r.get("team")),str(r.get("season"))))
            if ar:
                # Keep the exhaustive database identity/season fields while
                # layering all available analytics values onto the row.
                for k,v in ar.items():
                    if k not in ("team","season","season_type","source"):
                        r[k]=v
    except Exception:
        pass

    # A franchise search is still exhaustive, but it should respect the
    # selected statistic and sort direction. Seasons with no value remain in
    # the database and are placed after seasons with valid values.
    if search:
        key=_TEAM_STAT_KEY_MAP.get(statistic, statistic)
        effective_direction=("asc" if statistic in ("rDRtg","DRtg") else "desc") if not direction else direction.lower()
        reverse=effective_direction in ("desc","high","highest")
        def _rank_value(r):
            v=r.get(key)
            try:
                return float(v)
            except (TypeError,ValueError):
                return None
        rows.sort(
            key=lambda r: (
                _rank_value(r) is None,
                _rank_value(r) if _rank_value(r) is not None else 0
            ),
            reverse=reverse
        )
    else:
        rows.sort(key=lambda r:(_season_end_year(r.get("season")) or 9999,
                               str(r.get("team",""))))
    return {"rows":rows,"count":len(rows),"seasons":cached.get("seasons",[]),
            "season":season or "All","ready":True,"building":False,"status":"ready",
            "database":True,"total_team_seasons":len(cached.get("rows",[])),"era":era,"statistic":statistic,"direction":direction}


def api_team_roster_profile(team, season=None, season_type="Regular Season"): 
    roster_cache=TEAM_INDEX_CACHE.with_name("team_rosters_v1.json")
    if roster_cache.exists():
        try:
            payload=json.loads(roster_cache.read_text(encoding="utf-8"))
            key=f"{season_type}|||{team}|||{season or ''}"
            if key in payload.get("rosters",{}):
                r=payload["rosters"][key]
                return {"team":team,"season":season,"players":r.get("players",[]),
                        "player_count":len(r.get("players",[])),"ready":True}
        except Exception:
            pass
    source=_load_team_source()
    c=_team_columns(source) if source is not None else {"team":None,"season":None,"player":None,"pid":None,"mp":None,"pts":None}
    if not c["team"] or not c["season"]:
        return {"error":"Team data is unavailable in the canonical master dataset."}
    d=source.copy()
    d[c["team"]]=d[c["team"]].astype(str).str.strip()
    m=d[c["team"]].str.casefold().eq(str(team).casefold())
    if season: m &= d[c["season"]].astype(str).eq(str(season))
    d=d[m].copy()
    if d.empty:return {"team":team,"season":season,"players":[],"error":"Team-season not found."}
    players=[]
    for _,r in d.iterrows():
        players.append({"player_id":clean(r[c["pid"]]) if c["pid"] else None,
                        "player_name":clean(r[c["player"]]) if c["player"] else None,
                        "minutes":clean(r[c["mp"]]) if c["mp"] else None,
                        "points":clean(r[c["pts"]]) if c["pts"] else None})
    return {"team":str(d[c["team"]].iloc[0]),"season":str(d[c["season"]].iloc[0]),
            "players":players,"player_count":len(players)}

def _json_percent_key(key):
    raw=str(key).lower()
    n=re.sub(r"[^a-z0-9]", "", raw)
    if "percentile" in n:
        return False
    if n in {"rts", "relativets", "relativetspct", "relativetspercent"}:
        return True
    if "%" in raw and not raw.startswith(("rdrtg", "rortg", "rnrtg", "rpace")):
        return True
    # Explicit percentage fields. rTS is a percentage-point differential and
    # therefore uses the same 0-100 unit normalization as TS percentage.
    return n in {
        "fgpct","2ppct","3ppct","ftpct","tspct","efgpct","tovpct",
        "orbpct","drbpct","drebpct","orebpct","trbpct","astpct",
        "stlpct","blkpct","usgpct","ftr","3par","wlpct","winpct",
        "opptovpct","oppefgpct","opponenttovpct","opponentefgpct",
        "deftovpct","defegfpct","defensivetovpct","defensiveefgpct",
    }

def normalize_percentage_payload(value, key=None):
    if isinstance(value, dict):
        return {k: normalize_percentage_payload(v, k) for k,v in value.items()}
    if isinstance(value, list):
        return [normalize_percentage_payload(v, key) for v in value]
    if key is not None and _json_percent_key(key) and isinstance(value, (int,float)) and np.isfinite(value):
        # rTS is a percentage-point differential. Keep the same conservative
        # fractional-source threshold used at CSV ingestion. Values such as
        # +1.4964 are already canonical +1.4964 and must NOT become +149.64.
        nkey=re.sub(r"[^a-z0-9]", "", str(key).lower())
        threshold=0.5 if nkey in {"rts","relativets","relativetspct","relativetspercent"} else 1.5
        if abs(float(value)) <= threshold:
            return float(value)*100.0
    return value

class Handler(BaseHTTPRequestHandler):
    def send_binary(self, status, body, content_type, cache_control="public, max-age=3600"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def send_json(self, status, payload):
        payload = normalize_percentage_payload(payload)
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Browser/client closed the request. There is nothing left to send.
            return

    def do_GET(self):
        try:
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/api/v1/playoff-peak-diagnostics":
                pop=_playoff_peak_population()
                return self.send_json(200, {
                    "ok": True,
                    "players_with_peak": len(pop),
                    "sample": [
                        {
                            "player_id": v.get("player_id"),
                            "player_name": v.get("player_name"),
                            "seasons": v.get("seasons"),
                            "sdi": v.get("sdi"),
                            "sdi_percentile": v.get("sdi_percentile"),
                        }
                        for v in list(pop.values())[:10]
                    ],
                })
            if u.path == "/api/v1/health":
                return self.send_json(200, {"ok": True})
            if u.path == "/api/v1/diagnostics":
                return self.send_json(200, {
                    "ok": True,
                    "root": str(ROOT),
                    "paths": {k: str(v) for k,v in PATHS.items()},
                    "exists": {k: bool(v.exists()) for k,v in PATHS.items()},
                })
            if u.path == "/api/v1/statistics":
                return self.send_json(200, api_stat_registry())
            if u.path == "/api/v1/compare-diagnostics":
                try:
                    per=load_canonical_percentiles()
                    sc=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
                    pc={c:percentile_column(per,c) for c in ("Season","Era","Historical")}
                    return self.send_json(200,{
                        "ok":True,
                        "source":"canonical_long_format",
                        "rows":int(len(per)),
                        "statistics":int(per[sc].nunique()) if sc else 0,
                        "percentile_columns":pc,
                        "columns":[str(c) for c in per.columns if "percentile" in str(c).lower()],
                    })
                except Exception as e:
                    return self.send_json(500,{"ok":False,"error":str(e),"type":type(e).__name__})
            if u.path == "/api/v1/compare":
                return self.send_json(200, api_compare_players(
                    q.get("player_a", [""])[0],
                    q.get("player_b", [""])[0],
                    q.get("start_a", [None])[0],
                    q.get("end_a", [None])[0],
                    q.get("start_b", [None])[0],
                    q.get("end_b", [None])[0],
                    q.get("season_type", ["Regular Season"])[0],
                    q.get("context", ["Season"])[0],
                ))
            if u.path == "/api/v1/big-board":
                result = api_big_board(
                    q.get("season", [None])[0],
                    q.get("context", ["Historical"])[0],
                    q.get("statistic", [None])[0],
                    q.get("sort", ["desc"])[0],
                    q.get("search", [None])[0],
                    int(q.get("limit", ["100"])[0]),
                    q.get("scope", ["single"])[0],
                    q.get("season_type", ["Regular Season"])[0],
                    q.get("era", [""])[0],
                )
                # The scatter plot uses the Big Board as its observation
                # source. Guarantee every observation carries the canonical
                # website headshot, regardless of which board builder produced
                # the row.
                if isinstance(result, dict) and isinstance(result.get("rows"), list):
                    for row in result["rows"]:
                        if not row.get("headshot_url"):
                            row["headshot_url"] = _headshot_url_for(
                                row.get("player_id"), row.get("player_name")
                            )
                return self.send_json(200, result)
            m = re.fullmatch(r"/api/v1/players/(.+?)/headshot", u.path)
            if m:
                requested=unquote(m.group(1))
                url=_headshot_url_for(requested, requested)
                if not url:
                    return self.send_json(404, {"error":"Headshot not found"})
                try:
                    if str(url).lower().startswith(("http://","https://")):
                        req=Request(str(url), headers={
                            "User-Agent":"Mozilla/5.0 NBA-PER75/1.0",
                            "Accept":"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                            "Referer":"https://www.nba.com/",
                        })
                        with urlopen(req, timeout=12) as resp:
                            body=resp.read()
                            ctype=resp.headers.get("Content-Type","image/jpeg").split(";")[0]
                    else:
                        fp=Path(str(url))
                        if not fp.is_absolute():
                            fp=(ROOT/fp).resolve()
                        body=fp.read_bytes()
                        ctype={"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(fp.suffix.lower().lstrip("."),"application/octet-stream")
                    if not body:
                        raise ValueError("Empty image response")
                    return self.send_binary(200,body,ctype)
                except Exception as e:
                    return self.send_json(404, {"error":"Headshot could not be loaded","type":type(e).__name__})
            if u.path == "/api/v1/players":
                return self.send_json(200, {"players": api_players(q.get("q", [""])[0])})
            if u.path == "/api/v1/teams/analytics":
                return self.send_json(200, api_team_analytics(
                    q.get("search", [""])[0],
                    q.get("season", [""])[0],
                    q.get("season_type", ["Regular Season"])[0],
                    q.get("statistic", ["rDRtg"])[0],
                    q.get("direction", ["desc"])[0],
                    int(q.get("limit", ["100"])[0] or 100),
                    q.get("era", [""])[0]
                ))
            if u.path == "/api/v1/teams/profile":
                return self.send_json(200, api_team_profile(
                    q.get("team", [""])[0],
                    q.get("season", [""])[0],
                    q.get("season_type", ["Regular Season"])[0],
                    q.get("scope", ["season"])[0]
                ))
            if u.path == "/api/v1/teams":
                return self.send_json(200, api_teams(
                    q.get("search", [""])[0],
                    q.get("season", [""])[0] or None,
                    q.get("season_type", ["Regular Season"])[0],
                    q.get("era", [""])[0],
                    q.get("statistic", ["rDRtg"])[0],
                    q.get("direction", ["asc"])[0]
                ))
            m = re.fullmatch(r"/api/v1/teams/(.+)", u.path)
            if m:
                return self.send_json(200, api_team_roster_profile(
                    unquote(m.group(1)),
                    q.get("season", [""])[0] or None,
                    q.get("season_type", ["Regular Season"])[0]
                ))

            m = re.fullmatch(r"/api/v1/players/(.+?)/context", u.path)
            if m:
                return self.send_json(200, api_context_profile(
                    unquote(m.group(1)),
                    q.get("season", [None])[0],
                    q.get("context", ["Historical"])[0],
                    q.get("season_type", ["Regular Season"])[0],
                ))
            m = re.fullmatch(r"/api/v1/players/(.+?)/spider", u.path)
            if m:
                return self.send_json(200, api_spider(
                    unquote(m.group(1)),
                    q.get("season", [None])[0],
                    q.get("context", ["Historical"])[0],
                    q.get("stats", [None])[0],
                    q.get("season_type", ["Regular Season"])[0],
                ))
            m = re.fullmatch(r"/api/v1/players/(.+?)/profile", u.path)
            if m:
                return self.send_json(200, api_profile(
                    unquote(m.group(1)),
                    q.get("season", [None])[0],
                    q.get("season_type", ["Regular Season"])[0],
                ))
            return self.send_json(404, {"error": "Route not found"})
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                return self.send_json(500, {"error": str(e), "type": type(e).__name__})
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return


def _precompute_regular_peak_cache_if_missing():
    """Check for the canonical regular peak cache without building it at API startup.

    Website193 deliberately keeps the expensive league-wide build out of the
    server startup path. A separate build script can generate the cache offline.
    Existing valid v2 caches are still recognized and used normally.
    """
    path = ROOT / "data" / "precomputed_5_year_peak" / "regular_profile_peaks_v2.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("version") == "regular_profile_peaks_v2"
    except Exception:
        return False


def _preload_playoff_peak_cache():
    """Warm the canonical playoff peak cache once at API startup."""
    key="__playoff_peak_population_v1__"
    if key in CACHE:
        return CACHE[key]
    population=_playoff_peak_population()
    return population

def _preload_big_board_cache():
    """Warm the expensive regular-season Big Board path at API startup.

    The first Big Board click should not pay the cost of locating/reading the
    canonical percentile table and building the PTS/75 eligibility gate.
    """
    load_canonical_percentiles()
    load_master_seasons()
    _bref_master_eligibility("PTS_per75","Regular Season")
    # Warm the exact default board used by the frontend.
    api_big_board(
        season="Historical Percentile",
        context="Historical",
        statistic="PTS_per75",
        sort_direction="desc",
        limit=100,
        scope="single",
        season_type="Regular Season",
        era=None,
    )

if __name__ == "__main__":
    print("NBA PER-75 Local API")
    print("Team data mode: selecting the most populated existing team-season source")
    try:
        if TEAM_ANALYTICS_CACHE.exists(): TEAM_ANALYTICS_CACHE.unlink()
    except Exception: pass
    # Restore the Team opponent-stat portion without touching logos or any
    # other Team fields. This is the same fast local/bulk repair that was used
    # when Opponent TOV% / Opponent eFG% first appeared successfully. It runs
    # only when the current canonical Team source has no opponent coverage.
    try:
        print("Checking Team opponent-stat continuity...")
        print("Team opponent-stat status:", _ensure_team_data_fast())
    except Exception as e:
        print("Team opponent-stat continuity check failed:", repr(e))
    server=ThreadingHTTPServer((HOST, PORT), Handler)

    # IMPORTANT: start accepting requests immediately. Previously the API did
    # not bind to port 8000 until all Big Board / SDI / peak caches finished
    # warming. The frontend could therefore fire its first profile request
    # while nothing was listening, producing the misleading "Start the local
    # API / API request failed (500)" state. Refreshing worked because startup
    # had finished by then.
    print("Listening at http://127.0.0.1:8000")
    print("Leave this window running while using the website.")

    def warm_caches():
        try:
            print("Warming Big Board data cache...")
            _preload_big_board_cache()
            print("Big Board cache ready.")
        except Exception as e:
            print("Big Board cache warm failed:", repr(e))

        try:
            print("Warming NEW SDI v4 season index...")
            _load_regular_sdi_v4_player_seasons()
            print("NEW SDI v4 season index ready.")
        except Exception as e:
            print("NEW SDI v4 season index warm failed:", repr(e))

        # v21: warm the dedicated Player Profile regular-season SDI cache.
        # This cache is separate from the legacy canonical SDI CSV and contains
        # the corrected season-specific category composites/percentiles.
        try:
            print("Warming v21 regular Player Profile SDI cache...")
            _v21_build_profile_sdi_cache(playoff=False)
            print("v21 regular Player Profile SDI cache ready.")
        except Exception as e:
            print("v21 regular Player Profile SDI cache warm failed:", repr(e))

        # Website193: never build the league-wide regular peak cache at API startup.
        # A missing cache must not keep the server busy for minutes. An offline
        # builder is provided at local_api/build_regular_peak_cache_v2.py.
        try:
            print("Checking canonical regular 5-Year Peak cache...")
            if _precompute_regular_peak_cache_if_missing():
                print("Canonical regular 5-Year Peak cache ready.")
            else:
                print("Canonical regular 5-Year Peak cache not built; startup will continue and profiles use the live canonical selector.")
        except Exception as e:
            print("Canonical regular 5-Year Peak cache check failed:", repr(e))

        try:
            print("Warming precomputed playoff 5-Year Peak cache...")
            _preload_playoff_peak_cache()
            print("Playoff 5-Year Peak cache ready.")
        except Exception as e:
            print("Playoff 5-Year Peak cache warm failed:", repr(e))

        # v21: playoff individual-season SDI is built directly from the
        # authoritative playoff percentile layer. Do this once at startup so
        # clicking Playoffs never pays the full-population calculation cost.
        try:
            print("Warming v21 playoff individual-season SDI cache...")
            _v21_build_profile_sdi_cache(playoff=True)
            print("v21 playoff individual-season SDI cache ready.")
        except Exception as e:
            print("v21 playoff individual-season SDI cache warm failed:", repr(e))

    import threading
    threading.Thread(target=warm_caches, name="NBA-PER75-cache-warm", daemon=True).start()
    server.serve_forever()
