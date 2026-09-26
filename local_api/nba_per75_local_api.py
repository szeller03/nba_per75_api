
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
    from public_data_layer import search_players as public_search_players, search_players_batch as public_search_players_batch, player_season_bundles as public_player_season_bundles, player_season_bundle as public_player_season_bundle, big_board as public_big_board, big_board_companion, explorer_population as public_explorer_population, teams as public_teams, warm_public_profile_data
except Exception:
    public_search_players = public_search_players_batch = public_player_season_bundles = public_player_season_bundle = public_big_board = public_explorer_population = public_teams = warm_public_profile_data = None
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
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# --- SDI v4 revised top-level weights ---
SDI_V4_TOP_LEVEL_WEIGHTS = {
    "scoring_volume": 0.22,
    "scoring_efficiency": 0.20,
    "creation_playmaking": 0.20,
    "rebounding": 0.105,
    "defense": 0.22,
    "impact_value": 0.055,
}

# Playoff SDI deliberately excludes categories that are not historically
# defensible across the full postseason record. Impact / Value is excluded
# because it is WOWY-based and unavailable in playoffs. Defense is excluded
# because STL/BLK tracking is historically incomplete and activity-only
# measures are not a sufficiently consistent representation of postseason
# defense across the full 1952-present sample. The remaining four categories
# retain their prior relative weights and are renormalized to 100%.
# Playoff SDI uses the locked regular-season SDI v4 weights/formulas as its
# source of truth.  Only two playoff exclusions are applied: Defense and
# Impact / Value are removed entirely, and WOWY Offense is removed from
# Creation & Playmaking with the remaining Creation groups proportionally
# renormalized.  The regular-season constants above are never modified.
_PLAYOFF_REGULAR_TOP = {
    "Scoring Volume": 0.20,
    "Scoring Efficiency": 0.18,
    "Creation & Playmaking": 0.18,
    "Rebounding": 0.105,
    "Defense": 0.20,
    "Impact & Value": 0.135,
}
_PLAYOFF_TOP_DENOM = sum(_PLAYOFF_REGULAR_TOP[k] for k in (
    "Scoring Volume", "Scoring Efficiency", "Creation & Playmaking", "Rebounding"
))
PLAYOFF_SDI_TOP_LEVEL_WEIGHTS = {
    k: _PLAYOFF_REGULAR_TOP[k] / _PLAYOFF_TOP_DENOM
    for k in ("Scoring Volume", "Scoring Efficiency", "Creation & Playmaking", "Rebounding")
}
PLAYOFF_SDI_CATEGORY_GROUP_RENORM = {
    "Creation & Playmaking": {
        # Regular-season Creation groups are .385/.315/.300.
        # Removing WOWY Offense leaves .385/.315, normalized to .55/.45.
        "Creation Output": 0.55,
        "Ball Security / Creation Cost": 0.45,
    },
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
        # Career category scores are a frozen/authoritative layer. Search the
        # project tree for that exact legacy source so a data-folder relocation
        # cannot silently trigger a recomputation from the active SDI formula.
        path = _recursive_file(["regular_career_sdi_v4_wowy_rts.csv"])
        out = {"id": {}, "name": {}}
        if path is None or not path.exists():
            _CAREER_SDI_AXES = out
            return
        sd = pd.read_csv(path, low_memory=False)
        sid = col(sd,["Player_ID","PlayerId","PlayerID","player_id"])
        sn = col(sd,["Player","Player_Name","Display_Name","player_name","Name"])
        mapping=[("Scoring Volume","Career_scoring_volume"),("Scoring Efficiency","Career_scoring_efficiency"),("Creation & Playmaking","Career_creation_playmaking"),("Rebounding","Career_rebounding"),("Defense","Career_defense"),("Impact & Value","Career_impact_value")]
        # Preserve the underlying Career category composites exactly as the
        # authoritative source computes them.  The player-facing spider,
        # however, is a percentile-based display: each category score is
        # percentile-ranked across the qualified Career population.  Changing
        # top-level SDI weights must therefore never alter a category's own
        # score; it only changes how that score contributes to the overall SDI.
        raw_rows=[]
        for _, r in sd.iterrows():
            item={"id": str(r.get(sid,"" )).strip() if sid else "",
                  "name": str(r.get(sn,"" )).replace("*","").strip().casefold() if sn else ""}
            for label, field in mapping:
                val=pd.to_numeric(r.get(field,np.nan),errors="coerce")
                item[label]=float(val) if pd.notna(val) else np.nan
                cov=pd.to_numeric(r.get(field+"_Coverage",np.nan),errors="coerce")
                item[label+"_coverage"]=None if pd.isna(cov) else float(cov)
            raw_rows.append(item)

        # Route-A/Route-B career companion percentile: higher category score is
        # better, and the qualified population is the same population used by
        # the canonical Career SDI layer.  The raw composite remains available
        # as `score` for diagnostics; `value` is the viewer-facing percentile.
        for label, _field in mapping:
            vals=pd.Series([x.get(label,np.nan) for x in raw_rows],dtype="float64")
            valid=vals.notna()
            pct=pd.Series(np.nan,index=vals.index,dtype="float64")
            if valid.any():
                ranks=vals.loc[valid].rank(method="average",ascending=True)
                n=int(valid.sum())
                pct.loc[valid]=100.0 if n==1 else 100.0*(ranks-1.0)/(n-1.0)
            for i,item in enumerate(raw_rows):
                item[label+"_percentile"]=float(pct.iloc[i]) if pd.notna(pct.iloc[i]) else np.nan

        for item in raw_rows:
            axes=[]
            for label, field in mapping:
                raw=item.get(label,np.nan)
                pctl=item.get(label+"_percentile",np.nan)
                if pd.notna(raw):
                    cov=item.get(label+"_coverage")
                    axes.append({"axis":label,
                                 "value":float(pctl) if pd.notna(pctl) else float(raw),
                                 "score":float(raw),
                                 "percentile":float(pctl) if pd.notna(pctl) else None,
                                 "coverage":cov})
            if not axes:
                continue
            if item.get("id"):
                out["id"][item["id"]]=axes
            if item.get("name"):
                out["name"][item["name"]]=axes
        _CAREER_SDI_AXES=out

def _rebuild_career_category_axes_from_current_formula(pid=None, pname=None):
    """Rebuild Career category axes from the current Career percentile layer.

    The legacy regular_career_sdi_v4_wowy_rts.csv is a frozen composite and can
    retain category values calculated with an older subcategory formula. Career
    profile axes must instead be regenerated from the canonical career
    statistic-percentile rows using the active locked aggregation specification.
    This keeps changes such as AST:TOV=100% from being masked by a stale cache.
    """
    try:
        rows=_regular_career_profile_rows(player_id=pid, player_name=pname)
        if not rows:
            return []
        pm=pd.DataFrame(rows)
        pct_col="Career_Percentile"
        if pct_col not in pm.columns:
            return []
        axes=_availability_aware_category_axes(pm,pct_col,playoff=False)
        if not axes:
            return []
        return axes
    except Exception:
        return []


def _career_sdi_axes(pid=None, pname=None):
    """Return Career SDI axes with percentile values for Profile display.

    The authoritative Career category layer supplies the raw category scores.
    The Profile must display category percentiles, never those raw scores.
    Defense is a special evidence-aware case: the locked WOWY Defense layer is
    the defensible Career source for sparse early tracking. Its season-level
    WOWY Defense percentiles are averaged across the player's qualifying career
    seasons, preventing a tiny recorded STL/BLK sample from turning Wilt's
    Career Defense into an artificial 100.
    """
    _warm_career_sdi_axes()
    cache=_CAREER_SDI_AXES or {}
    axes=[]
    if pid is not None:
        axes=cache.get("id",{}).get(str(pid).strip(),[]) or []
    if not axes and pname:
        axes=cache.get("name",{}).get(str(pname).replace("*","").strip().casefold(),[]) or []
    axes=[dict(a) for a in axes]
    if not axes:
        return []

    # Convert the authoritative raw category scores to their category
    # percentiles. This keeps raw SDI in `score` while `value` is explicitly
    # the percentile consumed by the Profile UI.
    pop={}
    for payload_axes in (cache.get("id",{}) or {}).values():
        for a in payload_axes or []:
            label=str(a.get("axis") or a.get("label") or "")
            if label.casefold()=="defense":
                continue
            raw=a.get("score",a.get("raw_score"))
            try: raw=float(raw)
            except Exception: continue
            if np.isfinite(raw): pop.setdefault(label,[]).append(raw)

    for a in axes:
        label=str(a.get("axis") or a.get("label") or "")
        raw=a.get("score",a.get("raw_score"))
        try: raw=float(raw)
        except Exception: raw=None
        a["score"]=raw
        a["raw_score"]=raw
        if label.casefold()=="defense":
            continue
        a["percentile"]=_percentile_rank_0_100(raw,pop.get(label,[])) if raw is not None else None
        a["value"]=a["percentile"]

    # Evidence-aware Career Defense from the authoritative player WOWY season
    # layer. This is intentionally separate from the sparse STL/BLK composites.
    try:
        wpath=_recursive_file(["player_wowy_statistics_v1.csv"])
        if wpath is not None and wpath.exists():
            wd=pd.read_csv(wpath,low_memory=False)
            nc=col(wd,["Player","Player_Name","Display_Name","player_name","Name"])
            ic=col(wd,["Player_ID","PlayerId","PlayerID","player_id"])
            dc=col(wd,["WOWY_Defense_Percentile"])
            if dc and (ic or nc):
                hit=pd.DataFrame()
                if ic and pid is not None:
                    hit=wd.loc[wd[ic].astype(str).str.strip().eq(str(pid).strip())].copy()
                if hit.empty and nc and pname:
                    nk=_normalize_peak_lookup_name(pname)
                    hit=wd.loc[wd[nc].map(_normalize_peak_lookup_name).eq(nk)].copy()
                if not hit.empty:
                    wp=pd.to_numeric(hit[dc],errors="coerce").dropna()
                    if not wp.empty:
                        defense_pct=float(wp.mean())
                        for a in axes:
                            if str(a.get("axis") or a.get("label") or "").casefold()=="defense":
                                # Keep the authoritative category score for
                                # diagnostics, but the Profile-facing value is
                                # the evidence-aware WOWY Defense percentile.
                                a["percentile"]=defense_pct
                                a["value"]=defense_pct
                                a["coverage"]=None
                                break
    except Exception:
        pass

    return axes

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
        # Build the visible Career category axes from the authoritative Career
        # SDI category layer. The raw category score stays in `score`; the
        # Profile-facing `value` is always the category percentile.
        category_axes_by_id = {}
        category_axes_by_name = {}

        # Career Defense is evidence-aware: use the authoritative season-level
        # WOWY Defense percentile layer rather than allowing sparse STL/BLK
        # tracking to produce an artificial 100 for historical players.
        _career_wowy_def_pct_id = {}
        _career_wowy_def_pct_name = {}
        try:
            _wpath = _recursive_file(["player_wowy_statistics_v1.csv"])
            if _wpath is not None and _wpath.exists():
                _wd = pd.read_csv(_wpath, low_memory=False)
                _wic = col(_wd,["Player_ID","PlayerId","PlayerID","player_id"])
                _wnc = col(_wd,["Player","Player_Name","Display_Name","player_name","Name"])
                _wdc = col(_wd,["WOWY_Defense_Percentile"])
                if _wdc:
                    _wd["__def_pct"] = pd.to_numeric(_wd[_wdc], errors="coerce")
                    _wd = _wd.dropna(subset=["__def_pct"])
                    if _wic:
                        _career_wowy_def_pct_id = _wd.groupby(_wd[_wic].astype(str).str.strip())["__def_pct"].mean().to_dict()
                    if _wnc:
                        _career_wowy_def_pct_name = _wd.groupby(_wd[_wnc].map(lambda v: str(v).replace("*","").strip().casefold()))["__def_pct"].mean().to_dict()
        except Exception:
            _career_wowy_def_pct_id = {}
            _career_wowy_def_pct_name = {}

        # Career STL/BLK are only legitimate inputs when the underlying career
        # record has meaningful tracking coverage. A career rate/value created
        # from one recorded season (e.g. Wilt's historical BLK record) must not
        # be treated as if the stat were observed for his entire career.
        _tracking_coverage = {}
        try:
            _prof_path=ROOT / "player_profiles_v1" / "player_season_profiles.csv"
            if _prof_path.exists():
                _pr=pd.read_csv(_prof_path,low_memory=False)
                _pst=col(_pr,["Season_Type","SeasonType","season_type","Phase"])
                if _pst:
                    _pr=_pr.loc[_pr[_pst].astype(str).str.strip().str.casefold().isin({"regular season","regular","reg season"})].copy()
                _ppid=col(_pr,["Player_ID","PlayerId","PlayerID","player_id"])
                _pmp=col(_pr,["MP","Minutes","minutes"])
                if _ppid:
                    _pr["__pidkey"]=_pr[_ppid].astype(str).str.strip()
                    _pr["__mpkey"]=pd.to_numeric(_pr[_pmp],errors="coerce") if _pmp else 0.0
                    for _stat,_raw in [("STL_per75","STL_raw"),("BLK_per75","BLK_raw")]:
                        if _raw in _pr.columns:
                            _rv=pd.to_numeric(_pr[_raw],errors="coerce")
                            for _pidkey,_gg in _pr.groupby("__pidkey",sort=False):
                                _mpv=pd.to_numeric(_gg["__mpkey"],errors="coerce").fillna(0.0)
                                _mask=_rv.loc[_gg.index].notna() & _mpv.gt(0)
                                total_mp=float(_mpv.sum())
                                observed_mp=float(_mpv.loc[_mask].sum()) if _mask.any() else 0.0
                                _tracking_coverage.setdefault(str(_pidkey).strip(),{})[_stat]=(observed_mp/total_mp if total_mp>0 else 0.0)
        except Exception:
            _tracking_coverage={}

        for _, r0 in qualified.iterrows():
            pid0 = str(r0.get("Player_ID", "")).strip()
            pname0 = str(r0.get("Player", "")).replace("*", "").strip()
            stat_rows0 = []
            for stat0 in REGULAR_STATS:
                if stat0 not in r0.index:
                    continue
                value0 = r0.get(stat0, np.nan)
                pct0 = r0.get(f"__pct__{stat0}", np.nan)
                if pd.isna(value0):
                    continue
                stat_rows0.append({
                    "Statistic": stat0,
                    "Career_Value": clean(value0),
                    "Career_Percentile": clean(pct0),
                })
            if stat_rows0:
                # Exclude historically under-tracked STL/BLK career evidence
                # from the defense formula when coverage is below 50% of career
                # minutes. This does not affect WOWY Defense, which remains the
                # authoritative regular-season defensive component.
                _pidcov=_tracking_coverage.get(pid0,{})
                _filtered=[]
                for _sr in stat_rows0:
                    _st=_sr.get("Statistic")
                    if _st in {"STL_per75","BLK_per75","STL_pct","BLK_pct"}:
                        _base="STL_per75" if _st.startswith("STL") else "BLK_per75"
                        if float(_pidcov.get(_base,0.0)) < 0.50:
                            continue
                    _filtered.append(_sr)
                stat_rows0=_filtered
            # Use the authoritative raw Career category composites. Do not
            # rebuild them from individual statistic percentiles: that was the
            # source of the historical Wilt/Russell Defense discrepancy and can
            # silently drop Impact / Value.
            axes0=[dict(a) for a in ((_CAREER_SDI_AXES or {}).get("id",{}).get(pid0,[]) or [])]
            if not axes0 and pname0:
                axes0=[dict(a) for a in ((_CAREER_SDI_AXES or {}).get("name",{}).get(pname0.casefold(),[]) or [])]
            for ax0 in axes0:
                raw=ax0.get("score",ax0.get("raw_score"))
                try: raw=float(raw)
                except Exception: raw=None
                ax0["score"]=raw
                ax0["raw_score"]=raw
                # _warm_career_sdi_axes already computes category percentiles
                # from the authoritative raw Career population.
                pct=ax0.get("percentile")
                try: pct=float(pct) if pct is not None else None
                except Exception: pct=None
                ax0["percentile"]=pct
                ax0["value"]=pct
                if str(ax0.get("axis") or ax0.get("label") or "").casefold()=="defense":
                    w_pct=_career_wowy_def_pct_id.get(pid0)
                    if w_pct is None and pname0:
                        w_pct=_career_wowy_def_pct_name.get(pname0.casefold())
                    if w_pct is not None:
                        ax0["percentile"]=float(w_pct)
                        ax0["value"]=float(w_pct)
            if pid0:
                category_axes_by_id[pid0] = axes0
            if pname0:
                category_axes_by_name[pname0.casefold()] = axes0

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

            # These are the raw category SDI composites generated from the
            # active canonical Career percentile layer and locked subcategory
            # weights. They are the values the Player Profile should display.
            career_axes = category_axes_by_id.get(pid, [])
            if not career_axes:
                career_axes = category_axes_by_name.get(pname, [])
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
    ("1952-1969", 1952, 1969, "1952–1969 · Shot Clock Era"),
    ("1970-1979", 1970, 1979, "1970–1979 · Merger Era"),
    ("1980-1990", 1980, 1990, "1980–1990 · Showtime Era"),
    ("1991-1998", 1991, 1998, "1991–1998 · Jordan Era"),
    ("1999-2006", 1999, 2006, "1999–2006 · Deadball Era"),
    ("2007-2013", 2007, 2013, "2007–2013 · Superteam Era"),
    ("2014-2020", 2014, 2020, "2014–2020 · Moreyball Era"),
    ("2021-2026", 2021, 2026, "2021–2026 · Positionless Era"),
]

