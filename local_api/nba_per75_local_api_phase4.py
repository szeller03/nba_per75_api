
from __future__ import annotations
import unicodedata

import json
import math
import re
import hashlib
from io import BytesIO
import os
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote
from urllib.request import Request, urlopen

import pandas as pd
try:
    from public_data_layer import search_players as public_search_players, search_players_batch as public_search_players_batch, player_season_bundles as public_player_season_bundles, player_season_bundle as public_player_season_bundle, big_board as public_big_board, big_board_companion, explorer_population as public_explorer_population, teams as public_teams
except Exception:
    public_search_players = public_search_players_batch = public_player_season_bundles = public_player_season_bundle = public_big_board = public_explorer_population = public_teams = None
import numpy as np

# Production data lives outside the website source tree. Use the established
# NBA_Per75 directory first, with a nearby-folder fallback for copied projects.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ESTABLISHED_ROOT = Path(os.environ.get("NBA_PER75_ROOT", str(_PROJECT_ROOT)))
_ROOT_CANDIDATES = [
    _PROJECT_ROOT,
    _ESTABLISHED_ROOT,
]
ROOT = next(
    (p for p in _ROOT_CANDIDATES if (p / "data").exists()),
    _ESTABLISHED_ROOT,
)
HOST = "127.0.0.1"
PORT = 8000

# --- SDI v4 revised top-level weights ---
SDI_V4_TOP_LEVEL_WEIGHTS = {
    "scoring_volume": 0.20,
    "scoring_efficiency": 0.18,
    "creation_playmaking": 0.18,
    "rebounding": 0.105,
    "defense": 0.20,
    "impact_value": 0.135,
}


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

def _headshot_url_for(player_id=None, player_name=None):
    """Canonical runtime resolver: shipped PNGs first, NBA CDN second; never B-Ref."""
    key="__canonical_headshot_registry_png_cdn_v2__"
    if key not in CACHE:
        lookup={}
        candidates=[ROOT/"public"/"player_headshots_final_v1"/"player_headshot_registry_active_v1.csv",
                   ROOT/"player_headshots_final_v1"/"player_headshot_registry_active_v1.csv"]
        path=next((x for x in candidates if x.exists()),None)
        try:
            if path is None: raise FileNotFoundError("active headshot registry not found")
            hs=pd.read_csv(path,low_memory=False)
            idc=col(hs,["Player_ID","PlayerId","PlayerID","player_id"])
            nc=col(hs,["Player","Display_Name","Player_Name","Name"])
            uc=col(hs,["Headshot_URL","Verified_Headshot_URL","NBA_Headshot_URL","CDN_URL"])
            if uc:
                for _,r in hs.iterrows():
                    u=clean(r.get(uc))
                    if not u: continue
                    low=str(u).lower()
                    if low.startswith("/player_headshots_final_v1/") and low.endswith(".png"):
                        resolved=u
                    elif "cdn.nba.com/headshots/" in low and low.endswith(".png"):
                        resolved=u
                    else:
                        continue
                    if idc:
                        raw=clean(r.get(idc))
                        if raw: lookup[("id",str(raw).strip())]=resolved
                    if nc:
                        raw=clean(r.get(nc))
                        if raw: lookup[("name",str(raw).strip().casefold().replace("*",""))]=resolved
        except Exception:
            lookup={}
        CACHE[key]=lookup
    lookup=CACHE[key]
    if player_id is not None:
        u=lookup.get(("id",str(player_id).strip()))
        if u: return u
    if player_name is not None:
        u=lookup.get(("name",str(player_name).strip().casefold().replace("*","")))
        if u: return u
    return None

TEAM_INDEX_CACHE = Path(__file__).resolve().parent / "cache" / "team_index_v1.json"
TEAM_ANALYTICS_CACHE = Path(__file__).resolve().parent / "cache" / "team_analytics_v1.json"
TEAM_COMPETITIVE_CONTEXT_CACHE = Path(__file__).resolve().parent / "cache" / "team_competitive_context_v4.json"
TEAM_PLAYOFF_SUCCESS_CACHE = Path(__file__).resolve().parent / "cache" / "team_playoff_success_v1.json"
TEAM_BUILD_STATE = {"status":"idle","started_at":None,"finished_at":None,"error":None}
TEAM_BUILD_LOCK = threading.Lock()

def clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v.item() if hasattr(v, "item") else v

def find_csv(folder, terms):
    """Find the requested CSV, preferring exact canonical filenames."""
    folder=Path(folder)
    if not folder.exists():
        return None
    files=list(folder.rglob("*.csv"))
    if not files:
        return None
    terms=[str(t).lower() for t in terms]
    scored=[]
    for f in files:
        n=f.name.lower()
        stem=f.stem.lower()
        exact=sum(100 for t in terms if n == t or stem == t)
        contains=sum(3 for t in terms if t in n)
        depth=len(f.relative_to(folder).parts)
        scored.append((exact+contains,-depth,f))
    scored.sort(key=lambda x:(-x[0],-x[1],x[2].name.lower()))
    best=scored[0]
    # A fuzzy match must actually contain the requested term. Never return an
    # unrelated CSV simply because the directory is non-empty.
    if best[0] < 3:
        return None
    return best[2]

def load(key, terms):
    if key in CACHE:
        return CACHE[key]
    f = find_csv(PATHS[key], terms)
    if not f:
        raise FileNotFoundError(f"No CSV found for {key}: {PATHS[key]}")
    df = pd.read_csv(f, low_memory=False)
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
        work["__public_name"].astype(str).str.casefold()
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
    # Prefer the stable NBA_Player_ID when available. The identity build can
    # contain separate website/source Player_ID rows for the same person
    # (often one clean name and one asterisked/source variant) while both rows
    # share the same NBA_Player_ID. Those must resolve to ONE public profile.
    # If NBA_Player_ID is unavailable, fall back to the source Player_ID.
    nba_col=next((cc for cc in ["NBA_Player_ID","NBA_PlayerId","nba_player_id","NBA_ID"] if cc in work.columns),None)
    if nba_col:
        nba_num=pd.to_numeric(work[nba_col],errors="coerce")
        work["__identity_key"]=nba_num.map(lambda x:str(int(x)) if pd.notna(x) else "")
        if c.get("id"):
            fallback=work[c["id"]].astype(str).str.strip()
            work["__identity_key"]=work["__identity_key"].where(work["__identity_key"].ne(""),fallback)
        else:
            work["__identity_key"]=work["__identity_key"].where(work["__identity_key"].ne(""),work["__public_key"])
    elif c.get("id"):
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

    # Final cleanup for legacy identity rows with no NBA_Player_ID. If an
    # exact public name maps to exactly one authoritative master Player_ID,
    # all source variants of that name are the same public identity. This
    # handles older records such as a clean/asterisked Tiny Archibald pair
    # without collapsing legitimate namesakes that have multiple master IDs.
    try:
        ms=load_master_seasons()
        if not ms.empty and c.get("id") and c.get("name"):
            mpid=col(ms,["Player_ID","PlayerId","PlayerID","player_id"])
            mname=col(ms,["Player","Player_Name","Display_Name","player_name","Name"])
            if mpid and mname:
                mm=ms[[mpid,mname]].copy()
                mm["__nk"]=(mm[mname].astype(str).str.replace(r"\*+","",regex=True).str.casefold()
                            .str.replace(r"[^a-z0-9]+"," ",regex=True)
                            .str.replace(r"\s+"," ",regex=True).str.strip().str.casefold())
                mm=mm.drop_duplicates(["__nk",mpid])
                unique_master={k:g[mpid].astype(str).str.strip().iloc[0]
                               for k,g in mm.groupby("__nk") if g[mpid].astype(str).str.strip().nunique()==1}
                for nk,grp in work.groupby("__public_key",sort=False):
                    if nk not in unique_master or len(grp)<=1: continue
                    work.loc[grp.index,"__identity_key"]=unique_master[nk]
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
        canonical_hurl=_headshot_url_for(canon_pid,pname)
        if canonical_hurl:
            hurl=canonical_hurl
        out.append({"player_id":canon_pid,"player_name":pname,"headshot_url":hurl})
    return out


def load_master_seasons():
    """Authoritative player-season universe plus first-class individual WOWY stats."""
    f=PATHS["master"]
    if not f.exists():
        return pd.DataFrame()
    key="__master_seasons__"
    if key not in CACHE:
        CACHE[key]=_merge_wowy_into_player_seasons(pd.read_csv(f,low_memory=False))
    return CACHE[key]

def _load_wowy_stat_layer():
    """Canonical individual-player WOWY statistics and season percentiles."""
    key="__player_wowy_statistics_v1__"
    if key in CACHE: return CACHE[key]
    # Canonical cache first; merge/fill from the site copy instead of letting
    # a stale/incomplete data copy hide available WOWY seasons.
    candidates=[ROOT/"local_api"/"cache"/"player_wowy_statistics_v1.csv", ROOT/"data"/"player_wowy_statistics_v1.csv"]
    frames=[]
    for f in candidates:
        if f.exists():
            try:
                d=pd.read_csv(f,low_memory=False)
                d["__name_key"]=d["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
                d["__season_key"]=d["Season"].astype(str).str.strip()
                frames.append(d)
            except Exception:
                continue
    if frames:
        d=pd.concat(frames,ignore_index=True,sort=False)
        d=d.drop_duplicates(["Player_ID","Season"],keep="first")
        CACHE[key]=d
        return d
    CACHE[key]=pd.DataFrame(); return CACHE[key]

def _merge_wowy_into_player_seasons(df):
    if df is None or df.empty: return df
    w=_load_wowy_stat_layer()
    if w.empty: return df
    pcol=col(df,["Player","Player_Name","Display_Name","player_name","Name"])
    scol=col(df,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    if not pcol or not scol: return df
    out=df.copy()
    out["__wowy_name"]=out[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
    out["__wowy_season"]=out[scol].map(_season_label_any)
    wm=w[["__name_key","__season_key","WOWY_Offense","WOWY_Defense","WOWY_Net","WOWY_Offense_Percentile","WOWY_Defense_Percentile","WOWY_Net_Percentile"]].drop_duplicates(["__name_key","__season_key"],keep="first")
    out=out.merge(wm,left_on=["__wowy_name","__wowy_season"],right_on=["__name_key","__season_key"],how="left",suffixes=("","__wowy"))
    return out.drop(columns=["__wowy_name","__wowy_season","__name_key","__season_key"],errors="ignore")


def load_qualification_population():
    folder=PATHS["qualification"]
    f=find_csv(folder,["regular_qualification_population","qualification_population"])
    if not f:
        return pd.DataFrame()
    key="__qualification_population__"
    if key not in CACHE:
        CACHE[key]=pd.read_csv(f,low_memory=False)
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

    qualified_career["Career_Percentile"]=np.nan
    for stat, idx in qualified_career.groupby("_stat_key").groups.items():
        vals=pd.to_numeric(qualified_career.loc[idx,"_career_value"],errors="coerce")
        higher=stat not in {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
        qualified_career.loc[idx,"Career_Percentile"]=_playoff_percentile(vals,higher=higher)

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



_REGULAR_CAREER_SPIDER_ROWS = None
_REGULAR_CAREER_SPIDER_PAYLOADS = None
_REGULAR_CAREER_SPIDER_LOCK = threading.Lock()
_CAREER_SDI_AXES = None
_CAREER_SDI_LOCK = threading.Lock()

def _warm_career_sdi_axes():
    """Index authoritative Career SDI axes once for instant Career spider requests."""
    global _CAREER_SDI_AXES
    if _CAREER_SDI_AXES is not None:
        return
    with _CAREER_SDI_LOCK:
        if _CAREER_SDI_AXES is not None:
            return
        path = ROOT / "data" / "regular_career_sdi_v4_wowy_rts.csv"
        out = {"id": {}, "name": {}}
        if not path.exists():
            _CAREER_SDI_AXES = out
            return
        sd = pd.read_csv(path, low_memory=False)
        sid = col(sd,["Player_ID","PlayerId","PlayerID","player_id"])
        sn = col(sd,["Player","Player_Name","Display_Name","player_name","Name"])
        mapping=[("Scoring Volume","Career_scoring_volume"),("Scoring Efficiency","Career_scoring_efficiency"),("Creation & Playmaking","Career_creation_playmaking"),("Rebounding","Career_rebounding"),("Defense","Career_defense"),("Impact & Value","Career_impact_value")]
        for _, r in sd.iterrows():
            axes=[]
            for label, field in mapping:
                val=pd.to_numeric(r.get(field,np.nan),errors="coerce")
                if pd.notna(val):
                    cov=pd.to_numeric(r.get(field+"_Coverage",np.nan),errors="coerce")
                    axes.append({"axis":label,"value":float(val),"coverage":None if pd.isna(cov) else float(cov)})
            if not axes:
                continue
            if sid:
                pid=str(r.get(sid,"" )).strip()
                if pid: out["id"][pid]=axes
            if sn:
                name=str(r.get(sn,"" )).replace("*","").strip().casefold()
                if name: out["name"][name]=axes
        _CAREER_SDI_AXES=out

def _career_sdi_axes(pid=None, pname=None):
    _warm_career_sdi_axes()
    cache=_CAREER_SDI_AXES or {}
    if pid is not None and str(pid).strip() in cache.get("id",{}):
        return cache["id"][str(pid).strip()]
    if pname:
        return cache.get("name",{}).get(str(pname).replace("*","").strip().casefold(),[])
    return []


def _warm_regular_career_spider_cache():
    """Precompute response-ready canonical regular-season Career spider data once.

    Fix 36 extends Fix 35: the HTTP Career spider path must not perform pandas
    work, master-table scans, identity resolution, or category aggregation.
    """
    global _REGULAR_CAREER_SPIDER_ROWS, _REGULAR_CAREER_SPIDER_PAYLOADS
    if _REGULAR_CAREER_SPIDER_ROWS is not None and _REGULAR_CAREER_SPIDER_PAYLOADS is not None:
        return
    with _REGULAR_CAREER_SPIDER_LOCK:
        if _REGULAR_CAREER_SPIDER_ROWS is not None and _REGULAR_CAREER_SPIDER_PAYLOADS is not None:
            return

        # The Career spider uses authoritative WOWY-aware Career SDI axes.
        _warm_career_sdi_axes()
        career = _build_regular_career_table()
        if career.empty:
            _REGULAR_CAREER_SPIDER_ROWS = {}
            _REGULAR_CAREER_SPIDER_PAYLOADS = {}
            return

        qualified = career.loc[career["Qualified_Career"].astype(bool)].copy() if "Qualified_Career" in career.columns else pd.DataFrame()
        if qualified.empty:
            _REGULAR_CAREER_SPIDER_ROWS = {}
            _REGULAR_CAREER_SPIDER_PAYLOADS = {}
            return

        # Compute the exact same percentile definition used by Fix 35, once.
        qualified["Career_Percentile"] = np.nan
        for stat in REGULAR_STATS:
            if stat not in qualified.columns:
                continue
            vals = pd.to_numeric(qualified[stat], errors="coerce")
            valid = vals.notna()
            if not valid.any():
                continue
            higher = stat not in {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
            pct = _playoff_percentile(vals, higher=higher)
            qualified.loc[valid, f"__pct__{stat}"] = pct.loc[valid]

        rows_by_id = {}
        rows_by_name = {}
        payloads_by_id = {}
        payloads_by_name = {}
        sdi_cache = _CAREER_SDI_AXES or {}
        sdi_by_id = sdi_cache.get("id", {}) if isinstance(sdi_cache, dict) else {}

        for _, r in qualified.iterrows():
            pid = str(r.get("Player_ID", "")).strip()
            pname_raw = str(r.get("Player", "")).replace("*", "").strip()
            pname = pname_raw.casefold()
            rows = []
            pct_map = {}
            for stat in REGULAR_STATS:
                if stat not in r.index:
                    continue
                pct_col = f"__pct__{stat}"
                pct = r.get(pct_col, np.nan)
                value = r.get(stat, np.nan)
                if pd.isna(value):
                    continue
                clean_value = clean(value)
                clean_pct = clean(pct)
                rows.append({
                    "Statistic": stat,
                    "Career_Value": clean_value,
                    "Career_Percentile": clean_pct,
                    "Career_Percentile_Qualified": pd.notna(pct),
                })
                pct_map[stat] = clean_pct

            career_axes = sdi_by_id.get(pid, [])
            if not career_axes:
                # Preserve Fix 35's fallback behavior for any player without an
                # authoritative Career SDI row, but perform it during warm-up.
                try:
                    career_axes = _availability_aware_category_axes(
                        pd.DataFrame(rows), "Career_Percentile"
                    )
                except Exception:
                    career_axes = []
            payload = {
                "found": True,
                "player": {"player_id": pid, "player_name": pname_raw},
                "season": "Career",
                "context": "Career",
                "available_contexts": {"Season": False, "Era": False, "Historical": False, "Career": True},
                "category_axes": career_axes,
                "stat_axes": [],
            }

            if pid:
                rows_by_id[pid] = rows
                payloads_by_id[pid] = payload
            if pname:
                rows_by_name[pname] = rows
                payloads_by_name[pname] = payload

        _REGULAR_CAREER_SPIDER_ROWS = {"id": rows_by_id, "name": rows_by_name}
        _REGULAR_CAREER_SPIDER_PAYLOADS = {"id": payloads_by_id, "name": payloads_by_name}

def _regular_career_profile_rows(player_id=None, player_name=None):
    """Return cached canonical regular-season Career spider rows for one player."""
    _warm_regular_career_spider_cache()
    cache = _REGULAR_CAREER_SPIDER_ROWS or {}
    by_id = cache.get("id", {})
    by_name = cache.get("name", {})
    if player_id is not None:
        rows = by_id.get(str(player_id).strip())
        if rows is not None:
            return rows
    if player_name:
        key = str(player_name).replace("*", "").strip().casefold()
        rows = by_name.get(key)
        if rows is not None:
            return rows
    return []


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
            cols=pd.read_csv(master_path,nrows=0).columns.tolist()
            ctype=col(pd.DataFrame(columns=cols),["Season_Type","SeasonType","Season_Type_ID","Phase"])
            if ctype:
                key="__master_playoff__"
                if key not in CACHE:
                    m=pd.read_csv(master_path,low_memory=False)
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
            cols=pd.read_csv(f,nrows=0).columns.tolist()
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
        CACHE[key]=pd.read_csv(f,low_memory=False)
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
    "FTr","3PAr","rTS","WOWY_Offense","WOWY_Defense","WOWY_Net",
    "PER","BPM","OBPM","DBPM","VORP","WS/48","OWS","DWS",
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
    "FTr","3PAr","rTS","ORtg","DRtg","WOWY_Offense","WOWY_Defense","WOWY_Net",
    "PER","BPM","OBPM","DBPM","VORP","WS/48","OWS","DWS",
    "OREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct","AST_TOV","DREB_pct"
]
PLAYOFF_PER75_STATS = {
    "PTS_per75","FG_per75","FGA_per75","3P_per75","3PA_per75","2P_per75","2PA_per75",
    "FT_per75","FTA_per75","ORB_per75","DRB_per75","TRB_per75","AST_per75","STL_per75",
    "BLK_per75","TOV_per75","PF_per75"
}
PLAYOFF_ADDITIVE_STATS = {"WS/48","OWS","DWS","VORP"}
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
    """Return a true 0–100 performance percentile.

    Higher-is-better statistics place the largest value at 100.
    Lower-is-better statistics place the smallest value at 100.
    The previous implementation reversed both directions, which made
    playoff percentiles (and several career/index consumers that reuse this
    helper) run backwards.
    """
    x=pd.to_numeric(series,errors="coerce")
    out=pd.Series(np.nan,index=series.index,dtype=float)
    valid=x.notna(); n=int(valid.sum())
    if n==0: return out
    if n==1:
        out.loc[valid]=100.0
        return out
    if higher:
        # Higher value = better: smallest is 0th percentile, largest is 100th.
        ranks=x.loc[valid].rank(method="average",ascending=True)
        out.loc[valid]=100.0*(ranks-1)/(n-1)
    else:
        # Lower value = better: smallest is 100th percentile, largest is 0th.
        ranks=x.loc[valid].rank(method="average",ascending=True)
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
            probe=pd.read_csv(path,nrows=5,low_memory=False)
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

    raw=pd.read_csv(source,low_memory=False)
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
        CACHE[key]=pd.read_csv(f,low_memory=False)
    return CACHE[key].copy()

def _load_corrected_playoff_season_from_master():
    """Build the canonical playoff website season layer from nba_per75_master_v46."""
    key="__corrected_playoff_master_season_v1__"
    if key in CACHE: return CACHE[key]
    master_path=PATHS.get("master")
    if not master_path or not Path(master_path).exists():
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    df=pd.read_csv(master_path,low_memory=False)
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
        "FG_pct":"FG_pct","2P_pct":"2P_pct","3P_pct":"3P_pct","FT_pct":"FT_pct","TS_pct":"TS_pct","FTr":"FTr","3PAr":"3PAr","rTS":"rTS","ORtg":"ORtg","DRtg":"DRtg","NRtg":"NRtg","Relative_ORtg":"Relative_ORtg","Relative_DRtg":"Relative_DRtg","Relative_NRtg":"Relative_NRtg","PER":"PER","BPM":"BPM","OBPM":"OBPM","DBPM":"DBPM","VORP":"VORP","WS/48":"WS/48","OWS":"OWS","DWS":"DWS","OREB_pct":"OREB_pct","AST_pct":"AST_pct","STL_pct":"STL_pct","BLK_pct":"BLK_pct","TOV_pct":"TOV_pct","AST_TOV":"AST_TOV","DREB_pct":"DREB_pct"}
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
    additive={"WS/48","OWS","DWS","VORP"}
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
        if higher:
            ranks=x.loc[valid].rank(method="average",ascending=True)
            out.loc[valid]=100*(ranks-1)/(n-1)
        else:
            ranks=x.loc[valid].rank(method="average",ascending=True)
            out.loc[valid]=100*(n-ranks)/(n-1)
        return out
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
            # If this source row has an NBA_Player_ID, resolve that stable ID
            # directly to the canonical registry before using name fallback.
            nba_req=next((cc for cc in ["NBA_Player_ID","NBA_PlayerId","nba_player_id","NBA_ID"] if cc in raw_match.columns),None)
            if nba_req and ic.get("id"):
                nval=pd.to_numeric(raw_match.iloc[0][nba_req],errors="coerce")
                if pd.notna(nval):
                    nba_num=pd.to_numeric(identity.get("NBA_Player_ID",pd.Series(index=identity.index,dtype=float)),errors="coerce") if "NBA_Player_ID" in identity.columns else pd.Series(index=identity.index,dtype=float)
                    hit=identity.loc[nba_num.eq(nval)]
                    if len(hit)==1:
                        return clean(hit.iloc[0][ic["id"]]), clean(hit.iloc[0][ic["name"]])
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


def _playoff_profile_sdi_payload(percentile_rows, pct_col=None, pid=None,
                                 season=None, is_career=False):
    """Build the six playoff SDI axes and completed Route-A SDI for Profile.

    This is the missing bridge between the playoff percentile/profile layer and
    the Player Profile six-dimension UI. It intentionally keeps Route A SDI as
    the primary score; it does not re-percentile the SDI.
    """
    if percentile_rows is None:
        return [], None, None

    pm = percentile_rows.copy() if isinstance(percentile_rows, pd.DataFrame) else pd.DataFrame(percentile_rows)
    if pm.empty:
        return [], None, None

    if pct_col is None:
        pct_col = "Career_Percentile" if is_career else percentile_column(pm, "Season")
    if not pct_col or pct_col not in pm.columns:
        return [], None, None

    try:
        axes = _availability_aware_category_axes(pm, pct_col)
    except Exception:
        axes = []

    # Normalize category labels to the six labels used by the Profile.
    label_map = {
        "Scoring Volume": "Scoring",
        "Scoring": "Scoring",
        "Scoring Efficiency": "Efficiency",
        "Efficiency": "Efficiency",
        "Creation & Playmaking": "Creation / Playmaking",
        "Creation / Playmaking": "Creation / Playmaking",
        "Rebounding": "Rebounding",
        "Defense": "Defense",
        "Impact & Value": "Impact / Value",
        "Impact / Value": "Impact / Value",
    }
    normalized=[]
    for a in axes:
        try:
            value=float(a.get("value"))
        except Exception:
            continue
        item=dict(a)
        item["axis"]=label_map.get(str(a.get("axis","")).strip(), str(a.get("axis","")).strip())
        item["value"]=value
        normalized.append(item)

    # Compute the same locked top-level weighted composite, but against the
    # supplied percentile family (Career for Career, Season for a season).
    sdi=None
    try:
        spec=_load_sdi_v4_spec()
        top=spec.get("top_level_category_weights",{}) if isinstance(spec,dict) else {}
        vals={str(a.get("axis","")).strip():float(a.get("value"))
              for a in axes if a.get("value") is not None}
        # Map UI labels back to spec labels.
        vals2={
            "Scoring Volume": vals.get("Scoring Volume", vals.get("Scoring")),
            "Efficiency": vals.get("Efficiency"),
            "Creation & Playmaking": vals.get("Creation & Playmaking", vals.get("Creation / Playmaking")),
            "Rebounding": vals.get("Rebounding"),
            "Defense": vals.get("Defense"),
            "Impact & Value": vals.get("Impact & Value", vals.get("Impact / Value")),
        }
        usable=[(float(v),float(top.get(k,0.0))) for k,v in vals2.items()
                if v is not None and pd.notna(v) and float(top.get(k,0.0))>0]
        if usable:
            den=sum(w for _,w in usable)
            sdi=sum(v*w for v,w in usable)/den if den else None
    except Exception:
        sdi=None

    return normalized, sdi, pct_col


def _playoff_profile_cache_sdi(pid, pname, season):
    """Read a rebuilt playoff season SDI cache when available.

    Supports both the Phase-3 schema and older six-column playoff SDI caches.
    """
    candidates=[
        ROOT/"local_api"/"cache"/"playoff_sdi_v4_player_seasons.csv",
        ROOT/"data"/"precomputed_sdi_v4"/"playoff_player_season_sdi_v4.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            d=pd.read_csv(path,low_memory=False)
            if d.empty:
                continue
            idc=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
            nc=col(d,["Player","Player_Name","Display_Name","Name","player_name"])
            sc=col(d,["Season","SeasonEndYear","Season_End_Year","Year"])
            sdic=col(d,["SDI_v4_Playoffs","SDI_v4","SDI"])
            if not sc or not sdic:
                continue
            q=d.copy()
            if idc and pid is not None:
                hit=q.loc[q[idc].astype(str).str.strip().eq(str(pid).strip())].copy()
            else:
                hit=pd.DataFrame()
            if hit.empty and nc and pname:
                key=str(pname).replace("*","").strip().casefold()
                hit=q.loc[q[nc].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(key)].copy()
            if hit.empty:
                continue
            wanted=_season_end_year(season)
            if wanted is not None:
                hit["__y"]=hit[sc].map(_season_end_year)
                hit=hit.loc[hit["__y"].eq(wanted)]
            if hit.empty:
                continue
            return float(pd.to_numeric(hit.iloc[0][sdic],errors="coerce"))
        except Exception:
            continue
    return None

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
        if stat_values.get("2P_pct") is None:
            _two_pct=_derive_two_point_pct_from_row(raw_rows)
            if _two_pct is not None:
                stat_values["2P_pct"]=_two_pct
                profile["2P_pct"]=_two_pct

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

    # PHASE 4: expose playoff SDI directly on the profile response.
    # Previously api_playoff_profile returned playoff statistics/percentiles but
    # never supplied the six-dimensional SDI payload consumed by the Profile UI,
    # which caused valid playoff profiles (e.g. Kareem) to display NQ/empty spider.
    _playoff_pct_df=pd.DataFrame(percentiles)
    _playoff_pct_col = "Career_Percentile" if is_career else percentile_column(_playoff_pct_df, "Season")
    _playoff_axes, _playoff_sdi_from_pct, _playoff_pct_family = _playoff_profile_sdi_payload(
        _playoff_pct_df, _playoff_pct_col, pid=pid, season=requested_view, is_career=is_career
    )

    _cached_playoff_sdi = None
    if not is_career and requested_view:
        _cached_playoff_sdi = _playoff_profile_cache_sdi(pid, pname, requested_view)

    # Season-level SDI comes from the rebuilt Phase-3 cache when present.
    # Career SDI is computed from the finalized Career percentile family rather
    # than averaging season SDIs.
    _playoff_sdi = _cached_playoff_sdi if _cached_playoff_sdi is not None else _playoff_sdi_from_pct

    if profile is None:
        profile = {}
    if _playoff_sdi is not None and pd.notna(_playoff_sdi):
        profile["SDI_v4_Playoffs"] = float(_playoff_sdi)
        profile["SDI_v4"] = float(_playoff_sdi)

    return {
        "found":True,
        "view":requested_view,
        "is_career":is_career,
        "player":{"player_id":pid,"player_name":pname,"headshot_url":headshot},
        "seasons":seasons,
        "profile":profile,
        "playoff_statistics":stat_values,
        "percentiles":percentiles,
        "category_axes":_playoff_axes,
        "sdi_v4":float(_playoff_sdi) if _playoff_sdi is not None and pd.notna(_playoff_sdi) else None,
        "SDI_v4":float(_playoff_sdi) if _playoff_sdi is not None and pd.notna(_playoff_sdi) else None,
        "SDI_v4_Playoffs":float(_playoff_sdi) if _playoff_sdi is not None and pd.notna(_playoff_sdi) else None,
        "playoff_sdi_source":(
            "phase3_playoff_sdi_cache" if _cached_playoff_sdi is not None
            else ("playoff_percentile_profile" if _playoff_sdi_from_pct is not None else None)
        ),
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
    """SDI with evidence-aware category contribution.

    Missing statistics are not imputed. Available statistics retain their
    intended relative weights inside each group. Missing groups reduce the
    category's evidence coverage rather than being renormalized into full
    category weight. The resulting category contribution is performance *
    coverage, while the six locked top-level category weights remain fixed.
    """
    if rows is None or rows.empty:
        return np.nan
    stat_col=choose_col(rows,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    pct_col=percentile_column(rows,"Season")
    if not stat_col or not pct_col: return np.nan
    spec=_load_sdi_v4_spec()
    if not spec: return np.nan
    vals=(rows.assign(__stat=rows[stat_col].astype(str).str.strip(),
                      __pct=pd.to_numeric(rows[pct_col],errors="coerce"))
          .dropna(subset=["__pct"])
          .drop_duplicates("__stat",keep="first")
          .set_index("__stat")["__pct"].to_dict())
    category_scores={}
    category_coverage={}
    for category,groups in spec.items():
        if category in {"peak_rules","top_level_category_weights","top_level_category_total_weight"} or not isinstance(groups,dict):
            continue
        group_scores=[]
        intended_group_weight=0.0
        observed_group_weight=0.0
        for group_name,group_spec in groups.items():
            if not isinstance(group_spec,dict): continue
            group_weight=float(group_spec.get("weight",0.0))
            intended_group_weight += group_weight
            stats=group_spec.get("statistics",{}) or {}
            usable=[(float(vals[s]),float(w)) for s,w in stats.items()
                    if s in vals and pd.notna(vals[s]) and pd.notna(w)]
            if not usable: continue
            den=sum(w for _,w in usable)
            if den<=0: continue
            group_score=sum(v*w for v,w in usable)/den
            group_scores.append((group_score,group_weight))
            observed_group_weight += group_weight
        if intended_group_weight<=0 or not group_scores: continue
        # Performance is based on available evidence only.
        score_den=sum(w for _,w in group_scores)
        category_scores[category]=sum(v*w for v,w in group_scores)/score_den
        # Coverage is the fraction of intended group weight represented.
        category_coverage[category]=min(1.0,observed_group_weight/intended_group_weight)
    top=spec.get("top_level_category_weights",{})
    total=0.0
    for category,score in category_scores.items():
        weight=float(top.get(category,0.0))
        coverage=float(category_coverage.get(category,0.0))
        total += score*coverage*weight
    return float(total / 100.0) if total else np.nan

def _load_regular_sdi_v4_player_seasons():
    """Load the authoritative regular-season SDI v4 WOWY index.

    Missing statistics and unavailable WOWY rows are excluded, not imputed.
    Available statistic, subgroup, and category weights are renormalized within
    the evidence that exists. Coverage is retained as metadata.
    """
    key="__regular_sdi_v4_wowy_player_seasons__"
    if key in CACHE:
        return CACHE[key]
    cache_path=ROOT/"local_api"/"cache"/"regular_sdi_v4_wowy_rts_player_seasons.csv"
    if cache_path.exists():
        try:
            d=pd.read_csv(cache_path,low_memory=False)
            if "__pid" not in d.columns:
                d["__pid"]=d["Player_ID"].astype(str).str.strip()
            if "__season" not in d.columns:
                d["__season"]=pd.to_numeric(d["SeasonEndYear"],errors="coerce")
            CACHE[key]=d
            return d
        except Exception:
            pass
    per=load("percentiles",["player_season_percentiles_long"])
    if per.empty:
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    pc=identity_cols(per)
    stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    season_col=choose_col(per,["Season","season","Season_ID"])
    pct_col=percentile_column(per,"Season")
    if not stat_col or not season_col or not pct_col:
        CACHE[key]=pd.DataFrame(); return CACHE[key]
    spec=_load_sdi_v4_spec()
    mapping=[]
    for category,groups in spec.items():
        if category in {"peak_rules","top_level_category_weights","top_level_category_total_weight"} or not isinstance(groups,dict): continue
        for group_name,gs in groups.items():
            if not isinstance(gs,dict): continue
            for stat,sw in (gs.get("statistics",{}) or {}).items():
                mapping.append((category,group_name,stat,float(sw),float(gs.get("weight",1.0))))
    wm=pd.DataFrame(mapping,columns=["__cat","__group","__stat","__sw","__gw"])
    d=per[[pc.get("id",pc.get("player")),season_col,stat_col,pct_col]].copy()
    d.columns=["__pid_raw", "__season_raw","__stat","__pct"]
    d["__stat"]=d["__stat"].astype(str).str.strip()
    d["__pct"]=pd.to_numeric(d["__pct"],errors="coerce")
    d=d.dropna(subset=["__pct"]).merge(wm,left_on="__stat",right_on="__stat",how="inner")
    d["__season"]=d["__season_raw"].map(_season_end_year)
    d=d.dropna(subset=["__season"]).copy(); d["__season"]=d["__season"].astype(int)
    d["__pid"]=d["__pid_raw"].astype(str).str.strip()
    d["__num"]=d["__pct"]*d["__sw"]
    g=(d.groupby(["__pid","__season","__cat","__group"],as_index=False,sort=False)
         .agg(__num=("__num","sum"),__sw=("__sw","sum"),__gw=("__gw","first")))
    g["__group_score"]=g["__num"]/g["__sw"].replace(0,np.nan)
    c=(g.groupby(["__pid","__season","__cat"],as_index=False,sort=False)
         .agg(__num=("__group_score",lambda x: np.nan),
              __gw=("__gw","sum")))
    # Weighted category scores and group-weight sums in a vectorized second pass.
    g["__weighted"]=g["__group_score"]*g["__gw"]
    c=(g.groupby(["__pid","__season","__cat"],as_index=False,sort=False)
         .agg(__num=("__weighted","sum"),__gw=("__gw","sum")))
    c["__category_score"]=c["__num"]/c["__gw"].replace(0,np.nan)
    intended=(wm[["__cat","__group","__gw"]].drop_duplicates()
              .groupby("__cat",as_index=False)["__gw"].sum()
              .rename(columns={"__gw":"__intended_gw"}))
    c=c.merge(intended,on="__cat",how="left")
    c["__coverage"]=c["__gw"]/c["__intended_gw"].replace(0,np.nan)
    tw=spec.get("top_level_category_weights",{})
    c["__top_weight"]=c["__cat"].map(tw).astype(float)
    c["__weighted_category"]=c["__category_score"]*c["__top_weight"]
    # v5: renormalize across categories with evidence. No coverage penalty.
    s=(c.groupby(["__pid","__season"],as_index=False,sort=False)
         .agg(__num=("__weighted_category","sum"),__den=("__top_weight","sum")))
    s["SDI_v4"]=s["__num"]/s["__den"].replace(0,np.nan)
    cov=(c.assign(__covw=c["__coverage"]*c["__top_weight"])
         .groupby(["__pid","__season"],as_index=False)["__covw"].sum()
         .rename(columns={"__covw":"SDI_Category_Coverage"}))
    s=s.merge(cov,on=["__pid","__season"],how="left")
    # Preserve category coverage for transparency.
    wide=c.pivot_table(index=["__pid","__season"],columns="__cat",values="__coverage",aggfunc="first").reset_index()
    wide.columns=[str(x) for x in wide.columns]
    s=s.merge(wide,on=["__pid","__season"],how="left")
    for cat in tw:
        if cat in s.columns:
            s[f"SDI_{cat}_Coverage"]=pd.to_numeric(s[cat],errors="coerce")
    # Player name is not needed by the engine, but is useful to the API.
    if pc.get("player"):
        names=per[[pc.get("id",pc.get("player")),pc["player"]]].drop_duplicates()
        names.columns=["__pid","Player"]
        names["__pid"]=names["__pid"].astype(str).str.strip()
        s=s.merge(names.drop_duplicates("__pid"),on="__pid",how="left")
    s["Season"]=s["__season"].map(_season_label_any)
    s.to_csv(cache_path,index=False)
    CACHE[key]=s
    return s


def _new_sdi_v4_for_player(match, requested_pid=None, requested_name=None):
    """Return season -> NEW SDI v4 for one player."""
    idx=_load_regular_sdi_v4_player_seasons()
    if idx.empty:
        return {}

    pid=str(requested_pid).strip() if requested_pid is not None else None
    if pid:
        m=idx.loc[idx["__pid"].astype(str).str.strip().eq(pid)].copy()
    else:
        m=pd.DataFrame()

    # If the percentile layer has a stale/source ID, fall back to the name
    # present in the player's master rows by resolving that master ID.
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

    if m.empty:
        return {}

    return dict(zip(m["__season"].astype(int),pd.to_numeric(m["SDI_v4"],errors="coerce")))

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
            d=pd.read_csv(cache_path,low_memory=False)
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
        header=pd.read_csv(dfile,nrows=0)
        dpid=col(header,["Player_ID","PlayerId","PlayerID","player_id"])
        dname=col(header,["Player","Player_Name","Display_Name","player_name","Name"])
        dseason=col(header,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        dscore=col(header,["Dominance_Index","dominance_index","Index_Score","Index"])
        use=[x for x in [dpid,dname,dseason,dscore] if x]
        if not dscore or not dseason:
            CACHE[cache_key]=pd.DataFrame()
            return CACHE[cache_key]
        d=pd.read_csv(dfile,usecols=use,low_memory=False)
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


def _canonical_five_year_peak_profile(requested_pid=None, requested_name=None):
    request_key=("__regular_5yr_profile_v2__",
                 str(requested_pid).strip() if requested_pid is not None else "",
                 str(requested_name or "").replace("*","").strip().casefold())
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
    # AUTHORITATIVE PRECOMPUTED REGULAR 5-YEAR PEAK PATH
    # The canonical regular peak has already been calculated offline using
    # the locked/reweighted SDI v4 formula. Never recompute it at request time.
    precomputed = _load_precomputed_regular_peak_profile(
        requested_pid=requested_pid, requested_name=requested_name
    )
    if precomputed is not None:
        CACHE[request_key] = precomputed
        return precomputed

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
            if pidcol and requested_pid is not None:
                match=work.loc[work[pidcol].astype(str).str.strip().eq(str(requested_pid).strip())].copy()
            else:
                wanted=str(requested_name or "").replace("*","").strip().casefold()
                match=work.loc[work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
            if match.empty and requested_name:
                wanted=str(requested_name).replace("*","").strip().casefold()
                match=work.loc[work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
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
                        match, requested_pid=requested_pid, requested_name=requested_name
                    )
                    match["__sdi"]=match["__season_year"].map(sdi_map)

                    best=None
                    for cand in candidates:
                        scores=pd.to_numeric(cand["__sdi"],errors="coerce").dropna().tolist()
                        score=float(np.mean(scores)) if len(scores)==5 else 0.0
                        if best is None or score>best[0]:
                            best=(score,cand.copy())
                    if best:
                        cand=best[1]
                        stats=[str(x) for x in REGULAR_STATS if str(x) in cand.columns]
                        row={"Player_ID":str(requested_pid or ""), "Player":str(requested_name or cand[pcol].iloc[0]),
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


# SDI_V4_AUTHORITATIVE_MANIFEST = data/SDI_V4_AUTHORITATIVE_MANIFEST.json

def _load_authoritative_playoff_sdi_v4():
    """Load the authoritative playoff SDI v4 season/appearance index."""
    key="__authoritative_playoff_sdi_v4__"
    if key in CACHE:
        return CACHE[key]
    path=ROOT/"data"/"precomputed_sdi_v4"/"playoff_player_season_sdi_v4.csv"
    try:
        d=pd.read_csv(path,low_memory=False) if path.exists() else pd.DataFrame()
    except Exception:
        d=pd.DataFrame()
    CACHE[key]=d
    return d

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
    wanted_name=_normalize_peak_lookup_name(requested_name)
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



def _normalize_peak_lookup_name(value):
    """Accent/punctuation-insensitive player name key for peak-cache lookup."""
    text=unicodedata.normalize("NFKD", str(value or "").replace("*",""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+"," ",text.casefold()).strip()

def _load_precomputed_regular_peak_profile(requested_pid=None, requested_name=None):
    """Read one precomputed regular-season 5-Year Peak profile.

    This is intentionally a read-only fast path. The expensive peak/window/
    percentile work is performed by build_precomputed_5_year_peaks.py.
    """
    path=ROOT / "data" / "precomputed_5_year_peak" / "regular_profile_peaks_wowy_canonical_v1.json"
    if not path.exists():
        return None
    try:
        cache_key="__precomputed_regular_peak_profiles_v7_sdi_v4_authoritative__"
        if cache_key in CACHE:
            payload=CACHE[cache_key]
        else:
            payload=json.loads(path.read_text(encoding="utf-8"))
            CACHE[cache_key]=payload
        players=payload.get("players",[])
        wanted_id=str(requested_pid).strip() if requested_pid is not None else ""
        wanted_name=_normalize_peak_lookup_name(requested_name)
        hit=None
        if wanted_id:
            for p in players:
                if str(p.get("player_id","")).strip()==wanted_id:
                    hit=p; break
        if hit is None and wanted_name:
            for p in players:
                if _normalize_peak_lookup_name(p.get("player_name",""))==wanted_name:
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

        peak_headshot=_headshot_url_for(hit.get("player_id"), hit.get("player_name"))
        return {
            "found":True,
            "available":True,
            "player":{"player_id":hit.get("player_id"),"player_name":hit.get("player_name"),"headshot_url":peak_headshot},
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
            "source":"precomputed_5_year_peak_authoritative_v6",
            "peak_cache_version":"regular_profile_peaks_wowy_canonical_v1",
        }
    except Exception as e:
        return {"found":False,"available":False,"error":f"Precomputed peak dataset could not be read: {e}"}


def _profile_data_identity(requested_pid, requested_name):
    """Return (public_pid, data_pid) for profile-backed source tables."""
    public_pid=str(requested_pid).strip() if requested_pid is not None else None
    name_key=re.sub(
        r"[^a-z0-9]+"," ",
        str(requested_name or "").replace("*","").casefold()
    ).strip()

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
                    .str.casefold()
                    .str.replace(r"[^a-z0-9]+"," ",regex=True)
                    .str.replace(r"\s+"," ",regex=True).str.strip())
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
                        .str.casefold()
                        .str.replace(r"[^a-z0-9]+"," ",regex=True)
                        .str.replace(r"\s+"," ",regex=True).str.strip())
            counts=pp.loc[pp["__nk"].eq(name_key)].groupby("__pid").size().sort_values(ascending=False)
            for candidate in counts.index.tolist():
                if candidate not in candidates:
                    candidates.append(candidate)

    return public_pid, (candidates[0] if candidates else public_pid)

def api_player_seasons(requested, season_type="Regular Season"):
    """Return the canonical individual player-season universe for the profile selector."""
    pid,pname=resolve_player_identity(requested)
    master=load_master_seasons()
    if master.empty:
        return {"found":False,"player":{"player_id":pid,"player_name":pname},"seasons":[]}
    mc=identity_cols(master)
    mm=filter_player(master,pid) if pid is not None else pd.DataFrame()
    if mm.empty and pname:
        mm=filter_player(master,pname)
    is_playoffs=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    stcol=mc.get("season_type")
    if stcol and not mm.empty:
        if is_playoffs:
            mm=mm.loc[mm[stcol].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})]
        else:
            mm=mm.loc[~mm[stcol].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})]
    scol=mc.get("season")
    seasons=sorted(mm[scol].dropna().astype(str).unique().tolist()) if scol and not mm.empty else []
    return {
        "found":bool(pid or pname),
        "player":{"player_id":pid,"player_name":pname},
        "season_type":"Playoffs" if is_playoffs else "Regular Season",
        "seasons":seasons,
    }


def _derive_two_point_pct_from_row(row_or_df):
    """Derive 2P% from canonical made/attempted two-point values when the
    profile source omitted the precomputed percentage.

    This is a display/data hydration fallback only; it does not alter the
    underlying canonical source. It is especially important for historical
    seasons where 2P% was not persisted even though FG/FGA and 3P/3PA are.
    """
    if row_or_df is None:
        return None
    try:
        df = row_or_df if isinstance(row_or_df, pd.DataFrame) else pd.DataFrame([row_or_df])
        if df.empty:
            return None
        made_col=col(df,["2P","2P_raw","2FG","2FGM","2PM"])
        att_col=col(df,["2PA","2PA_raw","2FGA","2FGA_raw","2P_attempts"])
        made=pd.to_numeric(df.iloc[0][made_col],errors="coerce") if made_col else np.nan
        att=pd.to_numeric(df.iloc[0][att_col],errors="coerce") if att_col else np.nan
        if pd.isna(att):
            fg_col=col(df,["FG","FG_raw","FGM"]); fga_col=col(df,["FGA","FGA_raw"]); tp_col=col(df,["3P","3P_raw","3PM"]); tpa_col=col(df,["3PA","3PA_raw"])
            fga=pd.to_numeric(df.iloc[0][fga_col],errors="coerce") if fga_col else np.nan
            tpa=pd.to_numeric(df.iloc[0][tpa_col],errors="coerce") if tpa_col else 0.0
            fg=pd.to_numeric(df.iloc[0][fg_col],errors="coerce") if fg_col else np.nan
            tp=pd.to_numeric(df.iloc[0][tp_col],errors="coerce") if tp_col else 0.0
            if pd.notna(fga): att=fga-(tpa if pd.notna(tpa) else 0.0)
            if pd.isna(made) and pd.notna(fg): made=fg-(tp if pd.notna(tp) else 0.0)
        if pd.notna(made) and pd.notna(att) and float(att)>0:
            return float(made)/float(att)
    except Exception:
        return None
    return None


def api_profile(requested, season, season_type="Regular Season"):
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
            pid,pname=resolve_player_identity(requested)
            return _canonical_playoff_five_year_peak_profile(pid,pname)
        return api_playoff_profile(requested, season)
    if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        # AUTHORITATIVE REGULAR 5-YEAR PEAK CACHE.
        # Try the requested key directly, then resolve identity and retry by
        # canonical name. There is intentionally NO live/fallback peak builder.
        precomputed=_load_precomputed_regular_peak_profile(
            requested_pid=requested, requested_name=requested
        )
        if precomputed is not None:
            return precomputed

        pid,pname=resolve_player_identity(requested)
        precomputed=_load_precomputed_regular_peak_profile(pid,pname)
        if precomputed is not None:
            return precomputed

        return {"found":False,"available":False,
                "error":"No precomputed regular 5-Year Peak record for this player."}

    pid,pname=resolve_player_identity(requested)
    public_pid,data_pid=_profile_data_identity(pid,pname)
    # Profile routes should operate on a canonical ID. Ambiguous name-only
    # requests are not allowed to silently select one of multiple people.
    if pid is None and requested and str(requested).strip().casefold() != str(pname).strip().casefold():
        return {"found":False,"available":False,"error":"Player identity could not be resolved uniquely."}

    playoff_source, playoff_source_path = load_playoff_source()

    try:
        profiles = load("profiles", ["player_season_profiles", "season_profiles"])
    except FileNotFoundError:
        profiles = pd.DataFrame()
    pm = filter_player(profiles, data_pid) if pid is not None and not profiles.empty else pd.DataFrame()
    if pm.empty and pid is None and pname and not profiles.empty:
        pm = filter_player(profiles, pname)
    # Profile source also contains both regular-season and playoff rows.
    # Keep the requested season type isolated before using an enriched row.
    _profile_st_col=col(profiles,["Season_Type","season_type","SeasonType"]) if not profiles.empty else None
    if _profile_st_col and not pm.empty and str(season_type).casefold() not in {"playoffs","playoff","postseason"}:
        pm=pm.loc[~pm[_profile_st_col].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()
    pc = identity_cols(profiles) if not profiles.empty else {"id":None,"name":None,"season":None}

    # FULL PLAYER-SEASON UNIVERSE: the master season source controls which
    # seasons appear on a profile. Percentile qualification never removes a season.
    master=load_master_seasons()
    mm=filter_player(master, data_pid) if (not master.empty and pid is not None) else pd.DataFrame()
    if mm.empty and not master.empty and pid is None and pname:
        mm=filter_player(master,pname)
    mc=identity_cols(master) if not master.empty else {}

    is_playoffs = str(season_type).casefold() in {"playoffs","playoff","postseason"}

    # The canonical master contains both regular-season and playoff rows.
    # Never let a playoff row leak into a regular-season profile simply because
    # it appears first for the requested player/season.
    if not is_playoffs and not mm.empty:
        _master_st_col=col(master,["Season_Type","season_type","SeasonType"])
        if _master_st_col:
            mm=mm.loc[~mm[_master_st_col].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()

    if is_playoffs and not playoff_source.empty:
        psc=col(playoff_source,["Season","season"])
        season_source=playoff_source
        sc=psc
        seasons=sorted(
            pd.to_numeric(playoff_source[psc],errors="coerce").dropna().astype(int).astype(str).unique().tolist()
        ) if psc else []
    else:
        season_source=mm if not mm.empty else pm
        sc=mc.get("season") if mc else pc["season"]
        seasons=sorted(season_source[sc].dropna().astype(str).unique().tolist()) if sc and not season_source.empty else []

    requested_view = normalize_requested_season(season) if season else (seasons[-1] if seasons else None)
    is_career = requested_view == "Career"

    if is_career:
        current=season_source.copy()
        chosen="Career"
    else:
        chosen=requested_view
        if sc and chosen and not season_source.empty:
            current=season_source.loc[season_source[sc].astype(str).eq(chosen)].copy()
        else:
            current=season_source.head(1)

        if is_playoffs:
            # Playoff raw source is authoritative for playoff profile existence.
            current = season_source.loc[
                season_source[sc].astype(str).eq(str(chosen))
            ].copy() if sc and chosen and not season_source.empty else season_source.head(0)
        else:
            # Prefer the enriched regular-season profile row for qualified seasons,
            # but retain the master row when the season is not percentile-qualified.
            if not current.empty and pc.get("season") and chosen and not pm.empty:
                enriched=pm.loc[pm[pc["season"]].astype(str).eq(chosen)].copy()
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
            if cm.empty:
                # Preserve a valid player response even if a future data refresh
                # temporarily lacks the career aggregate row.
                career={"Player_ID":data_pid,"Player":pname}
            career["Season"]="Career"
            career["Career_Seasons_Represented"]=int(cm.shape[0]) if not cm.empty else int(len(current))
            career["Career_Qualification"]=("G >= 400 AND MP >= 10,000")
            career["Qualified_Career"] = bool(pd.to_numeric(career.get("G", np.nan), errors="coerce") >= 400 and pd.to_numeric(career.get("MP", np.nan), errors="coerce") >= 10000)
            career["Career_SDI_Qualified"] = career["Qualified_Career"]
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
                # Percentile registry IDs can differ from the profile/master ID
                # across historical data builds. The canonical player name is the
                # authoritative fallback; never drop percentiles merely because
                # the two layers use different identifiers.
                if per_match.empty:
                    per_match = filter_player(per, pname)
                if per_match.empty:
                    try:
                        _pc=identity_cols(per)
                        _pn=_pc.get("name")
                        if _pn and pname:
                            _wanted=str(pname).replace("*","").strip().casefold()
                            per_match=per.loc[per[_pn].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(_wanted)].copy()
                    except Exception:
                        pass
                per_c = identity_cols(per)
                if per_c["season"] and chosen:
                    per_match = per_match.loc[
                        per_match[per_c["season"]].astype(str).eq(chosen)
                    ]
                percentile_rows = [
                    {k: clean(v) for k, v in row.items()}
                    for row in per_match.to_dict("records")
                ]
                # 2P% is a valid historical statistic before the modern
                # three-point era. The legacy long-percentile table starts its
                # 2P% population too late, so inject the audited pre-1979
                # season-relative percentile layer for those seasons.
                if chosen:
                    try:
                        _two_p=ROOT / "data" / "2p_pct_pre1979_season_percentiles.csv"
                        if _two_p.exists() and _season_end_year(chosen) is not None and _season_end_year(chosen) < 1979:
                            _tw=pd.read_csv(_two_p,low_memory=False)
                            _tw=_tw.loc[_tw["Season"].astype(str).eq(str(chosen))].copy()
                            _wanted=str(pname or "").replace("*","").strip().casefold()
                            _tw=_tw.loc[_tw["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(_wanted)]
                            for _st_rm in ("2P_pct","2PA_per75"):
                                percentile_rows=[r for r in percentile_rows if re.sub(r"[^a-z0-9]","",str(r.get("Statistic",r.get("statistic",""))).casefold())!=re.sub(r"[^a-z0-9]","",_st_rm.casefold())]
                            for _r in _tw.to_dict("records"):
                                percentile_rows.append({k:clean(v) for k,v in _r.items()} | {"Era_Percentile":None,"Historical_Percentile":None})
                    except Exception:
                        pass
                # WS/48 in the legacy master/percentile files is a mislabeled
                # total-Win-Shares field. The companion `.1` field in the
                # canonical profile layer is the true WS/48 rate. Build the
                # percentile from that authoritative rate field.
                if chosen and not profiles.empty:
                    try:
                        _psc=col(profiles,["Season","season","Season_ID"])
                        _pst=col(profiles,["Season_Type","season_type","SeasonType"])
                        _pname=col(profiles,["Player","Player_Name","player_name","Name"])
                        _pws=col(profiles,["WS/48.1","WS_per48","WS48"])
                        if _psc and _pname and _pws:
                            wswork=profiles.copy()
                            if _pst:
                                wswork=wswork.loc[~wswork[_pst].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()
                            wswork=wswork.loc[wswork[_psc].astype(str).eq(str(chosen))].copy()
                            wswork["__ws48_actual"]=pd.to_numeric(wswork[_pws],errors="coerce")
                            wswork=wswork.dropna(subset=["__ws48_actual"])
                            # Restrict the percentile population to the same
                            # canonical player-season universe represented by
                            # the long percentile table for this season.
                            if per_c.get("name") and per_c.get("season"):
                                qseason=per.loc[per[per_c["season"]].astype(str).eq(str(chosen))].copy()
                                qnames=set(qseason[per_c["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold())
                                wswork["__name_key"]=wswork[_pname].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
                                if qnames:
                                    wswork=wswork.loc[wswork["__name_key"].isin(qnames)].copy()
                            if not wswork.empty:
                                vals=wswork["__ws48_actual"]
                                ranks=vals.rank(method="average",ascending=False)
                                pctvals=100*(len(vals)-ranks)/(len(vals)-1) if len(vals)>1 else pd.Series(100.,index=vals.index)
                                target=wswork.loc[wswork["__name_key"].eq(str(pname).replace("*","").strip().casefold())].head(1) if "__name_key" in wswork else wswork.loc[wswork[_pname].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(str(pname).replace("*","").strip().casefold())].head(1)
                                if not target.empty:
                                    percentile_rows=[r for r in percentile_rows if re.sub(r"[^a-z0-9]","",str(r.get("Statistic",r.get("statistic",""))).casefold())!="ws48"]
                                    percentile_rows.append({"Statistic":"WS/48","Value":clean(target.iloc[0]["__ws48_actual"]),"Season_Percentile":clean(pctvals.loc[target.index[0]]),"Era_Percentile":None,"Historical_Percentile":None})
                    except Exception:
                        pass
    except Exception:
        pass

    # Always expose the canonical 46-stat values from the master season row as
    # a fallback. This matters for valid but percentile-unqualified seasons
    # (for example Jordan 1985-86 and other small-sample seasons).
    statistic_values={}
    if is_career:
        # Career profile values are already the canonical career aggregation.
        # Never source Career display values from `current`, which is a
        # season-oriented dataframe and can otherwise leak the first season.
        _profile_keys = {
            re.sub(r"[^a-z0-9]", "", str(k).casefold()): k
            for k in (profile or {}).keys()
        }
        for stat in REGULAR_STATS:
            _key = _profile_keys.get(re.sub(r"[^a-z0-9]", "", str(stat).casefold()))
            statistic_values[stat] = clean(profile[_key]) if _key is not None else None
    elif not current.empty:
        raw=current.iloc[0]
        for stat in REGULAR_STATS:
            if stat == "WS/48":
                # In the legacy profile/master CSVs, `WS/48` is actually the
                # total Win Shares field while `WS/48.1` is the true Win Shares
                # per 48 minutes rate (e.g. .322 for LeBron in 2012-13).
                source_col=col(current,["WS/48.1","WS_per48","WS48"] ) or col(current,["WS/48"])
            else:
                source_col=col(current,[stat])
            statistic_values[stat]=clean(raw[source_col]) if source_col else None

    # Fill missing historical per-75 values from the canonical raw season
    # profile. Some pre-1979 rows have valid raw 2PA/2P/etc. but no precomputed
    # per-75 field; do not let that erase a legitimate recorded value.
    if not is_career and chosen and not profiles.empty:
        try:
            _sp=profiles.copy()
            _spid=col(_sp,["Player_ID","PlayerId","PlayerID","player_id"])
            _spname=col(_sp,["Player","Player_Name","Display_Name","player_name","Name"])
            _spseason=col(_sp,["Season","season","Season_ID"])
            _spstype=col(_sp,["Season_Type","SeasonType","season_type","Phase"])
            if _spstype:
                _sp=_sp.loc[_sp[_spstype].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
            if _spseason:
                _sp=_sp.loc[_sp[_spseason].astype(str).eq(str(chosen))].copy()
            if _spid and pid is not None:
                _hit=_sp.loc[_sp[_spid].astype(str).str.strip().eq(str(pid).strip())].copy()
            else:
                _wanted=str(pname or "").replace("*","").strip().casefold()
                _hit=_sp.loc[_sp[_spname].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(_wanted)].copy() if _spname else _sp.iloc[0:0]
            if not _hit.empty:
                _sr=_hit.iloc[0]
                _poss=pd.to_numeric(_sr.get("Estimated_Possessions",np.nan),errors="coerce")
                if pd.notna(_poss) and _poss>0:
                    _raw_map={"PTS_per75":"PTS_raw","FG_per75":"FG_raw","FGA_per75":"FGA_raw","3P_per75":"3P_raw","3PA_per75":"3PA_raw","2P_per75":"2P_raw","2PA_per75":"2PA_raw","FT_per75":"FT_raw","FTA_per75":"FTA_raw","ORB_per75":"ORB_raw","DRB_per75":"DRB_raw","TRB_per75":"TRB_raw","AST_per75":"AST_raw","STL_per75":"STL_raw","BLK_per75":"BLK_raw","TOV_per75":"TOV_raw","PF_per75":"PF_raw"}
                    for _st,_raw in _raw_map.items():
                        _raw_val = _sr[_raw] if _raw in _sr.index else np.nan
                        # Pre-three-point-era profiles sometimes leave 2PA_raw blank even though
                        # FGA_raw is fully recorded. In those seasons 2PA equals FGA.
                        if _st == "2PA_per75" and pd.isna(_raw_val):
                            _fga = pd.to_numeric(_sr.get("FGA_raw",np.nan),errors="coerce")
                            _tpa = pd.to_numeric(_sr.get("3PA_raw",np.nan),errors="coerce")
                            if pd.notna(_fga):
                                _raw_val = _fga - (_tpa if pd.notna(_tpa) else 0.0)
                        if statistic_values.get(_st) is None and pd.notna(_raw_val):
                            statistic_values[_st]=clean(float(_raw_val)/_poss*75.0)
        except Exception:
            pass

    # Historical 2P% hydration: some canonical profile rows contain the
    # underlying 2-point makes/attempts but no persisted 2P_pct field. Derive
    # the value from those counts so a valid percentage never renders as blank.
    if not is_career and statistic_values.get("2P_pct") is None and not current.empty:
        _two_pct=_derive_two_point_pct_from_row(current)
        if _two_pct is not None:
            statistic_values["2P_pct"]=_two_pct
            if isinstance(profile,dict):
                profile["2P_pct"]=_two_pct

    # Canonical 46-stat value map. Keep exact registry keys and a normalized
    # alias map so frontend display can never lose a recorded value because of
    # punctuation/casing/legacy column naming.
    statistic_values_normalized={}
    for _k,_v in statistic_values.items():
        _nk=re.sub(r"[^a-z0-9]","",str(_k).casefold())
        if _nk:
            statistic_values_normalized[_nk]=_v

    # Inject canonical WOWY values into the live profile response. The profile
    # source may predate the WOWY layer, so relying only on its columns would
    # leave the statistic database wired correctly while the visible value stayed blank.
    if not is_career and chosen:
        try:
            w=_load_wowy_stat_layer()
            if not w.empty:
                wanted=str(pname or "").replace("*","").strip().casefold()
                wm=w.loc[(w["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)) & (w["Season"].astype(str).eq(str(chosen)))]
                if not wm.empty:
                    wr=wm.iloc[0]
                    for _st in ["WOWY_Offense","WOWY_Defense","WOWY_Net"]:
                        statistic_values[_st]=clean(wr[_st])
                        statistic_values_normalized[re.sub(r"[^a-z0-9]","",_st.casefold())]=statistic_values[_st]
                    if isinstance(profile,dict):
                        profile.update({k:clean(wr[k]) for k in ["WOWY_Offense","WOWY_Defense","WOWY_Net"]})
        except Exception:
            pass

    # Add the audited WOWY season percentiles to the profile's percentile rows.
    if not is_career and chosen:
        try:
            w=_load_wowy_stat_layer(); wanted=str(pname or "").replace("*","").strip().casefold()
            wm=w.loc[(w["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)) & (w["Season"].astype(str).eq(str(chosen)))] if not w.empty else pd.DataFrame()
            if not wm.empty:
                wr=wm.iloc[0]
                percentile_rows=[r for r in percentile_rows if str(r.get("Statistic","")).strip() not in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}]
                for _st,_pc in [("WOWY_Offense","WOWY_Offense_Percentile"),("WOWY_Defense","WOWY_Defense_Percentile"),("WOWY_Net","WOWY_Net_Percentile")]:
                    percentile_rows.append({"Player_ID":clean(wr["Player_ID"]),"Player":clean(wr["Player"]),"Season":clean(wr["Season"]),"SeasonEndYear":clean(wr["SeasonEndYear"]),"Statistic":_st,"Value":clean(wr[_st]),"Season_Percentile":clean(wr[_pc]),"Era_Percentile":None,"Historical_Percentile":None})
        except Exception:
            pass

    # Expose the same availability-aware six-dimension axes directly on the
    # profile response. This lets the Player Profile backside render from the
    # successful /profile request without depending on a second /spider request.
    category_axes = []
    try:
        if is_career and not is_playoff:
            sdi_path=ROOT / "data" / "regular_career_sdi_v4_wowy_rts.csv"
            if sdi_path.exists():
                sd=pd.read_csv(sdi_path,low_memory=False)
                sd_id=col(sd,["Player_ID","PlayerId","PlayerID","player_id"])
                sd_name=col(sd,["Player","Player_Name","Display_Name","player_name","Name"])
                hit=pd.DataFrame()
                if sd_id and pid is not None:
                    hit=sd.loc[sd[sd_id].astype(str).str.strip().eq(str(pid).strip())].copy()
                if hit.empty and sd_name and pname:
                    key=str(pname).replace("*","").strip().casefold()
                    hit=sd.loc[sd[sd_name].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(key)].copy()
                if not hit.empty:
                    r=hit.iloc[0]
                    mapping=[("Scoring Volume","Career_scoring_volume"),("Scoring Efficiency","Career_scoring_efficiency"),("Creation & Playmaking","Career_creation_playmaking"),("Rebounding","Career_rebounding"),("Defense","Career_defense"),("Impact & Value","Career_impact_value")]
                    category_axes=[{"axis":a,"value":clean(r[c]),"coverage":clean(r.get(c.replace("Career_","Career_")+"_Coverage",np.nan))} for a,c in mapping if pd.notna(pd.to_numeric(r.get(c,np.nan),errors="coerce"))]
        if not category_axes and percentile_rows:
            _pct_key = "Career_Percentile" if is_career else percentile_column(pd.DataFrame(percentile_rows), "Season")
            if _pct_key:
                _pm_axes = pd.DataFrame(percentile_rows)
                category_axes = _availability_aware_category_axes(_pm_axes, _pct_key)
    except Exception:
        category_axes = []

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
        "individual_seasons": [s for s in seasons if str(s) not in {"Career", "5-Year Peak"}],
        "profile": profile,
        "statistic_values": statistic_values,
        "statistic_values_normalized": statistic_values_normalized,
        "percentiles": percentile_rows,
        "category_axes": category_axes,
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
        CACHE[key] = pd.read_csv(path, low_memory=False)
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

    axes=_availability_aware_category_axes(pm,pct_col)

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

    # Peak percentile rows contain only the selected-window statistics, so use
    # the same availability-aware category aggregation as regular/playoff spiders.
    pm_peak=pd.DataFrame(rows)
    if not pm_peak.empty:
        pc=choose_col(pm_peak,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
        if pc:
            pm_peak["_stat_key"]=pm_peak[pc].astype(str).str.strip()
        category_axes=_availability_aware_category_axes(pm_peak,"Peak_Percentile")
        # Keep the canonical peak stat axes already computed above.

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
    return _playoff_spider_from_percentiles(pm,pid,pname,season,context,stats)


def _availability_aware_category_axes(pm, pct_col):
    """Return six category performance axes plus evidence coverage.

    The performance axis is computed from available evidence using the
    intended internal weights. Coverage is separately reported and is used by
    SDI contribution, never as a hidden 50th-percentile imputation.
    """
    if pm is None or pm.empty or not pct_col:
        return []
    spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
    cat=choose_col(spec,["Category"]); grp=choose_col(spec,["Group_ID","Group","Group_Id"])
    st=choose_col(spec,["Statistic","Stat"])
    sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    gw=choose_col(spec,["Group_Weight"])
    if not all([cat,grp,st,sw,gw]): return []
    x=pm.copy()
    stat_col=choose_col(x,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not stat_col: return []
    x["_stat_key"]=x[stat_col].astype(str).str.strip()
    x["_pct"]=pd.to_numeric(x[pct_col],errors="coerce")
    vals=(x.dropna(subset=["_pct"]).drop_duplicates("_stat_key")
            .set_index("_stat_key")["_pct"].to_dict())
    allowed=["Scoring Volume","Scoring Efficiency","Creation & Playmaking",
             "Rebounding","Defense","Impact & Value"]
    w=spec.loc[spec[cat].astype(str).str.strip().isin(allowed)].copy()
    w["_stat_key"]=w[st].astype(str).str.strip()
    w["_sw"]=pd.to_numeric(w[sw],errors="coerce")
    w["_gw"]=pd.to_numeric(w[gw],errors="coerce")
    axes=[]
    for category in allowed:
        cg=w.loc[w[cat].astype(str).str.strip().eq(category)]
        if cg.empty: continue
        unique_groups=cg[[grp,"_gw"]].drop_duplicates()
        intended=float(unique_groups["_gw"].sum())
        group_scores=[]
        observed=0.0
        for group,g in cg.groupby(grp,sort=False):
            usable=g.loc[g["_stat_key"].isin(vals)].copy()
            if usable.empty: continue
            weights=usable["_sw"].to_numpy(dtype=float)
            scores=np.array([float(vals[s]) for s in usable["_stat_key"].astype(str)],dtype=float)
            denom=weights.sum()
            if denom<=0: continue
            group_score=float(np.average(scores,weights=weights))
            group_weight=float(usable["_gw"].iloc[0])
            group_scores.append((group_score,group_weight))
            observed += group_weight
        if group_scores:
            denom=sum(weight for _,weight in group_scores)
            value=sum(score*weight for score,weight in group_scores)/denom if denom>0 else float(np.mean([score for score,_ in group_scores]))
            coverage=min(1.0,observed/intended) if intended>0 else 0.0
            axes.append({"axis":category,"value":float(value),"coverage":float(coverage),
                         "contribution_multiplier":float(coverage)})
    return axes

def api_spider(requested, season=None, context="Historical", stats=None, season_type="Regular Season"):
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        return api_playoff_spider(requested,season,context,stats)

    # FIX 36: Career spider is now a true response-ready in-memory lookup.
    # Fix 35 cached the percentile population, but every request still passed
    # through identity resolution and master/profile DataFrame scans. Those
    # scans were the remaining multi-second profile-navigation bottleneck.
    if str(season).casefold() == "career" or str(context).casefold() == "career":
        _warm_regular_career_spider_cache()
        cache = _REGULAR_CAREER_SPIDER_PAYLOADS or {}
        req = str(requested or "").strip()
        payload = cache.get("id", {}).get(req)
        if payload is None:
            payload = cache.get("name", {}).get(req.replace("*", "").strip().casefold())
        if payload is not None:
            out = dict(payload)
            rows = _REGULAR_CAREER_SPIDER_ROWS.get("id", {}).get(req)
            if rows is None:
                rows = _REGULAR_CAREER_SPIDER_ROWS.get("name", {}).get(req.replace("*", "").strip().casefold(), [])
            pct_map = {str(r.get("Statistic")): r.get("Career_Percentile") for r in rows}
            requested_stats = [x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
            out["stat_axes"] = [{"axis": st, "value": pct_map.get(st)} for st in requested_stats]
            return out

    pid,pname=resolve_player_identity(requested)
    public_pid,data_pid=_profile_data_identity(pid,pname)
    if pid is None and not pname: return {"found":False}

    context=context if context in {"Season","Era","Historical","Career"} else "Historical"

    career_authoritative_axes=[]

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
        # Career six-dimension axes come from the authoritative WOWY-aware
        # career SDI cache. Do not reconstruct them from career percentiles:
        # a statistic with only a tiny historical tracking sample (e.g. Wilt's
        # single recorded BLK season) must not become a full-strength axis input.
        try:
            career_authoritative_axes = _career_sdi_axes(pid, pname)
        except Exception:
            career_authoritative_axes=[]
    else:
        per=load("percentiles",["player_season_percentiles_long"])
        pm=filter_player(per,data_pid if data_pid is not None else pname)
        if pm.empty: pm=filter_player(per,pname)
        pc=identity_cols(per)
        if pc["season"] and season:
            requested_season=normalize_requested_season(season)
            pm=pm.loc[pm[pc["season"]].map(_season_label_any).eq(str(requested_season))]
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

    axes=career_authoritative_axes if (context=="Career" and career_authoritative_axes) else _availability_aware_category_axes(pm,pct)

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
        requested_season=normalize_requested_season(season)
        pm=pm.loc[pm[pc["season"]].map(_season_label_any).eq(str(requested_season))]
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
        header=pd.read_csv(f,nrows=0)
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
            base=pd.read_csv(f,usecols=use,low_memory=False)
        else:
            base=pd.read_csv(f,low_memory=False)
        # WOWY is a first-class player statistic: add its canonical raw values
        # and seasonal percentiles to the same long-format registry consumed by
        # Profiles, Big Board, Comparison and Explorer.
        w=_load_wowy_stat_layer()
        if not w.empty:
            rows=[]
            for value_col,pct_col,stat in [("WOWY_Offense","WOWY_Offense_Percentile","WOWY_Offense"),("WOWY_Defense","WOWY_Defense_Percentile","WOWY_Defense"),("WOWY_Net","WOWY_Net_Percentile","WOWY_Net")]:
                q=w.loc[pd.to_numeric(w[value_col],errors="coerce").notna()].copy()
                if q.empty: continue
                rows.append(pd.DataFrame({
                    "Player_ID":q["Player_ID"],"Player":q["Player"],"Season":q["Season"],
                    "SeasonEndYear":q["SeasonEndYear"],"Statistic":stat,"Value":q[value_col],
                    "Season_Percentile":q[pct_col],"Era_Percentile":pd.NA,"Historical_Percentile":pd.NA
                }))
            if rows:
                base=pd.concat([base,*rows],ignore_index=True,sort=False)
        CACHE[key]=base
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
ERA_AVERAGE_ADDITIVE = {"OWS","DWS","VORP"}
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
        # The finalized profile layer stores the actual WS/48 rate in WS/48.1,
        # while several legacy sources expose total Win Shares under WS/48.
        # Prefer the actual rate when it exists and minute-weight it across
        # selected seasons; otherwise retain the legacy total-WS conversion.
        rate_col=col(rows,["WS/48.1","WS_per48","WS48_actual"])
        mp=col(rows,["MP","Minutes","minutes"])
        if rate_col and mp:
            w=pd.to_numeric(rows[rate_col],errors="coerce"); m=pd.to_numeric(rows[mp],errors="coerce")
            x=pd.DataFrame({"v":w,"w":m}).dropna(); x=x[x.w>0]
            return float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan
        ws=col(rows,["WS/48"] )
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

def _apply_availability_aware_career_values(out):
    """Correct career stats when historical stat tracking begins mid-career.

    Never treat an unrecorded statistic as zero.  The canonical season-profile
    layer is one row per player-season and carries NaN for genuinely untracked
    fields, so it is the authoritative source for this correction.
    """
    if out is None or out.empty or "Player_ID" not in out.columns:
        return out
    prof_path=ROOT / "player_profiles_v1" / "player_season_profiles.csv"
    if not prof_path.exists():
        return out
    try:
        prof=pd.read_csv(prof_path,low_memory=False)
        st=col(prof,["Season_Type","SeasonType","season_type","Phase"])
        if st:
            prof=prof.loc[prof[st].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
        pid=col(prof,["Player_ID","PlayerId","PlayerID","player_id"])
        if not pid or prof.empty:
            return out
        prof["__pid"]=prof[pid].astype(str).str.strip()
        prof["__mp"]=pd.to_numeric(prof.get("MP",np.nan),errors="coerce")
        prof["__poss"]=pd.to_numeric(prof.get("Estimated_Possessions",np.nan),errors="coerce")
        # A canonical profile should already be one player-season row.  If a
        # legacy source happens to contain duplicates, keep the row with the
        # greatest minutes rather than double-counting a season.
        if "Season" in prof.columns:
            prof["__season"]=prof["Season"].map(_season_label_any)
            prof=prof.sort_values(["__pid","__season","__mp"],ascending=[True,True,False],kind="stable")
            prof=prof.drop_duplicates(["__pid","__season"],keep="first")

        raw_to_rate={
            "FG_per75":"FG_raw","FGA_per75":"FGA_raw","3P_per75":"3P_raw","3PA_per75":"3PA_raw",
            "2P_per75":"2P_raw","2PA_per75":"2PA_raw","FT_per75":"FT_raw","FTA_per75":"FTA_raw",
            "ORB_per75":"ORB_raw","DRB_per75":"DRB_raw","TRB_per75":"TRB_raw","AST_per75":"AST_raw",
            "STL_per75":"STL_raw","BLK_per75":"BLK_raw","TOV_per75":"TOV_raw","PF_per75":"PF_raw",
            "PTS_per75":"PTS_raw",
        }
        percentage_denoms={
            "FG_pct":("FG_raw","FGA_raw"), "2P_pct":("2P_raw","2PA_raw"),
            "3P_pct":("3P_raw","3PA_raw"), "FT_pct":("FT_raw","FTA_raw"),
        }
        ratio_defs={
            "AST_TOV":("AST_raw","TOV_raw"), "FTr":("FTA_raw","FGA_raw"), "3PAr":("3PA_raw","FGA_raw"),
        }
        cumulative={"OWS":"OWS","DWS":"DWS","VORP":"VORP"}
        mp_weighted=["OREB_pct","DREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct","PER","BPM","OBPM","DBPM"]
        # Only overwrite a statistic when the underlying evidence exists. This
        # leaves unrelated canonical career calculations untouched.
        grouped=prof.groupby("__pid",sort=False)
        for pid_key,g in grouped:
            target_idx=out.index[out["Player_ID"].astype(str).str.strip().eq(str(pid_key).strip())]
            if len(target_idx)==0:
                continue
            oi=target_idx[0]
            poss=pd.to_numeric(g["__poss"],errors="coerce") if "__poss" in g else pd.Series(dtype=float)
            for stat,raw in raw_to_rate.items():
                if raw not in g.columns or "__poss" not in g.columns: continue
                num=pd.to_numeric(g[raw],errors="coerce")
                mask=num.notna() & poss.notna() & poss.gt(0)
                if not mask.any(): continue
                denom=float(poss.loc[mask].sum())
                if denom<=0: continue
                out.at[oi,stat]=float(num.loc[mask].sum()/denom*75.0)
            for stat,(numcol,dencol) in percentage_denoms.items():
                if numcol not in g.columns or dencol not in g.columns: continue
                num=pd.to_numeric(g[numcol],errors="coerce"); den=pd.to_numeric(g[dencol],errors="coerce")
                mask=num.notna() & den.notna() & den.gt(0)
                if mask.any(): out.at[oi,stat]=float(num.loc[mask].sum()/den.loc[mask].sum())
            # TS% and rTS use the natural TS-attempt denominator.
            if all(c in g.columns for c in ["PTS_raw","FGA_raw","FTA_raw"]):
                pts=pd.to_numeric(g["PTS_raw"],errors="coerce"); fga=pd.to_numeric(g["FGA_raw"],errors="coerce"); fta=pd.to_numeric(g["FTA_raw"],errors="coerce")
                tsa=fga+0.44*fta; mask=pts.notna()&tsa.notna()&tsa.gt(0)
                if mask.any():
                    ts=float(pts.loc[mask].sum()/(2*tsa.loc[mask].sum())); out.at[oi,"TS_pct"]=ts
                    if "League_TS_pct" in g.columns:
                        lts=pd.to_numeric(g["League_TS_pct"],errors="coerce")
                        lm=mask & lts.notna()
                        if lm.any(): out.at[oi,"rTS"]=float((pts.loc[lm].sum()/(2*tsa.loc[lm].sum()) - (lts.loc[lm]*tsa.loc[lm]).sum()/tsa.loc[lm].sum())*100.0)
            for stat,(numcol,dencol) in ratio_defs.items():
                if numcol not in g.columns or dencol not in g.columns: continue
                num=pd.to_numeric(g[numcol],errors="coerce"); den=pd.to_numeric(g[dencol],errors="coerce")
                mask=num.notna()&den.notna()&den.gt(0)
                if mask.any(): out.at[oi,stat]=float(num.loc[mask].sum()/den.loc[mask].sum())
            for stat,colname in cumulative.items():
                if colname not in g.columns: continue
                v=pd.to_numeric(g[colname],errors="coerce"); v=v.dropna()
                if not v.empty: out.at[oi,stat]=float(v.sum())
            if "__mp" in g.columns:
                mp=pd.to_numeric(g["__mp"],errors="coerce")
                for stat in mp_weighted:
                    if stat not in g.columns: continue
                    v=pd.to_numeric(g[stat],errors="coerce")
                    mask=v.notna()&mp.notna()&mp.gt(0)
                    if mask.any(): out.at[oi,stat]=float((v.loc[mask]*mp.loc[mask]).sum()/mp.loc[mask].sum())
        return out
    except Exception:
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
    career_file=(ROOT / "data" / "nba_per75_career_availability_v3.csv") if (ROOT / "data" / "nba_per75_career_availability_v3.csv").exists() else find_csv(ROOT / "data", ["nba_per75_career_v2"])
    if career_file is not None:
        cache_key=f"__regular_career_canonical__:{career_file}"
        if cache_key in CACHE:
            return CACHE[cache_key]
        career=pd.read_csv(career_file,low_memory=False)
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
            # The legacy canonical career file exposes a column named WS/48
            # that is actually total Win Shares. Replace that one field with
            # the true weighted WS/48 rate from the existing canonical
            # player-season profile layer (WS/48.1).
            try:
                prof_path=ROOT / "player_profiles_v1" / "player_season_profiles.csv"
                if prof_path.exists():
                    prof=pd.read_csv(prof_path,low_memory=False)
                    pst=col(prof,["Season_Type","SeasonType","season_type","Phase"])
                    if pst:
                        prof=prof.loc[prof[pst].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
                    pp_id=col(prof,["Player_ID","PlayerId","PlayerID","player_id"])
                    pp_name=col(prof,["Player","Player_Name","Display_Name","player_name","Name"])
                    pp_mp=col(prof,["MP","Minutes","minutes"])
                    pp_ws48=col(prof,["WS/48.1","WS_per48","WS48_actual"])
                    if pp_mp and pp_ws48 and (pp_id or pp_name):
                        prof["__mp"] = pd.to_numeric(prof[pp_mp],errors="coerce")
                        prof["__ws48"] = pd.to_numeric(prof[pp_ws48],errors="coerce")
                        prof=prof.loc[prof["__mp"].notna() & prof["__ws48"].notna() & (prof["__mp"]>0)].copy()
                        if pp_id:
                            ws_map=prof.groupby(prof[pp_id].astype(str).str.strip()).apply(lambda g: float((g["__ws48"]*g["__mp"]).sum()/g["__mp"].sum()), include_groups=False).to_dict()
                            out["WS/48"]=out["Player_ID"].astype(str).str.strip().map(ws_map)
                        elif pp_name:
                            prof["__name"]=prof[pp_name].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
                            ws_map=prof.groupby("__name").apply(lambda g: float((g["__ws48"]*g["__mp"]).sum()/g["__mp"].sum()), include_groups=False).to_dict()
                            out["WS/48"]=out["Player"].astype(str).str.strip().str.casefold().map(ws_map)
            except Exception:
                pass
            # WOWY is a first-class player statistic. Career values are
            # minutes-weighted across available regular-season WOWY seasons.
            w=_load_wowy_stat_layer()
            if not w.empty:
                w["__mp"] = pd.to_numeric(w.get("MP", np.nan), errors="coerce") if "MP" in w.columns else np.nan
                # Join available player IDs when present; fall back to canonical names.
                wm=w.copy()
                if "Player_ID" in out.columns and wm["Player_ID"].notna().any():
                    wm["__idkey"]=wm["Player_ID"].astype(str).str.strip()
                    
                    def _wavg_wowy(g, value_col):
                        v=pd.to_numeric(g.get(value_col, np.nan), errors="coerce")
                        m=pd.to_numeric(g.get("__mp", np.nan), errors="coerce")
                        mask=v.notna() & m.notna() & m.gt(0)
                        if not mask.any(): return np.nan
                        return float((v.loc[mask]*m.loc[mask]).sum()/m.loc[mask].sum())
                    vals=wm.groupby("__idkey",dropna=False).apply(
                        lambda g: pd.Series({
                            "WOWY_Offense":_wavg_wowy(g,"WOWY_Offense"),
                            "WOWY_Defense":_wavg_wowy(g,"WOWY_Defense"),
                            "WOWY_Net":_wavg_wowy(g,"WOWY_Net")
                        }), include_groups=False).reset_index()
                    out["__idkey"]=out["Player_ID"].astype(str).str.strip()
                    out=out.merge(vals,on="__idkey",how="left",suffixes=("","__wowycareer")).drop(columns=["__idkey"],errors="ignore")
                else:
                    
                    wm["__namekey"]=wm["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
                    vals=wm.groupby("__namekey",dropna=False).apply(
                        lambda g: pd.Series({
                            "WOWY_Offense":_wavg_wowy(g,"WOWY_Offense"),
                            "WOWY_Defense":_wavg_wowy(g,"WOWY_Defense"),
                            "WOWY_Net":_wavg_wowy(g,"WOWY_Net")
                        }), include_groups=False).reset_index()
                    out["__namekey"]=out["Player"].astype(str).str.strip().str.casefold()
                    out=out.merge(vals,on="__namekey",how="left").drop(columns=["__namekey"],errors="ignore")
            # Fix all career statistics whose historical tracking starts mid-career.
            out=_apply_availability_aware_career_values(out)
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
    keys=[pid,player]
    for key,g in work.groupby(keys,dropna=False,sort=False):
        pidv,name=key
        row={"Player_ID":clean(pidv),"Player":clean(name),
             "G":g["__G"].sum(min_count=1),"MP":g["__MP"].sum(min_count=1)}
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
            elif stat == "WS/48":
                row[stat]=float(48*vals.mul(mp).sum(min_count=1)/mp.sum()) if vals.notna().any() and mp.notna().any() and mp.sum()>0 else np.nan
            elif stat in {"OWS","DWS","VORP"}:
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
    career=career.sort_values("_pct" if career["_pct"].notna().any() else "_value_num",
                              ascending=(sort_direction=="asc"),na_position="last").head(int(limit))
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
    # WOWY is a first-class player statistic and has its own audited canonical
    # qualification flag. Do not pass its slug IDs through the legacy BRef gate,
    # which can otherwise reject every WOWY row because the two identity layers
    # use different ID namespaces.
    if str(statistic or "").strip() in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}:
        w=_load_wowy_stat_layer()
        if w.empty or c_season not in work.columns or c_player not in work.columns:
            return work.iloc[0:0].copy()
        q=w.loc[w["PER75_Qualified"].astype(bool),["Player","Season"]].copy()
        q["__qname"]=q["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        q["__qseason"]=q["Season"].astype(str).str.strip()
        wk=work.copy()
        wk["__qname"]=wk[c_player].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        wk["__qseason"]=wk[c_season].map(_season_label_any)
        wk=wk.merge(q[["__qname","__qseason"]].drop_duplicates(),on=["__qname","__qseason"],how="inner")
        return wk.drop(columns=["__qname","__qseason"],errors="ignore")
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

def _sdi_big_board(season=None, context="Historical", sort_direction="desc",
                   search=None, limit=100, scope="single",
                   season_type="Regular Season", era=None):
    """Canonical Statistical Dominance Index Big Board.

    SDI is not a normal statistic-percentile row. It is the composite output
    of the locked SDI v4 formula. Therefore every Big Board scope must consume
    the dedicated precomputed SDI v4 source for that scope and rank the actual
    SDI score, not a percentile of an unrelated statistic row.

    Scope definitions:
      - single: precomputed player-season SDI v4
      - career: precomputed career SDI v4
      - era_average: arithmetic mean of the player's qualifying season SDIs
        within the selected era, using the same era-average qualification gate
      - five_year_peak: authoritative regular/playoff 5-Year Peak SDI cache
    """
    st = str(season_type or "Regular Season").casefold()
    is_playoff = st in {"playoffs","playoff","postseason"}
    scope_key = str(scope or "single").casefold().replace("-","_").replace(" ","_")
    base = ROOT/"data"/"precomputed_sdi_v4"
    season_file = (ROOT/"local_api"/"cache"/"regular_sdi_v4_wowy_rts_player_seasons.csv") if not is_playoff else (base/"playoff_player_season_sdi_v4.csv")

    def _finish_sdi(df, scope_name, season_value, context_value):
        df=df.dropna(subset=["_value_num"]).copy()
        if search and "Player" in df.columns:
            df=df.loc[df["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        if df.empty:
            return {"rows":[],"count":0,"scope":scope_name,"season_type":season_type,
                    "season":season_value,"season_options":[],"statistic":"Statistical Dominance Index",
                    "context":context_value}
        df=df.sort_values("_value_num",ascending=(sort_direction=="asc"),kind="stable")
        ranks=df["_value_num"].rank(method="average",ascending=False)
        n=len(df)
        df["_pct"]=100.0 if n<=1 else 100.0*(n-ranks)/(n-1)
        df=df.head(int(limit)).reset_index(drop=True)
        rows=[]
        for i,r in df.iterrows():
            rows.append({"rank":i+1,"player_id":clean(r.get("Player_ID")),
                         "player_name":clean(r.get("Player")),"season":clean(r.get("season",season_value)),
                         "season_label":clean(r.get("season_label",season_value)),
                         "statistic":"Statistical Dominance Index","value":clean(r["_value_num"]),
                         "percentile":clean(r["_pct"]),"context":context_value,
                         "headshot_url":_headshot_url_for(clean(r.get("Player_ID")),clean(r.get("Player")))})
        return {"rows":rows,"count":len(rows),"scope":scope_name,"season_type":season_type,
                "season":season_value,"season_options":[],"historical_scope":False,
                "career_scope":scope_name=="career","context":context_value,
                "statistic":"Statistical Dominance Index","era":era or None}

    # ---- SINGLE SEASON -----------------------------------------------------
    if scope_key in {"single","season"}:
        fn = "playoff_player_season_sdi_v4.csv" if is_playoff else "regular_player_season_sdi_v4.csv"
        p = base/fn
        if not p.exists():
            return {"rows":[],"count":0,"scope":"single","season_type":season_type,
                    "statistic":"Statistical Dominance Index",
                    "note":f"Missing authoritative SDI v4 source: {p.name}"}
        d = pd.read_csv(p,low_memory=False)
        d["__year"]=pd.to_numeric(d["SeasonEndYear"],errors="coerce")
        d["__sdi_score"]=pd.to_numeric(d["SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in d.columns) else "SDI_v4"],errors="coerce")
        if era:
            d=d.loc[d["__year"].map(_era_key).eq(str(era).strip())].copy()
        requested=str(season or "").strip()
        historical=requested.casefold() in {"","historical","historical percentile","all","all seasons"}
        if not historical:
            target_year=_season_end_year(requested)
            if target_year is not None:
                d=d.loc[d["__year"].eq(int(target_year))].copy()
        if search:
            d=d.loc[d["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        d["_value_num"]=pd.to_numeric(d["__sdi_score"],errors="coerce")
        d=d.dropna(subset=["_value_num"]).copy()
        # For a selected season, all players compete within that season. For
        # Historical, every valid player-season is a row in the population.
        d=d.sort_values("_value_num",ascending=(sort_direction=="asc"),kind="stable")
        d=d.head(int(limit)).reset_index(drop=True)
        # Percentile is computed within the displayed ranking population:
        # higher SDI is always better.
        # Use the full filtered population for percentile, not the top-N slice.
        allvals = pd.to_numeric(
            (pd.read_csv(p,low_memory=False)["SDI_v4"]),errors="coerce"
        ).dropna()
        if era:
            allraw=pd.read_csv(p,low_memory=False)
            ay=pd.to_numeric(allraw["SeasonEndYear"],errors="coerce")
            allraw=allraw.loc[ay.map(_era_key).eq(str(era).strip())]
            allvals=pd.to_numeric(allraw["SDI_v4"],errors="coerce").dropna()
        elif not historical:
            allraw=pd.read_csv(p,low_memory=False)
            ay=pd.to_numeric(allraw["SeasonEndYear"],errors="coerce")
            allvals=pd.to_numeric(allraw.loc[ay.eq(int(target_year)),"SDI_v4"],errors="coerce").dropna()
        # Percentile for the selected rows against the appropriate population.
        ranks=pd.Series(allvals).rank(method="average",ascending=False)
        pct_map_values={}
        # For duplicate scores, map by score so tied values receive the same pct.
        for value in d["_value_num"].unique():
            rank=float(pd.Series(allvals).rank(method="average",ascending=False)[pd.Series(allvals).eq(value)].iloc[0]) if (pd.Series(allvals).eq(value)).any() else np.nan
            n=len(allvals)
            pct_map_values[value]=100.0 if n<=1 else 100.0*(n-rank)/(n-1)
        d["_pct"]=d["_value_num"].map(pct_map_values)
        out=[]
        for i,r in d.iterrows():
            out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),
                        "player_name":clean(r["Player"]),
                        "season":int(r["SeasonEndYear"]),
                        "season_label":_season_label_any(r["SeasonEndYear"]),
                        "statistic":"Statistical Dominance Index",
                        "value":clean(r["_value_num"]),
                        "percentile":clean(r["_pct"]),
                        "context":context,
                        "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))})
        years=sorted(pd.to_numeric(pd.read_csv(p,low_memory=False)["SeasonEndYear"],errors="coerce").dropna().astype(int).unique().tolist())
        return {"rows":out,"count":len(out),"scope":"single","season_type":season_type,
                "season":"Historical Percentile" if historical else _season_label_any(int(target_year)),
                "season_options":[{"value":str(y),"label":_season_label_any(y)} for y in years],
                "historical_scope":historical,"career_scope":False,"context":context,
                "statistic":"Statistical Dominance Index","era":era or None,
                "note":"SDI values come directly from the authoritative SDI v4 player-season precomputation; ranking is by the actual SDI score."}

    # ---- CAREER ------------------------------------------------------------
    if scope_key in {"career","career_average"}:
        fn="playoff_career_sdi_v4.csv" if is_playoff else "regular_career_sdi_v4_wowy_rts.csv"
        p=base/fn
        if (not is_playoff) and not p.exists():
            src=pd.read_csv(season_file,low_memory=False)
            src["__score"]=pd.to_numeric(src["SDI_v4_WOWY"],errors="coerce")
            src["MP"]=pd.to_numeric(src["MP"],errors="coerce")
            src["G"]=pd.to_numeric(src["G"],errors="coerce")
            rows=[]
            for pid,g in src.groupby("Player_ID",dropna=False,sort=False):
                q=g.dropna(subset=["__score"]).copy()
                if q.empty: continue
                w=q["MP"].clip(lower=0)
                score=float((q["__score"]*w).sum()/w.sum()) if w.sum()>0 else float(q["__score"].mean())
                rows.append({"Player_ID":pid,"Player":str(q["Player"].iloc[0]),"Career_SDI_v4":score,"Qualifying_Seasons":int(len(q)),"Career_MP":float(w.sum()),"Average_SDI_Coverage":float(pd.to_numeric(q["SDI_Category_Coverage"],errors="coerce").mean())})
            pd.DataFrame(rows).to_csv(p,index=False)
        if not p.exists():
            return {"rows":[],"count":0,"scope":"career","season_type":season_type,
                    "statistic":"Statistical Dominance Index"}
        d=pd.read_csv(p,low_memory=False)
        d["_value_num"]=pd.to_numeric(d["Career_SDI_v4"],errors="coerce")
        d=d.dropna(subset=["_value_num"]).copy()
        # Derive the career eligibility gate from the same authoritative
        # precomputed season-SDI source. This avoids legacy playoff source IDs
        # (which may legitimately differ from the canonical SDI IDs).
        seasons=pd.read_csv(season_file,low_memory=False)
        if "G" not in seasons.columns and "games" in seasons.columns: seasons["G"]=seasons["games"]
        if "MP" not in seasons.columns and "minutes" in seasons.columns: seasons["MP"]=seasons["minutes"]
        seasons["G"]=pd.to_numeric(seasons["G"],errors="coerce").fillna(0)
        seasons["MP"]=pd.to_numeric(seasons["MP"],errors="coerce").fillna(0)
        elig=seasons.groupby("Player_ID").agg(G=("G","sum"),MP=("MP","sum")).reset_index()
        if is_playoff:
            elig=elig.loc[(elig["G"]>=50)&(elig["MP"]>=1500)]
        else:
            elig=elig.loc[(elig["G"]>=400)&(elig["MP"]>=10000)]
        d=d.loc[d["Player_ID"].astype(str).isin(set(elig["Player_ID"].astype(str)))].copy()
        if search:
            d=d.loc[d["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        d=d.sort_values("_value_num",ascending=(sort_direction=="asc"),kind="stable")
        allvals=d["_value_num"].copy()
        n=len(allvals)
        ranks=allvals.rank(method="average",ascending=False)
        d["_pct"]=100.0 if n<=1 else 100.0*(n-ranks)/(n-1)
        d=d.head(int(limit)).reset_index(drop=True)
        out=[]
        for i,r in d.iterrows():
            out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),
                        "player_name":clean(r["Player"]),"season":"Career",
                        "season_label":"Career","statistic":"Statistical Dominance Index",
                        "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),
                        "context":"Career","headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))})
        return {"rows":out,"count":len(out),"scope":"career","season_type":season_type,
                "season":"Career","season_options":[{"value":"Career","label":"Career"}],
                "historical_scope":False,"career_scope":True,"context":"Career",
                "statistic":"Statistical Dominance Index",
                "note":"Career SDI comes directly from the authoritative SDI v4 career precomputation; career eligibility follows the established career board thresholds."}

    # ---- ERA AVERAGE -------------------------------------------------------
    if scope_key in {"era_average","era"}:
        if not era:
            return {"rows":[],"count":0,"scope":"era_average","season_type":season_type,
                    "statistic":"Statistical Dominance Index","era":None,
                    "note":"Select an era to calculate an SDI Era Average."}
        if not season_file.exists():
            return {"rows":[],"count":0,"scope":"era_average","season_type":season_type,
                    "statistic":"Statistical Dominance Index","era":era}
        d=pd.read_csv(season_file,low_memory=False)
        d["__year"]=pd.to_numeric(d["SeasonEndYear"],errors="coerce")
        d["G"]=pd.to_numeric(d["G"],errors="coerce").fillna(0)
        d["MP"]=pd.to_numeric(d["MP"],errors="coerce").fillna(0)
        d["SDI_v4"]=pd.to_numeric(d["SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in d.columns) else "SDI_v4"],errors="coerce")
        d=d.loc[d["__year"].map(_era_key).eq(str(era).strip())].copy()

        # Use the same era-average participation concept as the site's
        # established Era Average board, but operate on the canonical SDI
        # season source so public/source ID drift cannot erase players.
        schedule=d.groupby("__year")["G"].max().to_dict()
        if is_playoff:
            d["__qualified"]=(d["G"]>=7)&(d["MP"]>=125)
        else:
            d["__qualified"]=[
                float(g)>=math.ceil(.60*float(schedule.get(int(y),82) or 82)) and float(mp)>=1400
                for g,mp,y in zip(d["G"],d["MP"],d["__year"])
            ]
        bounds=next(((a,b) for k,a,b,_ in ERA_DEFINITIONS if k==str(era).strip()),(None,None))
        rows=[]
        if bounds[0] is not None:
            for pid,g in d.groupby("Player_ID",dropna=False,sort=False):
                years=sorted(g["__year"].dropna().astype(int).unique().tolist())
                if not years: continue
                lo=max(bounds[0],min(years)); hi=min(bounds[1],max(years))
                eligible=max(0,hi-lo+1)
                qseasons=int(g["__qualified"].sum())
                participation=qseasons/eligible if eligible else 0
                games=float(g["G"].sum()); minutes=float(g["MP"].sum())
                ming=ERA_AVERAGE_PLAYOFF_MIN_GAMES if is_playoff else ERA_AVERAGE_REGULAR_MIN_GAMES
                minm=ERA_AVERAGE_PLAYOFF_MIN_MINUTES if is_playoff else ERA_AVERAGE_REGULAR_MIN_MINUTES
                if participation+1e-12 < ERA_AVERAGE_PARTICIPATION or games<ming or minutes<minm:
                    continue
                q=g.loc[g["__qualified"]].dropna(subset=["SDI_v4"])
                if q.empty: continue
                rows.append({"Player_ID":pid,"Player":str(g["Player"].iloc[0]),
                             "_value_num":float(q["SDI_v4"].mean())})
        outdf=pd.DataFrame(rows)
        return _finish_sdi(outdf,scope_name="era_average",season_value="Era Average",context_value="Era")

    # ---- FIVE-YEAR PEAK ----------------------------------------------------
    if scope_key in {"five_year_peak","5_year_peak","5year_peak","peak"}:
        if not is_playoff:
            src=pd.read_csv(season_file,low_memory=False)
            src["__year"]=pd.to_numeric(src["SeasonEndYear"],errors="coerce")
            src["__score"]=pd.to_numeric(src["SDI_v4_WOWY"],errors="coerce")
            src["__g"]=pd.to_numeric(src["G"],errors="coerce")
            src["__mp"]=pd.to_numeric(src["MP"],errors="coerce")
            rows=[]; schedule=src.groupby("__year")["__g"].max().to_dict()
            for pid,g in src.groupby("Player_ID",dropna=False,sort=False):
                g=g.sort_values("__year").drop_duplicates("__year",keep="first")
                qualified=[]
                for _,r in g.iterrows():
                    sched=float(schedule.get(int(r["__year"]),82) or 82)
                    if float(r["__g"])>=math.ceil(.60*sched) and float(r["__mp"])>=1400: qualified.append(r)
                q=pd.DataFrame(qualified) if qualified else pd.DataFrame()
                for i in range(max(0,len(q)-4)):
                    cand=q.iloc[i:i+5]
                    if len(cand)!=5 or int(cand["__year"].iloc[-1])-int(cand["__year"].iloc[0])>5: continue
                    if era and _era_key(int(cand["__year"].iloc[0]))!=str(era).strip(): continue
                    z=cand.dropna(subset=["__score"]);
                    if z.empty: continue
                    w=z["__mp"].clip(lower=0); score=float((z["__score"]*w).sum()/w.sum()) if w.sum()>0 else float(z["__score"].mean())
                    rows.append({"Player_ID":clean(pid),"Player":str(cand["Player"].iloc[0]),"Peak_Start_Year":int(cand["__year"].iloc[0]),"Peak_End_Year":int(cand["__year"].iloc[-1]),"_value_num":score})
            return _finish_sdi(pd.DataFrame(rows),"five_year_peak","5-Year Peak","Historical")
        p=ROOT/"data"/"precomputed_5_year_peak"/(
            "playoff_profile_peaks_authoritative_v10.csv"
            if is_playoff else "regular_profile_peaks_authoritative_v10.csv"
        )
        if not p.exists():
            return {"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,
                    "statistic":"Statistical Dominance Index"}
        d=pd.read_csv(p,low_memory=False)
        d["_value_num"]=pd.to_numeric(d["peak_sdi"],errors="coerce")
        d=d.dropna(subset=["_value_num"]).copy()
        if era:
            d=d.loc[d["peak_start_year"].map(_era_key).eq(str(era).strip())].copy()
        if search:
            d=d.loc[d["player_name"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        d["Player_ID"]=d["player_id"]; d["Player"]=d["player_name"]
        vals=d["_value_num"].copy()
        ranks=vals.rank(method="average",ascending=False); n=len(vals)
        d["_pct"]=100.0 if n<=1 else 100.0*(n-ranks)/(n-1)
        d=d.sort_values("_value_num",ascending=(sort_direction=="asc"),kind="stable").head(int(limit)).reset_index(drop=True)
        out=[]
        for i,r in d.iterrows():
            out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
                        "season":int(r["peak_start_year"]),
                        "season_label":f'{_season_label_any(r["peak_start_year"])} → {_season_label_any(r["peak_end_year"])}',
                        "statistic":"Statistical Dominance Index","value":clean(r["_value_num"]),
                        "percentile":clean(r["_pct"]),"context":"Historical",
                        "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))})
        return {"rows":out,"count":len(out),"scope":"five_year_peak","season_type":season_type,
                "season":"5-Year Peak","season_options":[{"value":"5-Year Peak","label":"5-Year Peak"}],
                "historical_scope":False,"career_scope":False,"context":"Historical",
                "statistic":"Statistical Dominance Index","era":era or None,
                 "note":("Playoff" if is_playoff else "Regular-season")+" 5-Year Peak SDI uses the authoritative SDI v4 peak cache."}

    return {"rows":[],"count":0,"scope":scope_key,"season_type":season_type,
            "statistic":"Statistical Dominance Index","note":"Unsupported SDI Big Board scope."}


def api_big_board(season=None, context="Historical", statistic=None,
                  sort_direction="desc", search=None, limit=100, scope="single",
                  season_type="Regular Season", era=None, companion=False):
    """Canonical season-wide Big Board.

    The season selector has one Historical Percentile scope covering every
    player-season, followed by one option for every season in the database.
    """
    scope_key=str(scope).casefold()
    _stat_key=str(statistic or "").strip().casefold().replace("_"," ").replace("-"," ")
    _is_sdi=_stat_key in {"", "statistical dominance index", "statistical dominance", "sdi"}
    if _is_sdi:
        return _sdi_big_board(season,context,sort_direction,search,limit,scope,season_type,era)
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
    if statistic and not career_scope and not companion:
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
    # WOWY's audited canonical percentile layer is explicitly seasonal. For a
    # selected season (and for Historical browsing of season rows), use the
    # season percentile rather than silently selecting an empty Era/Historical
    # column.
    if str(statistic or "").strip() in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}:
        pct_col=col(work,["Season_Percentile","SeasonPercentile","Season_Pctl","SeasonPctl","Percentile_Season","Pctl_Season"])
    else:
        pct_col=col(work,pct_candidates.get("Historical" if historical_scope else context,[]))
    if pct_col is None:
        pct_col=col(work,["Percentile","percentile","Pctl","pctl","Percentile_Value","percentile_value"])
    if pct_col is None:
        raise ValueError("Canonical percentile source has no usable percentile column.")

    # Dominance Index board.
    if not statistic:
        idx_file=find_recursive_csv(ROOT,["player_statistical_dominance_v1","dominance_index"])
        if idx_file:
            d=pd.read_csv(idx_file,low_memory=False)
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
            cols=[str(c).lower() for c in pd.read_csv(f,nrows=2,low_memory=False).columns]
            if any("percentile" in c for c in cols): score+=100
            if any(c.replace("_","") in {"playerid","player_id"} for c in cols): score+=50
            if "season" in cols or "season_id" in cols: score+=50
        except Exception:
            pass
        return score

    unique.sort(key=score,reverse=True)
    for f in unique:
        try:
            df=pd.read_csv(f,low_memory=False)
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


def _comparison_percentiles_bulk(player_id, player_name, years, stats, context, is_playoffs=False):
    """Resolve all comparison percentiles for one player in one source scan.

    The previous comparison path filtered the canonical percentile table once
    per statistic. A two-player comparison can request dozens of statistics,
    turning one comparison into many full DataFrame scans. This helper narrows
    the source to the player/year universe once, then builds all requested
    statistic percentile series from that small frame.
    """
    out={str(stat):pd.Series(np.nan,index=years,dtype=float) for stat in stats}
    if not years or not stats:
        return out
    try:
        if is_playoffs:
            per=_comparison_percentile_source(True)
        else:
            per=load_canonical_percentiles()
    except Exception:
        try:
            per=_comparison_percentile_source(is_playoffs)
        except Exception:
            return out
    if per is None or per.empty:
        return out

    pidc=col(per,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(per,["Player","Player_Name","Display_Name","Name","player_name"])
    seac=col(per,["Season","season","Season_ID","SeasonEndYear","Season_End_Year","Year"])
    statc=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not seac or not statc:
        return out

    q=pd.DataFrame()
    if pidc and player_id is not None:
        q=per.loc[per[pidc].astype(str).str.strip().eq(str(player_id).strip())].copy()
    if q.empty and namec:
        wanted=str(player_name or "").replace("*","").strip().casefold()
        names=per[namec].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        q=per.loc[names.eq(wanted)].copy()
    if q.empty:
        return out

    q["__pct_year"]=q[seac].map(_season_end_year)
    q=q.dropna(subset=["__pct_year"]).copy()
    if q.empty:
        return out
    q["__pct_year"]=q["__pct_year"].astype(int)
    q=q.loc[q["__pct_year"].isin([int(y) for y in years])].copy()
    if q.empty:
        return out

    wanted_stats={str(x).strip().casefold() for x in stats}
    aliases={
        "ts_pct":{"ts_pct","ts%","ts"},
        "fg_pct":{"fg_pct","fg%"},
        "2p_pct":{"2p_pct","2p%"},
        "3p_pct":{"3p_pct","3p%"},
        "ft_pct":{"ft_pct","ft%"},
    }
    stat_to_source={}
    for requested in stats:
        key=str(requested).strip().casefold()
        stat_to_source[str(requested)]=aliases.get(key,{key})
    normalized_stat=q[statc].astype(str).str.strip().str.casefold()
    keep=pd.Series(False,index=q.index)
    for variants in stat_to_source.values():
        keep |= normalized_stat.isin(variants)
    q=q.loc[keep].copy()
    if q.empty:
        return out

    pctcol=percentile_column(q,context)
    if not pctcol:
        for fallback in (["Era","Historical"] if context=="Season" else
                         ["Season","Historical"] if context=="Era" else
                         ["Era","Season"]):
            pctcol=percentile_column(q,fallback)
            if pctcol: break
    if not pctcol:
        return out

    q["__pct"]=pd.to_numeric(q[pctcol],errors="coerce")
    q["__stat_norm"]=normalized_stat.loc[q.index]
    q=q.dropna(subset=["__pct_year","__pct"])
    if q.empty:
        return out

    for requested, variants in stat_to_source.items():
        part=q.loc[q["__stat_norm"].isin(variants),["__pct_year","__pct"]]
        if part.empty:
            continue
        part=part.drop_duplicates("__pct_year",keep="first").set_index("__pct_year")
        out[requested]=part["__pct"].reindex([int(y) for y in years])
    return out


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

        # Resolve every requested percentile for this player in one indexed
        # source scan instead of rescanning the canonical table once per stat.
        pct_bulk=_comparison_percentiles_bulk(
            pid,name,actual_years,stats,context,is_playoffs
        )

        for stat in stats:
            if stat not in rows.columns and _playoff_source_column(rows,stat) is None:
                continue
            if is_playoffs:
                scol=_playoff_source_column(rows,stat)
            else:
                scol=(col(rows,["WS/48.1","WS_per48","WS48_actual"]) if stat=="WS/48" else stat)
            if scol not in rows.columns:
                # Legacy regular-season sources may only expose total WS under
                # the WS/48 header; let the aggregation fallback handle that.
                if not (stat=="WS/48" and "WS/48" in rows.columns):
                    continue
                scol="WS/48"
            temp=rows.copy()
            if scol != stat:
                temp[stat]=temp[scol]
            value=_era_average_statistic(temp,stat,per75,additive,denom)
            stat_values[stat]=clean(value)

            pct_series=None
            try:
                years=rows["__comparison_year"].astype(int).tolist()
                pct_series=pct_bulk.get(str(stat))
                if pct_series is not None:
                    pct_series=pct_series.reindex(years)
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
        registry=pd.read_csv(canonical,low_memory=False)
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
    for _stat,_desc in [("WOWY_Offense","WOWY Offensive Impact"),("WOWY_Defense","WOWY Defensive Impact"),("WOWY_Net","WOWY Net Impact")]:
        if _stat not in existing:
            registry=pd.concat([registry,pd.DataFrame([{"Statistic":_stat,"Description":_desc}])],ignore_index=True)
    if stat_col:
        registry=registry.loc[~registry[stat_col].astype(str).str.strip().isin({"NRtg","Relative_ORtg","Relative_DRtg","Relative_NRtg","rORtg","rDRtg","rORTG","rDRTG"})].copy()
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
    header=pd.read_csv(f,nrows=0,low_memory=False)
    c=_team_columns(header)
    if not c["team"] or not c["season"]:
        CACHE[key]=None;return None
    wanted=list(dict.fromkeys([x for x in [c["team"],c["season"],c["player"],c["pid"],c["mp"],c["pts"],c["wins"],c["losses"]] if x]))
    CACHE[key]=pd.read_csv(f,usecols=wanted,low_memory=False)
    return CACHE[key]


TEAM_ANALYTICS_STATS = [
    ("rDRtg","rDRtg","lower"),
    ("rORtg","rORtg","higher"),
    ("NRtg","NRtg","higher"),
    ("Pace","Pace","higher"),
    ("rPace","rPace","higher"),
    ("ORtg","ORtg","higher"),
    ("DRtg","DRtg","lower"),
    ("TS%","TS_pct","higher"),
    ("eFG%","eFG_pct","higher"),
    ("3PAr","3PAr","higher"),
    ("TOV%","TOV_pct","lower"),
    ("ORB%","ORB_pct","higher"),
    ("FTr","FTr","higher"),
    ("Opp TOV%","Opp_TOV_pct","higher"),
    ("Opp eFG%","Opp_eFG_pct","lower"),
]

def _norm_col(s):
    return re.sub(r"[^a-z0-9]","",str(s).lower())

def _find_col(cols, names):
    mp={_norm_col(c):c for c in cols}
    for n in names:
        if _norm_col(n) in mp:return mp[_norm_col(n)]
    return None

def _find_team_analytics_source(season_type="Regular Season"):
    base=Path(os.environ.get("NBA_PER75_ROOT", str(ROOT)))
    nba_per75_root=Path(os.environ.get("NBA_PER75_ROOT", str(base.parent/"NBA_Per75")))
    # Website176 bundles the enriched Team master so the Team layer is self-contained.
    bundled=Path(__file__).resolve().parents[1]/"data"/"nba_per75_team_master_enriched.csv"
    canonical=bundled if bundled.exists() else nba_per75_root/"data"/"nba_per75_team_master_enriched.csv"
    if not canonical.exists():
        canonical=nba_per75_root/"data"/"nba_per75_team_master.csv"
    if canonical.exists():
        try:
            h=pd.read_csv(canonical,nrows=0,low_memory=False); cols=list(h.columns)
            tc=_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
            sc=_find_col(cols,["Season","season"])
            oc=_find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"])
            dc=_find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"])
            pc=_find_col(cols,["Pace","PACE"])
            if tc and sc and oc and dc and pc:
                return canonical
        except Exception:
            pass
    candidates=[]
    try:
        files=list(base.rglob("*.csv"))
    except Exception:
        files=[]
    def excluded(p):
        n=p.name.lower()
        return any(x in n for x in (
            "nba_per75_master","player_","percentile","profile","identity",
            "taxonomy","qualification","visualization","comparison"
        ))
    # Prefer the canonical team-season export over older generated team files.
    preferred=[p for p in files if not excluded(p) and (
        "team" in p.name.lower() or "teams" in p.name.lower() or
        "standings" in p.name.lower() or "franchise" in p.name.lower()
    )]
    preferred.sort(key=lambda p: (
        0 if any(x in p.name.lower() for x in ("team_seasons_v1","team_season","team_data")) else 1,
        -p.stat().st_mtime
    ))
    others=[p for p in files if p not in preferred and not excluded(p)]
    candidates=preferred+others
    for p in candidates:
        try:
            h=pd.read_csv(p,nrows=0,low_memory=False); cols=list(h.columns)
            tc=_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
            sc=_find_col(cols,["Season","season"])
            stc=_find_col(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"])
            oc=_find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"])
            dc=_find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"])
            pc=_find_col(cols,["Pace","PACE"])
            if not (tc and sc and oc and dc and pc): continue
            if season_type=="Playoffs":
                if stc is None and not re.search(r"playoff|postseason",p.name,re.I): continue
            return p
        except Exception:
            continue
    return None


def _team_metric_columns(cols):
    cols=list(cols)
    def first(names):
        targets={_norm_col(x) for x in names}
        for c in cols:
            if _norm_col(c) in targets:
                return c
        return None
    def duplicate_pair(names):
        targets={_norm_col(x) for x in names}
        matches=[c for c in cols if _norm_col(c) in targets]
        return matches[0] if matches else None, matches[-1] if len(matches)>1 else None
    efg_off, efg_opp = duplicate_pair(["eFG_pct","eFG%","EFG_PCT"])
    tov_off, tov_opp = duplicate_pair(["TOV_pct","TOV%","TOV_PCT"])
    mapping={
        "team":first(["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"]),
        "season":first(["Season","season"]),
        "season_type":first(["Season_Type","SeasonType","Season Type","Type","League_Type"]),
        "ortg":first(["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"]),
        "drtg":first(["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"]),
        "pace":first(["Pace","PACE"]),
        "rpace":first(["rPace","RPace","Relative_Pace","RelativePace"]),
        "rortg":first(["rORtg","rORTG","Relative_ORtg","Relative_ORTG"]),
        "rdrtg":first(["rDRtg","rDRTG","Relative_DRtg","Relative_DRTG"]),
        "nrtg":first(["NRtg","NRTG","Net_Rtg","NetRtg","NetRating"]),
        "tspct":first(["TS_pct","TS%","TS_PCT"]),
        "efgpct":efg_off,
        "threepar":first(["3PAr","3PA_rate","ThreePA_Rate"]),
        "tovpct":tov_off,
        "orbpct":first(["ORB_pct","ORB%","ORB_PCT"]),
        "ftr":first(["FTr","FT_Rate","FTR"]),
        "logo_id":first(["Logo_ID","LogoID","logo_id"]),
        "logo_file":first(["Logo_File","LogoFile","logo_file"]),
        "logo_source":first(["Logo_Source","LogoSource","logo_source"]),
        "wins":first(["W","Wins","Win","Playoff_Wins"]),
        "losses":first(["L","Losses","Loss","Playoff_Losses"]),
        "seed":first(["Seed","seed","Playoff_Seed"]),
        "rk":first(["Rk","RK","Rank"]),
        "opp_tovpct":first(["Opp_TOV_pct","Opp TOV%","Opponent_TOV_pct","Opponent TOV%","OppTOV%","Opponent_TOV%","Opponent TOV Pct","Opponent_TOV_PCT","Opp TOV Pct","TOV_pct_Opp","TOV%_Opp","Opp_TOV_PCT","OppTOV_pct","OpponentTOV_pct","OpponentTurnoverPct","Opponent_Turnover_Percentage"]) or tov_opp,
        "opp_efgpct":first(["Opp_eFG_pct","Opp eFG%","Opponent_eFG_pct","Opponent eFG%","OppeFG%","Opponent_eFG%","Opponent eFG Pct","Opponent_eFG_PCT","Opp eFG Pct","eFG_pct_Opp","eFG%_Opp","Opp_eFG_PCT","OppeFG_pct","OpponentEFG_pct","OpponentEffectiveFGPct","Opponent_Effective_FG_Percentage","Def_eFG_pct","Def eFG%","Defensive_eFG_pct","Defensive eFG%","Defensive_eFG%","DefeFG%","Opp eFG%"]) or efg_opp,
        # Counting inputs used to reconstruct the offensive Four Factors when
        # duplicate eFG%/TOV% headers are present in the source.
        "fg":first(["FG","FGM","Field Goals","Field_Goals"]),
        "fga":first(["FGA","Field Goal Attempts","Field_Goal_Attempts"]),
        "threep":first(["3P","3PM","3PT","Three Pointers","Three_Pointers"]),
        "threepa":first(["3PA","3PTA","Three Point Attempts","Three_Point_Attempts"]),
        "fta":first(["FTA","Free Throw Attempts","Free_Throw_Attempts"]),
        "pts":first(["PTS","Points","Tm PTS","Team PTS"]),
        "tov":first(["TOV","Turnovers","Tm TOV","Team TOV"]),
        "orb":first(["ORB","Offensive Rebounds","Tm ORB","Team ORB"]),
    }
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

        h=pd.read_csv(path,nrows=0,low_memory=False)
        c=_team_metric_columns(h.columns)
        if not (c["team"] and c["season"] and c["ortg"] and c["drtg"] and c["pace"]):
            continue
        wanted=list(dict.fromkeys([x for x in c.values() if x]))
        d=pd.read_csv(path,usecols=wanted,low_memory=False)
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

        # Reconstruct the offensive Four Factors from the team's own counting
        # columns.  This deliberately bypasses duplicate-header resolution so
        # the first eFG%/TOV% column can never be mistaken for the opponent
        # column (or vice versa). Basketball-Reference defines the offense and
        # defense Four Factors as separate quantities.
        def _series(key):
            col=c.get(key)
            return pd.to_numeric(d[col],errors="coerce") if col else pd.Series(np.nan,index=d.index)
        fgm=_series("fg"); fga=_series("fga"); threem=_series("threep"); threes=_series("threepa")
        fta=_series("fta"); pts=_series("pts"); tov=_series("tov"); orb=_series("orb")
        if c.get("efgpct") and c.get("fga"):
            # Prefer explicit offensive eFG only when the source has a uniquely
            # named offensive field. If duplicate eFG% headers exist, derive it.
            explicit_dupe = c.get("opp_efgpct") == c.get("efgpct")
            if explicit_dupe or len([x for x in h.columns if _norm_col(x) in {_norm_col("eFG_pct"),_norm_col("eFG%"),_norm_col("EFG_PCT")}])>1:
                with np.errstate(divide="ignore",invalid="ignore"):
                    d[c["efgpct"]]=(fgm + 0.5*threem)/fga
        elif c.get("fga") and c.get("fg"):
            with np.errstate(divide="ignore",invalid="ignore"):
                d["__derived_efgpct"]=(fgm + 0.5*threem)/fga
            c["efgpct"]="__derived_efgpct"
        if c.get("tovpct") and c.get("fga") and c.get("fta") and c.get("tov"):
            explicit_dupe = c.get("opp_tovpct") == c.get("tovpct")
            if explicit_dupe or len([x for x in h.columns if _norm_col(x) in {_norm_col("TOV_pct"),_norm_col("TOV%"),_norm_col("TOV_PCT")}])>1:
                with np.errstate(divide="ignore",invalid="ignore"):
                    d[c["tovpct"]]=100.0*tov/(fga+0.44*fta+tov)
        elif c.get("fga") and c.get("fta") and c.get("tov"):
            with np.errstate(divide="ignore",invalid="ignore"):
                d["__derived_tovpct"]=100.0*tov/(fga+0.44*fta+tov)
            c["tovpct"]="__derived_tovpct"

        # Reconstruct the remaining profile-relative inputs from the team's own
        # columns whenever possible. Percent values are stored as percentage
        # points in the source (e.g. .293 -> 29.3), while relative display values
        # are computed later as percentage-point differences.
        if c.get("fga") and c.get("fta"):
            with np.errstate(divide="ignore",invalid="ignore"):
                d["__derived_ftr"]=fta/fga
            c["ftr"]="__derived_ftr"
        if c.get("fga") and c.get("threepa"):
            with np.errstate(divide="ignore",invalid="ignore"):
                d["__derived_threepar"]=threes/fga
            c["threepar"]="__derived_threepar"
        if c.get("fga") and c.get("fta") and c.get("pts"):
            with np.errstate(divide="ignore",invalid="ignore"):
                d["__derived_tspct"]=pts/(2.0*(fga+0.44*fta))
            c["tspct"]="__derived_tspct"

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
                if pd.notna(v):
                    r[key]=float(v) if key not in ("logo_id","logo_file","logo_source") else str(v)

            # Guard against accidentally ingesting a player-level source.
            if r.get("nrtg") is not None:
                implied=r["ortg"]-r["drtg"]
                if abs(implied-r["nrtg"])>0.15:
                    r["nrtg"]=implied
            else:
                r["nrtg"]=r["ortg"]-r["drtg"]
            if r.get("seed") is None and r.get("rk") is not None:
                r["seed_fallback_rank"] = r.get("rk")
            rows.append(r)

        # Relative ratings are calculated from the actual team-season population
        # every time. Do not trust pre-existing rORtg/rDRtg/rPace columns because
        # some historical exports contain raw values in those fields.
        by={}
        for r in rows: by.setdefault(r["season"],[]).append(r)
        for rs in by.values():
            def mean(key):
                vals=[float(r[key]) for r in rs if r.get(key) is not None and np.isfinite(float(r[key]))]
                return sum(vals)/len(vals) if vals else None
            mo,md,mp=mean("ortg"),mean("drtg"),mean("pace")
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
        "version":19,
        "season_types":season_types,
        "rows":all_rows,
        "seasons":sorted({r["season"] for r in all_rows},reverse=True),
        "source_report":source_report,
        "opponent_columns":{
            st:{k:v for k,v in _team_metric_columns(
                pd.read_csv(Path(src),nrows=0,low_memory=False).columns
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




def _team_competitive_context_payload():
    if not TEAM_COMPETITIVE_CONTEXT_CACHE.exists():
        return {}
    try:
        p=json.loads(TEAM_COMPETITIVE_CONTEXT_CACHE.read_text(encoding="utf-8"))
        return p if isinstance(p,dict) else {}
    except Exception:
        return {}


def _context_team_key(name):
    s=re.sub(r"[^a-z0-9]", "", str(name or "").replace("*", "").lower())
    aliases={
        "okc":"oklahomacitythunder","gsw":"goldenstatewarriors","gs":"goldenstatewarriors",
        "nyk":"newyorkknicks","ny":"newyorkknicks","sas":"sanantoniospurs","sa":"sanantoniospurs",
        "phx":"phoenixsuns","pho":"phoenixsuns","phi":"philadelphia76ers","phl":"philadelphia76ers",
        "nop":"neworleanspelicans","no":"neworleanspelicans","was":"washingtonwizards","wsh":"washingtonwizards",
        "lac":"losangelesclippers","lal":"losangeleslakers","utah":"utahjazz","uta":"utahjazz",
        "sea":"seattlesupersonics","njn":"brooklynnets","van":"memphisgrizzlies",
        "syr":"philadelphia76ers","roc":"sacramentokings","cin":"sacramentokings","kck":"sacramentokings",
        "stl":"atlantahawks","mlh":"atlantahawks","tri":"atlantahawks","phw":"goldenstatewarriors",
        "sfw":"goldenstatewarriors","ftw":"detroitpistons","wsb":"washingtonwizards","cap":"washingtonwizards",
        "bal":"washingtonwizards","blb":"washingtonwizards","ino":"indianapolispacers",
    }
    return aliases.get(s,s)


def _merge_team_competitive_context(rows):
    # First use the existing competitive-context layer, then apply the
    # Basketball-Reference-derived playoff outcome map when available.
    success_map={}
    try:
        if TEAM_PLAYOFF_SUCCESS_CACHE.exists():
            sp=json.loads(TEAM_PLAYOFF_SUCCESS_CACHE.read_text(encoding="utf-8"))
            success_map=sp.get("rows",{}) if isinstance(sp,dict) else {}
    except Exception:
        success_map={}
    payload=_team_competitive_context_payload()
    seasons=payload.get("seasons",{}) if isinstance(payload,dict) else {}
    if not seasons:return rows
    for r in rows:
        se=str(r.get("season") or "")
        tm=_context_team_key(r.get("team"))
        matches=seasons.get(se,[])
        hit=None
        for x in matches:
            if _context_team_key(x.get("team_key") or x.get("team"))==tm:
                hit=x;break
        if hit:
            for k in ("seed","conference","wins","losses","playoff_finish","playoff_status","playoff_round","series_wins","series_losses"):
                if k in hit:r[k]=hit[k]
            r["competitive_context_source"]="Land of Basketball + Basketball-Reference (V2)"
        sk=f"{se}|||{str(r.get('team') or '').replace('*','').strip()}"
        if sk in success_map:
            r["playoff_status"]=success_map[sk]
            r["playoff_finish"]=success_map[sk]
            r["competitive_context_source"]="Basketball-Reference series cache + canonical team qualification"
    return rows

def _team_analytics_payload():
    if TEAM_ANALYTICS_CACHE.exists():
        try:
            p=json.loads(TEAM_ANALYTICS_CACHE.read_text(encoding="utf-8"))
            if p.get("version")==19 and p.get("season_types"):
                return p
        except Exception:
            pass
    return _build_team_analytics_cache()



_TEAM_STAT_KEY_MAP = {
    "rDRtg":"rdrtg","rORtg":"rortg","NRtg":"nrtg","Pace":"pace","rPace":"rpace",
    "ORtg":"ortg","DRtg":"drtg","TS%":"tspct",
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
    _merge_team_competitive_context(all_rows)

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
    # Team Profiles use relative versions for the rate/factor statistics.
    # The relative value is team minus that season's team average, expressed in
    # percentage points for ratio statistics (e.g. .293-.202 -> +9.1%).
    profile_defs=[
        ("Relative ORtg","rORtg","rortg","higher","number"),
        ("Relative DRtg","rDRtg","rdrtg","lower","number"),
        ("NRtg","NRtg","nrtg","higher","number"),
        ("Relative Pace","rPace","rpace","higher","number"),
        ("Relative TS%","rTS%","tspct","higher","ratio"),
        ("Relative eFG%","reFG%","efgpct","higher","ratio"),
        ("Relative 3PAr","r3PAr","threepar","higher","ratio"),
        ("Relative FTr","rFTr","ftr","higher","ratio"),
        ("Relative TOV%","rTOV%","tovpct","lower","ratio"),
        ("Relative ORB%","rORB%","orbpct","higher","ratio"),
        ("Relative Opponent TOV%","rOpponent TOV%","opp_tovpct","higher","ratio"),
        ("Relative Opponent eFG%","rOpponent eFG%","opp_efgpct","lower","ratio"),
    ]
    stats=[]
    season_pop=populations["season"]
    for label,key,rawkey,direction,kind in profile_defs:
        value=row.get(rawkey)
        vals=[r.get(rawkey) for r in season_pop]
        vals_num=[float(v) for v in vals if v is not None and np.isfinite(float(v))]
        if value is None or not np.isfinite(float(value)) or not vals_num:
            continue
        avg=sum(vals_num)/len(vals_num)
        rel=float(value)-avg
        if kind=="ratio": rel*=100.0
        # For percentage/rate metrics, the historical percentile population is
        # built from the same relative metric across every historical team-season.
        historical_rel=[]
        for rr in all_rows:
            rv=rr.get(rawkey)
            if rv is None or not np.isfinite(float(rv)): continue
            # Compute the historical season mean for this raw key lazily below.
            historical_rel.append(rv)
        # Build exact season-relative population once per raw key.
        rel_population=[]
        for season_key in sorted({str(rr.get("season")) for rr in all_rows}):
            sp=[rr for rr in all_rows if str(rr.get("season"))==season_key]
            vv=[rr.get(rawkey) for rr in sp if rr.get(rawkey) is not None and np.isfinite(float(rr.get(rawkey)))]
            if not vv: continue
            aa=sum(float(x) for x in vv)/len(vv)
            rel_population.extend([(float(x)-aa)*(100.0 if kind=="ratio" else 1.0) for x in vv])
        pct=_team_percentile(rel,rel_population,higher=(direction=="higher"))
        stats.append({"key":key,"label":label,"value":rel,"direction":direction,
                      "relative_kind":kind,"percentiles":{"historical":pct},
                      "raw_value":value,"season_average":avg})
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
    _merge_team_competitive_context(rows)
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
            # FAST PUBLIC DATA LAYER: these endpoints use one indexed SQLite database
            # and never touch the large research CSVs on the request path.
            if u.path == "/api/v1/public/players" and public_search_players:
                qv=q.get("q",[""])[0]
                return self.send_json(200,{"players":public_search_players(qv,50),"public_layer":True})
            if u.path == "/api/v1/public/players/curated" and public_search_players_batch:
                raw=q.get("names",[""])[0]
                names=[unquote(x).strip() for x in raw.split(",") if x.strip()]
                return self.send_json(200,{"players":public_search_players_batch(names),"public_layer":True,"batch":True})
            m=re.fullmatch(r"/api/v1/public/players/(.+?)/season-bundles",u.path)
            if m and public_player_season_bundles:
                return self.send_json(200,public_player_season_bundles(unquote(m.group(1)),q.get("season_type",["Regular Season"])[0]))
            m=re.fullmatch(r"/api/v1/public/players/(.+?)/profile",u.path)
            if m and public_player_season_bundle:
                return self.send_json(200,public_player_season_bundle(unquote(m.group(1)),q.get("season",[""])[0],q.get("season_type",["Regular Season"])[0]))
            if u.path == "/api/v1/public/big-board-companion" and big_board_companion:
                raw_ids=q.get("player_ids",[""])[0]
                player_ids=[unquote(x).strip() for x in raw_ids.split(",") if x.strip()]
                return self.send_json(200,big_board_companion(q.get("statistic",["PTS_per75"])[0],q.get("season",["Historical Percentile"])[0],q.get("context",["Historical"])[0],player_ids,q.get("era",[""])[0]))
            if u.path == "/api/v1/public/explorer" and public_explorer_population:
                def _num(name):
                    raw=q.get(name,[None])[0]
                    if raw in (None, "", "null", "None"): return None
                    try: return float(raw)
                    except Exception: return None
                xs=q.get("x_statistic",["PTS_per75"])[0]; ys=q.get("y_statistic",["rTS"])[0]
                season_q=q.get("season",["Historical Percentile"])[0]; st=q.get("season_type",["Regular Season"])[0]
                scope_q=q.get("scope",["single"])[0]; era_q=q.get("era",[""])[0]; search_q=q.get("search",[""])[0]
                xmin,xmax,ymin,ymax=_num("x_min"),_num("x_max"),_num("y_min"),_num("y_max")
                result=public_explorer_population(xs,ys,season_q,st,era_q,search_q,xmin,xmax,ymin,ymax,100,scope_q)
                if result.get("fallback"):
                    # Preserve the existing methodology for non-indexed views while
                    # applying the new Explorer semantics: join the full X/Y result,
                    # filter both axes, then rank/limit by X.
                    requested_context = "Career" if scope_q=="career" else ("Historical" if scope_q=="five_year_peak" else ("Era" if scope_q=="era" else ("Era" if era_q else "Historical")))
                    requested_season = None if scope_q in {"career","era","five_year_peak"} else season_q
                    xb=api_big_board(requested_season,requested_context,xs,"desc",search_q,10000,scope_q,st,era_q)
                    yb=api_big_board(requested_season,requested_context,ys,"desc",search_q,10000,scope_q,st,era_q)
                    xrows=xb.get("rows",[]) if isinstance(xb,dict) else []; yrows=yb.get("rows",[]) if isinstance(yb,dict) else []
                    key=lambda r:f"{r.get('player_id') or r.get('player_name')}|||{r.get('season_label') or r.get('season') or ''}"
                    ym={key(r):r for r in yrows}; merged=[]
                    for r in xrows:
                        yr=ym.get(key(r)); xv, yv = (float(r.get("value")) if r.get("value") is not None else None), (float(yr.get("value")) if yr and yr.get("value") is not None else None)
                        if xv is None or yv is None: continue
                        if xmin is not None and xv<xmin or xmax is not None and xv>xmax or ymin is not None and yv<ymin or ymax is not None and yv>ymax: continue
                        merged.append({'player_id':r.get('player_id'),'player_name':r.get('player_name'),'season':r.get('season'),'season_label':r.get('season_label') or r.get('season'),'xValue':xv,'yValue':yv,'headshot_url':None})
                    merged.sort(key=lambda r:(-r['xValue'],str(r.get('player_name') or '').casefold()))
                    total=len(merged); result={'rows':merged[:100],'count':min(total,100),'total':total,'population_total':total,'x_statistic':xs,'y_statistic':ys,'season':season_q,'season_type':st,'scope':scope_q,'era':era_q,'ranked_by':'x','rank_direction':'desc','public_layer':False,'available_bounds':{'xmin':min((r['xValue'] for r in merged),default=None),'xmax':max((r['xValue'] for r in merged),default=None),'ymin':min((r['yValue'] for r in merged),default=None),'ymax':max((r['yValue'] for r in merged),default=None)}}
                if isinstance(result,dict) and isinstance(result.get("rows"),list):
                    for row in result["rows"]:
                        if not row.get("headshot_url"): row["headshot_url"]=_headshot_url_for(row.get("player_id"),row.get("player_name"))
                return self.send_json(200,result)
            if u.path == "/api/v1/public/big-board" and public_big_board:
                return self.send_json(200,public_big_board(q.get("statistic",["PTS_per75"])[0],q.get("season",["Historical Percentile"])[0],q.get("context",["Historical"])[0],q.get("sort",["desc"])[0],q.get("search",[""])[0],int(q.get("limit",["100"])[0] or 100),q.get("era",[""])[0]))
            if u.path == "/api/v1/public/teams" and public_teams:
                return self.send_json(200,public_teams(q.get("season",[""])[0],q.get("season_type",["Regular Season"])[0],q.get("era",[""])[0]))
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
                    str(q.get("companion", ["0"])[0]).casefold() in {"1","true","yes"},
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
                    candidate_urls=[str(url)]
                    last_error=None
                    if candidate_urls and str(candidate_urls[0]).lower().startswith(("http://","https://")):
                        for candidate_url in candidate_urls:
                            try:
                                req=Request(str(candidate_url), headers={
                                    "User-Agent":"Mozilla/5.0 NBA-PER75/1.0",
                                    "Accept":"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                                    "Referer":"https://www.basketball-reference.com/",
                                })
                                with urlopen(req, timeout=12) as resp:
                                    body=resp.read()
                                    ctype=resp.headers.get("Content-Type","image/jpeg").split(";")[0]
                                if body and str(ctype).startswith("image/"):
                                    break
                            except Exception as exc:
                                last_error=exc
                                body=b""
                                continue
                        if not body:
                            if last_error: raise last_error
                            raise ValueError("Empty image response")
                    else:
                        fp=Path(str(url))
                        if not fp.is_absolute():
                            rel=str(fp).lstrip("/\\")
                            fp=(ROOT/"public"/rel).resolve()
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

            m = re.fullmatch(r"/api/v1/players/(.+?)/seasons", u.path)
            if m:
                return self.send_json(200, api_player_seasons(
                    unquote(m.group(1)),
                    q.get("season_type", ["Regular Season"])[0],
                ))
            m = re.fullmatch(r"/api/v1/players/(.+?)/categories", u.path)
            if m:
                requested=unquote(m.group(1))
                result=api_spider(
                    requested,
                    q.get("season", ["Career"])[0],
                    q.get("context", ["Historical"])[0],
                    q.get("stats", [None])[0],
                    q.get("season_type", ["Regular Season"])[0],
                )
                return self.send_json(200, {
                    "player_id": result.get("player",{}).get("player_id"),
                    "Player": result.get("player",{}).get("player_name"),
                    "data": result.get("category_axes",[]),
                })
            m = re.fullmatch(r"/api/v1/players/(.+?)/subcategories", u.path)
            if m:
                requested=unquote(m.group(1))
                pid,pname=resolve_player_identity(requested)
                result=api_spider(
                    requested,
                    q.get("season", ["Career"])[0],
                    q.get("context", ["Historical"])[0],
                    q.get("stats", [None])[0],
                    q.get("season_type", ["Regular Season"])[0],
                )
                # Return the six category axes plus the underlying weighted
                # subcategory definitions, using the canonical aggregation spec.
                spec=load_exact_csv("aggregation_spec","player_subcategory_aggregation_spec_v1.csv")
                rows=[]
                if not spec.empty:
                    cat=choose_col(spec,["Category"]); grp=choose_col(spec,["Group_ID","Group","Group_Id"])
                    st=choose_col(spec,["Statistic","Stat"]); sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
                    if all([cat,grp,st,sw]):
                        for _,rr in spec.iterrows():
                            rows.append({
                                "Category":str(rr[cat]),
                                "Subcategory":str(rr[grp]),
                                "Statistic":str(rr[st]),
                                "Statistic_Weight":float(rr[sw]) if pd.notna(rr[sw]) else None,
                            })
                return self.send_json(200, {
                    "player_id":pid,"Player":pname,
                    "data":rows,
                    "category_axes":result.get("category_axes",[]),
                })
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
    """Build the regular 5-Year Peak JSON once when the API starts.

    This moves the expensive league-wide calculation out of the user's click
    path. Once written, profile requests read only the selected player's row.
    """
    path=ROOT / "data" / "precomputed_5_year_peak" / "regular_profile_peaks.json"
    if path.exists():
        return True
    try:
        builder_candidates=[
            ROOT/"analysis"/"build_precomputed_5_year_peaks.py",
            ROOT/"local_api"/"build_precomputed_5_year_peaks.py",
        ]
        builder=next((p for p in builder_candidates if p.exists()),None)
        if builder:
            import subprocess,sys
            subprocess.run([sys.executable,str(builder)],cwd=str(ROOT),check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
            return path.exists()
        # Fall back to the canonical single-player calculation already present
        # in this API. This runs once at API startup and persists the results.
        reg=_canonical_identity_registry()
        if reg.empty:
            return False
        ic=identity_cols(reg)
        if not ic.get("id") or not ic.get("name"):
            return False
        players=[]
        total=len(reg)
        for n,(_,rr) in enumerate(reg.iterrows(),1):
            pid=clean(rr[ic["id"]])
            pname=clean(rr[ic["name"]])
            try:
                result=_canonical_five_year_peak_profile(pid,pname)
                if result and result.get("found"):
                    p=result.get("profile",{}) or {}
                    stats=result.get("statistic_values",{}) or {}
                    # Persist only the compact fields required by the profile
                    # fast path.
                    packed={
                        "player_id":pid,
                        "player_name":pname,
                        "peak_start_year":p.get("Peak_Start_Year"),
                        "peak_end_year":p.get("Peak_End_Year"),
                        "peak_seasons":p.get("Peak_Seasons",[]),
                        "peak_era":p.get("Peak_Era"),
                        "peak_sdi":p.get("Peak_SDI"),
                        "statistics":stats,
                    }
                    players.append(packed)
            except Exception:
                continue
        if players:
            payload={"version":"regular_profile_peaks_v1",
                     "player_count":len(players),"players":players}
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
            return True
    except Exception:
        return False
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

        try:
            print("Warming precomputed playoff 5-Year Peak cache...")
            _preload_playoff_peak_cache()
            print("Playoff 5-Year Peak cache ready.")
        except Exception as e:
            print("Playoff 5-Year Peak cache warm failed:", repr(e))

        try:
            print("Warming Career spider cache...")
            _warm_regular_career_spider_cache()
            print("Career spider cache ready.")
        except Exception as e:
            print("Career spider cache warm failed:", repr(e))

        try:
            print("Warming Career SDI spider axes...")
            _warm_career_sdi_axes()
            print("Career SDI spider axes ready.")
        except Exception as e:
            print("Career SDI spider warm failed:", repr(e))

    import threading
    threading.Thread(target=warm_caches, name="NBA-PER75-cache-warm", daemon=True).start()
    server.serve_forever()



def _sdi_v4_weighted_top_level(category_scores):
    """Combine available SDI categories using the locked intended weights.

    Missing categories are not assigned a 50th-percentile score. Their intended
    weights are removed and the available category weights are renormalized.
    """
    w=SDI_V4_TOP_LEVEL_WEIGHTS
    usable=[(float(category_scores[k]),float(weight)) for k,weight in w.items()
            if k in category_scores and category_scores[k] is not None and pd.notna(category_scores[k])]
    if not usable: return None
    den=sum(weight for _,weight in usable)
    return sum(value*weight for value,weight in usable)/den if den>0 else None