def _career_recorded_ast_tov(player_id=None, player_name=None):
    """Career AST:TOV using only regular-season seasons with recorded turnovers.

    Turnover-unrecorded seasons are excluded rather than treated as zero.
    Multi-team seasons are aggregated by season before the career ratio is formed.
    """
    try:
        master=load_master_seasons()
        if master is None or master.empty:
            return None
        pidc=col(master,["Player_ID","PlayerId","PlayerID","player_id"])
        namec=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
        stc=col(master,["Season_Type","season_type","SeasonType"])
        sc=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        astc=col(master,["AST"])
        tovc=col(master,["TOV"])
        if not sc or not astc or not tovc:
            return None
        m=master.copy()
        if stc:
            m=m.loc[~m[stc].astype(str).str.casefold().isin({"playoffs","playoff","postseason"})].copy()
        if pidc and player_id is not None:
            m=m.loc[m[pidc].astype(str).str.strip().eq(str(player_id).strip())].copy()
        elif namec and player_name:
            wanted=str(player_name).replace("*","").strip().casefold()
            m=m.loc[m[namec].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
        if m.empty:
            return None
        m["__season_key"]=m[sc].map(_season_label_any)
        m["__ast"]=pd.to_numeric(m[astc],errors="coerce")
        m["__tov"]=pd.to_numeric(m[tovc],errors="coerce")
        # Aggregate team rows within each season first. A season qualifies for
        # the ratio only when a positive recorded TOV total exists.
        by=m.groupby("__season_key",dropna=True)[["__ast","__tov"]].sum(min_count=1)
        by=by.loc[pd.to_numeric(by["__tov"],errors="coerce").gt(0)]
        if by.empty:
            return None
        total_ast=pd.to_numeric(by["__ast"],errors="coerce").sum(min_count=1)
        total_tov=pd.to_numeric(by["__tov"],errors="coerce").sum(min_count=1)
        if pd.isna(total_ast) or pd.isna(total_tov) or float(total_tov)<=0:
            return None
        return float(total_ast)/float(total_tov)
    except Exception:
        return None

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

def _existing_season_column(df):
    """Return the first season/year column that actually exists in df."""
    if df is None or df.empty:
        return None
    for name in ["SeasonEndYear","Season_End_Year","SeasonEnd","season_end_year","Season","season"]:
        if name in df.columns:
            return name
    return None

def _playoff_era(year):
    try: y=int(year)
    except Exception: return "UNRESOLVED"
    bands=[(k,a,b) for k,a,b,_label in ERA_DEFINITIONS]
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

    return {
        "found":True,
        "view":requested_view,
        "is_career":is_career,
        "player":{"player_id":pid,"player_name":pname,"headshot_url":headshot},
        "seasons":seasons,
        "profile":profile,
        "playoff_statistics":stat_values,
        "percentiles":percentiles,
        "playoff_available":True,
        "playoff_source":str(CACHE.get("__final_playoff_46_source_path__",PATHS["playoff_46"])),
        "season_type":"Playoffs",
        "available_contexts":context_avail,
        "statistic_registry":PLAYOFF_STATS,
        "career_note":(
            "Career playoff values come from the finalized playoff career 46-stat layer. "
            "Career percentiles require G >= 50 and MP >= 1,500. Single-season playoff percentiles require G >= 4 and MP >= 75."
            if is_career else None
        ),
    }



def _locked_sdi_v4_spec():
    """Single authoritative regular-season SDI v4 formula for Player Profiles.

    This intentionally does not read the older external SDI JSON because that
    file contains an obsolete equal-weight/60-40 efficiency formula.
    """
    return {
        "scoring_volume": {
            "Primary Scoring Output": {"weight": 0.45, "statistics": {"PTS_per75": 1.0}},
            "Scoring Composition": {"weight": 0.55, "statistics": {"FGA_per75": 35/55, "FTA_per75": 20/55}},
        },
        "scoring_efficiency": {
            "Overall Efficiency": {"weight": 0.65, "statistics": {"rTS": 1.0}},
            "Component Efficiency": {"weight": 0.35, "statistics": {"2P_pct": 0.50, "3P_pct": 0.40, "FT_pct": 0.10}},
        },
        "creation_playmaking": {
            "Creation Output": {"weight": 0.55, "statistics": {"AST_per75": 0.80, "AST_pct": 0.20}},
            "Ball Security / Creation Cost": {"weight": 0.45, "statistics": {"AST_TOV": 1.0}},
        },
        "rebounding": {
            "Rebounding Production": {"weight": 0.75, "statistics": {"ORB_per75": 0.45, "DRB_per75": 0.35, "TRB_per75": 0.20}},
            "Rebounding Rate": {"weight": 0.25, "statistics": {"OREB_pct": 0.45, "DREB_pct": 0.35, "TRB_pct": 0.20}},
        },
        "defense": {
            "Defensive Activity": {"weight": 0.20, "statistics": {"BLK_per75": 0.65, "STL_per75": 0.35}},
            "Defensive Activity Rate": {"weight": 0.30, "statistics": {"BLK_pct": 0.65, "STL_pct": 0.35}},
            "Defensive Efficiency": {"weight": 0.30, "statistics": {"DRtg": 0.10, "Relative_DRtg": 0.90}},
            "Estimated Defensive Impact": {"weight": 0.15, "statistics": {"DBPM": 1.0}},
            "Defensive Cumulative Value": {"weight": 0.05, "statistics": {"DWS": 1.0}},
        },
        "impact_value": {
            "Relative Team-Level Efficiency": {"weight": 0.35, "statistics": {"Relative_ORtg": 0.90, "ORtg": 0.10}},
            "Relative Team-Level Defensive Efficiency": {"weight": 0.15, "statistics": {"Relative_DRtg": 0.90, "DRtg": 0.10}},
            "Estimated Overall Impact": {"weight": 0.20, "statistics": {"BPM": 1.0}},
            "Estimated Offensive Impact": {"weight": 0.10, "statistics": {"OBPM": 1.0}},
            "Composite Box-Score Impact": {"weight": 0.05, "statistics": {"PER": 1.0}},
            "Cumulative Value": {"weight": 0.10, "statistics": {"VORP": 0.34, "DWS": 0.33, "OWS": 0.33}},
            "Win Estimate": {"weight": 0.05, "statistics": {"WS_per48": 1.0}},
        },
        "top_level_category_weights": dict(SDI_V4_TOP_LEVEL_WEIGHTS),
        "top_level_category_total_weight": 1.0,
    }


def _load_sdi_v4_spec():
    """Load the single authoritative SDI v4 formula used by Player Profiles."""
    key="__sdi_v4_spec_authoritative__"
    if key not in CACHE:
        CACHE[key]=_locked_sdi_v4_spec()
    return CACHE[key]


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
    key="__regular_sdi_v4_new_formula_player_seasons__"
    if key in CACHE:
        return CACHE[key]
    cache_path=ROOT/"local_api"/"cache"/"regular_sdi_v4_new_formula_player_seasons.csv"
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
            # Start with the canonical/public ID, but do not assume that ID
            # is the identifier used by the regular-season master. Some profile
            # identities have a complete name-matched season history under a
            # source ID while the public ID exists only in the website registry.
            # For the Profile 5-Year Peak path, the player's canonical name is
            # the safe bridge because the normal Player Profile has already
            # resolved that identity.
            if pidcol and requested_pid is not None:
                match=work.loc[work[pidcol].astype(str).str.strip().eq(str(requested_pid).strip())].copy()
            else:
                match=pd.DataFrame()
            if requested_name:
                wanted=str(requested_name).replace("*","").strip().casefold()
                name_match=work.loc[work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
                # If the ID match is absent or cannot supply a complete peak
                # candidate set, use the authoritative same-name season rows.
                # This is an identity-resolution fallback only; aggregation and
                # qualification remain unchanged.
                if match.empty or len(match) < 5:
                    match=name_match
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

    # LAST-RESORT PROFILE-SOURCE FALLBACK
    # Some installations have a complete canonical player-season profile table
    # while the master season table is missing/aliased for a particular player.
    # The Profile source is already used by the normal Player Profile route, so
    # use that same source here rather than returning found=false. This is still
    # a single-player lookup; it does not rebuild the league peak population and
    # does not alter any qualification or aggregation rules.
    try:
        profiles=load("profiles",["player_season_profiles","season_profiles"])
        ppcol=col(profiles,["Player","Player_Name","Display_Name","player_name","Name"])
        ppidcol=col(profiles,["Player_ID","PlayerId","PlayerID","player_id"])
        pscol=col(profiles,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        pgcol=col(profiles,["G","Games","games"])
        pmpcol=col(profiles,["MP","Minutes","minutes"])
        pstcol=col(profiles,["Season_Type","SeasonType","season_type","Phase"])
        if ppcol and pscol and pgcol and pmpcol and not profiles.empty:
            work=profiles.copy()
            if pstcol:
                work=work.loc[~work[pstcol].astype(str).str.strip().str.casefold().isin({"playoffs","playoff","postseason"})].copy()
            if ppidcol and requested_pid is not None:
                pmatch=work.loc[work[ppidcol].astype(str).str.strip().eq(str(requested_pid).strip())].copy()
            else:
                pmatch=pd.DataFrame()
            if requested_name:
                wanted=str(requested_name).replace("*","").strip().casefold()
                nmatch=work.loc[work[ppcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold().eq(wanted)].copy()
                if pmatch.empty or len(pmatch)<5:
                    pmatch=nmatch
            if not pmatch.empty:
                pmatch["__season_year"]=pmatch[pscol].map(_season_end_year)
                pmatch["__G"]=pd.to_numeric(pmatch[pgcol],errors="coerce")
                pmatch["__MP"]=pd.to_numeric(pmatch[pmpcol],errors="coerce")
                pmatch=pmatch.dropna(subset=["__season_year"]).copy()
                pmatch["__season_year"]=pmatch["__season_year"].astype(int)
                pmatch=pmatch.sort_values(["__season_year","__MP"],ascending=[True,False]).drop_duplicates(["__season_year"],keep="first")
                schedule=pmatch.groupby("__season_year")["__G"].max().dropna().to_dict()
                qualified=[]
                for _,rr in pmatch.iterrows():
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
                    sdi_map=_new_sdi_v4_for_player(pmatch,requested_pid=requested_pid,requested_name=requested_name)
                    pmatch["__sdi"]=pmatch["__season_year"].map(sdi_map)
                    best=None
                    for cand in candidates:
                        scores=pd.to_numeric(cand["__sdi"],errors="coerce").dropna().tolist()
                        score=float(np.mean(scores)) if len(scores)==5 else 0.0
                        if best is None or score>best[0]: best=(score,cand.copy())
                    if best:
                        cand=best[1]
                        stats=[str(x) for x in REGULAR_STATS if str(x) in cand.columns]
                        row={"Player_ID":str(requested_pid or ""),"Player":str(requested_name or cand[ppcol].iloc[0]),"Season":"5-Year Peak",
                             "Peak_Start_Year":int(cand["__season_year"].min()),"Peak_End_Year":int(cand["__season_year"].max()),
                             "Peak_Seasons":[_season_label_any(y) for y in cand["__season_year"].tolist()],"Peak_Era":_era_key(int(cand["__season_year"].min())),"Peak_SDI":best[0]}
                        for stat in stats:
                            row[stat]=clean(_era_average_statistic(cand,stat,ERA_AVERAGE_PER75_REGULAR,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS))
                        result={"found":True,"available":True,"player":{"player_id":requested_pid,"player_name":row["Player"]},"profile":row,
                                "statistic_values":{k:row.get(k) for k in stats},"percentiles":[{"Statistic":stat,"Value":row.get(stat),"Peak_Value":row.get(stat),"Peak_Percentile":None} for stat in stats],
                                "seasons":["5-Year Peak"],"season":"5-Year Peak","season_type":"Regular Season","is_five_year_peak":True,
                                "peak":{"start":row["Peak_Start_Year"],"end":row["Peak_End_Year"],"seasons":row["Peak_Seasons"],"era":row["Peak_Era"],"sdi":best[0]}}
                        CACHE[request_key]=result
                        return result
    except Exception:
        pass

    # Legacy all-player peak reconstruction remains intentionally disabled.
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
    """Compute the season-level four-category playoff SDI used for peak selection."""
    long=_playoff_long_percentiles(source,career=False)
    if long.empty:
        return pd.DataFrame()
    statc=col(long,["Statistic","statistic","Stat"])
    pidc=col(long,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(long,["Player","Player_Name","Display_Name","player_name","Name"])
    seac=col(long,["Season","season","Season_ID"])
    pctc="Historical_Percentile" if "Historical_Percentile" in long.columns else None
    if not statc or not namec or not seac or not pctc: return pd.DataFrame()

    # Use the exact active playoff aggregation spec so peak selection and
    # season/profile SDI cannot silently diverge.
    spec=_playoff_sdi_aggregation_spec_df()
    scat=choose_col(spec,["Category"]); sgrp=choose_col(spec,["Group_ID","Group","Group_Id"])
    sstat=choose_col(spec,["Statistic","Stat"]); ssw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    sgw=choose_col(spec,["Group_Weight"])
    if not all([scat,sgrp,sstat,ssw,sgw]): return pd.DataFrame()

    w=spec.copy()
    w["_stat_key"]=w[sstat].astype(str).str.strip()
    w["_sw"]=pd.to_numeric(w[ssw],errors="coerce"); w["_gw"]=pd.to_numeric(w[sgw],errors="coerce")
    w=w.dropna(subset=["_sw","_gw"])
    long=long.copy()
    long["_stat_key"]=long[statc].astype(str).str.strip()
    long["_pct_num"]=pd.to_numeric(long[pctc],errors="coerce")
    base=[c for c in [pidc,namec,seac] if c]
    pieces=[]
    for (category,group),g in w.groupby([scat,sgrp],sort=False):
        m=long.merge(g[["_stat_key","_sw"]],on="_stat_key",how="inner").dropna(subset=["_pct_num"])
        # A 0%-weighted statistic is intentionally excluded from the weighted
        # average. It contributes nothing to the group score and, if it is the
        # only available statistic, must not produce a zero-weight crash.
        m=m.loc[m["_sw"]>0].copy()
        if m.empty: continue
        gs=(m.groupby(base,dropna=False)
              .apply(lambda z: np.average(z["_pct_num"],weights=z["_sw"]),include_groups=False)
              .reset_index(name="_group_score"))
        gs["_gw"]=float(g["_gw"].iloc[0]); gs["_category"]=str(category); pieces.append(gs)
    if not pieces:return pd.DataFrame()
    groups=pd.concat(pieces,ignore_index=True)
    groups["_top_weight"]=groups["_category"].map(PLAYOFF_SDI_TOP_LEVEL_WEIGHTS)
    groups=groups.dropna(subset=["_top_weight"])
    groups["_w"]=groups["_group_score"]*groups["_gw"]
    cat=(groups.groupby(base+ ["_category"],dropna=False)
         .agg(_weighted=("_w","sum"),_gw=("_gw","sum"))
         .reset_index())
    cat["_category_score"]=cat["_weighted"]/cat["_gw"].replace(0,np.nan)
    cat["_top_weight"]=cat["_category"].map(PLAYOFF_SDI_TOP_LEVEL_WEIGHTS)
    cat=cat.dropna(subset=["_category_score","_top_weight"])
    cat["_weighted_category"]=cat["_category_score"]*cat["_top_weight"]
    out=(cat.groupby(base,dropna=False)
         .agg(_weighted=("_weighted_category","sum"),_top_weight=("_top_weight","sum"))
         .reset_index())
    out["SDI"]=out["_weighted"]/out["_top_weight"].replace(0,np.nan)
    return out


PLAYOFF_PEAK_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "playoff_peak_v3_four_category.json"

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
    """Load/build the authoritative playoff SDI using the locked four-category formula."""
    key="__authoritative_playoff_sdi_v4_new_formula__"
    if key in CACHE:
        return CACHE[key]
    d=_build_playoff_sdi_v4_index()
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
        "player":{"player_id":hit.get("player_id"),"player_name":hit.get("player_name"),
                  "headshot_url":_headshot_url_for(hit.get("player_id"),hit.get("player_name"))},
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
    # PLAYER PROFILE ONLY: keep the canonical profile artifact on the exact
    # version used by the last known-good Player Profile build. The Big Board
    # has its own v2 peak bundle and is intentionally not changed here.
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

        # The precomputed league cache is the preferred fast path, but it may
        # legitimately be missing a player when the cache was built from an
        # older identity universe. Fall back to the existing single-player
        # canonical peak resolver rather than returning found=false. That
        # resolver evaluates only this player's qualifying windows and does
        # not rebuild the league-wide peak population. This preserves the
        # locked Player Profile peak methodology while making the regular
        # season Peak button robust to cache identity/version gaps.
        fallback=_canonical_five_year_peak_profile(pid,pname)
        if fallback and fallback.get("found"):
            return fallback

        # Some Player Profile links use a canonical public ID while the
        # authoritative regular-season master stores the player's season rows
        # under a source/data ID. Resolve that exact profile identity before
        # giving up. This is a profile-only identity bridge; it does not change
        # Big Board data, qualification rules, or peak calculations.
        data_pid=pid
        try:
            _public_pid,_data_pid=_profile_data_identity(pid,pname)
            if _data_pid:
                data_pid=_data_pid
        except Exception:
            pass
        if str(data_pid or "") != str(pid or ""):
            fallback=_canonical_five_year_peak_profile(data_pid,pname)
            if fallback and fallback.get("found"):
                # Keep the public Player Profile identity even when the peak
                # was resolved from the underlying source/data ID.
                if isinstance(fallback.get("player"),dict):
                    fallback["player"]["player_id"]=pid
                if isinstance(fallback.get("profile"),dict):
                    fallback["profile"]["Player_ID"]=pid
                return fallback

        return {"found":False,"available":False,
                "error":"No qualifying regular 5-Year Peak record for this player."}

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
            career_ast_tov=_career_recorded_ast_tov(player_id=data_pid, player_name=pname)
            if career_ast_tov is not None:
                career["AST_TOV"]=float(career_ast_tov)
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

    # Expose the same authoritative SDI axes directly on the profile response.
    # For a regular individual season, the displayed six values are NOT generic
    # weighted averages of the component statistic percentiles. They are the
    # season-relative percentiles of the locked SDI category composites.
    category_axes = []
    try:
        if is_career and not is_playoff:
            category_axes=_rebuild_career_category_axes_from_current_formula(pid,pname)
        elif (not is_playoff and not is_career and str(chosen).casefold() not in {"5-year peak","5 year peak","five-year peak","five_year_peak"}):
            _canonical_axes, _canonical_overall = _canonical_regular_season_sdi_axes(
                pid=pid, pname=pname, season=chosen
            )
            if _canonical_axes:
                _pct_map = _regular_season_category_percentiles(chosen, _canonical_axes)
                category_axes=[]
                for _ax in _canonical_axes:
                    _label=str(_ax.get("axis") or _ax.get("label") or "")
                    _pct=_pct_map.get(_label)
                    _copy=dict(_ax)
                    _copy["value"]=float(_pct) if _pct is not None else None
                    _copy["percentile"]=float(_pct) if _pct is not None else None
                    category_axes.append(_copy)
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

    axes, overall_sdi, overall_pct = _playoff_sdi_category_axes_and_overall(
        pm, pct_col, context=context, season=season, pid=pid, pname=pname
    )

    requested=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
    stat_axes=[{"axis":s,"value":vals.get(s)} for s in requested]
    out={"found":True,"player":{"player_id":pid,"player_name":pname},
         "season":season,"context":context,
         "available_contexts":{"Season":context=="Season","Era":context=="Era",
                               "Historical":context=="Historical","Career":context=="Career"},
         "category_axes":axes,"stat_axes":stat_axes}
    if overall_sdi is not None:
        out["sdi"]=float(overall_sdi)
        out["raw_sdi"]=float(overall_sdi)
    if overall_pct is not None:
        out["sdi_percentile"]=float(overall_pct)
    return out

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
    # Initialize this before the conditional: an empty/malformed percentile
    # payload must produce a valid empty spider, not an UnboundLocalError/500.
    category_axes=[]
    pm_peak=pd.DataFrame(rows)
    if not pm_peak.empty:
        pc=choose_col(pm_peak,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
        if pc:
            pm_peak["_stat_key"]=pm_peak[pc].astype(str).str.strip()
        category_axes=_availability_aware_category_axes(pm_peak,"Peak_Percentile",playoff=True)
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

_PLAYOFF_SEASON_BUNDLE_CACHE={}
_PLAYOFF_SEASON_SDI_CACHE=None
_PLAYOFF_SEASON_SDI_CACHE_LOCK=threading.Lock()

def _playoff_category_scores_from_percentiles(pm, pct_col):
    """Compute the locked playoff category scores from one player-season frame.

    This is the same category aggregation used by the canonical playoff spider;
    it is factored only so the already-loaded percentile layer can be indexed
    once for individual-season lookups. No source values or weights are changed.
    """
    spec=_playoff_sdi_aggregation_spec()
    if pm is None or pm.empty or not pct_col: return {}
    stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not stat_col or pct_col not in pm.columns: return {}
    x=pm.copy(); x["__stat"]=x[stat_col].astype(str).str.strip(); x["__pct"]=pd.to_numeric(x[pct_col],errors="coerce")
    vals=(x.dropna(subset=["__pct"]).drop_duplicates("__stat").set_index("__stat")["__pct"].to_dict())
    scores={}
    for category,groups in spec.items():
        group_scores=[]
        for _group,gspec in groups.items():
            vals_w=[(float(vals[stat]),float(weight)) for stat,weight in (gspec.get("statistics",{}) or {}).items() if stat in vals and pd.notna(vals[stat])]
            if vals_w:
                den=sum(w for _,w in vals_w)
                if den>0: group_scores.append((sum(v*w for v,w in vals_w)/den,float(gspec.get("weight",0))))
        if group_scores:
            den=sum(w for _,w in group_scores)
            if den>0: scores[category]=sum(v*w for v,w in group_scores)/den
    return scores

def _warm_playoff_season_sdi_cache():
    """Build a response-ready playoff individual-season SDI lookup.

    This is a read-only acceleration layer over the canonical playoff
    percentile table.  It deliberately uses the same availability-aware
    category aggregation as the live playoff spider, then ranks those category
    scores within each exact playoff season.  No source statistics, percentile
    values, or SDI weights are changed.
    """
    global _PLAYOFF_SEASON_SDI_CACHE
    if _PLAYOFF_SEASON_SDI_CACHE is not None:
        return _PLAYOFF_SEASON_SDI_CACHE
    with _PLAYOFF_SEASON_SDI_CACHE_LOCK:
        if _PLAYOFF_SEASON_SDI_CACHE is not None:
            return _PLAYOFF_SEASON_SDI_CACHE

        out_id={}; out_name={}
        try:
            full=load_playoff_percentile_long(career=False)
            if full is None or full.empty:
                _PLAYOFF_SEASON_SDI_CACHE={"id":out_id,"name":out_name}
                return _PLAYOFF_SEASON_SDI_CACHE

            stat_col=choose_col(full,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
            pid_col=col(full,["Player_ID","PlayerId","PlayerID","player_id"])
            name_col=col(full,["Player","Player_Name","Display_Name","player_name","Name"])
            season_col=col(full,["Season","season","Season_ID"])
            pct_col=percentile_column(full,"Season")
            if not stat_col or not season_col or not pct_col or (not pid_col and not name_col):
                _PLAYOFF_SEASON_SDI_CACHE={"id":out_id,"name":out_name}
                return _PLAYOFF_SEASON_SDI_CACHE

            work=full.copy()
            work["__season_key"]=work[season_col].map(_season_label_any)
            work["__pct"]=pd.to_numeric(work[pct_col],errors="coerce")
            work=work.loc[work["__season_key"].notna() & work["__season_key"].astype(str).str.len().gt(0)].copy()
            if pid_col:
                work["__id"]=work[pid_col].astype(str).str.strip()
            else:
                work["__id"]=work[name_col].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()

            # Build raw category scores for every player-season using the exact
            # same availability-aware category implementation used by the live
            # playoff spider.  This is intentionally not the legacy playoff
            # season SDI CSV.
            score_rows=[]
            for (ident,season_key),g in work.groupby(["__id","__season_key"],sort=False):
                # Build the playoff raw category composites directly from the
                # authoritative locked playoff specification.  Do not use the
                # generic availability adapter here: that adapter intentionally
                # reports coverage-oriented values and can omit a category when
                # one subgroup is absent.  Player Profile playoff SDI needs the
                # same category composite methodology as the regular-season
                # profile, with only Defense/Impact removed.
                raw_scores=_playoff_category_scores_from_percentiles(g,pct_col)
                label_map={
                    "scoring_volume":"Scoring Volume",
                    "scoring_efficiency":"Scoring Efficiency",
                    "creation_playmaking":"Creation / Playmaking",
                    "rebounding":"Rebounding",
                }
                scores={label_map.get(str(cat),str(cat)):float(val)
                        for cat,val in raw_scores.items() if pd.notna(val)}
                if scores:
                    score_rows.append((str(ident),str(season_key),scores))

            populations={}
            for _ident,sy,scores in score_rows:
                for cat,v in scores.items():
                    populations.setdefault((sy,cat),[]).append(float(v))

            for ident,sy,scores in score_rows:
                axes=[]
                for cat,score in scores.items():
                    pct=_percentile_rank_0_100(score,populations.get((sy,cat),[]))
                    axes.append({
                        "axis":cat,
                        "label":cat,
                        "value":float(pct) if pct is not None else None,
                        "score":float(score),
                        "raw_score":float(score),
                        "percentile":float(pct) if pct is not None else None,
                    })
                out_id[(ident,sy)]=axes

            if name_col:
                for (ident,sy),g in work.groupby(["__id","__season_key"],sort=False):
                    nm=str(g[name_col].iloc[0] or "").replace("*","").strip().casefold()
                    axes=out_id.get((str(ident),str(sy)))
                    if nm and axes:
                        out_name[(nm,str(sy))]=axes

        except Exception as exc:
            # Never silently turn a warm-up implementation error into a false
            # "0 rows" cache.  Preserve a usable empty cache, but expose the
            # exact reason in the API console so a bad source/schema can be
            # diagnosed without touching the underlying data.
            print("Playoff individual-season SDI cache build failed:", repr(exc))
            out_id={}; out_name={}

        _PLAYOFF_SEASON_SDI_CACHE={"id":out_id,"name":out_name}
        return _PLAYOFF_SEASON_SDI_CACHE

def _playoff_season_sdi_axes(pid,pname,season):
    cache=_warm_playoff_season_sdi_cache() or {}
    sy=str(_season_label_any(season) or season or "").strip()
    pidkey=str(pid or "").strip()
    axes=cache.get("id",{}).get((pidkey,sy)) if pidkey else None
    if axes is None:
        nk=str(pname or "").replace("*","").strip().casefold()
        axes=cache.get("name",{}).get((nk,sy)) if nk else None
    if axes is None and pidkey:
        # Some canonical playoff percentile files retain a legacy source ID.
        # The exact display name is the safe identity fallback for these rows.
        try:
            _pid,_pname=resolve_player_identity(pidkey)
            nk2=str(_pname or "").replace("*","").strip().casefold()
            axes=cache.get("name",{}).get((nk2,sy)) if nk2 else None
        except Exception:
            pass
    return axes


def api_playoff_season_bundles(requested):
    """Return individual playoff seasons directly from the canonical playoff master.

    This endpoint is deliberately independent of the regular public SQLite
    season-bundle layer and of the playoff profile wrapper. Each returned row
    is constructed from the exact validated playoff player-season record used
    by the canonical playoff data routes. This removes any opportunity for a
    regular-season bundle or profile fallback to leak into the playoff table.
    """
    pid,pname=resolve_player_identity(requested)
    bundle_key=(str(pid or "").strip(),str(pname or "").replace("*","").strip().casefold())
    cached_bundle=_PLAYOFF_SEASON_BUNDLE_CACHE.get(bundle_key)
    if cached_bundle is not None:
        return cached_bundle
    source=load_playoff_46_season()
    if source is None or source.empty:
        return {"found":False,"player":{"player_id":pid,"player_name":pname},"seasons":[],"rows":[],"career":None,"season_type":"Playoffs"}

    player_rows=_playoff_player_match(source,pid,pname).copy()
    scol=col(player_rows,["Season","season","Season_ID"])
    if not scol or player_rows.empty:
        return {"found":True,"player":{"player_id":pid,"player_name":pname},"seasons":[],"rows":[],"career":None,"season_type":"Playoffs"}

    # Keep the source's canonical YYYY-YY selector while preserving source
    # row order by season end year.
    player_rows["__label"]=player_rows[scol].map(_season_label_any)
    player_rows["__year"]=player_rows[scol].map(_season_end_year)
    player_rows=player_rows.sort_values(["__year","__label"],na_position="last")

    # Load the canonical playoff percentile layer once and isolate this player's
    # rows once. The prior implementation re-matched the full percentile table
    # for every season in the player's career, which multiplied a large scan by
    # the number of playoff seasons and produced the 16+ second transition.
    playoff_pct=load_playoff_percentile_long(career=False)
    player_pct_by_season={}
    if playoff_pct is not None and not playoff_pct.empty:
        ppid=col(playoff_pct,["Player_ID","PlayerId","PlayerID","player_id"])
        pname_col=col(playoff_pct,["Player","Player_Name","Display_Name","player_name","Name"])
        pscol=col(playoff_pct,["Season","season","Season_ID"])
        psub=_playoff_player_match(playoff_pct,pid,pname)
        if not psub.empty and pscol:
            psub=psub.copy(); psub["__label"]=psub[pscol].map(_season_label_any)
            for _,pr in psub.iterrows():
                lab=str(pr.get("__label") or "").strip()
                if lab:
                    player_pct_by_season.setdefault(lab,[]).append({k:clean(v) for k,v in pr.to_dict().items() if not str(k).startswith("__")})

    rows=[]; seasons=[]
    for _,raw in player_rows.iterrows():
        label=str(raw.get("__label") or "").strip()
        if not label or label in seasons:
            continue
        seasons.append(label)
        vals={}
        for stat in PLAYOFF_STATS:
            sc=_playoff_source_column(player_rows,stat)
            vals[stat]=clean(raw.get(sc)) if sc else None
        # The profile table also needs games/minutes and the canonical identity.
        for k in ("G","GS","MP","Player","Player_ID","Season","SeasonEndYear"):
            if k in raw.index:
                vals[k]=clean(raw.get(k))
        profile=dict(vals)
        profile["Season"]=label
        profile["Season_Type"]="Playoffs"
        # FIX75: attach the canonical playoff percentile rows for this exact
        # player-season. The direct FIX74 source-routing fix intentionally built
        # the bundle from the validated playoff master, but left `percentiles`
        # empty. Reuse the same canonical playoff percentile layer used by the
        # playoff spider so the profile table gets Season/Era/Historical
        # percentiles without changing any underlying statistic values.
        percentile_rows=list(player_pct_by_season.get(label,[]))
        # Attach the exact canonical individual-season playoff SDI axes to the
        # already-built bundle so the profile can render them without another
        # expensive spider request. This is a response cache only.
        source_pid=clean(raw.get("Player_ID")) if "Player_ID" in raw.index else None
        source_name=clean(raw.get("Player")) if "Player" in raw.index else None
        sdi_axes=_playoff_season_sdi_axes(source_pid or pid, source_name or pname, label)
        if not sdi_axes and (source_pid != pid or source_name != pname):
            sdi_axes=_playoff_season_sdi_axes(pid,pname,label)

        bundle={
            "found":True,
            "view":label,
            "is_career":False,
            "player":{"player_id":pid,"player_name":pname or clean(raw.get("Player")),"headshot_url":""},
            "seasons":[label],
            "individual_seasons":[label],
            "profile":profile,
            "statistic_values":vals,
            "statistic_values_normalized":vals,
            "percentiles":percentile_rows,
            "playoff_available":True,
            "playoff_source":"validated_playoff_master",
            "playoff_statistics":vals,
            "season_type":"Playoffs",
            "sdi_category_axes":sdi_axes or []
        }
        rows.append({"season":label,"bundle":bundle})

    player={"player_id":pid,"player_name":pname}
    if rows:
        player.update(rows[0]["bundle"].get("player") or {})
    result={"found":True,"player":player,"seasons":seasons,"rows":rows,
            "career":None,"season_type":"Playoffs","playoff_available":True,
            "source":"validated_playoff_master_direct"}
    _PLAYOFF_SEASON_BUNDLE_CACHE[bundle_key]=result
    return result

def api_playoff_spider(requested,season=None,context="Historical",stats=None):
    pid,pname=resolve_player_identity(requested)
    if str(season).strip().casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        return _playoff_peak_spider_from_profile(_canonical_playoff_five_year_peak_profile(pid,pname), stats)
    if pid is None and not pname: return {"found":False}

    context="Career" if str(season).casefold()=="career" else (
        context if context in {"Season","Era","Historical"} else "Historical"
    )
    # Individual playoff seasons can be served entirely from the response-ready
    # cache built from the same canonical percentile layer. Career and Peak keep
    # their existing proven paths.
    if context=="Season":
        axes=_playoff_season_sdi_axes(pid,pname,season)
        if axes is not None:
            return {"found":True,"player":{"player_id":pid,"player_name":pname},
                    "season":season,"context":"Season",
                    "available_contexts":{"Season":True,"Era":False,"Historical":False,"Career":False},
                    "category_axes":axes,"stat_axes":[]}
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


def _playoff_sdi_aggregation_spec_df():
    """Return the locked playoff SDI aggregation spec as a tabular view.

    The authoritative spec above is intentionally represented as a nested
    dictionary because the playoff SDI category-axis code consumes it that
    way.  Several index/axis builders, however, operate on the same spec as
    a DataFrame.  This adapter changes only the representation; it does not
    change any statistic, group weight, category weight, or formula.
    """
    spec=_playoff_sdi_aggregation_spec()
    rows=[]
    for category, groups in spec.items():
        for group_name, group_spec in groups.items():
            group_weight=float(group_spec.get("weight",0))
            for stat, stat_weight in (group_spec.get("statistics",{}) or {}).items():
                rows.append({
                    "Category":category,
                    "Group_ID":group_name,
                    "Statistic":stat,
                    "Statistic_Weight":float(stat_weight),
                    "Group_Weight":group_weight,
                })
    return pd.DataFrame(rows, columns=[
        "Category","Group_ID","Statistic","Statistic_Weight","Group_Weight"
    ])


def _playoff_sdi_aggregation_spec():
    """Return the playoff projection of the authoritative regular-season formula."""
    spec=_locked_sdi_v4_spec()
    # Remove categories unavailable by the locked playoff methodology.
    spec.pop("defense",None)
    spec.pop("impact_value",None)
    spec["creation_playmaking"].pop("WOWY Offensive Impact",None)
    # These are metadata entries in the regular-season spec, not category
    # groups. Leaving them in the playoff projection makes downstream group
    # iteration treat the numeric category weights as dictionaries and causes
    # the warm-up failure: AttributeError("'float' object has no attribute 'get'").
    spec.pop("top_level_category_weights",None)
    spec.pop("top_level_category_total_weight",None)
    spec.pop("peak_rules",None)
    # The regular Creation groups already sum to 1.00 after WOWY is absent.
    return spec


def _build_playoff_sdi_v4_index():
    """Build the authoritative playoff SDI index from canonical playoff percentiles.

    This is intentionally computed from the same canonical playoff 46-stat
    layer used by Player Profile, rather than consuming the legacy
    playoff_player_season_sdi_v4.csv whose formula included unavailable WOWY.
    """
    per=load_playoff_percentile_long(False)
    if per is None or per.empty:
        return pd.DataFrame()
    stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    pid_col=col(per,["Player_ID","PlayerId","PlayerID","player_id"])
    name_col=col(per,["Player","Player_Name","Display_Name","player_name","Name"])
    season_col=col(per,["Season","season","Season_ID"])
    pct_col=percentile_column(per,"Season")
    if not stat_col or not season_col or not pct_col or not name_col:
        return pd.DataFrame()
    spec=_playoff_sdi_aggregation_spec_df()
    cat=choose_col(spec,["Category"]); grp=choose_col(spec,["Group_ID","Group","Group_Id"])
    st=choose_col(spec,["Statistic","Stat"]); sw=choose_col(spec,["Statistic_Weight","Stat_Weight","Within_Group_Weight"])
    gw=choose_col(spec,["Group_Weight"])
    if not all([cat,grp,st,sw,gw]): return pd.DataFrame()
    x=per.copy()
    x["__stat"]=x[stat_col].astype(str).str.strip()
    x["__pct"]=pd.to_numeric(x[pct_col],errors="coerce")
    x["__season"]=x[season_col].map(_season_end_year)
    x=x.dropna(subset=["__pct","__season"]).copy(); x["__season"]=x["__season"].astype(int)
    x["__pid"]=x[pid_col].astype(str).str.strip() if pid_col else x[name_col].astype(str).str.strip()
    x["__player"]=x[name_col].astype(str).str.replace(r"\*+","",regex=True).str.strip()
    w=spec[[cat,grp,st,sw,gw]].copy()
    w.columns=["__cat","__grp","__spec_stat","__sw","__gw"]
    w["__spec_stat"]=w["__spec_stat"].astype(str).str.strip()
    w["__sw"]=pd.to_numeric(w["__sw"],errors="coerce"); w["__gw"]=pd.to_numeric(w["__gw"],errors="coerce")
    w=w.dropna(subset=["__sw","__gw"])
    pieces=[]
    base=["__pid","__player","__season"]
    for (category,group),g in w.groupby(["__cat","__grp"],sort=False):
        m=x.merge(g[["__spec_stat","__sw"]],left_on="__stat",right_on="__spec_stat",how="inner")
        m=m.dropna(subset=["__pct","__sw"])
        if m.empty: continue
        # One stat should contribute once per player-season.
        m=m.sort_values(["__pid","__player","__season","__stat"]).drop_duplicates(base+["__stat"])
        gs=(m.assign(__num=m["__pct"]*m["__sw"])
              .groupby(base,sort=False)
              .agg(__num=("__num","sum"),__den=("__sw","sum"))
              .reset_index())
        gs["__group_score"]=gs["__num"]/gs["__den"].replace(0,np.nan)
        gs["__cat"]=str(category); gs["__grp"]=str(group); gs["__gw"]=float(g["__gw"].iloc[0])
        pieces.append(gs)
    if not pieces: return pd.DataFrame()
    groups=pd.concat(pieces,ignore_index=True)
    groups["__weighted_group"]=groups["__group_score"]*groups["__gw"]
    catdf=(groups.groupby(base+["__cat"],sort=False)
           .agg(__num=("__weighted_group","sum"),__den=("__gw","sum"))
           .reset_index())
    catdf["__category_score"]=catdf["__num"]/catdf["__den"].replace(0,np.nan)
    tw=PLAYOFF_SDI_TOP_LEVEL_WEIGHTS
    catdf["__top_weight"]=catdf["__cat"].map(tw).astype(float)
    catdf=catdf.dropna(subset=["__category_score","__top_weight"])
    catdf["__weighted_category"]=catdf["__category_score"]*catdf["__top_weight"]
    s=(catdf.groupby(base,sort=False)
       .agg(__num=("__weighted_category","sum"),__den=("__top_weight","sum"))
       .reset_index())
    s["SDI_v4"]=s["__num"]/s["__den"].replace(0,np.nan)
    wide=catdf.pivot_table(index=base,columns="__cat",values="__category_score",aggfunc="first").reset_index()
    for c in ["Scoring Volume","Scoring Efficiency","Creation & Playmaking","Rebounding","Defense"]:
        if c in wide.columns:
            wide=wide.rename(columns={c:"SDI_"+c.replace(" ","_").replace("&","and").replace("/","_")})
    out=s.merge(wide,on=base,how="left")
    out=out.rename(columns={"__pid":"Player_ID","__player":"Player","__season":"SeasonEndYear"})
    out["G"]=pd.to_numeric(per.groupby([per[pid_col] if pid_col else per[name_col],per[season_col]])["G"].first().reset_index(drop=True),errors="coerce") if False else np.nan
    # G/MP are recovered from the canonical source for qualification/display.
    source=load_playoff_46_season()
    if source is not None and not source.empty:
        spid=col(source,["Player_ID","PlayerId","PlayerID","player_id"]); sn=col(source,["Player","Player_Name","Display_Name","player_name","Name"]); ss=col(source,["Season","season","Season_ID"]); sg=col(source,["G","Games","games"]); sm=col(source,["MP","Minutes","minutes"])
        if sn and ss:
            z=source.copy(); z["__pid"]=z[spid].astype(str).str.strip() if spid else z[sn].astype(str).str.strip(); z["__player"]=z[sn].astype(str).str.replace(r"\*+","",regex=True).str.strip(); z["__season"]=z[ss].map(_season_end_year); z["G"]=pd.to_numeric(z[sg],errors="coerce") if sg else np.nan; z["MP"]=pd.to_numeric(z[sm],errors="coerce") if sm else np.nan
            z=z.groupby(["__pid","__player","__season"],as_index=False,sort=False).agg(G=("G","sum"),MP=("MP","sum"))
            out=out.merge(z.rename(columns={"__pid":"Player_ID","__player":"Player","__season":"SeasonEndYear"}),on=["Player_ID","Player","SeasonEndYear"],how="left")
    return out

def _playoff_sdi_category_axes_and_overall(pm, pct_col, context="Season", season=None, pid=None, pname=None):
    """Compute playoff SDI category scores and *their percentiles*.

    The visible Player Profile SDI values must be percentiles of the NEW
    playoff SDI category scores, not raw statistic percentiles. This is the
    missing link that allowed a generic percentile aggregation to show an
    efficiency value that did not correspond to the newly rebuilt SDI.
    """
    spec=_playoff_sdi_aggregation_spec()
    if pm is None or pm.empty or not pct_col:
        return [], None, None
    stat_col=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    if not stat_col:
        return [], None, None

    def category_scores(frame):
        x=frame.copy()
        x["__stat"]=x[stat_col].astype(str).str.strip()
        x["__pct"]=pd.to_numeric(x[pct_col],errors="coerce")
        vals=(x.dropna(subset=["__pct"]).drop_duplicates("__stat")
              .set_index("__stat")["__pct"].to_dict())
        scores={}
        for category,groups in spec.items():
            group_scores=[]
            for group_name,gspec in groups.items():
                vals_w=[]
                for stat,weight in (gspec.get("statistics",{}) or {}).items():
                    if stat in vals:
                        vals_w.append((float(vals[stat]),float(weight)))
                if not vals_w:
                    continue
                den=sum(w for _,w in vals_w)
                if den>0:
                    group_scores.append((sum(v*w for v,w in vals_w)/den,float(gspec.get("weight",0))))
            if group_scores:
                den=sum(w for _,w in group_scores)
                scores[category]=sum(v*w for v,w in group_scores)/den if den>0 else np.nan
        return scores

    target_scores=category_scores(pm)

    # Build the same category-score population used to percentile the target.
    # Single-season percentiles are ranked within each playoff season; Career
    # percentiles are ranked across the qualified playoff career population.
    full=load_playoff_percentile_long(context=="Career")
    if full is None or full.empty:
        return ([{"axis":k,"label":k,"value":None,"score":v,"raw_score":v,"percentile":None}
                 for k,v in target_scores.items()],
                None,None)
    fstat=choose_col(full,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    fpid=col(full,["Player_ID","PlayerId","PlayerID","player_id"])
    fname=col(full,["Player","Player_Name","Display_Name","player_name","Name"])
    fseason=col(full,["Season","season","Season_ID"])
    if not fstat:
        return [],None,None
    # Build score for every identity/season in the percentile population.
    full=full.copy(); full["__stat"]=full[fstat].astype(str).str.strip()
    full["__pct"]=pd.to_numeric(full[pct_col],errors="coerce") if pct_col in full.columns else np.nan
    if context=="Career":
        idcols=[c for c in [fpid,fname] if c]
        if not idcols:
            return [],None,None
        full["__id"]=(full[fpid].astype(str).str.strip() if fpid else full[fname].astype(str).str.strip().str.casefold())
        groups=[]
        for ident,g in full.groupby("__id",sort=False):
            groups.append((ident,category_scores(g)))
    else:
        full["__season_key"]=full[fseason].map(_season_label_any) if fseason else ""
        full["__id"]=(full[fpid].astype(str).str.strip() if fpid else full[fname].astype(str).str.strip().str.casefold())
        groups=[]
        for (ident,sy),g in full.groupby(["__id","__season_key"],sort=False):
            groups.append(((ident,sy),category_scores(g)))

    populations={k:[] for k in target_scores}
    for _,scores in groups:
        for k,v in scores.items():
            if k in populations and np.isfinite(v): populations[k].append(float(v))

    axes=[]
    for category,score in target_scores.items():
        arr=populations.get(category,[])
        pct=_percentile_rank_0_100(score,arr)
        axes.append({"axis":category,"label":category,"value":float(pct) if pct is not None else None,
                     "score":float(score),"raw_score":float(score),
                     "percentile":float(pct) if pct is not None else None})

    # Overall playoff SDI is the weighted mean of the four retained category
    # scores. Its displayed percentile is also ranked against the same four-
    # category SDI population, rather than being confused with a category score.
    tw=PLAYOFF_SDI_TOP_LEVEL_WEIGHTS
    usable={k:v for k,v in target_scores.items() if k in tw and np.isfinite(v)}
    overall=(sum(v*tw[k] for k,v in usable.items())/sum(tw[k] for k in usable)) if usable else None
    overall_population=[]
    for _,scores in groups:
        u={k:v for k,v in scores.items() if k in tw and np.isfinite(v)}
        if u:
            overall_population.append(sum(v*tw[k] for k,v in u.items())/sum(tw[k] for k in u))
    overall_pct=_percentile_rank_0_100(overall,overall_population) if overall is not None else None
    return axes,overall,overall_pct


def _availability_aware_category_axes(pm, pct_col, playoff=False):
    """Return six category performance axes plus evidence coverage.

    The performance axis is computed from available evidence using the
    intended internal weights. Coverage is separately reported and is used by
    SDI contribution, never as a hidden 50th-percentile imputation.
    """
    if pm is None or pm.empty or not pct_col:
        return []
    if playoff:
        spec=_playoff_sdi_aggregation_spec_df()
    else:
        rows=[]
        for category, groups in _locked_sdi_v4_spec().items():
            if category in {"top_level_category_weights","top_level_category_total_weight"}: continue
            for group_name, group_spec in groups.items():
                for stat, stat_weight in (group_spec.get("statistics",{}) or {}).items():
                    rows.append({"Category":category,"Group_ID":group_name,"Statistic":stat,
                                 "Statistic_Weight":float(stat_weight),"Group_Weight":float(group_spec.get("weight",0))})
        spec=pd.DataFrame(rows,columns=["Category","Group_ID","Statistic","Statistic_Weight","Group_Weight"])
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
    # Canonicalize category labels across the locked config/spec. The config
    # uses "Creation / Playmaking" and "Impact / Value", while older runtime
    # code used ampersands. Keep the public axis names stable while accepting
    # either spelling in source files.
    _canon_category={
        "scoring volume":"Scoring Volume",
        "scoring efficiency":"Scoring Efficiency",
        "efficiency":"Scoring Efficiency",
        "creation / playmaking":"Creation & Playmaking",
        "creation & playmaking":"Creation & Playmaking",
        "rebounding":"Rebounding",
        "defense":"Defense",
        "impact / value":"Impact & Value",
        "impact & value":"Impact & Value",
    }
    _spec_category=spec[cat].astype(str).str.strip().str.casefold().map(_canon_category).fillna(spec[cat].astype(str).str.strip())
    allowed=( ["Scoring Volume","Scoring Efficiency","Creation & Playmaking",
             "Rebounding"] if playoff else
             ["Scoring Volume","Scoring Efficiency","Creation & Playmaking",
             "Rebounding","Defense","Impact & Value"] )
    w=spec.loc[_spec_category.isin(allowed)].copy()
    w["_canonical_category"]=_spec_category.loc[w.index]
    w["_stat_key"]=w[st].astype(str).str.strip()
    w["_sw"]=pd.to_numeric(w[sw],errors="coerce")
    w["_gw"]=pd.to_numeric(w[gw],errors="coerce")
    axes=[]
    for category in allowed:
        cg=w.loc[w["_canonical_category"].eq(category)]
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
            axes.append({"axis":category,"value":float(value),"percentile":float(value),
                         "coverage":float(coverage),
                         "contribution_multiplier":float(coverage)})
    return axes


def _load_canonical_regular_season_sdi_wowy():
    """Load the existing canonical raw regular-season SDI/WOWY season layer."""
    key="__canonical_regular_season_sdi_wowy__"
    if key in CACHE:
        return CACHE[key]
    candidates=[
        ROOT/"local_api"/"cache"/"regular_sdi_v4_wowy_player_seasons.csv",
        ROOT/"data"/"regular_sdi_v4_wowy_player_seasons.csv",
        ROOT/"data"/"precomputed_sdi_v4"/"regular_sdi_v4_wowy_player_seasons.csv",
        ROOT/"regular_sdi_v4_wowy_player_seasons.csv",
    ]
    path=next((p for p in candidates if p.exists()),None)
    if path is None:
        try:
            path=find_recursive_csv(ROOT, ["regular_sdi_v4_wowy_player_seasons.csv"])
        except Exception:
            path=None
    if path is None or not path.exists():
        CACHE[key]=pd.DataFrame()
        return CACHE[key]
    try:
        d=pd.read_csv(path,low_memory=False)
    except Exception:
        d=pd.DataFrame()
    CACHE[key]=d
    return d


def _percentile_rank_0_100(value, population):
    """Return a 0-100 same-season percentile with the maximum fixed at 100."""
    try:
        v=float(value)
    except Exception:
        return None
    arr=np.asarray([x for x in population if x is not None and np.isfinite(x)],dtype=float)
    if arr.size==0 or not np.isfinite(v):
        return None
    if arr.size==1:
        return 100.0
    less=float((arr < v).sum())
    return float(100.0*less/(arr.size-1))


def _regular_profile_raw_category_scores(season):
    """Compute regular-season raw SDI category scores from canonical statistic percentiles."""
    per=load_canonical_percentiles()
    if per is None or per.empty:
        return pd.DataFrame()

    stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
    season_col=identity_cols(per).get("season") or choose_col(per,["Season","season","Season_ID"])
    pid_col=col(per,["Player_ID","PlayerId","PlayerID","player_id"])
    name_col=col(per,["Player","Player_Name","Display_Name","player_name","Name"])
    pct_col=percentile_column(per,"Season")
    if not stat_col or not season_col or not pct_col or (not pid_col and not name_col):
        return pd.DataFrame()

    w=per.copy()
    w["__season_key"]=w[season_col].map(_season_label_any)
    w["__pct"]=pd.to_numeric(w[pct_col],errors="coerce")
    w=w.loc[w["__season_key"].notna() & w["__pct"].notna()].copy()
    w["__stat"]=w[stat_col].astype(str).str.strip()
    w["__pid"]=w[pid_col].astype(str).str.strip() if pid_col else w[name_col].astype(str).str.strip()
    w["__name"]=w[name_col].astype(str).str.replace(r"\*+","",regex=True).str.strip() if name_col else ""

    # The canonical long percentile table does not contain the audited
    # historical 2P% percentile rows for pre-1979 seasons.  Hydrate those
    # rows from the project's existing authoritative historical layer.
    try:
        two_p_path=ROOT/"data"/"2p_pct_pre1979_season_percentiles.csv"
        if two_p_path.exists():
            two_p=pd.read_csv(two_p_path,low_memory=False)
            ts=choose_col(two_p,["Season","season","Season_ID"])
            tp=col(two_p,["Player_ID","PlayerId","PlayerID","player_id"])
            tn=col(two_p,["Player","Player_Name","Display_Name","player_name","Name"])
            tt=choose_col(two_p,["Statistic","statistic","Stat"])
            tx=percentile_column(two_p,"Season")
            if ts and tt and tx and (tp or tn):
                two_p["__season_key"]=two_p[ts].map(_season_label_any)
                two_p["__stat"]=two_p[tt].astype(str).str.strip()
                two_p["__pct"]=pd.to_numeric(two_p[tx],errors="coerce")
                two_p=two_p.loc[
                    two_p["__stat"].eq("2P_pct") &
                    two_p["__season_key"].notna() &
                    two_p["__season_key"].map(_season_end_year).fillna(9999).lt(1979) &
                    two_p["__pct"].notna()
                ].copy()
                if not two_p.empty:
                    if pid_col and tp:
                        two_p["__pid"]=two_p[tp].astype(str).str.strip()
                    elif tn:
                        two_p["__pid"]=two_p[tn].astype(str).str.strip()
                    else:
                        two_p["__pid"]=""
                    two_p["__name"]=two_p[tn].astype(str).str.replace(r"\*+","",regex=True).str.strip() if tn else ""
                    w=pd.concat([w[["__pid","__season_key","__stat","__pct","__name"]],
                                 two_p[["__pid","__season_key","__stat","__pct","__name"]]],
                                ignore_index=True,sort=False)
    except Exception as exc:
        print("Regular raw SDI 2P% hydration skipped:",repr(exc))

    requested=normalize_requested_season(season)
    d=w.loc[w["__season_key"].eq(str(requested))].copy()
    if d.empty:
        return pd.DataFrame()

    spec=_load_sdi_v4_spec()
    rows=[]
    for key,g in d.groupby("__pid",sort=False):
        vals=(g.drop_duplicates("__stat",keep="first")
                .set_index("__stat")["__pct"].to_dict())
        out={"__pid":key}
        for category,groups in spec.items():
            if category in {"peak_rules","top_level_category_weights","top_level_category_total_weight"} or not isinstance(groups,dict):
                continue
            group_scores=[]
            for group_spec in groups.values():
                if not isinstance(group_spec,dict):
                    continue
                usable=[(float(vals[st]),float(weight))
                        for st,weight in (group_spec.get("statistics",{}) or {}).items()
                        if st in vals and pd.notna(vals[st]) and pd.notna(weight)]
                if not usable:
                    continue
                den=sum(weight for _,weight in usable)
                if den>0:
                    group_scores.append((sum(v*weight for v,weight in usable)/den,
                                         float(group_spec.get("weight",0))))
            if group_scores:
                den=sum(weight for _,weight in group_scores)
                out[category]=sum(v*weight for v,weight in group_scores)/den if den>0 else np.nan
            else:
                out[category]=np.nan
        rows.append(out)
    return pd.DataFrame(rows)

def _regular_season_category_percentiles(season, target_axes):
    """Rank current-formula raw category SDI scores against that season's population."""
    if not target_axes:
        return {}
    scores=_regular_profile_raw_category_scores(season)
    if scores.empty:
        return {}
    mapping=[
        ("Scoring Volume","scoring_volume"),
        ("Scoring Efficiency","scoring_efficiency"),
        ("Creation / Playmaking","creation_playmaking"),
        ("Rebounding","rebounding"),
        ("Defense","defense"),
        ("Impact / Value","impact_value"),
    ]
    target={str(x.get("axis") or x.get("label") or ""):x for x in target_axes}
    out={}
    for label,key in mapping:
        if label not in target or key not in scores.columns: continue
        raw=target[label].get("score",target[label].get("raw_score",target[label].get("value")))
        vals=pd.to_numeric(scores[key],errors="coerce").dropna().to_numpy(dtype=float)
        out[label]=_percentile_rank_0_100(raw,vals)
    return out


def _career_raw_category_percentile_populations():
    """Build Career raw-category SDI populations from the current canonical Career formula."""
    _warm_regular_career_spider_cache()
    payloads=(_REGULAR_CAREER_SPIDER_PAYLOADS or {}).get("id",{})
    pop={}
    for payload in payloads.values():
        for ax in payload.get("category_axes",[]) or []:
            label=str(ax.get("axis") or ax.get("label") or "")
            raw=ax.get("score",ax.get("raw_score",ax.get("value")))
            try: raw=float(raw)
            except Exception: continue
            if np.isfinite(raw):
                pop.setdefault(label,[]).append(raw)
    # If an authoritative WOWY Impact / Value layer exists but the current
    # career-statistic layer could not expose it, retain that existing population
    # rather than inventing a replacement.
    if "Impact & Value" not in pop:
        _warm_career_sdi_axes()
        for axes in ((_CAREER_SDI_AXES or {}).get("id",{}) or {}).values():
            for ax in axes or []:
                label=str(ax.get("axis") or ax.get("label") or "")
                if label.casefold() != "impact & value":
                    continue
                raw=ax.get("score",ax.get("raw_score"))
                try: raw=float(raw)
                except Exception: continue
                if np.isfinite(raw): pop.setdefault("Impact & Value",[]).append(raw)
    return pop


def _canonical_regular_season_sdi_axes(pid=None, pname=None, season=None):
    """Return raw regular-season SDI category values from the authoritative formula."""
    if season is None:
        return [], None
    scores=_regular_profile_raw_category_scores(season)
    if scores.empty:
        return [], None
    key=None
    if pid is not None:
        key=str(pid).strip()
    if key is None and pname:
        key=str(pname).strip()
    if key is None:
        return [], None
    hit=scores.loc[scores["__pid"].astype(str).str.strip().eq(key)]
    if hit.empty and pname:
        # Fallback when the percentile source uses names rather than IDs.
        wanted=re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",str(pname)).casefold())
        hit=scores.loc[scores["__pid"].map(lambda x: re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",str(x)).casefold())).eq(wanted)]
    if hit.empty:
        return [], None
    r=hit.iloc[0]
    mapping=[
        ("Scoring Volume","scoring_volume"),
        ("Scoring Efficiency","scoring_efficiency"),
        ("Creation / Playmaking","creation_playmaking"),
        ("Rebounding","rebounding"),
        ("Defense","defense"),
        ("Impact / Value","impact_value"),
    ]
    axes=[]
    for label,field in mapping:
        v=pd.to_numeric(r.get(field,np.nan),errors="coerce")
        if pd.notna(v):
            axes.append({"axis":label,"label":label,"value":float(v),"score":float(v),"raw_score":float(v),"percentile":None})
    return axes, None

_REGULAR_SEASON_SPIDER_CACHE = None
_REGULAR_SEASON_SPIDER_CACHE_LOCK = threading.Lock()

_REGULAR_PEAK_CATEGORY_POPULATION_CACHE = None

def _regular_peak_category_population():
    """Build the regular 5-Year Peak category populations once, vectorized.

    This is a performance-only equivalent of the previous per-player/per-category
    DataFrame filtering loop. It uses the same existing canonical peak JSON and
    canonical SDI/WOWY season layer; no statistics or methodology are changed.
    """
    global _REGULAR_PEAK_CATEGORY_POPULATION_CACHE
    if _REGULAR_PEAK_CATEGORY_POPULATION_CACHE is not None:
        return _REGULAR_PEAK_CATEGORY_POPULATION_CACHE

    empty={label:[] for label,_ in [
        ("Scoring Volume","SDI_scoring_volume"),
        ("Scoring Efficiency","SDI_scoring_efficiency"),
        ("Creation / Playmaking","SDI_creation_playmaking"),
        ("Rebounding","SDI_rebounding"),
        ("Defense","SDI_defense"),
        ("Impact / Value","SDI_impact_value"),
    ]}

    path=None
    for candidate in (
        "regular_profile_peaks_wowy_canonical_v2.json",
        "regular_profile_peaks_v4.json",
        "regular_profile_peaks_v5.json",
        "regular_profile_peaks.json",
    ):
        try:
            path=next((x for x in ROOT.rglob(candidate) if x.is_file()),None)
        except Exception:
            path=None
        if path is not None and path.exists():
            break
    if path is None or not path.exists():
        _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
        return empty

    d=_load_canonical_regular_season_sdi_wowy()
    if d.empty:
        _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
        return empty

    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        players=payload.get("players",[]) or []
        mapping=[
            ("Scoring Volume","SDI_scoring_volume"),
            ("Scoring Efficiency","SDI_scoring_efficiency"),
            ("Creation / Playmaking","SDI_creation_playmaking"),
            ("Rebounding","SDI_rebounding"),
            ("Defense","SDI_defense"),
            ("Impact / Value","SDI_impact_value"),
        ]
        sy=col(d,["SeasonEndYear","Season_End_Year","Year"])
        pidc=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
        namec=col(d,["Player","Player_Name","Display_Name","player_name","Name"])
        if not sy or (not pidc and not namec):
            _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
            return empty

        cols=[sy]+[x for x in [pidc,namec]+[f for _,f in mapping] if x]
        work=d[cols].copy()
        work["__year"]=pd.to_numeric(work[sy],errors="coerce")
        work=work.dropna(subset=["__year"]).copy()
        work["__year"]=work["__year"].astype(int)
        if pidc: work["__pid"]=work[pidc].astype(str).str.strip()
        else: work["__pid"]=""
        if namec: work["__namekey"]=work[namec].map(_normalize_peak_lookup_name)
        else: work["__namekey"]=""

        peak_rows=[]
        for pl in players:
            seasons=pl.get("peak_seasons") or pl.get("Peak_Seasons") or []
            years=[_season_end_year(x) for x in seasons]
            years=[int(y) for y in years if y is not None]
            if len(years)<5:
                continue
            peak_rows.append({
                "player_id":str(pl.get("player_id") or pl.get("Player_ID") or "").strip(),
                "namekey":_normalize_peak_lookup_name(pl.get("player_name") or pl.get("Player") or pl.get("Name") or ""),
                "years":years,
            })

        exploded=[]
        for pl in peak_rows:
            for y in pl["years"]:
                exploded.append((pl["player_id"],pl["namekey"],y))
        if not exploded:
            _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
            return empty

        e=pd.DataFrame(exploded,columns=["__peak_pid","__peak_namekey","__year"])
        # Prefer exact Player_ID matches when the peak cache uses the same ID
        # namespace. Otherwise use the same normalized-name fallback as the
        # original category_score() implementation.
        id_match=e.merge(
            work.loc[work["__pid"].ne(""),["__pid","__year"]+[f for _,f in mapping]],
            left_on=["__peak_pid","__year"],right_on=["__pid","__year"],how="left",suffixes=("","_d")
        )
        id_has=id_match[[f for _,f in mapping]].notna().any(axis=1)
        remaining=e.loc[~id_has].copy()
        if not remaining.empty:
            name_match=remaining.merge(
                work[["__namekey","__year"]+[f for _,f in mapping]],
                left_on=["__peak_namekey","__year"],right_on=["__namekey","__year"],how="left",suffixes=("","_d")
            )
            combined=pd.concat([id_match.loc[id_has,["__peak_pid","__peak_namekey","__year"]+[f for _,f in mapping],],
                                name_match[["__peak_pid","__peak_namekey","__year"]+[f for _,f in mapping]]],ignore_index=True)
        else:
            combined=id_match.loc[id_has,["__peak_pid","__peak_namekey","__year"]+[f for _,f in mapping]]

        grouped=combined.groupby(["__peak_pid","__peak_namekey"],sort=False)[[f for _,f in mapping]].mean(numeric_only=True)
        for _,row in grouped.iterrows():
            for label,field in mapping:
                v=pd.to_numeric(row.get(field,np.nan),errors="coerce")
                if pd.notna(v): empty[label].append(float(v))
    except Exception:
        # Preserve the prior behavior's safe empty result on cache-build errors.
        _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
        return empty

    _REGULAR_PEAK_CATEGORY_POPULATION_CACHE=empty
    return empty


_REGULAR_PEAK_SDI_AXES_CACHE = {}

def _regular_peak_category_percentile_axes(peak):
    """Return percentile-only SDI axes for the exact canonical regular 5-Year Peak.

    The peak window is authoritative; this adapter only ranks the six category
    SDI composites for that already-selected window. It never substitutes the
    raw category score for the Profile-facing percentile.
    """
    if not peak or not peak.get("found") or not peak.get("available"):
        return []
    p=peak.get("player") or {}
    cache_key=(str(p.get("player_id") or "").strip(), _normalize_peak_lookup_name(p.get("player_name") or ""))
    if cache_key in _REGULAR_PEAK_SDI_AXES_CACHE:
        return _REGULAR_PEAK_SDI_AXES_CACHE[cache_key]

    path=None
    for candidate in (
        "regular_profile_peaks_wowy_canonical_v2.json",
        "regular_profile_peaks_v4.json",
        "regular_profile_peaks_v5.json",
        "regular_profile_peaks.json",
    ):
        try:
            path=next((x for x in ROOT.rglob(candidate) if x.is_file()),None)
        except Exception:
            path=None
        if path is not None and path.exists():
            break
    if path is None or not path.exists():
        return []

    d=_load_canonical_regular_season_sdi_wowy()
    if d.empty:
        return []
    sy=col(d,["SeasonEndYear","Season_End_Year","Year"])
    pidc=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(d,["Player","Player_Name","Display_Name","player_name","Name"])
    if not sy or (not pidc and not namec):
        return []
    work=d.copy()
    work["__year"]=pd.to_numeric(work[sy],errors="coerce")
    work=work.dropna(subset=["__year"]).copy(); work["__year"]=work["__year"].astype(int)
    if pidc: work["__pid"]=work[pidc].astype(str).str.strip()
    else: work["__pid"]=""
    if namec: work["__namekey"]=work[namec].map(_normalize_peak_lookup_name)
    else: work["__namekey"]=""

    mapping=[
        ("Scoring Volume","SDI_scoring_volume"),
        ("Scoring Efficiency","SDI_scoring_efficiency"),
        ("Creation / Playmaking","SDI_creation_playmaking"),
        ("Rebounding","SDI_rebounding"),
        ("Defense","SDI_defense"),
        ("Impact / Value","SDI_impact_value"),
    ]
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        players=payload.get("players",[]) or []
    except Exception:
        return []
    if not players:
        return []

    target_id=str((peak.get("player") or {}).get("player_id") or peak.get("profile",{}).get("Player_ID") or "").strip()
    target_name=_normalize_peak_lookup_name((peak.get("player") or {}).get("player_name") or peak.get("profile",{}).get("Player") or "")
    target_seasons=list((peak.get("peak") or {}).get("seasons") or peak.get("profile",{}).get("Peak_Seasons") or [])
    target_years=[_season_end_year(x) for x in target_seasons]
    target_years=[int(y) for y in target_years if y is not None]
    if not target_years:
        return []

    def category_score(player_id, player_name, years, field):
        sub=work.loc[work["__year"].isin(years)]
        hit=pd.DataFrame()
        if player_id:
            hit=sub.loc[sub["__pid"].eq(str(player_id).strip())]
        if hit.empty and player_name:
            hit=sub.loc[sub["__namekey"].eq(_normalize_peak_lookup_name(player_name))]
        if hit.empty or field not in hit.columns:
            return np.nan
        vals=pd.to_numeric(hit[field],errors="coerce").dropna()
        if vals.empty:
            return np.nan
        # The canonical peak contains five seasons. Use the mean of the
        # underlying season-level category composites for the selected window.
        return float(vals.mean())

    pop=_regular_peak_category_population()
    target_scores={}

    # Calculate only the requested player's raw category scores from the exact
    # canonical peak window, using the same ID-then-name resolution as before.
    target_id=str((peak.get("player") or {}).get("player_id") or peak.get("profile",{}).get("Player_ID") or "").strip()
    target_name=_normalize_peak_lookup_name((peak.get("player") or {}).get("player_name") or peak.get("profile",{}).get("Player") or "")
    target_seasons=list((peak.get("peak") or {}).get("seasons") or peak.get("profile",{}).get("Peak_Seasons") or [])
    target_years=[_season_end_year(x) for x in target_seasons]
    target_years=[int(y) for y in target_years if y is not None]
    if not target_years:
        return []

    d=_load_canonical_regular_season_sdi_wowy()
    sy=col(d,["SeasonEndYear","Season_End_Year","Year"])
    pidc=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
    namec=col(d,["Player","Player_Name","Display_Name","player_name","Name"])
    if not sy or (not pidc and not namec):
        return []
    work=d.copy()
    work["__year"]=pd.to_numeric(work[sy],errors="coerce")
    work=work.loc[work["__year"].isin(target_years)].copy()
    if pidc: work["__pid"]=work[pidc].astype(str).str.strip()
    else: work["__pid"]=""
    if namec: work["__namekey"]=work[namec].map(_normalize_peak_lookup_name)
    else: work["__namekey"]=""
    hit=work.loc[work["__pid"].eq(target_id)].copy() if target_id and pidc else pd.DataFrame()
    if hit.empty and target_name and namec:
        hit=work.loc[work["__namekey"].eq(target_name)].copy()
    for label,field in mapping:
        if field not in hit.columns:
            continue
        v=pd.to_numeric(hit[field],errors="coerce").dropna()
        if not v.empty:
            target_scores[label]=float(v.mean())

    axes=[]
    for label,_field in mapping:
        raw=target_scores.get(label,np.nan)
        arr=np.asarray(pop[label],dtype=float)
        arr=arr[np.isfinite(arr)]
        if not np.isfinite(raw) or arr.size==0:
            continue
        pct=_percentile_rank_0_100(raw,arr)
        axes.append({"axis":label,"label":label,
                     "value":float(pct) if pct is not None else None,
                     "score":float(raw),"raw_score":float(raw),
                     "percentile":float(pct) if pct is not None else None})
    _REGULAR_PEAK_SDI_AXES_CACHE[cache_key]=axes
    return axes


def _warm_regular_peak_sdi_spider_cache():
    """Precompute the six category percentile axes for every canonical regular Peak.

    This is a read-only performance cache over the already-locked peak windows and
    canonical season-level SDI/WOWY layer. It does not recalculate or replace any
    player statistics or peak selection; it only makes the existing spider payload
    available as an in-memory lookup before a user clicks 5-Year Peak.
    """
    global _REGULAR_PEAK_SDI_AXES_CACHE
    if _REGULAR_PEAK_SDI_AXES_CACHE:
        return _REGULAR_PEAK_SDI_AXES_CACHE
    try:
        pop=_regular_peak_category_population()
        if not any(pop.values()):
            return _REGULAR_PEAK_SDI_AXES_CACHE
        payload_key="__precomputed_regular_peak_profiles_v7_sdi_v4_authoritative__"
        payload=CACHE.get(payload_key)
        if payload is None:
            # Reuse the exact loader so the canonical file and its representation
            # are identical to normal profile requests.
            _load_precomputed_regular_peak_profile(requested_pid="__warm_only__")
            payload=CACHE.get(payload_key)
        players=(payload or {}).get("players",[]) or []
        if not players:
            return _REGULAR_PEAK_SDI_AXES_CACHE
        d=_load_canonical_regular_season_sdi_wowy()
        if d.empty:
            return _REGULAR_PEAK_SDI_AXES_CACHE
        sy=col(d,["SeasonEndYear","Season_End_Year","Year"])
        pidc=col(d,["Player_ID","PlayerId","PlayerID","player_id"])
        namec=col(d,["Player","Player_Name","Display_Name","player_name","Name"])
        if not sy or (not pidc and not namec):
            return _REGULAR_PEAK_SDI_AXES_CACHE
        mapping=[
            ("Scoring Volume","SDI_scoring_volume"),
            ("Scoring Efficiency","SDI_scoring_efficiency"),
            ("Creation / Playmaking","SDI_creation_playmaking"),
            ("Rebounding","SDI_rebounding"),
            ("Defense","SDI_defense"),
            ("Impact / Value","SDI_impact_value"),
        ]
        cols=[sy]+[x for x in [pidc,namec]+[f for _,f in mapping] if x]
        work=d[cols].copy()
        work["__year"]=pd.to_numeric(work[sy],errors="coerce")
        work=work.dropna(subset=["__year"]).copy(); work["__year"]=work["__year"].astype(int)
        if pidc: work["__pid"]=work[pidc].astype(str).str.strip()
        else: work["__pid"]=""
        if namec: work["__namekey"]=work[namec].map(_normalize_peak_lookup_name)
        else: work["__namekey"]=""
        # Small lookup maps make the 5-season/player expansion O(players*5),
        # rather than repeatedly filtering a large DataFrame per player.
        by_id={}
        by_name={}
        for r in work.to_dict("records"):
            vals={f:r.get(f) for _,f in mapping}
            if r.get("__pid"):
                by_id[(str(r["__pid"]),int(r["__year"]))]=vals
            if r.get("__namekey"):
                by_name[(str(r["__namekey"]),int(r["__year"]))]=vals
        for pl in players:
            pid=str(pl.get("player_id") or pl.get("Player_ID") or "").strip()
            namekey=_normalize_peak_lookup_name(pl.get("player_name") or pl.get("Player") or pl.get("Name") or "")
            years=[_season_end_year(x) for x in (pl.get("peak_seasons") or pl.get("Peak_Seasons") or [])]
            years=[int(y) for y in years if y is not None]
            if len(years)<5: continue
            scores={label:[] for label,_ in mapping}
            for y in years:
                vals=by_id.get((pid,y)) if pid else None
                if vals is None: vals=by_name.get((namekey,y)) if namekey else None
                if vals:
                    for label,field in mapping:
                        v=pd.to_numeric(pd.Series([vals.get(field)]),errors="coerce").iloc[0]
                        if pd.notna(v): scores[label].append(float(v))
            axes=[]
            for label,_field in mapping:
                if not scores[label] or not pop.get(label): continue
                raw=float(np.mean(scores[label]))
                pct=_percentile_rank_0_100(raw,pop[label])
                axes.append({"axis":label,"label":label,"value":float(pct) if pct is not None else None,
                             "score":raw,"raw_score":raw,"percentile":float(pct) if pct is not None else None})
            key=(pid,namekey)
            if axes:
                _REGULAR_PEAK_SDI_AXES_CACHE[key]=axes
        return _REGULAR_PEAK_SDI_AXES_CACHE
    except Exception:
        return _REGULAR_PEAK_SDI_AXES_CACHE

def _warm_regular_season_spider_cache():
    """Build response-ready regular-season SDI percentile payloads from the locked formula.

    IMPORTANT: the legacy ``SDI_scoring_efficiency`` columns in the canonical
    WOWY CSV are not authoritative for the Player Profile display.  Recompute
    every category from the canonical season percentile layer using the locked
    SDI v4 specification, then rank those raw category composites within the
    exact season.  This prevents legacy formula values (including Kareem
    1971-72's old 63 efficiency value) from leaking into the profile.
    """
    global _REGULAR_SEASON_SPIDER_CACHE
    if _REGULAR_SEASON_SPIDER_CACHE is not None:
        return _REGULAR_SEASON_SPIDER_CACHE
    with _REGULAR_SEASON_SPIDER_CACHE_LOCK:
        if _REGULAR_SEASON_SPIDER_CACHE is not None:
            return _REGULAR_SEASON_SPIDER_CACHE
        out_id={}; out_name={}
        try:
            per=load_canonical_percentiles()
            if per is None or per.empty:
                _REGULAR_SEASON_SPIDER_CACHE={"id":{},"name":{}}
                return _REGULAR_SEASON_SPIDER_CACHE
            stat_col=choose_col(per,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
            season_col=identity_cols(per).get("season") or choose_col(per,["Season","season","Season_ID"])
            pid_col=col(per,["Player_ID","PlayerId","PlayerID","player_id"])
            name_col=col(per,["Player","Player_Name","Display_Name","player_name","Name"])
            pct_col=percentile_column(per,"Season")
            if not stat_col or not season_col or not pct_col or (not pid_col and not name_col):
                _REGULAR_SEASON_SPIDER_CACHE={"id":{},"name":{}}
                return _REGULAR_SEASON_SPIDER_CACHE

            w=per.copy()
            w["__season_key"]=w[season_col].map(_season_label_any)
            w["__pct"]=pd.to_numeric(w[pct_col],errors="coerce")
            w=w.loc[w["__season_key"].notna() & w["__pct"].notna()].copy()
            w["__stat"]=w[stat_col].astype(str).str.strip()
            if pid_col: w["__pid"]=w[pid_col].astype(str).str.strip()
            else: w["__pid"]=w[name_col].astype(str).str.strip()
            if name_col: w["__name"]=w[name_col].astype(str).str.replace(r"\*+","",regex=True).str.strip()
            else: w["__name"]=""
            w["__namekey"]=w["__name"].map(_normalize_peak_lookup_name)

            # Hydrate the audited historical 2P% percentile layer into the
            # response-ready individual-season SDI cache. This is required for
            # pre-1979 Scoring Efficiency because the locked formula includes
            # 2P% as a Component Efficiency input.
            try:
                two_p_path=ROOT/"data"/"2p_pct_pre1979_season_percentiles.csv"
                if two_p_path.exists():
                    two_p=pd.read_csv(two_p_path,low_memory=False)
                    ts=choose_col(two_p,["Season","season","Season_ID"])
                    tp=col(two_p,["Player_ID","PlayerId","PlayerID","player_id"])
                    tn=col(two_p,["Player","Player_Name","Display_Name","player_name","Name"])
                    tt=choose_col(two_p,["Statistic","statistic","Stat"])
                    tx=percentile_column(two_p,"Season")
                    if ts and tt and tx and (tp or tn):
                        two_p["__season_key"]=two_p[ts].map(_season_label_any)
                        two_p["__stat"]=two_p[tt].astype(str).str.strip()
                        two_p["__pct"]=pd.to_numeric(two_p[tx],errors="coerce")
                        two_p=two_p.loc[
                            two_p["__stat"].eq("2P_pct") &
                            two_p["__season_key"].notna() &
                            two_p["__season_key"].map(_season_end_year).fillna(9999).lt(1979) &
                            two_p["__pct"].notna()
                        ].copy()
                        if not two_p.empty:
                            if pid_col and tp:
                                two_p["__pid"]=two_p[tp].astype(str).str.strip()
                            elif tn:
                                two_p["__pid"]=two_p[tn].astype(str).str.strip()
                            else:
                                two_p["__pid"]=""
                            two_p["__name"]=two_p[tn].astype(str).str.replace(r"\*+","",regex=True).str.strip() if tn else ""
                            two_p["__namekey"]=two_p["__name"].map(_normalize_peak_lookup_name)
                            w=pd.concat([w, two_p[["__pid","__season_key","__stat","__pct","__name","__namekey"]]],ignore_index=True,sort=False)
            except Exception as exc:
                print("Regular individual-season SDI 2P% hydration skipped:",repr(exc))

            spec=_load_sdi_v4_spec()
            mappings=[
                ("Scoring Volume","scoring_volume"),
                ("Scoring Efficiency","scoring_efficiency"),
                ("Creation / Playmaking","creation_playmaking"),
                ("Rebounding","rebounding"),
                ("Defense","defense"),
                ("Impact / Value","impact_value"),
            ]

            # Collapse to one statistic-percentile observation per player-season.
            vals=(w.drop_duplicates(["__pid","__season_key","__stat"],keep="first")
                    .set_index(["__pid","__season_key","__stat"])["__pct"])
            rows=[]
            for (pid,season_key),g in w.groupby(["__pid","__season_key"],sort=False):
                statvals=(g.drop_duplicates("__stat",keep="first")
                            .set_index("__stat")["__pct"].to_dict())
                scores={}
                for category,groups in spec.items():
                    if category in {"peak_rules","top_level_category_weights","top_level_category_total_weight"} or not isinstance(groups,dict):
                        continue
                    group_scores=[]
                    for group_spec in groups.values():
                        if not isinstance(group_spec,dict): continue
                        usable=[(float(statvals[st]),float(weight)) for st,weight in (group_spec.get("statistics",{}) or {}).items()
                                if st in statvals and pd.notna(statvals[st]) and pd.notna(weight)]
                        if not usable: continue
                        den=sum(weight for _,weight in usable)
                        if den>0:
                            group_scores.append((sum(v*weight for v,weight in usable)/den,
                                                 float(group_spec.get("weight",0))))
                    if group_scores:
                        den=sum(weight for _,weight in group_scores)
                        if den>0: scores[category]=sum(v*weight for v,weight in group_scores)/den
                if scores:
                    name=str(g["__name"].iloc[0] or "").strip()
                    rows.append((str(pid),str(season_key),name,scores))

            populations={}
            for pid,season_key,name,scores in rows:
                for category,score in scores.items():
                    populations.setdefault((season_key,category),[]).append(float(score))

            for pid,season_key,name,scores in rows:
                year=_season_end_year(season_key)
                axes=[]
                for label,key in mappings:
                    score=scores.get(key)
                    if score is None: continue
                    pct=_percentile_rank_0_100(score,populations.get((season_key,key),[]))
                    if pct is None: continue
                    axes.append({"axis":label,"label":label,"value":float(pct),
                                 "score":float(score),"raw_score":float(score),"percentile":float(pct)})
                payload={"found":True,"player":{"player_id":pid,"player_name":name},
                         "season":season_key,"context":"Season",
                         "available_contexts":{"Season":True,"Era":False,"Historical":False,"Career":False},
                         "category_axes":axes,"stat_axes":[]}
                key=(pid,int(year)) if year is not None else None
                if key and pid: out_id[key]=payload
                if name and year is not None: out_name[(_normalize_peak_lookup_name(name),int(year))]=payload

            _REGULAR_SEASON_SPIDER_CACHE={"id":out_id,"name":out_name}
        except Exception as exc:
            print("Regular individual-season SDI cache build failed:",repr(exc))
            _REGULAR_SEASON_SPIDER_CACHE={"id":{},"name":{}}
        return _REGULAR_SEASON_SPIDER_CACHE

def _regular_season_spider_cached(requested, season):
    cache=_warm_regular_season_spider_cache()
    y=_season_end_year(season)
    if y is None: return None
    req=str(requested or "").strip()
    hit=(cache.get("id",{}) or {}).get((req,int(y)))
    if hit is not None: return hit
    try:
        name=resolve_player_identity(req)[1]
    except Exception:
        name=req
    key=_normalize_peak_lookup_name(name)
    return (cache.get("name",{}) or {}).get((key,int(y)))

def api_spider(requested, season=None, context="Historical", stats=None, season_type="Regular Season"):
    if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
        return api_playoff_spider(requested,season,context,stats)

    # Individual regular-season season spiders are fully materialized at warm-up.
    # Return the exact canonical category percentiles immediately instead of
    # re-running player identity + DataFrame filtering on every row click.
    if str(season).casefold() not in {"career","5-year peak","5 year peak","five-year peak","five_year_peak"} and str(context).casefold()=="season":
        cached=_regular_season_spider_cached(requested,season)
        if cached is not None:
            requested_stats=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
            if requested_stats:
                # The category payload is shared; only the optional custom stat
                # axes are resolved from the existing season percentile layer.
                try:
                    pid,pname=resolve_player_identity(requested)
                    per=load("percentiles",["player_season_percentiles_long"])
                    pm=filter_player(per,pid if pid is not None else pname)
                    ss=choose_col(pm,["Season","season","Season_ID"])
                    if ss: pm=pm.loc[pm[ss].map(_season_label_any).eq(str(normalize_requested_season(season)))]
                    sc=choose_col(pm,["Statistic","statistic","Stat","Statistic_Name","stat_name"])
                    pc=percentile_column(pm,"Season")
                    vals={}
                    if sc and pc:
                        vals=(pm.dropna(subset=[pc]).drop_duplicates(sc).set_index(sc)[pc].to_dict())
                    cached=dict(cached)
                    cached["stat_axes"]=[{"axis":st,"value":vals.get(st)} for st in requested_stats]
                except Exception:
                    pass
            return cached

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
        # If the response-ready Career cache cannot be warmed, fall through to
        # the canonical Career profile calculation below. This prevents a blank
        # regular-season Career spider when the cache is absent/stale.

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
        _warm_regular_peak_sdi_spider_cache()
        pk=peak.get("player") or {}
        pk_key=(str(pk.get("player_id") or "").strip(),_normalize_peak_lookup_name(pk.get("player_name") or ""))
        peak_authoritative_axes=_REGULAR_PEAK_SDI_AXES_CACHE.get(pk_key)
        if peak_authoritative_axes is None:
            peak_authoritative_axes=_regular_peak_category_percentile_axes(peak)
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

    if str(season).casefold() in {"5-year peak","5 year peak","five-year peak","five_year_peak"} and peak_authoritative_axes:
        axes=peak_authoritative_axes
    elif context=="Career":
        # Career category scores are a separate authoritative layer and must be
        # invariant to the active season SDI top-level weights.
        axes=career_authoritative_axes
    else:
        # Regular-season individual-season SDI is a first-class raw-score layer.
        # Read the existing canonical SDI/WOWY season row directly so the
        # Profile never loses its six SDI values because the general percentile
        # table or an auxiliary SDI cache is unavailable.
        canonical_axes, canonical_overall = _canonical_regular_season_sdi_axes(
            pid=pid, pname=pname, season=season
        )
        # Raw SDI must come only from the canonical SDI layer. NEVER fall back
        # to generic statistic percentiles here; that makes an SDI axis equal
        # to a percentile (e.g. Wilt Defense = 100) and hides legitimate raw
        # values for players whose percentile table lacks that category.
        axes = canonical_axes
        pct_map=_regular_season_category_percentiles(season,axes)
        for _ax in axes:
            _label=str(_ax.get("axis") or _ax.get("label") or "")
            _ax["percentile"]=pct_map.get(_label)
        if canonical_overall is not None:
            overall_sdi = canonical_overall

    requested_stats=[x.strip() for x in str(stats).split(",") if x.strip()] if stats else []
    stat_axes=[{"axis":st,"value":vals.get(st)} for st in requested_stats]
    out={"found":True,"player":{"player_id":pid,"player_name":pname},
         "season":season,"context":context,"available_contexts":available,
         "category_axes":axes,"stat_axes":stat_axes}
    if context!="Career" and str(season).casefold() not in {"5-year peak","5 year peak","five-year peak","five_year_peak"}:
        if 'overall_sdi' in locals() and overall_sdi is not None:
            out["sdi"]=float(overall_sdi)
            out["raw_sdi"]=float(overall_sdi)
    return out


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


# Era Average eligibility scales to the length of the selected era.
# Absolute game/minute cutoffs unfairly penalize short eras and over-favor long
# eras, so games and minutes are expressed as shares of the era's observed
# maximum player-season availability. Participation remains a separate gate.
ERA_AVERAGE_PARTICIPATION = 0.40
ERA_AVERAGE_REGULAR_GAME_SHARE = 0.25
ERA_AVERAGE_REGULAR_MINUTE_SHARE = 0.15
ERA_AVERAGE_PLAYOFF_GAME_SHARE = 0.25
ERA_AVERAGE_PLAYOFF_MINUTE_SHARE = 0.15

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
        w=pd.to_numeric(rows[poss],errors="coerce") if poss else pd.Series(np.nan,index=rows.index)
        # Use exact/estimated player possessions when available. If the source
        # lacks an explicit possession column, reconstruct possessions from
        # PTS and PTS/75 before falling back to MP*2. This keeps 5-year and Era
        # Per-75 values from becoming simple averages of season rates.
        if w.isna().all() or not w.notna().any():
            pts_col=col(rows,["PTS_raw","PTS","Points"]); pts75_col=col(rows,["PTS_per75","PTS/75"])
            if pts_col and pts75_col:
                pts=pd.to_numeric(rows[pts_col],errors="coerce"); p75=pd.to_numeric(rows[pts75_col],errors="coerce")
                w=pts/(p75/75.0).replace(0,np.nan)
        if w.isna().all() or not w.notna().any():
            mp=col(rows,["MP","Minutes","minutes"])
            w=pd.to_numeric(rows[mp],errors="coerce")*2.0 if mp else pd.Series(np.nan,index=rows.index)
        x=pd.DataFrame({"v":vals,"w":w}).dropna(); x=x[x.w>0]
        return float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan
    if statistic in denom_map:
        den_col=denom_map[statistic]
        dc=col(rows,[den_col, den_col.replace("_raw","")])
        d=pd.to_numeric(rows[dc],errors="coerce") if dc else pd.Series(np.nan,index=rows.index)
        # AST:TOV can be reconstructed from the season's raw totals or from
        # the corresponding per-75 rates when raw TOV is unavailable.
        if statistic=="AST_TOV" and (dc is None or d.isna().all()):
            astc=col(rows,["AST_raw","AST","Assists"]); tovc=col(rows,["TOV_raw","TOV","Turnovers"])
            if astc and tovc:
                d=pd.to_numeric(rows[tovc],errors="coerce")
            elif tovc is None:
                tp=col(rows,["TOV_per75"]);
                if tp:
                    poss=col(rows,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
                    w=pd.to_numeric(rows[poss],errors="coerce") if poss else pd.Series(np.nan,index=rows.index)
                    d=pd.to_numeric(rows[tp],errors="coerce")*w/75.0
        if d.notna().any():
            x=pd.DataFrame({"v":vals,"w":d}).dropna(); x=x[x.w>0]
            if not x.empty: return float((x.v*x.w).sum()/x.w.sum())
    mp=col(rows,["MP","Minutes","minutes"])
    w=pd.to_numeric(rows[mp],errors="coerce") if mp else pd.Series(np.nan,index=rows.index)
    x=pd.DataFrame({"v":vals,"w":w}).dropna(); x=x[x.w>0]
    return float((x.v*x.w).sum()/x.w.sum()) if not x.empty else np.nan

def _era_average_statistic_grouped(rows, statistic, per75_stats, additive_stats, denom_map, pid_col, name_col):
    """Vectorized era aggregation for one statistic.

    Produces the same weighting rules as _era_average_statistic but avoids a
    Python loop over every player. This is the critical fast path for Era
    Average selector changes.
    """
    if rows.empty or statistic not in rows.columns or not pid_col or not name_col:
        return pd.DataFrame()
    work=rows.copy()
    vals=pd.to_numeric(work[statistic],errors="coerce")
    work["__v"]=vals
    work["__mpw"]=pd.to_numeric(work.get("MP",pd.Series(np.nan,index=work.index)),errors="coerce")
    if statistic in additive_stats:
        # Additive statistics are summed directly. The grouped aggregation
        # still expects a denominator column for its common output contract,
        # so provide a unit weight rather than leaving __w undefined.
        work["__w"]=1.0
        work["__wv"]=work["__v"]
    elif statistic == "WS/48":
        rate_col=col(work,["WS/48.1","WS_per48","WS48_actual"])
        if rate_col:
            work["__v"]=pd.to_numeric(work[rate_col],errors="coerce")
            work["__wv"]=work["__v"]*work["__mpw"]
        else:
            ws_col=col(work,["WS/48"])
            work["__v"]=pd.to_numeric(work[ws_col],errors="coerce") if ws_col else np.nan
            work["__wv"]=48.0*work["__v"]
            # denominator is handled below via MP sum
            sums=work.groupby([pid_col,name_col],dropna=False).agg(_num=("__wv","sum"),_den=("__mpw","sum"),G=("__Gnum","sum"),MP=("__MPnum","sum"),Era_Eligible_Seasons=("__eligible_flag","sum"))
            sums[statistic]=sums["_num"]/sums["_den"].replace(0,np.nan)
            return sums.reset_index()
    elif statistic in per75_stats:
        poss=col(work,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
        if poss:
            work["__w"]=pd.to_numeric(work[poss],errors="coerce")
        else:
            work["__w"]=work["__mpw"]*2.0
        work["__wv"]=work["__v"]*work["__w"]
    elif statistic in denom_map:
        dc=col(work,[denom_map[statistic],denom_map[statistic].replace("_raw","")])
        work["__w"]=pd.to_numeric(work[dc],errors="coerce") if dc else np.nan
        if statistic=="AST_TOV" and work["__w"].isna().all():
            tovc=col(work,["TOV_raw","TOV","Turnovers"]); poss=col(work,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
            if tovc:
                work["__w"]=pd.to_numeric(work[tovc],errors="coerce")
            elif poss and "TOV_per75" in work.columns:
                work["__w"]=pd.to_numeric(work["TOV_per75"],errors="coerce")*pd.to_numeric(work[poss],errors="coerce")/75.0
        work["__wv"]=work["__v"]*work["__w"]
    else:
        work["__w"]=work["__mpw"]
        work["__wv"]=work["__v"]*work["__w"]
    # Avoid pandas named-aggregation resolution against a temporary column.
    # Some pandas builds can resolve the named source column before the
    # temporary frame has been materialized, producing the misleading
    # KeyError("Label(s) ['__w'] do not exist"). Compute each grouped Series
    # explicitly instead.
    group_keys=[work[pid_col], work[name_col]]
    grouped_num=work["__wv"].groupby(group_keys,dropna=False).sum(min_count=1)
    grouped_den=work["__w"].groupby(group_keys,dropna=False).sum(min_count=1)
    grouped_g=work["__Gnum"].groupby(group_keys,dropna=False).sum(min_count=1)
    grouped_mp=work["__MPnum"].groupby(group_keys,dropna=False).sum(min_count=1)
    grouped_q=work["__eligible_flag"].groupby(group_keys,dropna=False).sum(min_count=1)
    out=pd.concat([grouped_num.rename("_num"),grouped_den.rename("_den"),
                   grouped_g.rename("G"),grouped_mp.rename("MP"),
                   grouped_q.rename("Era_Eligible_Seasons")],axis=1).reset_index()
    out[statistic]=out["_num"]/out["_den"].replace(0,np.nan)
    if statistic in additive_stats:
        out[statistic]=out["_num"]
    return out

def _era_average_qualified_rows(source, season_type, era_key, statistic=None):
    """Return one aggregated era row per player after the agreed eligibility gate.

    Era-average aggregation is cached by dataset + era because the same
    population is reused for every statistic, sort direction, and search.
    """
    cache_key=f"__era_average_rows_v3__:{season_type}:{era_key}:{statistic or '__all__'}"
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
    # Determine qualifying seasons directly from the canonical rows.  The
    # previous implementation depended on exact player/season strings in a
    # separate qualification CSV; legacy spelling/asterisk/ID differences
    # could therefore erase valid seasons (notably George Gervin).
    if season_type.casefold().startswith("regular"):
        sched_by_year=work.groupby("__year")["__Gnum"].max().to_dict()
        era_rows["__schedule"]=era_rows["__year"].map(lambda y: float(sched_by_year.get(int(y),82) or 82))
        era_rows["__qualified_season"]=(
            era_rows["__Gnum"] >= era_rows["__schedule"].map(lambda x: math.ceil(0.60*float(x)))
        ) & era_rows["__MPnum"].ge(1400)
    else:
        era_rows["__qualified_season"]=(era_rows["__Gnum"]>=3)&(era_rows["__MPnum"]>=75)
    # Vectorized player qualification: avoid repeated per-player Python work.
    group_cols=[pid,pcol] if pid else [pcol]
    era_rows["__eligible_flag"]=era_rows["__qualified_season"].astype(int)
    # Calculate the requested statistic plus its known Big Board companion.
    # Keeping this scoped is important: calculating the entire regular-season
    # registry here can cause the all-stat warm path to fail on legacy aliases
    # and then make an otherwise valid Era Average request return no rows.
    # The companion is aggregated from the exact same qualified player-era rows,
    # so Era Average secondary values remain authoritative without a second
    # population build.
    era_companion_map={
        "PTS_per75":"rTS",
        "FGA_per75":"FG_pct", "3PA_per75":"3P_pct", "2PA_per75":"2P_pct",
        "ORB_per75":"OREB_pct", "DRB_per75":"DREB_pct",
        "TRB_per75":"ORB_per75", "STL_per75":"STL_pct", "BLK_per75":"BLK_pct",
        "FT_pct":"FTA_per75", "AST_pct":"AST_per75", "BLK_pct":"BLK_per75",
        "STL_pct":"STL_per75", "OREB_pct":"ORB_per75", "DREB_pct":"DRB_per75",
        "FG_pct":"FGA_per75", "3P_pct":"3PA_per75", "2P_pct":"2PA_per75",
        "AST_per75":"AST_TOV", "TOV_per75":"AST_TOV", "PF_per75":None,
        "rTS":"PTS_per75",
    }
    if statistic:
        companion_stat=era_companion_map.get(statistic)
        stats=list(dict.fromkeys([statistic] + ([companion_stat] if companion_stat else [])))
    else:
        # Startup warming retains the established all-stat path.
        stats=PLAYOFF_STATS
    # Determine each player's first/last appearance inside the era, then apply
    # the same participation/game/minute gate used by the legacy implementation.
    bounds_a,bounds_b=bounds
    appearance=work.assign(__namekey=work[pcol].astype(str).str.strip().str.casefold()).groupby([pid,"__namekey"] if pid else ["__namekey"],dropna=False)["__year"].agg(["min","max"])
    appearance["eligible_years"]=(appearance["max"].clip(lower=bounds_a)-appearance["min"].clip(upper=bounds_b)+1).clip(lower=0)
    summary=era_rows.groupby(group_cols,dropna=False).agg(
        G=("__Gnum","sum"), MP=("__MPnum","sum"),
        Era_Qualified_Seasons=("__eligible_flag","sum")
    ).reset_index()
    # Map eligible span using player identity; canonical name is retained for
    # display and does not require exact source-name matching across files.
    if pid:
        span=work.groupby(pid,dropna=False)["__year"].agg(first="min",last="max").reset_index()
        span["Era_Eligible_Seasons"]=(span["last"].clip(lower=bounds_a)-span["first"].clip(upper=bounds_b)+1).clip(lower=0)
        summary=summary.merge(span[[pid,"Era_Eligible_Seasons"]],on=pid,how="left")
    else:
        span=work.assign(__namekey=work[pcol].astype(str).str.strip().str.casefold()).groupby("__namekey")["__year"].agg(first="min",last="max").reset_index()
        span["Era_Eligible_Seasons"]=(span["last"].clip(lower=bounds_a)-span["first"].clip(upper=bounds_b)+1).clip(lower=0)
        summary["__namekey"]=summary[pcol].astype(str).str.strip().str.casefold()
        summary=summary.merge(span[["__namekey","Era_Eligible_Seasons"]],on="__namekey",how="left").drop(columns=["__namekey"])
    summary["Era_Participation"]=summary["Era_Qualified_Seasons"]/summary["Era_Eligible_Seasons"].replace(0,np.nan)
    era_max_games=float(work.groupby("__year")["__Gnum"].max().sum())
    era_max_minutes=float(work.groupby("__year")["__MPnum"].max().sum())
    game_share=ERA_AVERAGE_REGULAR_GAME_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_GAME_SHARE
    minute_share=ERA_AVERAGE_REGULAR_MINUTE_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MINUTE_SHARE
    summary["Era_Game_Share"]=summary["G"]/era_max_games if era_max_games>0 else np.nan
    summary["Era_Minute_Share"]=summary["MP"]/era_max_minutes if era_max_minutes>0 else np.nan
    summary=summary.loc[(summary["Era_Participation"]+1e-12>=ERA_AVERAGE_PARTICIPATION)&summary["Era_Game_Share"].ge(game_share)&summary["Era_Minute_Share"].ge(minute_share)].copy()
    if summary.empty:
        result=pd.DataFrame()
    else:
        # Only calculate the requested statistic(s), using vectorized groupby.
        # Resolve the same aliases used by the canonical playoff layer and
        # synthesize AST:TOV when the source exposes only raw AST/TOV totals.
        work2=era_rows.copy()
        for stat in stats:
            if stat not in work2.columns:
                alias_col=col(work2, PLAYOFF_STAT_ALIASES.get(stat,[stat]))
                if alias_col: work2[stat]=pd.to_numeric(work2[alias_col],errors="coerce")
            if stat=="AST_TOV" and (stat not in work2.columns or pd.to_numeric(work2[stat],errors="coerce").isna().all()):
                astc=col(work2,["AST_raw","AST","Assists"]); tovc=col(work2,["TOV_raw","TOV","Turnovers"])
                if astc and tovc:
                    den=pd.to_numeric(work2[tovc],errors="coerce"); num=pd.to_numeric(work2[astc],errors="coerce")
                    work2[stat]=num/den.replace(0,np.nan)
            if stat not in work2.columns: continue
            agg=_era_average_statistic_grouped(work2,stat,ERA_AVERAGE_PER75_REGULAR if season_type.casefold().startswith("regular") else ERA_AVERAGE_PER75_PLAYOFF,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS,pid,pcol)
            if agg.empty: continue
            keep=[pid,pcol,stat]
            summary=summary.merge(agg[keep],on=group_cols,how="left",suffixes=("","_stat"))
        summary["Player_ID"]=summary[pid].map(clean) if pid else summary[pcol].map(clean)
        summary["Player"]=summary[pcol].map(clean)
        summary["Era"]=era_key
        result=summary[["Player_ID","Player","Era","Era_Eligible_Seasons","Era_Qualified_Seasons","Era_Participation","G","MP"]+[st for st in stats if st in summary.columns]].copy()
    meta={"players_considered":int(era_rows[pcol].nunique()),"players_qualified":len(result)}
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
    request_cache_key=f"__big_board_era_v3__:{season_type}:{era_key}:{statistic}:{sort_direction}:{search or ''}:{int(limit)}"
    if request_cache_key in CACHE:
        return CACHE[request_cache_key]
    if not era_key:
        return {"rows":[],"count":0,"scope":"era_average","season_type":season_type,
                "era":None,"note":"Select an era to calculate an Era Average."}
    source=load_master_seasons() if season_type.casefold().startswith("regular") else load_playoff_46_season()
    # Prefer the all-stat era bundle warmed at API startup. This prevents each
    # statistic selector change from rebuilding the same qualified population.
    all_key=f"__era_average_rows_v3__:{season_type}:{era_key}:__all__"
    if statistic and all_key in CACHE:
        _all_rows,_all_meta=CACHE[all_key]
        rows=_all_rows.copy()
        meta=dict(_all_meta)
    else:
        rows,meta=_era_average_qualified_rows(source,season_type,era_key,statistic)
    if rows.empty or not statistic or statistic not in rows.columns:
        return {"rows":[],"count":0,"scope":"era_average","career_scope":False,
                "historical_scope":False,"context":"Era","season":"Era Average",
                "season_type":season_type,"era":era_key,"statistic":statistic or "Statistical Dominance Index",
                "note":"Era Average requires a selected statistic. The Statistical Dominance Index is intentionally deferred for this build.","qualification":{
                    "participation":ERA_AVERAGE_PARTICIPATION,"min_game_share":ERA_AVERAGE_REGULAR_GAME_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_GAME_SHARE,
                    "min_minute_share":ERA_AVERAGE_REGULAR_MINUTE_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MINUTE_SHARE},"meta":meta}
    higher=statistic not in (ERA_AVERAGE_LOWER - {"PF_per75"})
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
        companion_values={st:clean(r.get(st)) for st in (PLAYOFF_STATS if season_type.casefold().startswith("playoff") else REGULAR_STATS) if st in r.index and st != statistic and pd.notna(r.get(st))}
        out.append({"rank":rank,"player_id":clean(r.get("Player_ID")),"player_name":clean(r.get("Player")),
                    "season":"Era Average","season_label":"Era Average","statistic":statistic,
                    "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"context":"Era",
                    "headshot_url":_headshot_url_for(clean(r.get("Player_ID")),clean(r.get("Player"))),
                    "era":era_key,"era_participation":clean(r["Era_Participation"]),
                    "era_qualified_seasons":clean(r["Era_Qualified_Seasons"]),
                    "era_eligible_seasons":clean(r["Era_Eligible_Seasons"]),
                    "era_games":clean(r["G"]),"era_minutes":clean(r["MP"]),
                    "companion_values":companion_values})
    result={"rows":out,"count":len(out),"scope":"era_average","career_scope":False,
            "historical_scope":False,"context":"Era","season":"Era Average","season_type":season_type,
            "era":era_key,"statistic":statistic,"qualification":{
                "participation":ERA_AVERAGE_PARTICIPATION,"min_game_share":ERA_AVERAGE_REGULAR_GAME_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_GAME_SHARE,
                "min_minute_share":ERA_AVERAGE_REGULAR_MINUTE_SHARE if season_type.casefold().startswith("regular") else ERA_AVERAGE_PLAYOFF_MINUTE_SHARE},"meta":meta,
            "note":"Era Average aggregates qualified player-seasons across the selected era. Per-75 rates are possession-weighted; cumulative stats are summed; percentage/rate stats use their natural denominator when available."}
    CACHE[request_cache_key]=result
    return result


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

def _api_playoff_explorer_population(x_statistic="PTS_per75", y_statistic="rTS", season="Historical Percentile", era="", search="", x_min=None, x_max=None, y_min=None, y_max=None, limit=100):
    """Explorer-specific playoff population using the finalized 46-stat source.

    Explorer must not surface tiny playoff samples merely because a raw value
    exists. Match the canonical single-season playoff qualification gate:
    at least 3 games and 75 minutes. The Player Profile/Big Board layers remain
    untouched; this is an Explorer transport/filter only.
    """
    raw=_load_final_playoff_46_file(career=False)
    if raw.empty:
        raw=load_playoff_46_season()
    if raw.empty:
        return {"rows":[],"count":0,"total":0,"ready":False,"fallback":True}
    pcol=col(raw,["Player_ID","PlayerId","PlayerID","player_id"])
    ncol=col(raw,["Player","Player_Name","Display_Name","player_name","Name"])
    scol=col(raw,["Season","season","Season_ID"])
    gcol=col(raw,["G","Games","games"])
    mpcol=col(raw,["MP","Minutes","minutes"])
    if not ncol or not scol or not gcol or not mpcol:
        return {"rows":[],"count":0,"total":0,"ready":False,"fallback":True}
    xs=str(x_statistic or "PTS_per75"); ys=str(y_statistic or "rTS")
    xcol=_playoff_source_column(raw,xs); ycol=_playoff_source_column(raw,ys)
    if not xcol or not ycol:
        return {"rows":[],"count":0,"total":0,"ready":False,"error":"Unsupported playoff Explorer statistic"}
    work=raw.copy()
    work["__g"]=pd.to_numeric(work[gcol],errors="coerce")
    work["__mp"]=pd.to_numeric(work[mpcol],errors="coerce")
    work=work.loc[work["__g"].ge(PLAYOFF_SINGLE_MIN_GAMES) & work["__mp"].ge(PLAYOFF_SINGLE_MIN_MINUTES)].copy()
    if season and str(season).casefold() not in {"historical","historical percentile","all","all seasons"}:
        target=str(season).strip()
        work=work.loc[work[scol].astype(str).str.strip().eq(target)].copy()
    if era:
        work=work.loc[work[scol].map(_era_key).eq(str(era).strip())].copy()
    if search:
        work=work.loc[work[ncol].astype(str).str.contains(str(search),case=False,na=False)].copy()
    work["__x"]=pd.to_numeric(work[xcol],errors="coerce")
    work["__y"]=pd.to_numeric(work[ycol],errors="coerce")
    work=work.dropna(subset=["__x","__y"]).copy()
    if x_min is not None: work=work.loc[work["__x"].ge(float(x_min))]
    if x_max is not None: work=work.loc[work["__x"].le(float(x_max))]
    if y_min is not None: work=work.loc[work["__y"].ge(float(y_min))]
    if y_max is not None: work=work.loc[work["__y"].le(float(y_max))]
    sort_name=ncol
    work=work.sort_values(["__x",sort_name],ascending=[False,True],kind="stable")
    cap=max(1,min(int(limit or 100),100))
    total=len(work)
    rows=[]
    for i,(_,r) in enumerate(work.head(cap).iterrows(),1):
        pid=clean(r[pcol]) if pcol else None
        name=clean(r[ncol])
        rows.append({"rank":i,"player_id":pid,"player_name":name,"season":clean(r[scol]),
                     "season_label":_season_label_any(r[scol]),"xValue":clean(r["__x"]),"yValue":clean(r["__y"]),
                     "headshot_url":_headshot_url_for(pid,name)})
    season_rows=raw[[scol]].dropna().drop_duplicates().copy()
    season_rows["__sort"]=season_rows[scol].map(_season_end_year)
    season_rows=season_rows.sort_values("__sort")
    season_options=[{"value":clean(r[scol]),"label":_season_label_any(r[scol])} for _,r in season_rows.iterrows()]
    return {"rows":rows,"count":len(rows),"total":total,"population_total":total,
            "available_bounds":{"xmin":min((float(r["xValue"]) for r in rows),default=None),"xmax":max((float(r["xValue"]) for r in rows),default=None),
                                "ymin":min((float(r["yValue"]) for r in rows),default=None),"ymax":max((float(r["yValue"]) for r in rows),default=None)},
            "x_statistic":xs,"y_statistic":ys,"season":season or "Historical Percentile","season_type":"Playoffs",
            "scope":"single","era":era or "","ranked_by":"x","rank_direction":"desc","season_options":season_options,"public_layer":False,
            "qualification":"Single-season playoffs: ≥3 games and ≥75 minutes."}


def api_playoff_big_board(season=None,context="Historical",statistic=None,
                          sort_direction="desc",search=None,limit=100,scope="single",era=None):
    """Cached public playoff Big Board endpoint.

    The playoff source/percentile layers are already warmed at API startup.
    Cache the final response by its exact selector tuple as well, so switching
    back to a playoff table does not repeat the DataFrame merge/sort work.
    """
    key=("__playoff_big_board_response_v1__",str(season or ""),str(context or ""),
         str(statistic or ""),str(sort_direction or ""),str(search or ""),
         int(limit or 100),str(scope or ""),str(era or ""))
    if key in CACHE:
        return CACHE[key]
    result=_api_playoff_big_board_uncached(season,context,statistic,sort_direction,search,limit,scope,era)
    CACHE[key]=result
    return result


def _api_playoff_big_board_uncached(season=None,context="Historical",statistic=None,
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
        # Career playoff Explorer values must use the canonical career qualification
        # gate before any statistic is exposed. This prevents tiny playoff careers
        # (e.g. a handful of minutes) from producing extreme per-75 values.
        work=raw.copy()
        gcol_c=col(work,["G","Games","games"]); mpcol_c=col(work,["MP","Minutes","minutes"])
        if gcol_c and mpcol_c:
            work["__career_g"]=pd.to_numeric(work[gcol_c],errors="coerce")
            work["__career_mp"]=pd.to_numeric(work[mpcol_c],errors="coerce")
            work=work.loc[work["__career_g"].ge(50) & work["__career_mp"].ge(1500)].copy()
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
               "context":"Career",
               "companion_values":{st:clean(r.get(st)) for st in PLAYOFF_STATS
                                   if st != statistic and st in r.index and pd.notna(r.get(st))},
               "headshot_url":_headshot_url_for(clean(r[c_pid]) if c_pid else None,clean(r[c_player]))} for i,(_,r) in enumerate(work.iterrows(),1)]
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
            "percentile":clean(r["_pct_num"]),"context":context,
            "companion_values":{st:clean(r.get(st)) for st in PLAYOFF_STATS
                                if st != statistic and st in r.index and pd.notna(r.get(st))},
            "headshot_url":_headshot_url_for(clean(r[c_pid]) if c_pid else None,clean(r[c_player]))
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
                raw_col=raw if raw in g.columns else col(g,[raw,raw.replace("_raw",""),raw.replace("_raw","s")])
                if not raw_col: continue
                num=pd.to_numeric(g[raw_col],errors="coerce")
                use_poss=poss.copy()
                if use_poss.isna().all() or not use_poss.notna().any():
                    pts_col=col(g,["PTS_raw","PTS","Points"]); pts75_col=col(g,["PTS_per75","PTS/75"])
                    if pts_col and pts75_col:
                        pts=pd.to_numeric(g[pts_col],errors="coerce"); p75=pd.to_numeric(g[pts75_col],errors="coerce")
                        use_poss=pts/(p75/75.0).replace(0,np.nan)
                    if use_poss.isna().all(): use_poss=pd.to_numeric(g["__mp"],errors="coerce")*2.0
                mask=num.notna() & use_poss.notna() & use_poss.gt(0)
                if not mask.any(): continue
                denom=float(use_poss.loc[mask].sum())
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
            # Some canonical career exports omit AST/75 (or another Per-75
            # rate) even though the underlying career totals are present.
            # Reconstruct missing Per-75 rates from career totals and estimated
            # possessions rather than averaging season rates.
            poss_series=None
            poss_col=col(career,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
            if poss_col:
                poss_series=pd.to_numeric(career[poss_col],errors="coerce")
            if poss_series is None or poss_series.isna().all():
                pts_col=col(career,["PTS","PTS_raw","Points"]); pts75_col=col(career,["PTS_per75","PTS/75"])
                if pts_col and pts75_col:
                    pts=pd.to_numeric(career[pts_col],errors="coerce"); p75=pd.to_numeric(career[pts75_col],errors="coerce")
                    poss_series=pts/(p75/75.0).replace(0,np.nan)
            if poss_series is not None:
                out["__career_poss"]=poss_series
                raw_per75={"PTS_per75":"PTS","FG_per75":"FG","FGA_per75":"FGA","3P_per75":"3P","3PA_per75":"3PA",
                           "2P_per75":"2P","2PA_per75":"2PA","FT_per75":"FT","FTA_per75":"FTA",
                           "ORB_per75":"ORB","DRB_per75":"DRB","TRB_per75":"TRB","AST_per75":"AST",
                           "STL_per75":"STL","BLK_per75":"BLK","TOV_per75":"TOV","PF_per75":"PF"}
                for stat,raw in raw_per75.items():
                    if stat not in out.columns or pd.to_numeric(out[stat],errors="coerce").isna().all():
                        if raw in out.columns:
                            out[stat]=pd.to_numeric(out[raw],errors="coerce")/(poss_series/75.0).replace(0,np.nan)
                out=out.drop(columns=["__career_poss"],errors="ignore")
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
            if not out.empty and any(stat in out.columns for stat in PLAYOFF_STATS):
                CACHE[cache_key]=out
                return out
            # If the packaged canonical career layer has no usable regular-season
            # rows/stat columns, fall through to the canonical player-season
            # aggregation below instead of returning an empty career board.

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

# Career BRef qualification constants (restored for Big Board career filtering).
BREF_CAREER_PERCENT = {
    "NBA":{"FG_pct":("FG",2000),"FT_pct":("FT",1200),"3P_pct":("3P",250),"TS_pct":("TSA",5000)},
    "ABA":{"FG_pct":("FG",1000),"FT_pct":("FT",600),"3P_pct":("3P",125),"TS_pct":("TSA",2500)},
}
BREF_CAREER_PER75_MP = 15000
BREF_BASIC_STATS = {"MP","MIN","MIN_per_game","PTS","PTS_per75","TRB","TRB_per75","AST","AST_per75","STL","STL_per75","BLK","BLK_per75"}
BREF_PERCENT_STATS = {"FG_pct","FT_pct","3P_pct","TS_pct"}
# Big Board BRef qualification constants.  These were accidentally omitted
# from the v34 merge, which caused the startup Big Board warm to abort before
# reaching the regular 5-Year Peak prewarm.  Keep the legacy gate conservative
# and compatible with the existing canonical data layer.
BREF_ORTG_STATS = {"ORtg"}
BREF_ADV_STATS = {"BPM","VORP","WS","WS/48","PER","DWS","OWS"}
BREF_ORtg_POSS = {}
BREF_ADV_MP = {}
BREF_FG = {}
BREF_FT = {}
BREF_3P = {}
BREF_TSA = {}
BREF_BASIC_GAMES = {}

def _regular_career_big_board(statistic, sort_direction="desc", search=None, limit=100):
    career=_build_regular_career_table()
    if career.empty or not statistic: return []
    # WOWY Career is a first-class board. The canonical WOWY layer does not
    # carry minutes in its compact export, so join it to the authoritative
    # regular-season master by player + season before aggregating. This keeps
    # the existing career G/MP eligibility contract without requiring a
    # legacy career WOWY CSV.
    if str(statistic).strip() in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}:
        w=_load_wowy_stat_layer()
        if w is None or w.empty:
            return []
        w=w.copy()
        wname=col(w,["Player","Player_Name","Display_Name","player_name","Name"])
        wseason=col(w,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        if not wname or not wseason:
            return []
        # Build the WOWY weighting universe from the canonical player-season
        # data. Some finalized builds expose the master through a different
        # data-folder layout, so fall back to the player-season profile layer
        # rather than returning an empty Career WOWY board.
        master=load_master_seasons()
        if master is None or master.empty:
            master_file=_recursive_file([
                "nba_per75_master_v46.csv",
                "nba_per75_master_dreb_v2.csv",
                "nba_per75_master.csv"
            ])
            if master_file:
                try:
                    master=pd.read_csv(master_file,low_memory=False)
                except Exception:
                    master=pd.DataFrame()
        if master is None or master.empty:
            profile_file=_recursive_file(["player_season_profiles.csv"])
            if profile_file:
                try:
                    master=pd.read_csv(profile_file,low_memory=False)
                except Exception:
                    master=pd.DataFrame()
        if master is None or master.empty:
            return []
        mname=col(master,["Player","Player_Name","Display_Name","player_name","Name"])
        mseason=col(master,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
        if not mname or not mseason:
            return []
        mg=col(master,["G","Games","games"])
        mmp=col(master,["MP","Minutes","minutes"])
        if not mg or not mmp:
            return []
        wm=w.copy(); mm=master.copy()
        wm["__name_key"]=wm[wname].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        wm["__season_key"]=wm[wseason].map(_season_label_any)
        mm["__name_key"]=mm[mname].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
        mm["__season_key"]=mm[mseason].map(_season_label_any)
        weights=mm[["__name_key","__season_key",mg,mmp]].copy()
        weights["__games"]=pd.to_numeric(weights[mg],errors="coerce")
        weights["__mp"]=pd.to_numeric(weights[mmp],errors="coerce")
        weights=weights[["__name_key","__season_key","__games","__mp"]]
        weights=weights.dropna(subset=["__name_key","__season_key"]).copy()
        weights=weights.sort_values(["__name_key","__season_key","__mp"],ascending=[True,True,False],kind="stable").drop_duplicates(["__name_key","__season_key"],keep="first")
        wm=wm.merge(weights,on=["__name_key","__season_key"],how="inner")
        wm["__value"]=pd.to_numeric(wm[statistic],errors="coerce")
        wm=wm.dropna(subset=["__value","__mp","__games"]).loc[lambda x:x["__mp"].gt(0)].copy()
        if wm.empty:
            return []
        agg=wm.groupby("__name_key",dropna=False).apply(
            lambda g: pd.Series({
                "_value_num": float((g["__value"]*g["__mp"]).sum()/g["__mp"].sum()),
                "_career_games": float(g["__games"].sum()),
                "_career_minutes": float(g["__mp"].sum()),
            }), include_groups=False
        ).reset_index()
        names=wm.groupby("__name_key",dropna=False)[wname].first().to_dict()
        agg["Player"]=agg["__name_key"].map(names)
        agg=agg.loc[agg["_career_games"].ge(400) & agg["_career_minutes"].ge(10000)].copy()
        if search:
            agg=agg.loc[agg["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        higher=True
        agg["_pct"]=_playoff_percentile(agg["_value_num"],higher=higher) if not agg.empty else np.nan
        agg=agg.sort_values("_pct",ascending=(sort_direction=="asc"),kind="stable",na_position="last").head(int(limit))
        # Recover the canonical player ID from the career table when possible;
        # otherwise use the WOWY source ID.
        idmap={}
        if "Player_ID" in wm.columns:
            idmap=wm.groupby("__name_key")["Player_ID"].first().to_dict()
        rows=[]
        for rank,(_,r) in enumerate(agg.iterrows(),1):
            key=str(r["__name_key"])
            pid=idmap.get(key) or key
            rows.append({"rank":rank,"player_id":clean(pid),"player_name":clean(r["Player"]),
                         "season":"Career","season_label":"Career","statistic":statistic,
                         "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"context":"Career",
                         "career_games":clean(r["_career_games"]),"career_minutes":clean(r["_career_minutes"]),
                         "companion_values":{st:clean(r.get(st)) for st in PLAYOFF_STATS
                                             if st != statistic and st in r.index and pd.notna(r.get(st))},
                         "headshot_url":_headshot_url_for(clean(pid),clean(r["Player"]))})
        return rows
    if search:
        career=career.loc[career["Player"].astype(str).str.contains(str(search),case=False,na=False)]
    # Derived career AST:TOV follows the same canonical career population.
    # Build it from career AST/TOV totals rather than requiring a precomputed
    # AST_TOV column in the source export.
    if str(statistic).strip().casefold() == "ast_tov" and "AST_TOV" not in career.columns:
        ac=col(career,["AST","AST_raw","Assists"]); tc=col(career,["TOV","TOV_raw","Turnovers"])
        if ac and tc:
            career["AST_TOV"]=pd.to_numeric(career[ac],errors="coerce")/pd.to_numeric(career[tc],errors="coerce").replace(0,np.nan)
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
        companion_values={st:clean(r.get(st)) for st in REGULAR_STATS if st in r.index and st != statistic}
        rows.append({"rank":rank,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),
                     "season":"Career","season_label":"Career","statistic":statistic,
                     "value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"context":"Career",
                     "career_games":clean(r["G"]),"career_minutes":clean(r["MP"]),
                     "companion_values":companion_values,
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

def _five_year_peak_windows(season_type="Regular Season", era=None):
    """Cache the expensive player/window qualification once for every stat."""
    key=f"__big_board_peak_windows_v4__:{season_type}:{era or ''}"
    if key in CACHE:
        return CACHE[key]
    is_playoff=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    source=load_playoff_46_season() if is_playoff else load_master_seasons()
    if source.empty:
        CACHE[key]=[]; return []
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    pid=col(source,["Player_ID","PlayerId","PlayerID","player_id"])
    scol=col(source,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    gcol=col(source,["G","Games","games"]); mpcol=col(source,["MP","Minutes","minutes"])
    if not pcol or not scol or not gcol or not mpcol:
        CACHE[key]=[]; return []
    work=source.copy(); st=col(work,["Season_Type","SeasonType","season_type","Phase"])
    if st:
        wanted={"playoffs","playoff","postseason"} if is_playoff else {"regular season","regular","reg season"}
        work=work.loc[work[st].astype(str).str.strip().str.casefold().isin(wanted)].copy()
    work["__year"]=work[scol].map(_season_end_year); work["__g"]=pd.to_numeric(work[gcol],errors="coerce"); work["__mp"]=pd.to_numeric(work[mpcol],errors="coerce")
    work=work.dropna(subset=["__year"]).copy(); work["__year"]=work["__year"].astype(int)
    work["__pid"]=work[pid].astype(str).str.strip() if pid else work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip()
    work["__name"]=work[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip()
    identity=_canonical_identity_registry()
    if not identity.empty:
        ic=identity_cols(identity)
        if ic.get("id") and ic.get("name"):
            id_to_name=dict(zip(identity[ic["id"]].astype(str).str.strip(),identity[ic["name"]].astype(str).str.replace(r"\*+","",regex=True).str.strip()))
            work["__canonical_name"]=work["__pid"].map(id_to_name).fillna(work["__name"])
        else: work["__canonical_name"]=work["__name"]
    else: work["__canonical_name"]=work["__name"]
    schedule={} if is_playoff else work.groupby("__year")["__g"].max().dropna().to_dict()
    windows=[]
    for canonical_name,g in work.groupby("__canonical_name",dropna=False,sort=False):
        g=g.sort_values(["__year","__mp"],ascending=[True,False],kind="stable").drop_duplicates(["__year"],keep="first")
        if is_playoff:
            q=g.loc[(g["__g"]>=3)&(g["__mp"]>=75)].copy()
            candidates=[]
            for i in range(max(0,len(q)-4)):
                cand=q.iloc[i:i+5].copy()
                if len(cand)!=5: continue
                years=cand["__year"].astype(int).tolist()
                if years[-1]-years[0] != 4: continue
                if float(cand["__g"].sum()) < 35: continue
                candidates.append(cand)
        else:
            qualified=[]
            for _,r in g.iterrows():
                sched=float(schedule.get(int(r["__year"]),82) or 82)
                if float(r["__g"])>=math.ceil(.60*sched) and float(r["__mp"])>=1400: qualified.append(r)
            q=pd.DataFrame(qualified) if qualified else pd.DataFrame()
            candidates=[]
            for i in range(max(0,len(q)-4)):
                cand=q.iloc[i:i+5].copy()
                if len(cand)==5 and int(cand["__year"].iloc[-1])-int(cand["__year"].iloc[0])<=5: candidates.append(cand)
        for cand in candidates:
            start=int(cand["__year"].min()); end=int(cand["__year"].max()); peak_era=_era_key(start)
            if era and peak_era!=era: continue
            windows.append({"Player_ID":str(cand["__pid"].iloc[0]),"Player":str(canonical_name),"Peak_Start_Year":start,"Peak_End_Year":end,"Peak_Era":peak_era,"Peak_Seasons":[_season_label_any(x) for x in cand[scol].tolist()],"frame":cand.copy(deep=False)})
    CACHE[key]=windows
    return windows

def _load_precomputed_regular_peak_board_bundle(season_type="Regular Season", era=None):
    """Load the canonical offline regular 5-Year Peak profile cache when present.

    The profile peak artifact contains the same canonical peak window and all
    statistic values. Reusing it makes Big Board Peak selector changes a pure
    in-memory lookup instead of rebuilding thousands of windows.
    """
    if str(season_type).casefold() not in {"regular season","regular","reg season"}:
        return None
    path=ROOT/"data"/"precomputed_5_year_peak"/"regular_profile_peaks_wowy_canonical_v2.json"
    if not path.exists(): return None
    key="__regular_peak_board_precomputed_bundle_v1__"
    if key not in CACHE:
        try:
            payload=json.loads(path.read_text(encoding="utf-8")); players=payload.get("players",[])
            bundle={}
            for p in players:
                pid=str(p.get("player_id") or "").strip(); name=str(p.get("player_name") or "").strip()
                stats=p.get("statistics") or {}
                start=p.get("peak_start_year"); end=p.get("peak_end_year"); peak_era=p.get("peak_era") or _era_key(start)
                if era and str(peak_era)!=str(era): continue
                for st,val in stats.items():
                    if st.endswith("__percentile"): continue
                    try: num=float(val)
                    except (TypeError,ValueError): continue
                    if not np.isfinite(num): continue
                    bundle.setdefault(st,[]).append({"Player_ID":pid,"Player":name,"Peak_Start_Year":start,"Peak_End_Year":end,"Peak_Era":peak_era,"Peak_Seasons":p.get("peak_seasons",[]),"_value_num":num})
            for st,rows in bundle.items():
                df=pd.DataFrame(rows)
                lower={"TOV_per75","TOV_pct","DRtg","Relative_DRtg"}
                higher=st not in lower
                df=df.sort_values("_value_num",ascending=not higher,kind="stable").drop_duplicates(["Player_ID"],keep="first").reset_index(drop=True)
                bundle[st]=df
            CACHE[key]=bundle
        except Exception:
            CACHE[key]=None
    return CACHE[key]

def _five_year_peak_all_stat_values(season_type="Regular Season", era=None):
    """Build every Peak statistic from the cached qualifying windows in one pass.

    The expensive part of Peak is traversing every player's qualifying window.
    Doing that separately for every selected statistic made a stat-to-stat switch
    unnecessarily expensive. This bundle traverses the windows once and stores
    the best window/value for every statistic, so subsequent switches are cache
    lookups.
    """
    key=f"__big_board_peak_all_stats_v6__:{season_type}:{era or ''}"
    if key in CACHE:
        return CACHE[key]
    is_playoff=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    # Persistent Big Board Peak cache: once the canonical weighted peak bundle
    # has been built, selector changes and subsequent API restarts are pure
    # in-memory/file lookups instead of recomputing every player/window.
    if not is_playoff and not era:
        persistent=ROOT/"data"/"precomputed_5_year_peak"/"regular_big_board_peak_weighted_v6.pkl"
        if persistent.exists():
            try:
                bundle=pd.read_pickle(persistent)
                if isinstance(bundle,dict) and bundle:
                    nonempty=any(isinstance(v,pd.DataFrame) and not v.empty for v in bundle.values())
                    if nonempty:
                        # Accept the persisted bundle only when the requested
                        # artifact actually contains usable rows. Older builds
                        # could persist a 43-stat dictionary of empty frames;
                        # treating that as authoritative makes every Peak
                        # request return no data forever.
                        usable=sum(1 for v in bundle.values() if isinstance(v,pd.DataFrame) and not v.empty)
                        if usable:
                            CACHE[key]=bundle
                            return bundle
            except Exception:
                pass
    # Do not reuse the Player Profile's canonical SDI-selected peak here.
    # Big Board 5-Year Peak is statistic-specific: each statistic gets the
    # player's best valid five-season window for that statistic.
    windows=_five_year_peak_windows(season_type,era)
    stats=list(PLAYOFF_STATS if is_playoff else REGULAR_STATS)
    # Never persist an empty/invalid peak bundle. A stale empty cache artifact
    # must not make every Peak selector look like it has no data.
    if not windows:
        # Do not cache an empty population. A transient source/load failure
        # must not permanently poison the Peak selector for the lifetime of
        # the API process.
        return {}
    per75=ERA_AVERAGE_PER75_PLAYOFF if is_playoff else ERA_AVERAGE_PER75_REGULAR
    lower={"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
    by_stat={st:[] for st in stats}
    raw_to_rate={
        "PTS_per75":"PTS_raw","FG_per75":"FG_raw","FGA_per75":"FGA_raw",
        "3P_per75":"3P_raw","3PA_per75":"3PA_raw","2P_per75":"2P_raw","2PA_per75":"2PA_raw",
        "FT_per75":"FT_raw","FTA_per75":"FTA_raw","ORB_per75":"ORB_raw","DRB_per75":"DRB_raw",
        "TRB_per75":"TRB_raw","AST_per75":"AST_raw","STL_per75":"STL_raw","BLK_per75":"BLK_raw",
        "TOV_per75":"TOV_raw","PF_per75":"PF_raw"}
    pct_defs={"FG_pct":("FG_raw","FGA_raw"),"2P_pct":("2P_raw","2PA_raw"),
              "3P_pct":("3P_raw","3PA_raw"),"FT_pct":("FT_raw","FTA_raw"),
              "FTr":("FTA_raw","FGA_raw"),"3PAr":("3PA_raw","FGA_raw"),"AST_TOV":("AST_raw","TOV_raw")}
    for w in windows:
        cand=w["frame"].copy()
        window_values={}
        for st in stats:
            # Resolve canonical aliases first.
            if st not in cand.columns:
                alias_col=col(cand, PLAYOFF_STAT_ALIASES.get(st,[st]))
                if alias_col: cand[st]=pd.to_numeric(cand[alias_col],errors="coerce")
            # Reconstruct missing volume/rate statistics from underlying raw
            # totals. This is particularly important for historical BLK/75 and
            # other statistics whose presentation column may be absent in an
            # older master row.
            if st in raw_to_rate and (st not in cand.columns or pd.to_numeric(cand[st],errors="coerce").isna().all()):
                rawc=col(cand,[raw_to_rate[st],raw_to_rate[st].replace("_raw","")])
                if rawc:
                    poss=col(cand,["Estimated_Player_Possessions","Estimated_Possessions","Player_Possessions","Possessions"])
                    wposs=pd.to_numeric(cand[poss],errors="coerce") if poss else pd.Series(np.nan,index=cand.index)
                    if wposs.isna().all() or not wposs.notna().any():
                        ptsc=col(cand,["PTS_raw","PTS","Points"]); p75c=col(cand,["PTS_per75","PTS/75"])
                        if ptsc and p75c:
                            pts=pd.to_numeric(cand[ptsc],errors="coerce"); p75=pd.to_numeric(cand[p75c],errors="coerce")
                            wposs=pts/(p75/75.0).replace(0,np.nan)
                    if wposs.isna().all() or not wposs.notna().any():
                        mpc=col(cand,["MP","Minutes","minutes"]); wposs=pd.to_numeric(cand[mpc],errors="coerce")*2.0 if mpc else wposs
                    raw=pd.to_numeric(cand[rawc],errors="coerce")
                    cand[st]=raw/(wposs/75.0).replace(0,np.nan)
            if st in pct_defs and (st not in cand.columns or pd.to_numeric(cand[st],errors="coerce").isna().all()):
                nc=col(cand,[pct_defs[st][0],pct_defs[st][0].replace("_raw","")]); dc=col(cand,[pct_defs[st][1],pct_defs[st][1].replace("_raw","")])
                if nc and dc:
                    cand[st]=pd.to_numeric(cand[nc],errors="coerce")/pd.to_numeric(cand[dc],errors="coerce").replace(0,np.nan)
            if st not in cand.columns: continue
            # A 5-Year Peak is five qualifying seasons for the selected
            # statistic, not merely five qualifying seasons for the player.
            # This prevents historically untracked stats such as Wilt's BLK
            # from producing a fake peak from one observed season. Every one
            # of the five seasons in the winning window must have a valid
            # underlying value for the selected statistic.
            stat_valid=pd.to_numeric(cand[st],errors="coerce").notna()
            if int(stat_valid.sum()) < FIVE_YEAR_PEAK_N:
                continue
            val=_era_average_statistic(cand,st,per75,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
            if pd.isna(val): continue
            # First calculate every available statistic on this exact window.
            # We intentionally defer row creation until the entire window has
            # been evaluated so each primary Peak row receives the COMPLETE
            # companion-value dictionary, not only the statistics encountered
            # earlier in REGULAR_STATS.
            window_values[st]=float(val)
        if window_values:
            all_values={k:float(v) for k,v in window_values.items() if pd.notna(v) and np.isfinite(float(v))}
            for st,val in window_values.items():
                item={k:w[k] for k in ("Player_ID","Player","Peak_Start_Year","Peak_End_Year","Peak_Era","Peak_Seasons")}
                item["_value_num"]=float(val)
                item["_all_stat_values"]=dict(all_values)
                by_stat[st].append(item)
    bundle={}
    for st,rows in by_stat.items():
        if not rows:
            bundle[st]=pd.DataFrame(columns=["Player_ID","Player","Peak_Start_Year","Peak_End_Year","Peak_Era","Peak_Seasons","_value_num"])
            continue
        df=pd.DataFrame(rows)
        higher=st not in lower
        df=df.sort_values("_value_num",ascending=not higher,kind="stable").drop_duplicates(["Player"],keep="first").reset_index(drop=True)
        bundle[st]=df
    usable=sum(1 for v in bundle.values() if isinstance(v,pd.DataFrame) and not v.empty)
    if usable:
        CACHE[key]=bundle
        if not is_playoff and not era:
            try:
                path=ROOT/"data"/"precomputed_5_year_peak"/"regular_big_board_peak_weighted_v6.pkl"
                path.parent.mkdir(parents=True,exist_ok=True)
                pd.to_pickle(bundle,path)
            except Exception:
                pass
    return bundle

def _five_year_peak_board(season_type="Regular Season", era=None, statistic=None, sort_direction="desc", search=None, limit=100, anchor_statistic=None):
    """Fast 5-Year Peak Big Board using a cached qualified-window population."""
    request_cache_key=f"__big_board_peak_v5__:{season_type}:{era or ''}:{statistic}:{sort_direction}:{search or ''}:{int(limit)}"
    if request_cache_key in CACHE: return CACHE[request_cache_key]
    is_playoff=str(season_type).casefold() in {"playoffs","playoff","postseason"}
    stat=statistic or "PTS_per75"
    windows=_five_year_peak_windows(season_type,era)
    if not windows:
        result={"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,"era":era or None,"statistic":stat}; CACHE[request_cache_key]=result; return result
    per75=ERA_AVERAGE_PER75_PLAYOFF if is_playoff else ERA_AVERAGE_PER75_REGULAR
    # Normal primary-stat requests use the all-stat bundle. It is built once
    # from the cached windows and makes later statistic switches effectively
    # instantaneous. Anchored companion requests retain their exact-window path.
    if not anchor_statistic:
        bundle=_five_year_peak_all_stat_values(season_type,era)
        base_df=bundle.get(stat,pd.DataFrame()).copy() if isinstance(bundle,dict) else pd.DataFrame()
        if not base_df.empty:
            df=base_df
            higher=stat not in {"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}
            vals=df["_value_num"]; ranks=vals.rank(method="average",ascending=not higher); n=len(vals)
            df["_pct"]=100.0 if n==1 else 100.0*(n-ranks)/(n-1)
            if search: df=df.loc[df["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
            df=df.sort_values("_value_num",ascending=not higher,kind="stable").head(int(limit)).reset_index(drop=True)
            out=[]
            for i,r in df.iterrows():
                labels=[str(x) for x in r["Peak_Seasons"]]
                years=[_season_end_year(x) for x in labels]
                skipped=[] if is_playoff else [_season_label_any(y) for y in range(min(years),max(years)+1) if y not in years]
                out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),"season":clean(r["Peak_Start_Year"]),"season_label":f'{labels[0]} → {labels[-1]}',"peak_seasons":labels,"skipped_seasons":skipped,"peak_era":clean(r["Peak_Era"]),"value":clean(r["_value_num"]),"percentile":clean(r["_pct"]),"companion_values":clean(r.get("_all_stat_values",{}))})
            result={"rows":out,"count":len(out),"scope":"five_year_peak","season_type":season_type,"era":era or None,"statistic":stat,"note":("Playoff 5-Year Peak = five consecutive qualifying playoff appearances, each ≥3 G and ≥75 MP, with ≥35 total games." if is_playoff else "Regular-season 5-Year Peak = five qualifying seasons within a maximum six-calendar-season span. One skipped/non-qualifying season is allowed; two consecutive skipped seasons are not. Each included season must meet ≥60% schedule participation and ≥1,400 minutes.")}
            CACHE[request_cache_key]=result
            return result
    # Companion requests are anchored to the primary statistic's winning
    # window for each player. This prevents a secondary value from silently
    # coming from a different five-year peak.
    selected_windows=windows
    if anchor_statistic and windows:
        anchor_cache_key=f"__big_board_peak_anchor_windows_v1__:{season_type}:{era or ''}:{anchor_statistic}"
        if anchor_cache_key in CACHE:
            selected_windows=CACHE[anchor_cache_key]
        else:
            anchor_rows=[]
            for w in windows:
                cand=w["frame"]
                if anchor_statistic not in cand.columns: continue
                av=_era_average_statistic(cand,anchor_statistic,per75,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
                if pd.isna(av): continue
                z={k:w[k] for k in ("Player_ID","Player","Peak_Start_Year","Peak_End_Year","Peak_Era","Peak_Seasons")}; z["_anchor_num"]=float(av); z["_frame"]=cand; anchor_rows.append(z)
            if anchor_rows:
                adf=pd.DataFrame(anchor_rows)
                ahigher=anchor_statistic not in {"TOV_per75","TOV_pct","DRtg","Relative_DRtg"}
                adf=adf.sort_values("_anchor_num",ascending=not ahigher,kind="stable").drop_duplicates(["Player"],keep="first")
                selected_windows=[{**{k:z[k] for k in ("Player_ID","Player","Peak_Start_Year","Peak_End_Year","Peak_Era","Peak_Seasons")},"frame":z["_frame"]} for z in adf.to_dict("records")]
                CACHE[anchor_cache_key]=selected_windows
    rows=[]
    for w in selected_windows:
        cand=w["frame"]
        if stat not in cand.columns: continue
        val=_era_average_statistic(cand,stat,per75,ERA_AVERAGE_ADDITIVE,ERA_AVERAGE_DENOMS)
        if pd.isna(val): continue
        item={k:w[k] for k in ("Player_ID","Player","Peak_Start_Year","Peak_End_Year","Peak_Era","Peak_Seasons")}; item["_value_num"]=float(val); rows.append(item)
    if not rows:
        result={"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,"era":era or None,"statistic":stat}; CACHE[request_cache_key]=result; return result
    df=pd.DataFrame(rows); lower={"TOV_per75","PF_per75","TOV_pct","DRtg","Relative_DRtg"}; higher=stat not in lower
    # One canonical peak per player: rank windows by the requested statistic and keep the best.
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").drop_duplicates(["Player"],keep="first")
    vals=df["_value_num"]; ranks=vals.rank(method="average",ascending=not higher); n=len(vals); df["_pct"]=100.0 if n==1 else 100.0*(n-ranks)/(n-1)
    if search: df=df.loc[df["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
    df=df.sort_values("_value_num",ascending=not higher,kind="stable").head(int(limit)).reset_index(drop=True)
    out=[]
    for i,r in df.iterrows():
        labels=[str(x) for x in r["Peak_Seasons"]]; years=[_season_end_year(x) for x in labels]; skipped=[]
        if not is_playoff:
            full=list(range(min(years),max(years)+1)); skipped=[_season_label_any(y) for y in full if y not in years]
        out.append({"rank":i+1,"player_id":clean(r["Player_ID"]),"player_name":clean(r["Player"]),"season":clean(r["Peak_Start_Year"]),"season_label":f'{labels[0]} → {labels[-1]}',"peak_seasons":labels,"skipped_seasons":skipped,"peak_era":clean(r["Peak_Era"]),"value":clean(r["_value_num"]),"percentile":clean(r["_pct"])})
    result={"rows":out,"count":len(out),"scope":"five_year_peak","season_type":season_type,"era":era or None,"statistic":stat,"note":("Playoff 5-Year Peak = five consecutive qualifying playoff appearances, each ≥3 G and ≥75 MP, with ≥35 total games." if is_playoff else "Regular-season 5-Year Peak = five qualifying seasons within a maximum six-calendar-season span. One skipped/non-qualifying season is allowed; two consecutive skipped seasons are not. Each included season must meet ≥60% schedule participation and ≥1,400 minutes.")}
    CACHE[request_cache_key]=result; return result

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
    # SDI boards consume the new formula layer directly. This prevents stale
    # precomputed files from reintroducing the retired playoff Impact / WOWY
    # formula.
    if is_playoff:
        sdi_index = _load_authoritative_playoff_sdi_v4()
    else:
        _sdi_path = ROOT/"local_api"/"cache"/"regular_sdi_v4_wowy_rts_player_seasons.csv"
        sdi_index = pd.read_csv(_sdi_path,low_memory=False) if _sdi_path.exists() else _load_regular_sdi_v4_player_seasons()
    sdi_year_col = _existing_season_column(sdi_index)

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
        d = sdi_index.copy() if sdi_index is not None else pd.DataFrame()
        if d.empty:
            return {"rows":[],"count":0,"scope":"single","season_type":season_type,
                    "statistic":"Statistical Dominance Index",
                    "note":"Authoritative SDI v4 formula layer is unavailable."}
        year_col=sdi_year_col
        if not year_col:
            return {"rows":[],"count":0,"scope":"single","season_type":season_type,"statistic":"Statistical Dominance Index","note":"SDI v4 source has no season/year column."}
        d["__year"]=pd.to_numeric(d[year_col].map(_season_end_year),errors="coerce")
        score_col="SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in d.columns) else "SDI_v4"
        d["__sdi_score"]=pd.to_numeric(d[score_col],errors="coerce")
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
            sdi_index["SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in sdi_index.columns) else "SDI_v4"],
            errors="coerce"
        ).dropna()
        if era:
            allraw=sdi_index.copy()
            ay=pd.to_numeric(allraw[year_col].map(_season_end_year),errors="coerce")
            allraw=allraw.loc[ay.map(_era_key).eq(str(era).strip())]
            score_col2="SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in allraw.columns) else "SDI_v4"
            allvals=pd.to_numeric(allraw[score_col2],errors="coerce").dropna()
        elif not historical:
            allraw=sdi_index.copy()
            ay=pd.to_numeric(allraw[year_col].map(_season_end_year),errors="coerce")
            score_col2="SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in allraw.columns) else "SDI_v4"
            allvals=pd.to_numeric(allraw.loc[ay.eq(int(target_year)),score_col2],errors="coerce").dropna()
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
                        "season":int(r["__year"]),
                        "season_label":_season_label_any(r["__year"]),
                        "statistic":"Statistical Dominance Index",
                        "value":clean(r["_value_num"]),
                        "percentile":clean(r["_pct"]),
                        "context":context,
                        "headshot_url":_headshot_url_for(clean(r["Player_ID"]),clean(r["Player"]))})
        years=sorted(pd.to_numeric(d["__year"],errors="coerce").dropna().astype(int).unique().tolist())
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
        # Always derive Career SDI from the active season formula layer so
        # changing top-level weights cannot leave a stale career composite.
        src=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
        if not src.empty:
            score_col="SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in src.columns) else "SDI_v4"
            src["__score"]=pd.to_numeric(src.get(score_col),errors="coerce")
            src["MP"]=pd.to_numeric(src.get("MP"),errors="coerce")
            src["G"]=pd.to_numeric(src.get("G"),errors="coerce")
            rows=[]
            for pid,g in src.groupby("Player_ID",dropna=False,sort=False):
                q=g.dropna(subset=["__score"]).copy()
                if q.empty: continue
                w=q["MP"].clip(lower=0).fillna(0)
                score=float((q["__score"]*w).sum()/w.sum()) if w.sum()>0 else float(q["__score"].mean())
                rows.append({"Player_ID":pid,"Player":str(q["Player"].iloc[0]),"Career_SDI_v4":score,"Qualifying_Seasons":int(len(q)),"Career_MP":float(w.sum())})
            d=pd.DataFrame(rows)
        else:
            d=pd.DataFrame()
        if d.empty:
            return {"rows":[],"count":0,"scope":"career","season_type":season_type,
                    "statistic":"Statistical Dominance Index"}
        # Retain the established career eligibility gate below.
        if False:
            src=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
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
        d["_value_num"]=pd.to_numeric(d["Career_SDI_v4"],errors="coerce")
        d=d.dropna(subset=["_value_num"]).copy()
        # Derive the career eligibility gate from the same authoritative
        # precomputed season-SDI source. This avoids legacy playoff source IDs
        # (which may legitimately differ from the canonical SDI IDs).
        seasons=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
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
        d=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
        if d.empty:
            return {"rows":[],"count":0,"scope":"era_average","season_type":season_type,
                    "statistic":"Statistical Dominance Index","era":era}
        d["__year"]=pd.to_numeric(d[year_col].map(_season_end_year),errors="coerce")
        d["G"]=pd.to_numeric(d["G"],errors="coerce").fillna(0)
        d["MP"]=pd.to_numeric(d["MP"],errors="coerce").fillna(0)
        score_col="SDI_v4_WOWY" if (not is_playoff and "SDI_v4_WOWY" in d.columns) else "SDI_v4"
        d["SDI_v4"]=pd.to_numeric(d[score_col],errors="coerce")
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
                era_max_games=float(d.groupby("__year")["G"].max().sum())
                era_max_minutes=float(d.groupby("__year")["MP"].max().sum())
                game_share=ERA_AVERAGE_PLAYOFF_GAME_SHARE if is_playoff else ERA_AVERAGE_REGULAR_GAME_SHARE
                minute_share=ERA_AVERAGE_PLAYOFF_MINUTE_SHARE if is_playoff else ERA_AVERAGE_REGULAR_MINUTE_SHARE
                if participation+1e-12 < ERA_AVERAGE_PARTICIPATION or (games/era_max_games if era_max_games else 0)<game_share or (minutes/era_max_minutes if era_max_minutes else 0)<minute_share:
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
            src=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
            src["__year"]=pd.to_numeric(src[_existing_season_column(src)].map(_season_end_year),errors="coerce")
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
        if is_playoff:
            src=sdi_index.copy() if sdi_index is not None else pd.DataFrame()
            if src.empty:
                return {"rows":[],"count":0,"scope":"five_year_peak","season_type":season_type,
                        "statistic":"Statistical Dominance Index"}
            src["__year"]=pd.to_numeric(src[_existing_season_column(src)].map(_season_end_year),errors="coerce")
            src["__score"]=pd.to_numeric(src["SDI_v4"],errors="coerce")
            src["__g"]=pd.to_numeric(src["G"],errors="coerce").fillna(0)
            src["__mp"]=pd.to_numeric(src["MP"],errors="coerce").fillna(0)
            rows=[]
            for pid,g in src.groupby("Player_ID",dropna=False,sort=False):
                g=g.sort_values("__year").drop_duplicates("__year",keep="first")
                q=g.loc[g["__g"].ge(3)&g["__mp"].ge(75)].copy()
                if q.empty: continue
                years=q["__year"].astype(int).tolist()
                for i in range(max(0,len(years)-4)):
                    cand=q.iloc[i:i+5]
                    if len(cand)!=5: continue
                    if cand["__year"].iloc[-1]-cand["__year"].iloc[0]>4: continue
                    if float(cand["__g"].sum())<35: continue
                    if era and _era_key(int(cand["__year"].iloc[0]))!=str(era).strip(): continue
                    w=cand["__mp"].clip(lower=0); score=float((cand["__score"]*w).sum()/w.sum()) if w.sum()>0 else float(cand["__score"].mean())
                    rows.append({"Player_ID":clean(pid),"Player":str(cand["Player"].iloc[0]),"Peak_Start_Year":int(cand["__year"].iloc[0]),"Peak_End_Year":int(cand["__year"].iloc[-1]),"_value_num":score})
            return _finish_sdi(pd.DataFrame(rows),"five_year_peak","5-Year Peak","Historical")
        p=ROOT/"data"/"precomputed_5_year_peak"/"regular_profile_peaks_authoritative_v10.csv"
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
                  season_type="Regular Season", era=None, companion=False, anchor_statistic=None):
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
        if str(statistic or "").strip().casefold() == "ast_tov" and str(season_type).casefold() not in {"playoffs","playoff","postseason"}:
            rows=_regular_ast_tov_big_board(season="Career", context="Career", sort_direction=sort_direction, search=search, limit=limit, era=None, career=True)
            return {"seasons":[],"season_options":[{"value":"Career","label":"Career"}],"season":"Career","historical_scope":False,"career_scope":True,"context":"Career","statistic":"AST_TOV","rows":rows,"count":len(rows),"season_type":"Regular Season"}
        if str(season_type).casefold() in {"playoffs","playoff","postseason"}:
            return api_playoff_big_board(
                season="Career", context=context, statistic=statistic,
                sort_direction=sort_direction, search=search, limit=limit,
                scope="career", era=era
            )
        # WOWY career boards use the canonical career table and its shared
        # eligibility/companion-value contract.
        # Career uses the same response contract as Single Season and Era Average:
        # build the canonical career rows first, then return those rows directly.
        rows=_regular_career_big_board(statistic,sort_direction,search,limit)
        return {"seasons":[],"season_options":[{"value":"Career","label":"Career"}],
                "season":"Career","historical_scope":False,"career_scope":True,
                "context":"Career","statistic":statistic,"rows":rows,
                "count":len(rows),"season_type":"Regular Season"}
    if scope_key in {"five_year_peak","5-year peak","5 year peak","5year_peak","peak"}:
        return _five_year_peak_board(season_type,era,statistic,sort_direction,search,limit,anchor_statistic)
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

    # WOWY has an audited raw-value + seasonal-percentile layer. Rank WOWY
    # Big Boards by the actual WOWY value, not by a percentile column whose
    # orientation can differ between historical/single-season populations.
    # This is especially important for Historical Percentile scope: a 2009
    # LeBron value must outrank a lower 1979 Kareem value when the requested
    # statistic is WOWY Net.
    if str(statistic or "").strip() in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}:
        w=_load_wowy_stat_layer().copy()
        if w.empty:
            return {"rows":[],"count":0,"scope":scope,"season_type":season_type,"statistic":statistic}
        stat=str(statistic).strip()
        value_col=stat
        pct_col_name=f"{stat}_Percentile"
        w["__value"]=pd.to_numeric(w[value_col],errors="coerce")
        w=w.dropna(subset=["__value"]).copy()
        # Preserve the audited qualification population. Handle textual CSV
        # booleans explicitly; astype(bool) would incorrectly treat "False"
        # as true.
        if "PER75_Qualified" in w.columns:
            q=w["PER75_Qualified"]
            mask=q.astype(str).str.strip().str.casefold().isin({"1","true","yes","y","t"})
            if pd.api.types.is_bool_dtype(q): mask=q.fillna(False)
            w=w.loc[mask].copy()
        requested=str(season or "").strip()
        historical=requested.casefold() in {"","historical","historical percentile","all","all seasons"}
        if not historical:
            target=_season_end_year(requested)
            if target is not None: w=w.loc[w["Season"].map(_season_end_year).eq(int(target))].copy()
        if era: w=w.loc[w["Season"].map(_era_key).eq(str(era).strip())].copy()
        if search: w=w.loc[w["Player"].astype(str).str.contains(str(search),case=False,na=False)].copy()
        # Higher WOWY values are always better. Percentile is derived from the
        # same raw-value population so it cannot disagree with the displayed rank.
        w=w.sort_values("__value",ascending=(sort_direction=="asc"),kind="stable")
        allvals=w["__value"].copy()
        ranks=allvals.rank(method="average",ascending=False); n=len(allvals)
        pctmap={}
        for v in allvals.unique():
            rv=float(ranks[allvals.eq(v)].iloc[0])
            pctmap[v]=100.0 if n<=1 else 100.0*(n-rv)/(n-1)
        w["__pct"]=w["__value"].map(pctmap)
        w=w.head(int(limit)).reset_index(drop=True)
        rows=[]
        for i,r in w.iterrows():
            rows.append({"rank":i+1,"player_id":clean(r.get("Player_ID")),"player_name":clean(r.get("Player")),
                         "season":clean(r.get("Season")),"season_label":season_display_label(r.get("Season")),
                         "statistic":stat,"value":clean(r["__value"]),"percentile":clean(r["__pct"]),
                         "context":"Historical" if historical else context,
                         "headshot_url":_headshot_url_for(clean(r.get("Player_ID")),clean(r.get("Player")))})
        return {"seasons":[],"season_options":[],"season":"Historical Percentile" if historical else requested,
                "historical_scope":historical,"career_scope":False,"context":"Historical" if historical else context,
                "statistic":stat,"rows":rows,"count":len(rows),"season_type":season_type,"era":era or None}

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
    # The percentile layer can omit seasons that have no qualified percentile
    # rows. The selector, however, represents the complete historical season
    # universe. Union it with the canonical regular-season source so every
    # season appears on the initial render.
    if str(season_type).casefold().startswith("regular"):
        try:
            master=load_master_seasons()
            mc=col(master,["Season","season","Season_ID"])
            if mc:
                raw_seasons.extend(master[mc].dropna().astype(str).str.strip().unique().tolist())
        except Exception:
            pass
    raw_seasons=list(dict.fromkeys(raw_seasons))
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
        # WOWY career boards use the audited WOWY season layer directly.  This
        # preserves the established 400-game / 10,000-minute career eligibility
        # gate and avoids depending on the regular career CSV to carry WOWY
        # columns.
        if str(statistic or "").strip() in {"WOWY_Offense","WOWY_Defense","WOWY_Net"}:
            w=_load_wowy_stat_layer().copy()
            stat=str(statistic).strip()
            if not w.empty and stat in w.columns:
                w["__value"]=pd.to_numeric(w[stat],errors="coerce")
                w["__mp"]=pd.to_numeric(w["MP"],errors="coerce").fillna(0) if "MP" in w.columns else pd.Series(0.0,index=w.index)
                w["__g"]=pd.to_numeric(w["G"],errors="coerce").fillna(0) if "G" in w.columns else pd.Series(0.0,index=w.index)
                if "PER75_Qualified" in w.columns:
                    q=w["PER75_Qualified"]
                    mask=q.fillna(False) if pd.api.types.is_bool_dtype(q) else q.astype(str).str.strip().str.casefold().isin({"1","true","yes","y","t"})
                    w=w.loc[mask].copy()
                rows_w=[]
                for pid,g in w.groupby("Player_ID",dropna=False,sort=False):
                    g=g.dropna(subset=["__value"])
                    games=float(g["__g"].sum()); minutes=float(g["__mp"].sum())
                    if g.empty or games<400 or minutes<10000: continue
                    den=minutes
                    val=float((g["__value"]*g["__mp"]).sum()/den) if den>0 else float(g["__value"].mean())
                    pname=str(g["Player"].iloc[0]) if "Player" in g.columns else str(pid)
                    rows_w.append({"player_id":clean(pid),"player_name":clean(pname),"season":"Career","season_label":"Career","statistic":stat,"value":val})
                d=pd.DataFrame(rows_w)
                if not d.empty:
                    d=d.sort_values("value",ascending=(sort_direction=="asc"),kind="stable").reset_index(drop=True)
                    ranks=d["value"].rank(method="average",ascending=False); n=len(d)
                    d["percentile"]=100.0 if n<=1 else 100.0*(n-ranks)/(n-1)
                    d=d.head(int(limit))
                    rows_w_out=[]
                    for i,r in d.iterrows():
                        rows_w_out.append({**r.to_dict(),"rank":i+1,"headshot_url":_headshot_url_for(r["player_id"],r["player_name"])})
                    rows=rows_w_out
                else:
                    rows=[]
            else:
                rows=[]
        elif str(statistic or "").strip().casefold() == "ast_tov":
            rows=_regular_ast_tov_big_board(career=True, sort_direction=sort_direction,
                                            search=search, limit=limit)
        else:
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


def _comparison_merge_wowy(source):
    """Ensure comparison season rows carry canonical individual WOWY values.

    Comparison sources can predate the first-class WOWY layer. Merge by the
    same normalized player/season keys used elsewhere in the website so the
    comparison UI receives real WOWY values instead of nulls.
    """
    if source is None or source.empty:
        return source
    needed={"WOWY_Offense","WOWY_Defense","WOWY_Net"}
    if needed.issubset(set(source.columns)):
        return source
    w=_load_wowy_stat_layer()
    if w is None or w.empty:
        return source
    pcol=col(source,["Player","Player_Name","Display_Name","player_name","Name"])
    scol=col(source,["Season","season","Season_ID","SeasonEndYear","Season_End_Year"])
    if not pcol or not scol:
        return source
    out=source.copy()
    out["__cmp_wowy_name"]=out[pcol].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
    out["__cmp_wowy_season"]=out[scol].map(_season_label_any)
    wm=w.copy()
    if "__name_key" not in wm.columns:
        wm["__name_key"]=wm["Player"].astype(str).str.replace(r"\*+","",regex=True).str.strip().str.casefold()
    if "__season_key" not in wm.columns:
        wm["__season_key"]=wm["Season"].map(_season_label_any)
    cols=[c for c in ["__name_key","__season_key","WOWY_Offense","WOWY_Defense","WOWY_Net"] if c in wm.columns]
    if len(cols)<5:
        return out.drop(columns=["__cmp_wowy_name","__cmp_wowy_season"],errors="ignore")
    wm=wm[cols].drop_duplicates(["__name_key","__season_key"],keep="first")
    out=out.merge(wm,left_on=["__cmp_wowy_name","__cmp_wowy_season"],right_on=["__name_key","__season_key"],how="left",suffixes=("","__cmp_wowy"))
    for stat in needed:
        alt=f"{stat}__cmp_wowy"
        if stat not in out.columns and alt in out.columns:
            out[stat]=out[alt]
        elif alt in out.columns:
            base=pd.to_numeric(out[stat],errors="coerce") if stat in out.columns else pd.Series(np.nan,index=out.index)
            altv=pd.to_numeric(out[alt],errors="coerce")
            out[stat]=base.where(base.notna(),altv)
    return out.drop(columns=["__cmp_wowy_name","__cmp_wowy_season","__name_key","__season_key"]+[f"{x}__cmp_wowy" for x in needed],errors="ignore")


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
    # The regular-season profile source contains both regular-season and playoff
    # rows. Compare must isolate the requested season type before selecting
    # player-season rows; otherwise a single regular-season season can be
    # accidentally averaged with that player's playoff row from the same year.
    # Player Profile already applies this separation, so Compare must use the
    # same canonical season-type boundary.
    if not is_playoffs and source is not None and not source.empty:
        _cmp_st_col=col(source,["Season_Type","season_type","SeasonType","Phase"])
        if _cmp_st_col:
            _cmp_playoff_labels={"playoffs","playoff","postseason"}
            source=source.loc[~source[_cmp_st_col].astype(str).str.strip().str.casefold().isin(_cmp_playoff_labels)].copy()
    # WOWY is a first-class comparison statistic but older comparison sources
    # may not contain its columns. Merge the canonical layer before selecting
    # player seasons so regular and playoff comparisons use the same contract.
    source = _comparison_merge_wowy(source)
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
    ("Opp eFG%","Opp_eFG_pct","higher"),
]

def _norm_col(s):
    return re.sub(r"[^a-z0-9]","",str(s).lower())

def _find_col(cols, names):
    mp={_norm_col(c):c for c in cols}
    for n in names:
        if _norm_col(n) in mp:return mp[_norm_col(n)]
    return None

_TEAM_OFFENSIVE_FOUR_FACTORS_CACHE = None

def _team_name_key(v):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(v).replace("*", "").lower()).strip())

def _load_offensive_four_factor_overrides():
    """Load the canonical offensive eFG%/TOV% team-season values supplied by the user.

    This is a dedicated override layer: it supplies ONLY offensive eFG% and TOV%.
    Existing team analytics sources continue to provide opponent/defensive fields,
    ratings, pace, logos, etc. No BRef request is needed for these two fields.
    """
    global _TEAM_OFFENSIVE_FOUR_FACTORS_CACHE
    if _TEAM_OFFENSIVE_FOUR_FACTORS_CACHE is not None:
        return _TEAM_OFFENSIVE_FOUR_FACTORS_CACHE
    candidates=[
        Path(__file__).resolve().parent/"data"/"nba_per75_team_master.csv",
        Path(__file__).resolve().parents[1]/"data"/"nba_per75_team_master.csv",
    ]
    out={}
    for path in candidates:
        if not path.exists():
            continue
        try:
            h=pd.read_csv(path,nrows=0,low_memory=False)
            cols=list(h.columns)
            tc=_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"])
            sc=_find_col(cols,["Season","season"])
            stc=_find_col(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"])
            ec=_find_col(cols,["eFG_pct","eFG%","EFG_PCT"])
            tv=_find_col(cols,["TOV_pct","TOV%","TOV_PCT"])
            if not (tc and sc and ec and tv):
                continue
            use=[x for x in [tc,sc,stc,ec,tv] if x]
            d=pd.read_csv(path,usecols=use,low_memory=False)
            for _,row in d.iterrows():
                team=_team_name_key(row.get(tc))
                season=str(row.get(sc)).strip()
                st=str(row.get(stc)).strip() if stc else "Regular Season"
                if not team or not season:
                    continue
                try: efg=float(row.get(ec))
                except Exception: efg=None
                try: tov=float(row.get(tv))
                except Exception: tov=None
                if not (np.isfinite(efg) if efg is not None else False): efg=None
                if not (np.isfinite(tov) if tov is not None else False): tov=None
                if efg is None and tov is None:
                    continue
                # The supplied file stores eFG% as a fraction (e.g. .424)
                # and TOV% as percentage points (e.g. 14.5). Normalize only
                # the representation, not the underlying statistic.
                if efg is not None and abs(efg) <= 1.5: efg=efg
                if tov is not None and abs(tov) <= 1.5: tov=tov*100.0
                out[(st,season,team)]={"efgpct":efg,"tovpct":tov}
            if out:
                break
        except Exception:
            continue
    _TEAM_OFFENSIVE_FOUR_FACTORS_CACHE=out
    return out

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
        0 if p.name.lower() in ("nba_per75_team_master.csv", "nba_per75_team_master_enriched.csv") else (
            1 if any(x in p.name.lower() for x in ("team_seasons_v1","team_season","team_data")) else 2
        ),
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
    # Resolve duplicate Four-Factor headers by preserving their physical
    # order.  Some Basketball-Reference exports contain two columns named
    # eFG% and TOV%; pandas suffixes the second copies as .1.  The first copy
    # is offense and the second copy is defense/opponent.  The generic
    # normalized-column resolver can otherwise select the .1 copy for both.
    def _first_col(names):
        wanted={_norm_col(n) for n in names}
        for col in cols:
            if _norm_col(col) in wanted:
                return col
        return None
    def _first_matching(pred):
        for col in cols:
            if pred(_norm_col(col), str(col).lower()):
                return col
        return None
    def _duplicate_four_factor(base_names):
        # Prefer an explicitly labeled opponent/defensive column.
        explicit=_first_matching(lambda n,raw: ("opp" in n or "opponent" in n or "def" in n or "defensive" in n) and any(x in n for x in ("efg","tov")))
        if explicit is not None:
            return explicit
        # Otherwise select the second physical occurrence of the base header
        # (e.g. eFG% -> eFG%.1, TOV% -> TOV%.1).
        wanted={_norm_col(n) for n in base_names}
        seen=0
        for col in cols:
            if _norm_col(col) in wanted or any(_norm_col(col)==f"{x}1" for x in wanted):
                if _norm_col(col) in wanted:
                    seen += 1
                    if seen==2:
                        return col
                elif _norm_col(col).endswith("1"):
                    return col
        return None

    mapping={
        "team":_find_col(cols,["Team","Team_Abbreviation","TeamAbbreviation","Tm","Team_Name"]),
        "season":_find_col(cols,["Season","season"]),
        "season_type":_find_col(cols,["Season_Type","SeasonType","Season Type","Type","League_Type"]),
        "ortg":_find_col(cols,["ORtg","ORTG","OffRtg","Offensive_Rating","OffensiveRating"]),
        "drtg":_find_col(cols,["DRtg","DRTG","DefRtg","Defensive_Rating","DefensiveRating"]),
        "pace":_find_col(cols,["Pace","PACE"]),
        "rpace":_find_col(cols,["rPace","RPace","Relative_Pace","RelativePace"]),
        # Offensive counting inputs are used to reconstruct eFG%/TOV% when
        # an imported table has ambiguous or misordered duplicate Four-Factor columns.
        "fgm":_find_col(cols,["FG","FGM","FGM_raw","FG_made","Field Goals Made","Field_Goals_Made"]),
        "fga":_find_col(cols,["FGA","FGA_raw","Field Goal Attempts","Field_Goal_Attempts"]),
        "threepm":_find_col(cols,["3P","3PM","3PM_raw","3P_made","Three Pointers Made","Three_Pointers_Made"]),
        "threepa":_find_col(cols,["3PA","Three Point Attempts"]),
        "tov":_find_col(cols,["TOV","TOV_raw","Turnovers","Turnovers_raw"]),
        "fta":_find_col(cols,["FTA","FTA_raw","Free Throw Attempts","Free_Throw_Attempts"]),
        "pts":_find_col(cols,["PTS","Points"]),
        "rortg":_find_col(cols,["rORtg","rORTG","Relative_ORtg","Relative_ORTG"]),
        "rdrtg":_find_col(cols,["rDRtg","rDRTG","Relative_DRtg","Relative_DRTG"]),
        "nrtg":_find_col(cols,["NRtg","NRTG","Net_Rtg","NetRtg","NetRating"]),
        "tspct":_find_col(cols,["TS_pct","TS%","TS_PCT"]),
        "efgpct":_first_col(["eFG_pct","eFG%","EFG_PCT"]),
        "threepar":_find_col(cols,["3PAr","3PA_rate","ThreePA_Rate"]),
        "tovpct":_first_col(["TOV_pct","TOV%","TOV_PCT"]),
        "orbpct":_find_col(cols,["ORB_pct","ORB%","ORB_PCT"]),
        "ftr":_find_col(cols,["FTr","FT_Rate","FTR"]),
        "logo_id":_find_col(cols,["Logo_ID","LogoID","logo_id"]),
        "logo_file":_find_col(cols,["Logo_File","LogoFile","logo_file"]),
        "logo_source":_find_col(cols,["Logo_Source","LogoSource","logo_source"]),
        "wins":_find_col(cols,["W","Wins","Win","Playoff_Wins"]),
        "losses":_find_col(cols,["L","Losses","Loss","Playoff_Losses"]),
        "seed":_find_col(cols,["Seed","seed","Playoff_Seed"]),
        "rk":_find_col(cols,["Rk","RK","Rank"]),
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
        "opp_fgm":_find_col(cols,["Opp_FG","Opp_FGM","Opponent_FG","Opponent_FGM","Opponent Field Goals Made"]),
        "opp_fga":_find_col(cols,["Opp_FGA","Opponent_FGA","Opponent Field Goal Attempts"]),
        "opp_threepm":_find_col(cols,["Opp_3P","Opp_3PM","Opponent_3P","Opponent_3PM","Opponent Three Pointers Made"]),
        "opp_tov":_find_col(cols,["Opp_TOV","Opponent_TOV","Opponent Turnovers"]),
        "opp_fta":_find_col(cols,["Opp_FTA","Opponent_FTA","Opponent Free Throw Attempts"]),
    }
    # Never allow a defensive four-factor field to silently alias the
    # offensive field. If a source export flattened duplicate headers and the
    # resolver picked the same column, force it to be recovered from the
    # dedicated defensive column/cache instead.
    if mapping.get("opp_tovpct") == mapping.get("tovpct"):
        mapping["opp_tovpct"] = None
    if mapping.get("opp_efgpct") == mapping.get("efgpct"):
        mapping["opp_efgpct"] = None
    # If the explicit opponent resolver above did not find a named column,
    # recover the second physical Four-Factor copy.
    if not mapping["opp_tovpct"]:
        mapping["opp_tovpct"]=_duplicate_four_factor(["TOV_pct","TOV%","TOV_PCT"])
    if not mapping["opp_efgpct"]:
        mapping["opp_efgpct"]=_duplicate_four_factor(["eFG_pct","eFG%","EFG_PCT"])
    return mapping


def _num(v):
    try:
        if isinstance(v,str):
            t=v.strip().replace(",","")
            if t.endswith("%"):
                x=float(t[:-1])/100.0
            else:
                x=float(t)
        else:
            x=float(v)
        return None if not np.isfinite(x) else x
    except Exception:return None

def _coerce_percent_series(series):
    # Accept numeric percentages, fractions, and strings such as "54.8%".
    def cv(v):
        if isinstance(v,str):
            t=v.strip().replace(",","")
            if t.endswith("%"):
                try:return float(t[:-1])
                except Exception:return np.nan
        try:return float(v)
        except Exception:return np.nan
    return series.map(cv)

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
                d[colname]=_coerce_percent_series(d[colname])

        # If an imported source flattened duplicate Four-Factor columns and
        # still leaves the opponent fields unavailable, recover them from the
        # dedicated Basketball-Reference defensive Four Factors cache when it
        # exists. Never substitute the offensive eFG%/TOV% values.
        # Authoritative Basketball-Reference Four Factors cache. This cache
        # contains the distinct OFFENSE and DEFENSE columns from the source
        # table, so the team master cannot accidentally swap/duplicate eFG% or
        # TOV% when pandas has suffixed duplicate headers.
        bref_ff_path=Path(__file__).resolve().parent/"cache"/"bref_team_four_factors_v2.json"
        try:
            bref_ff=json.loads(bref_ff_path.read_text(encoding="utf-8")) if bref_ff_path.exists() else {"seasons":{}}
        except Exception:
            bref_ff={"seasons":{}}
        bref_cache_path=Path(__file__).resolve().parent/"cache"/"bref_team_defense_four_factors_v1.json"
        try:
            bref_cache=json.loads(bref_cache_path.read_text(encoding="utf-8")) if bref_cache_path.exists() else {"seasons":{}}
        except Exception:
            bref_cache={"seasons":{}}
        def _bref_team_key(v):
            return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",str(v).replace("*","")).strip().lower())

        offensive_ff_overrides={}
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

            # Explicit canonical offensive Four-Factor integration. The supplied
            # team master is authoritative for offensive eFG% and TOV%; merge those
            # values by season/team without replacing any defensive/opponent fields.
            _off=offensive_ff_overrides.get((requested,str(se),_team_name_key(tm)))
            if _off:
                if _off.get("efgpct") is not None:
                    r["efgpct"]=_off["efgpct"]
                if _off.get("tovpct") is not None:
                    r["tovpct"]=_off["tovpct"]

            # Reconstruct ALL offensive Four-Factor inputs from the team's
            # own counting stats whenever possible. This is deliberately
            # authoritative: duplicate Basketball-Reference headers can be
            # suffixed by pandas and a positional resolver must never turn
            # the defensive copy into the team's offensive value.
            # If raw counting inputs are unavailable but the canonical source
            # already contains a valid offensive percentage, preserve it.
            for _k in ("efgpct","tovpct","ftr"):
                if _k in r and _num(r.get(_k)) is not None:
                    r[_k]=_num(r.get(_k))
            try:
                fgm=float(r.get("fgm")); fga=float(r.get("fga")); threepm=float(r.get("threepm"))
                if fga>0: r["efgpct"]=(fgm+0.5*threepm)/fga
            except Exception: pass
            try:
                tov=float(r.get("tov")); fga=float(r.get("fga")); fta=float(r.get("fta"))
                den=fga+0.44*fta+tov
                if den>0: r["tovpct"]=tov/den
            except Exception: pass
            try:
                threepa=float(r.get("threepa")); fga=float(r.get("fga"))
                if fga>0: r["threepar"]=threepa/fga
            except Exception: pass
            # Do not derive FTr when BRef Four Factors is available. The
            # canonical Teams table had a mislabeled/defensive FTr value, so
            # BRef's explicit OFFENSE FTr is authoritative. Keep the local
            # formula only as a fallback for genuinely missing BRef data.
            if r.get("ftr") is None:
                try:
                    fta=float(r.get("fta")); fga=float(r.get("fga"))
                    if fga>0: r["ftr"]=fta/fga
                except Exception: pass
            try:
                pts=float(r.get("pts")); fga=float(r.get("fga")); fta=float(r.get("fta"))
                den=2*(fga+0.44*fta)
                if den>0: r["tspct"]=pts/den
            except Exception: pass

            # OFFENSIVE eFG% and TOV% come directly from the canonical team
            # master when those columns are present. Do NOT replace them from
            # the BRef Four Factors cache. The uploaded canonical team master
            # explicitly contains the offensive eFG% and TOV% columns, while
            # the existing opponent fields are already authoritative. This
            # prevents the defensive Four Factors from ever being substituted
            # into the offensive columns.
            #
            # BRef is retained only as an opponent-field fallback for seasons
            # where the existing opponent source is genuinely missing.
            ff=bref_ff.get("seasons",{}).get(f"{requested}|{se}",{}).get(_bref_team_key(tm),{})
            bref=bref_cache.get("seasons",{}).get(f"{requested}|{se}",{}).get(_bref_team_key(tm),{})
            # Once a verified BRef Four Factors row exists, its OFFENSIVE
            # eFG% and TOV% are authoritative. This deliberately overrides
            # any ambiguous/mislabeled team-master percentage columns.
            if ff.get("efgpct") is not None:
                r["efgpct"]=float(ff["efgpct"])
            if ff.get("tovpct") is not None:
                r["tovpct"]=float(ff["tovpct"])
            if ff.get("ftr") is not None:
                r["ftr"]=float(ff["ftr"])
            if r.get("opp_efgpct") is None and bref.get("opp_efgpct") is not None:
                r["opp_efgpct"]=float(bref["opp_efgpct"])
            if r.get("opp_tovpct") is None and bref.get("opp_tovpct") is not None:
                r["opp_tovpct"]=float(bref["opp_tovpct"])

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

        # Preserve canonical relative ratings from the team master whenever
        # present. Only derive them when the source genuinely lacks the field.
        by={}
        for r in rows: by.setdefault(r["season"],[]).append(r)
        for rs in by.values():
            ov=[r["ortg"] for r in rs if r.get("ortg") is not None]
            dv=[r["drtg"] for r in rs if r.get("drtg") is not None]
            pv=[r["pace"] for r in rs if r.get("pace") is not None]
            mo=sum(ov)/len(ov) if ov else None
            md=sum(dv)/len(dv) if dv else None
            mp=sum(pv)/len(pv) if pv else None
            for r in rs:
                r["nrtg"]=r["ortg"]-r["drtg"]
                if r.get("rortg") is None and mo is not None:r["rortg"]=r["ortg"]-mo
                if r.get("rdrtg") is None and md is not None:r["rdrtg"]=r["drtg"]-md
                if r.get("rpace") is None and mp is not None:r["rpace"]=r["pace"]-mp

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
        "version":26,
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
    def _clean_cache_json(v):
        if isinstance(v, dict): return {k:_clean_cache_json(x) for k,x in v.items()}
        if isinstance(v, list): return [_clean_cache_json(x) for x in v]
        if isinstance(v, float) and not np.isfinite(v): return None
        return v
    payload=_clean_cache_json(payload)
    TEAM_ANALYTICS_CACHE.write_text(json.dumps(payload,separators=(",",":"),allow_nan=False),encoding="utf-8")
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
            if p.get("version")==26 and p.get("season_types"):
                return p
        except Exception:
            pass
    return _build_team_analytics_cache()



_TEAM_STAT_KEY_MAP = {
    "rDRtg":"rdrtg","rORtg":"rortg","NRtg":"nrtg","Pace":"pace","rPace":"rpace",
    "ORtg":"ortg","DRtg":"drtg","TS%":"tspct",
    "eFG%":"efgpct","3PAr":"threepar","TOV%":"tovpct","ORB%":"orbpct","FTr":"ftr","Opp TOV%":"opp_tovpct","Opp eFG%":"opp_efgpct",
    "rdrtg":"rdrtg","rortg":"rortg","nrtg":"nrtg","pace":"pace","rpace":"rpace","ortg":"ortg","drtg":"drtg",
    "tspct":"tspct","efgpct":"efgpct","threepar":"threepar",
    "tovpct":"tovpct","orbpct":"orbpct","ftr":"ftr","opp_tovpct":"opp_tovpct","opp_efgpct":"opp_efgpct"
}
_TEAM_DISPLAY_STATS = [
    ("rDRtg","Relative DRtg","lower"),("rORtg","Relative ORtg","higher"),
    ("NRtg","NRtg","higher"),("Pace","Pace","higher"),("rPace","Relative Pace","higher"),("ORtg","ORtg","higher"),
    ("DRtg","DRtg","lower"),("TS%","TS%","higher"),
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
    # Clamp the result because midpoint tie handling can otherwise produce
    # values just above 100 when several teams share the maximum/minimum.
    if higher:
        raw=float((vals < x).sum() + 0.5*(vals == x).sum()) / float(len(vals)-1) * 100.0
    else:
        raw=float((vals > x).sum() + 0.5*(vals == x).sum()) / float(len(vals)-1) * 100.0
    return max(0.0,min(100.0,raw))

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
    # Some team statistics did not exist as recorded statistics in the
    # early NBA. The analytics source can contain backfilled/derived values,
    # but the Team Profile should not present those metrics for seasons before
    # their historical recording began. Keep this gate limited to the profile
    # presentation layer so the underlying team analytics data remains intact.
    season_end=_season_end_year(target_season)
    # Basketball-Reference's NBA team Advanced/Four Factors tables begin in
    # 1973-74 for TS%, eFG%, TOV%, ORB%, FTr and their defensive counterparts.
    # Three-point rate begins with the 1979-80 three-point era. Do not expose
    # later-recorded statistics on earlier team profiles even when a source
    # contains a backfilled/derived value.
    # Build a single consistent profile layer from RELATIVE team-season
    # statistics. Relative values are percentage-point / rating-point
    # differences from that season's league/team-season mean. Their
    # percentiles are historical across all qualified team-seasons.
    season_population=populations["season"]
    historical_population=populations["historical"]
    # Team Profile is intentionally built from relative team-season values.
    # Relative ORtg/DRtg/Pace and the relative Four Factors are each measured
    # against the team's season-wide team population mean, then percentile
    # ranked historically across the corresponding relative values. NRtg is
    # retained as a raw impact statistic with a historical percentile.
    rel_defs=[
        ("rORtg","Relative ORtg","ortg","higher"),
        ("rDRtg","Relative DRtg","drtg","lower"),
        ("rPace","Relative Pace","pace","higher"),
        ("rTS%","Relative TS%","tspct","higher"),
        ("reFG%","Relative eFG%","efgpct","higher"),
        ("r3PAr","Relative 3PAr","threepar","higher"),
        ("rFTr","Relative FTr","ftr","higher"),
        ("rTOV%","Relative TOV%","tovpct","lower"),
        ("rORB%","Relative ORB%","orbpct","higher"),
        ("rOpponent TOV%","Relative Opponent TOV%","opp_tovpct","higher"),
        ("rOpponent eFG%","Relative Opponent eFG%","opp_efgpct","lower"),
    ]
    profile_relative=[]
    # Cache each season mean once so profile requests remain cheap.
    season_means={}
    historical_rel_pop={k:[] for k,_,_,_ in rel_defs}
    for rs in historical_population:
        hs=str(rs.get("season") or "")
        season_means.setdefault(hs,{})
    for hs in list(season_means):
        hp=[rr for rr in historical_population if str(rr.get("season") or "")==hs]
        for key,label,raw,direction in rel_defs:
            vals=[_num(rr.get(raw)) for rr in hp]
            vals=[v for v in vals if v is not None]
            season_means[hs][raw]=(sum(vals)/len(vals)) if vals else None
    for rr in historical_population:
        hs=str(rr.get("season") or "")
        means=season_means.get(hs,{})
        for key,label,raw,direction in rel_defs:
            x=_num(rr.get(raw)); m=means.get(raw)
            if x is not None and m is not None:
                delta=x-m
                if key in {"rTS%","reFG%","r3PAr","rFTr","rTOV%","rORB%","rOpponent TOV%","rOpponent eFG%"}:
                    # Canonical team exports are mixed historically: some
                    # percentage fields are stored as fractions (0.2766),
                    # while others are already percentage points (27.66).
                    # Convert to percentage points only when the underlying
                    # values are fractional. Otherwise a normal +2.766-point
                    # ORB% difference would incorrectly become +276.6%.
                    if max(abs(x), abs(m)) <= 1.5:
                        delta *= 100.0
                historical_rel_pop[key].append(delta)

    for key,label,raw,direction in rel_defs:
        value=_num(row.get(raw))
        mean=season_means.get(target_season,{}).get(raw)
        rel_value=(value-mean) if value is not None and mean is not None else None
        # Ratio statistics are stored as fractions (e.g. .293). The profile
        # contract displays the difference in percentage points, so .293-.202
        # becomes +9.1%, not +0.091% or 0.0%.
        if rel_value is not None and key in {"rTS%","reFG%","r3PAr","rFTr","rTOV%","rORB%","rOpponent TOV%","rOpponent eFG%"}:
            # Match the source representation used by the target row and
            # season mean: fraction -> percentage points; already-percent ->
            # leave as percentage points.
            if value is not None and mean is not None and max(abs(value), abs(mean)) <= 1.5:
                rel_value *= 100.0
        pct=_team_percentile(rel_value,historical_rel_pop[key],higher=(direction=="higher")) if rel_value is not None else None
        profile_relative.append({"key":key,"label":label,"value":rel_value,"direction":direction,"percentiles":{"historical":pct}})

    # NRtg remains a profile metric. Its percentile is historical so every
    # profile value is evaluated against the same all-time team-season context.
    nr_value=_num(row.get("nrtg"))
    nr_pop=[_num(rr.get("nrtg")) for rr in historical_population]
    nr_pop=[v for v in nr_pop if v is not None]
    nr_pct=_team_percentile(nr_value,nr_pop,higher=True) if nr_value is not None else None
    profile_relative.append({"key":"NRtg","label":"NRtg","value":nr_value,"direction":"higher","percentiles":{"historical":nr_pct}})

    relative_start={"rTS%":1974,"reFG%":1974,"rTOV%":1978,"rORB%":1974,"rFTr":1974,"rOpponent TOV%":1978,"rOpponent eFG%":1974,"r3PAr":1980}
    stats=[]
    for item in profile_relative:
        start_year=relative_start.get(item["key"])
        if start_year is not None and (season_end is None or season_end < start_year):
            continue
        if item["value"] is None or item["percentiles"].get("historical") is None:
            continue
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
        # JSON has no NaN/Infinity values. Pandas/numpy can produce these
        # internally when a team-season Four-Factor field is unavailable;
        # convert them to JSON null instead of emitting invalid JSON such as
        # `"efgpct": NaN`, which breaks browser JSON.parse().
        def _json_safe(v):
            if isinstance(v, dict):
                return {k:_json_safe(x) for k,x in v.items()}
            if isinstance(v, (list, tuple)):
                return [_json_safe(x) for x in v]
            if isinstance(v, np.generic):
                v=v.item()
            if isinstance(v, float) and not np.isfinite(v):
                return None
            return v
        payload=_json_safe(payload)
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
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
            if m:
                requested=unquote(m.group(1))
                requested_type=q.get("season_type",["Regular Season"])[0]
                if str(requested_type).casefold() in {"playoffs","playoff","postseason"}:
                    return self.send_json(200,api_playoff_season_bundles(requested))
                if public_player_season_bundles:
                    return self.send_json(200,public_player_season_bundles(requested,requested_type))
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
                if str(st).casefold() in {"playoffs","playoff","postseason"} and str(scope_q).casefold()=="single":
                    result=_api_playoff_explorer_population(xs,ys,season_q,era_q,search_q,xmin,xmax,ymin,ymax,100)
                else:
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
                    q.get("anchor_statistic", [None])[0],
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
                        if fp.is_absolute():
                            rel=str(fp).lstrip("/\\")
                            fp=(ROOT/"public"/rel).resolve()
                        else:
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
    # Build the expensive multi-stat Peak/Era bundles in the background warm
    # phase. The user should not pay this cost when changing a board selector.
    # Warm Peak independently from Era. A failure in one scope must never
    # invalidate the already-built Peak bundle or make the other Big Board
    # scopes wait/fall back to on-demand computation.
    try:
        _five_year_peak_windows("Regular Season",None)
        _five_year_peak_all_stat_values("Regular Season",None)
        _five_year_peak_windows("Playoffs",None)
        _five_year_peak_all_stat_values("Playoffs",None)
        print("Big Board Peak bundles ready.")
    except Exception as _e:
        print("Big Board Peak warm failed:", repr(_e))
    # Era Average is already served through its existing per-era cached path.
    # Do not run the legacy all-era startup warm here: on some pandas builds
    # its temporary weighting column can collide with a source-column label
    # and raise KeyError("__w"). That warm is not required for the working
    # Era selector and must not be allowed to generate a startup error or
    # consume resources needed by the Peak bundle.
    print("Big Board Era startup warm skipped (existing cached path retained).")

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
            print("Warming public profile data...")
            if warm_public_profile_data is not None: warm_public_profile_data()
            print("Public profile data ready.")
        except Exception as e:
            print("Public profile data warm failed:", repr(e))

        try:
            print("Warming NEW SDI v4 season index...")
            _load_regular_sdi_v4_player_seasons()
            print("NEW SDI v4 season index ready.")
        except Exception as e:
            print("NEW SDI v4 season index warm failed:", repr(e))

        try:
            print("Warming individual regular-season SDI cache...")
            _warm_regular_season_spider_cache()
            print("Individual regular-season SDI cache ready.")
        except Exception as e:
            print("Individual regular-season SDI cache warm failed:", repr(e))

        try:
            print("Warming playoff percentile cache...")
            load_playoff_46_season()
            load_playoff_percentile_long(career=False)
            load_playoff_46_career()
            load_playoff_percentile_long(career=True)
            _warm_playoff_season_sdi_cache()
            try:
                _pc=_PLAYOFF_SEASON_SDI_CACHE or {}
                print("Playoff individual-season SDI cache ready:", len(_pc.get("id",{})), "rows")
            except Exception:
                print("Playoff individual-season SDI cache ready.")
            print("Playoff percentile cache ready.")
        except Exception as e:
            print("Playoff percentile cache warm failed:", repr(e))

        try:
            print("Warming precomputed playoff 5-Year Peak cache...")
            _preload_playoff_peak_cache()
            print("Playoff 5-Year Peak cache ready.")
        except Exception as e:
            print("Playoff 5-Year Peak cache warm failed:", repr(e))

        try:
            print("Warming regular 5-Year Peak cache...")
            _load_precomputed_regular_peak_profile(requested_pid="__warm_only__")
            _regular_peak_category_population()
            _warm_regular_peak_sdi_spider_cache()
            try:
                _five_year_peak_windows("Regular Season", None)
                _five_year_peak_windows("Playoffs", None)
                # IMPORTANT: the window cache alone is not enough for the
                # Big Board.  The first Peak selector previously still had to
                # traverse every qualifying window and aggregate every stat.
                # Materialize the complete statistic bundle during the warm
                # phase so the selector itself is an in-memory lookup.
                _five_year_peak_all_stat_values("Regular Season", None)
                print("Regular 5-Year Peak Big Board bundle ready.")
                _five_year_peak_all_stat_values("Playoffs", None)
                print("Playoff 5-Year Peak Big Board bundle ready.")
            except Exception as e:
                print("Big Board peak-window/bundle cache warm failed:", repr(e))
            print("Regular 5-Year Peak cache ready.")
        except Exception as e:
            print("Regular 5-Year Peak cache warm failed:", repr(e))

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

