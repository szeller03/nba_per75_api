import "./comparison_v1.css";
import "./performance_frontend_v1.js";
import "./performance_frontend_v1.css";
import "./design_v13_integration.css";
import { getPlayerProfileBundle } from "./api.js";
import "./website80_profile_completion.css";
import { Link, NavLink, Route, Routes, useParams, useNavigate, useLocation } from "react-router-dom";
import CANONICAL_HEADSHOTS from "./canonical_headshots_v1.json";
import homeLogo from "./assets/logo_concept_c.png";
import playerKareem from "./assets/player_kareem_enhanced.png";
import playerOscar from "./assets/player_oscar_enhanced.png";
import playerDuncan from "./assets/player_duncan_enhanced.png";
import {
  Search, BarChart3, GitCompareArrows, LayoutDashboard,
  Users, Shield, BookOpen, Menu, ChevronRight, Pencil
} from "lucide-react";
import React, { useState, useEffect, useRef } from "react";
import { searchPlayers, searchPlayersBatch, getPlayerProfile, getPlayerSeasons, getPlayerSeasonBundles, getPlayerSpider, getPlayerContextProfile, getPlayerCategories, getPlayerSubcategories, getStatisticRegistry, getBigBoard, getBigBoardCompanion, getBigBoardSeasonOptions, getPlayerComparison, getExplorerPopulation, getTeams, getTeamProfile, getTeamAnalytics, getTeamAnalyticsProfile, prefetchPlayerProfile, prefetchPlayerSpider } from "./api";

// Big Board response cache: once a scope/statistic is loaded, switching back to it is instantaneous.
const BIG_BOARD_REQUEST_CACHE = new Map();
import { playerDisplayName } from "./playerDisplayName";
import { TeamComparisonPage } from "./TeamComparisonPage";
import "./v13_exact.css";
import "./v13_final_corrections.css";
import "./player_profile_design_steps2_4.css";
import "./palette_v21_black_rose_white_red.css";
import "./palette_v22_vhs_no_rectangles.css";

const nav = [
  ["Home", "/", LayoutDashboard],
  ["Players", "/players", Users],
  ["Big Board", "/big-board", BarChart3],
  ["Compare", "/compare", GitCompareArrows],
  ["Explorer", "/explorer", Search],
  ["Teams", "/teams", Shield],
  ["Create Your Top 75", "/create-t50", GitCompareArrows],
  ["Methodology", "/methodology", BookOpen],
];

function percentileTextStyle(value) {
  const n=Math.max(0,Math.min(100,Number(value)||0));
  const midpoint=68;
  const stops=n<=midpoint
    ? [[174,48,66],[247,245,241],n/midpoint]
    : [[247,245,241],[102,185,232],(n-midpoint)/(100-midpoint)];
  const [a,b,t]=stops;
  const rgb=a.map((v,i)=>Math.round(v+(b[i]-v)*t));
  return {color:`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`};
}

function percentileVisualStyle(value) {
  const n=Math.max(0,Math.min(100,Number(value)||0));
  const midpoint=68;
  const stops=n<=midpoint
    ? [[174,48,66],[247,245,241],n/midpoint]
    : [[247,245,241],[102,185,232],(n-midpoint)/(100-midpoint)];
  const [a,b,t]=stops;
  const rgb=a.map((v,i)=>Math.round(v+(b[i]-v)*t));
  const luminance=(0.2126*rgb[0]+0.7152*rgb[1]+0.0722*rgb[2])/255;
  return {
    backgroundColor:`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`,
    color:luminance<0.62?'#ffffff':'#15171c',
    borderColor:`rgba(255,255,255,${luminance<0.62?0.16:0.32})`
  };
}


function Header() {
  const location = useLocation();
  return <header className="topbar">
    <div className="brand">
      <div className="brandmark">75</div>
      <span><strong>NBA PER-75</strong><small>Historical Basketball Analytics</small></span>
    </div>
    <nav className="nav">
      {nav.map(([label,path]) => <NavLink key={path} to={path} className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>{label.toUpperCase()}</NavLink>)}
    </nav>
    <input className="global-search" placeholder="Search players or teams..." aria-label="Search players or teams" />
  </header>;
}

function PageShell({ eyebrow, title, description, children, className="" }) {
  return <main className={`page ${className}`.trim()}>
    {eyebrow && <div className="eyebrow">{eyebrow}</div>}
    {title && <h1>{title}</h1>}
    {description && <p className="sub">{description}</p>}
    {children}
  </main>;
}

const Placeholder = ({title, text}) => (
  <div className="placeholder-card">
    <div className="placeholder-icon"><BarChart3 size={22}/></div>
    <h3>{title}</h3>
    <p>{text}</p>
  </div>
);

function Home() {
  const features = [
    ["PLAYER PROFILES", Users, "/players"],
    ["BIG BOARD", BarChart3, "/big-board"],
    ["COMPARE", GitCompareArrows, "/compare"],
    ["WORKSPACE", "workspace", "/explorer"],
    ["TEAMS", Shield, "/teams"],
    ["CREATE ALL-TIME LIST", Pencil, "/create-t50"]
  ];

  return <main className="home-concept">
    <section className="home-hero-wrap" aria-label="NBA PER-75 homepage introduction">
      <div className="home-hero">
        <div className="home-hero-frame">
          <div className="home-hero-backdrop" />
          <div className="home-hero-copy">
            <img className="home-hero-logo" src={homeLogo} alt="NBA PER-75 basketball 75 logo" />
            <div className="home-hero-text">
              <div className="home-hero-title">WEBSITE NAME</div>
              <div className="home-hero-kicker">HISTORICAL BASKETBALL ANALYTICS</div>
              <div className="home-hero-tagline">75 years of 75 data, your home for historical NBA statistics.</div>
            </div>
          </div>
        </div>
        <div className="home-hero-players" aria-hidden="true">
          <img className="home-player home-player-kareem" src={playerKareem} alt="" />
          <img className="home-player home-player-oscar" src={playerOscar} alt="" />
          <img className="home-player home-player-duncan" src={playerDuncan} alt="" />
        </div>
      </div>
    </section>

    <section className="home-feature-grid" aria-label="Website features">
      {features.map(([label, Icon, path]) => (
        <Link key={path} to={path} className="home-feature-circle">
          <span className={`home-feature-icon ${typeof Icon === "string" ? Icon : ""}`}>
            {Icon === "workspace" ? <><BarChart3 size={62} strokeWidth={2.2}/><Search className="workspace-search-icon" size={42} strokeWidth={2.6}/></> : label === "COMPARE" ? <span className="home-vs-icon">VS</span> : <Icon size={68} strokeWidth={2.25}/>}
          </span>
          <strong>{label}</strong>
          <span className="home-feature-explore">EXPLORE →</span>
        </Link>
      ))}
    </section>
  </main>;
}

const HISTORICAL_HEADSHOT_MAP = {};
const HISTORICAL_HEADSHOT_IDS = new Set(Object.keys(HISTORICAL_HEADSHOT_MAP));
const CREATE_T75_HEADSHOT_OVERRIDES = {
  "kareem abdul-jabbar": "/player_headshots_final_v1/P002997.png",
  "alex english": "/player_headshots_final_v1/P000102.png",
  "alex english*": "/player_headshots_final_v1/P000103.png",
  "shaquille o'neal": "https://cdn.nba.com/headshots/nba/latest/1040x760/406.png",
  "shaquille o’neal": "https://cdn.nba.com/headshots/nba/latest/1040x760/406.png",
  "nikola jokic": "https://cdn.nba.com/headshots/nba/latest/1040x760/203999.png",
  "nikola jokić": "https://cdn.nba.com/headshots/nba/latest/1040x760/203999.png",
  "manu ginobili": "https://cdn.nba.com/headshots/nba/latest/1040x760/1938.png",
  "nate \"tiny\" archibald": "/player_headshots_final_v1/P004459.png",
  "tiny archibald": "/player_headshots_final_v1/P004459.png",
  "amar’e stoudemire": "https://cdn.nba.com/headshots/nba/latest/1040x760/2405.png",
  "amar'e stoudemire": "https://cdn.nba.com/headshots/nba/latest/1040x760/2405.png",
  "penny hardaway": "https://cdn.nba.com/headshots/nba/latest/1040x760/358.png",
  "anfernee hardaway": "https://cdn.nba.com/headshots/nba/latest/1040x760/358.png"
};
function _nameKey(name="") {
  return String(name||"").normalize("NFKC").trim().toLowerCase().replace(/\s+/g," ");
}

// WEBSITE240 HEADSHOT CORRECTION 14 — a small subset of imported historical PNGs
// are extraction artifacts (line-only/action fragments), not usable portraits.
// Do not let those local files override the verified NBA CDN portrait.
const INVALID_HISTORICAL_HEADSHOTS = new Set([
  "P000002","P000003","P000005","P000009","P000020","P000024",
  "P000028","P000030","P000033","P000043","P000047","P000048"
]);

const INVALID_HISTORICAL_CDN_FALLBACKS = {
  "P000002":"https://cdn.nba.com/headshots/nba/latest/1040x760/1920.png",
  "P000003":"https://cdn.nba.com/headshots/nba/latest/1040x760/76672.png",
  "P000005":"https://cdn.nba.com/headshots/nba/latest/1040x760/2062.png",
  "P000009":"https://cdn.nba.com/headshots/nba/latest/1040x760/78627.png",
  "P000020":"https://cdn.nba.com/headshots/nba/latest/1040x760/77115.png",
  "P000024":"https://cdn.nba.com/headshots/nba/latest/1040x760/78286.png",
  "P000028":"https://cdn.nba.com/headshots/nba/latest/1040x760/77126.png",
  "P000030":"https://cdn.nba.com/headshots/nba/latest/1040x760/768.png",
  "P000033":"https://cdn.nba.com/headshots/nba/latest/1040x760/2492.png",
  "P000043":"https://cdn.nba.com/headshots/nba/latest/1040x760/1817.png",
  "P000047":"https://cdn.nba.com/headshots/nba/latest/1040x760/76237.png",
  "P000048":"https://cdn.nba.com/headshots/nba/latest/1040x760/154.png"
};
function _canonicalHistoricalHeadshot(player,name="") {
  const override=CREATE_T75_HEADSHOT_OVERRIDES[_nameKey(name)];
  const id=player?.player_id || player?.Player_ID || player?.id || "";
  const key=String(id||"");
  // Prefer the verified local PNG whenever the canonical map has one. Named CDN
  // overrides are only a fallback, so historical PNGs (e.g. Kareem) are preserved.
  const canonical=CANONICAL_HEADSHOTS[key] || HISTORICAL_HEADSHOT_MAP[key] || "";
  if (INVALID_HISTORICAL_HEADSHOTS.has(key)) return INVALID_HISTORICAL_CDN_FALLBACKS[key] || "";
  if(canonical && canonical.startsWith("/player_headshots_final_v1/")) return canonical;
  if(override && override.startsWith("/player_headshots")) return override;
  return canonical || override || "";
}
function _headshotCandidates(player,name,direct,endpoint){
  const override=CREATE_T75_HEADSHOT_OVERRIDES[_nameKey(name)];
  return [...new Set([override,direct,endpoint].filter(Boolean).map(x=>String(x).split("?")[0]))];
}
function Headshot({ player, name="", className="", alt="", preferDirect=false, preferCanonicalApi=false }) {
  const id=player?.player_id || player?.Player_ID || player?.Player_Slug || player?.id || "";
  const identity=id || name || player?.player_name || player?.name || "75";
  const endpoint=`/api/v1/players/${encodeURIComponent(identity)}/headshot`;
  const direct=player?.headshot_url || player?.Headshot_URL || player?.headshot || "";
  const localOverride=_canonicalHistoricalHeadshot(player,name);
  const initials=String(name || player?.player_name || player?.name || "75").split(/\s+/).filter(Boolean).map(x=>x[0]).join("").slice(0,2).toUpperCase();
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>setAttempt(0),[identity,direct,name]);
  const namedOverride=CREATE_T75_HEADSHOT_OVERRIDES[_nameKey(name)];
  const candidates=[...(preferCanonicalApi?[localOverride,namedOverride,endpoint,direct]:preferDirect?[direct]:[localOverride,namedOverride,direct,endpoint])].filter(Boolean).map(x=>String(x).split("?")[0]).filter((x,i,a)=>a.indexOf(x)===i);
  const src=candidates[attempt] || "";
  const isHistoricalLocal=String(src||"").startsWith("/player_headshots_final_v1/");
  if(!src)return <span className="sil">{initials}</span>;
  const explorerSpecial = _nameKey(name)==="george gervin" ? " explorer-george-gervin" : "";
  return <img className={`${className} headshot-proxy${isHistoricalLocal ? " historical-headshot" : ""}${explorerSpecial}`} src={src} alt={alt || name} onError={()=>setAttempt(x=>x+1)}/>;
}

function Players() {
  const [query,setQuery]=useState("");
  const [players,setPlayers]=useState([]),[curatedPlayers,setCuratedPlayers]=useState({}),[loading,setLoading]=useState(false);
  const curated=["Michael Jordan","LeBron James","Kareem Abdul-Jabbar","Magic Johnson","Larry Bird","Wilt Chamberlain","Bill Russell","Shaquille O'Neal","Tim Duncan","Stephen Curry","Kevin Durant","Hakeem Olajuwon","Oscar Robertson","Jerry West","Charles Barkley","Kevin Garnett","Kobe Bryant","Nikola Jokic","Giannis Antetokounmpo","Dwyane Wade"];
  useEffect(()=>{let active=true;searchPlayersBatch(curated).then(r=>{if(!active)return;const found=r?.players||{};const entries=curated.map(name=>[name,found[name]||{player_name:name}]);setCuratedPlayers(Object.fromEntries(entries));}).catch(()=>{if(active)setCuratedPlayers(Object.fromEntries(curated.map(name=>[name,{player_name:name}])));});return()=>{active=false;};},[]);
  useEffect(()=>{let active=true;if(!query){setPlayers([]);setLoading(false);return()=>{active=false;};}setLoading(true);const timer=setTimeout(()=>{searchPlayers(query).then(r=>{if(active)setPlayers(r.players||r.rows||[]);}).catch(()=>{if(active)setPlayers([]);}).finally(()=>{if(active)setLoading(false);});},150);return()=>{active=false;clearTimeout(timer);};},[query]);
  const card=(player,nameOverride,keySuffix="")=>{const name=nameOverride||playerDisplayName(player?.player_name||player?.name||"");const href=player?.player_id?`/players/${encodeURIComponent(player.player_id)}`:`/players/${encodeURIComponent(name)}`;return <Link key={`${href}-${keySuffix}`} onPointerDown={()=>prefetchPlayerProfile(player?.player_id || name,"full")} to={href} state={{player}} className="card result-card"><div className="photo"><Headshot player={player} name={name}/></div><div className="name">{name}</div><div className="team">NBA HISTORY</div></Link>;};
  return <main className="page"><div className="eyebrow">PLAYER DATABASE</div><h1>Players</h1><p className="sub">Search the complete historical player universe. Browse the card stream or search for a player to reveal matching cards.</p><div className="searchrow"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search players..."/><button className="btn alt" onClick={()=>setQuery("")}>Clear</button></div>{!query?<div className="conveyor"><div className="track">{[...curated,...curated].map((name,i)=>card(curatedPlayers[name],name,i))}</div></div>:<div className="results-grid">{loading?<div className="panel" style={{padding:20}}>Searching…</div>:players.length?players.map((p,i)=>card(p,null,i)):<div className="panel" style={{padding:20}}>No matching players.</div>}</div>}</main>;
}

function BigBoard() {
  const navigate=useNavigate();
  const [board,setBoard]=useState(null),[secondaryBoard,setSecondaryBoard]=useState(null);
  const [seasonOptions,setSeasonOptions]=useState([]);
  const [scope,setScope]=useState("single"),[seasonType,setSeasonType]=useState("Regular Season"),[season,setSeason]=useState("Historical Percentile"),[context,setContext]=useState("Historical"),[statistic,setStatistic]=useState("PTS_per75"),[sort,setSort]=useState("desc"),[search,setSearch]=useState(""),[era,setEra]=useState(""),[registry,setRegistry]=useState([]),[loading,setLoading]=useState(false),[secondarySort,setSecondarySort]=useState("none");
  const [boardLimit,setBoardLimit]=useState(500);
  // FIX 52 — explicit Big Board secondary-stat contract.  Only statistics
  // with a documented companion receive one; everything else intentionally
  // stays secondary-free rather than inheriting a global guess.
  const companionMap={
    "PTS_per75":"rTS",
    "FG_per75":"FG_pct", "FGA_per75":"FG_pct",
    "3P_per75":"3P_pct", "3PA_per75":"3P_pct",
    "2P_per75":"2P_pct", "2PA_per75":"2P_pct",
    "FT_per75":"FT_pct", "FTA_per75":"FT_pct",
    "ORB_per75":"OREB_pct", "OREB_per75":"OREB_pct",
    "DRB_per75":"DREB_pct", "DREB_per75":"DREB_pct",
    "TRB_per75":"OREB_per75",
    "AST_per75":"AST_TOV", "TOV_per75":"AST_TOV",
    "STL_per75":"STL_pct", "BLK_per75":"BLK_pct",
    "FG_pct":"FGA_per75", "2P_pct":"2PA_per75", "3P_pct":"3PA_per75",
    "FT_pct":"FTA_per75",
    "FTr":"FTA_per75", "3PAr":"3PA_per75",
    "AST_pct":"AST_per75", "TOV_pct":"TOV_per75",
    "OREB_pct":"ORB_per75", "DREB_pct":"DRB_per75",
    "STL_pct":"STL_per75", "BLK_pct":"BLK_per75",
    "rTS":"TS_pct",
    "AST_TOV":"AST_per75"
  };
  const companion=companionMap[statistic]||"";
  const apiStatistic=statistic==="SDI"?"Statistical Dominance Index":statistic;
  const hasSecondary=Boolean(companion);
  useEffect(()=>{setSecondarySort("none");},[statistic]);
  // Keep the complete season registry populated independently of the current board scope.
  // Era Average/Career responses intentionally do not carry single-season options, so relying
  // only on `board.season_options` caused the Playoffs dropdown to appear empty on first render.
  useEffect(()=>{
    let active=true;
    // Season options are a registry, not a ranked-board payload. Fetch them
    // directly from the canonical Big Board endpoint so the complete regular-
    // season universe is available immediately instead of inheriting the
    // first 500 ranked rows from the public shortcut.
    getBigBoardSeasonOptions(seasonType)
      .then(r=>{
        if(!active)return;
        const raw=[...(Array.isArray(r?.season_options)?r.season_options:[]),...(Array.isArray(r?.seasons)?r.seasons:[])];
        const seen=new Set();
        const opts=raw.filter(x=>{const v=String(x?.value??x??"");if(!v||seen.has(v))return false;seen.add(v);return true;});
        setSeasonOptions(opts);
      }).catch(()=>{if(active)setSeasonOptions([]);});
    return()=>{active=false;};
  },[seasonType]);
  const label=s=>({WOWY_Offense:"WOWY Offense",WOWY_Defense:"WOWY Defense",WOWY_Net:"WOWY Net"}[s]||String(s||"").replaceAll("_per75","/75").replaceAll("_pct","%").replace("AST_TOV","AST:TOV"));
  // Secondary context is now percentile-driven rather than raw-value-driven.
  // This prevents skewed distributions (especially rTS) from compressing the
  // useful visual range. The row receives a soft right-to-left percentile
  // gradient; the number itself remains clean and readable.
  const secondaryVisualScore=(metric,value,pct)=>{
    const n=Number(value);
    if(metric==="rTS" && Number.isFinite(n)){
      // rTS is intentionally capped at +/-4 for visual semantics.  +4 and
      // above are fully positive, -4 and below fully negative, with 0 as
      // the neutral midpoint. This prevents a broadly negative historical
      // distribution from making modestly positive rTS values look bad.
      return Math.max(0,Math.min(100,((Math.max(-4,Math.min(4,n))+4)/8)*100));
    }
    return Math.max(0,Math.min(100,Number(pct)));
  };
  const secondaryPercentileStyle=(pct,metric,value)=>{
    const n=secondaryVisualScore(metric,value,pct);
    const t=n/100;
    const red=[178,82,91], neutral=[225,220,210], green=[93,164,119];
    const rgb=t<=.5
      ? neutral.map((v,i)=>Math.round(red[i]+(v-red[i])*(t*2)))
      : neutral.map((v,i)=>Math.round(v+(green[i]-v)*((t-.5)*2)));
    const strong=.24;
    const soft=.07;
    return {background:`linear-gradient(270deg, rgba(${rgb[0]},${rgb[1]},${rgb[2]},${strong}) 0%, rgba(${rgb[0]},${rgb[1]},${rgb[2]},${soft}) 24%, rgba(${rgb[0]},${rgb[1]},${rgb[2]},0) 72%)`};
  };
  const grade=(metric,v)=>{const n=Number(v);if(!Number.isFinite(n))return"bb-neutral";if(metric==="rTS")return n>=6?"bb-elite":n>=3?"bb-verygood":n>=0?"bb-average":n>=-3?"bb-below":"bb-poor";if(metric==="TOV_per75")return n<=2?"bb-elite":n<=3?"bb-verygood":n<=4?"bb-average":n<=5?"bb-below":"bb-poor";if(metric==="OREB_per75")return n>=4?"bb-elite":n>=3?"bb-verygood":n>=2?"bb-average":n>=1.2?"bb-below":"bb-poor";if(metric==="SDI")return n>=90?"bb-elite":n>=75?"bb-verygood":n>=40?"bb-average":n>=20?"bb-below":"bb-poor";return"bb-neutral";};
  const bigBoardStatOrder=[
    ["SDI","SDI"],["PTS_per75","PTS/75"],["TRB_per75","TRB/75"],["DRB_per75","DRB/75"],["ORB_per75","ORB/75"],["AST_per75","AST/75"],["AST_TOV","AST:TOV"],["STL_per75","STL/75"],["BLK_per75","BLK/75"],["TOV_per75","TOV/75"],["FTA_per75","FTA/75"],["2PA_per75","2PA/75"],["3PA_per75","3PA/75"],["FGA_per75","FGA/75"],["rTS","rTS"],["TS_pct","TS%"],["FT_pct","FT%"],["2P_pct","2P%"],["3P_pct","3P%"],["FG_pct","FG%"],["FT_per75","FT/75"],["2P_per75","2P/75"],["3P_per75","3P/75"],["FG_per75","FG/75"],["WOWY_Offense","WOWY Offense"],["WOWY_Defense","WOWY Defense"],["WOWY_Net","WOWY Net"],["3PAr","3PAr"],["FTr","FTr"],["DREB_pct","DREB%"],["OREB_pct","OREB%"],["AST_pct","AST%"],["STL_pct","STL%"],["BLK_pct","BLK%"],["TOV_pct","TOV%"],["PF_per75","PF/75"],["PER","PER"],["BPM","BPM"],["OBPM","OBPM"],["DBPM","DBPM"],["VORP","VORP"],["WS/48","WS/48"],["OWS","OWS"],["DWS","DWS"]
  ];
  const registrySet=new Set((registry||[]).map(s=>String(s.statistic||s.Statistic||s.Stat||s.name||s)));
  const orderedBigBoardStats=bigBoardStatOrder;
  useEffect(()=>{
    setLoading(true);
    const requestedSeason=scope==="career"||scope==="era_average"?undefined:season;
    const requestedContext=scope==="career"?"Career":scope==="era_average"?"Era":context;
    const makeBoardKey=(stat,cmp,anchor)=>JSON.stringify([requestedSeason,requestedContext,stat||"",sort,search||"",boardLimit,scope,seasonType,era||"",!!cmp,anchor||""]);
    const cachedBoard=(stat,cmp=false,anchor="")=>{
      const key=makeBoardKey(stat,cmp,anchor);
      if(BIG_BOARD_REQUEST_CACHE.has(key)) return Promise.resolve(BIG_BOARD_REQUEST_CACHE.get(key));
      return getBigBoard(requestedSeason,requestedContext,stat||undefined,sort,search,cmp?boardLimit:boardLimit,scope,seasonType,era,cmp,anchor)
        .then(v=>{BIG_BOARD_REQUEST_CACHE.set(key,v);return v;});
    };
    const primaryPromise=cachedBoard(apiStatistic||undefined,false,"");
    const secondaryPromise=companion
      ? primaryPromise.then(primary=>{
          // Playoff and Peak rows now carry their companion values directly
          // on each primary row. Reusing those rows avoids a second playoff
          // Big Board request and makes playoff navigation materially faster.
          // Career is included here as well because its canonical rows carry
          // the same companion_values contract.
          if(seasonType==="Playoffs" || scope==="five_year_peak" || scope==="career") return {rows:(primary?.rows||[])};
          const ids=(primary?.rows||[]).map(r=>r?.player_id).filter(Boolean);
          if(scope==="single" && seasonType==="Regular Season" && ids.length){
            return getBigBoardCompanion(requestedSeason,requestedContext,companion,ids,era);
          }
          return cachedBoard(companion,true,"");
        })
      : Promise.resolve(null);
    Promise.all([primaryPromise,secondaryPromise])
      .then(([a,b])=>{ setBoard(a); setSecondaryBoard(b); })
      .catch(()=>{setBoard(null);setSecondaryBoard(null);})
      .finally(()=>setLoading(false));
  },[scope,seasonType,season,context,statistic,sort,search,era,companion,boardLimit]);
  const rows=board?.rows||[];
  const statLabel=statistic||"SDI";
  const normBoardSeason=v=>{const x=String(v??"").trim().toLowerCase().replace(/[–—]/g,"-");const m=x.match(/(\d{4})-(\d{2,4})/);if(m){const start=Number(m[1]);const end=Number(m[2].length===2?String(Math.floor(start/100))+m[2]:m[2]);return String(end);}const y=x.match(/\d{4}/);return y?y[0]:x;}; const normBoardName=v=>String(v??"").replace(/\*+/g,"").trim().toLowerCase(); const rowKeys=r=>{const season=normBoardSeason(r?.season_label??r?.season);const id=String(r?.player_id??"").trim().toLowerCase();const name=normBoardName(r?.player_name??r?.Player??r?.name);return [id&&`${id}|||${season}`,name&&`${name}|||${season}`].filter(Boolean);}; const secondaryIndex=new Map(); const secondaryPlayerIndex=new Map(); (secondaryBoard?.rows||[]).forEach(x=>{rowKeys(x).forEach(k=>secondaryIndex.set(k,x)); const pid=String(x?.player_id??"").trim().toLowerCase(); const name=normBoardName(x?.player_name??x?.Player??x?.name); if(pid) secondaryPlayerIndex.set(pid,x); if(name) secondaryPlayerIndex.set(`name:${name}`,x);}); const findSecondary=r=>{
      // Peak rows contain companion_values calculated on the exact same winning
      // five-season window. Always prefer that embedded value; never fall back
      // to the primary row itself, which would incorrectly display the primary
      // statistic again as the secondary.
      if(scope==="five_year_peak"){
        // Peak secondary values must come from the exact winning five-year
        // window embedded in the primary row. Never fall back to secondaryBoard
        // here because v40/v41 intentionally used the primary rows as the
        // transport for the precomputed Peak bundle; doing so would display the
        // primary statistic again (e.g. 32.3 PTS/75 as 32.3 rTS).
        if(r?.companion_values && Object.prototype.hasOwnProperty.call(r.companion_values,companion)){
          const v=r.companion_values[companion];
          if(v!=null && Number.isFinite(Number(v))) return {value:v};
        }
        return null;
      }
      // Playoff and Career primary rows are the authoritative transport for
      // companion values. Prefer the embedded companion before matching the
      // secondary board, because v54 reused the primary rows as the secondary
      // transport; matching that row first would make the secondary display the
      // primary statistic again (for example PTS/75 32.5 -> rTS 32.5).
      if((seasonType==="Playoffs" || scope==="career" || scope==="era_average") && r?.companion_values && Object.prototype.hasOwnProperty.call(r.companion_values,companion)){
        const v=r.companion_values[companion];
        if(v!=null && Number.isFinite(Number(v))) return {value:v};
      }
      const exact=rowKeys(r).map(k=>secondaryIndex.get(k)).find(Boolean);
      if(exact && String(exact?.statistic||"")!==String(statistic||"")) return exact;
      if(r?.companion_values && Object.prototype.hasOwnProperty.call(r.companion_values,companion)){const v=r.companion_values[companion]; if(v!=null && Number.isFinite(Number(v))) return {value:v};}
      if(scope!=="single"){const pid=String(r?.player_id??"").trim().toLowerCase(); const name=normBoardName(r?.player_name??r?.Player??r?.name); const candidate=(pid&&secondaryPlayerIndex.get(pid))||secondaryPlayerIndex.get(`name:${name}`)||null; return candidate && String(candidate?.statistic||"")!==String(statistic||"") ? candidate : null;} return null;};
  const percentStats=new Set(["FG_pct","2P_pct","3P_pct","FT_pct","TS_pct","FTr","3PAr","OREB_pct","DREB_pct","AST_pct","STL_pct","BLK_pct","TOV_pct"]);
  const displayPercentile=(stat,v)=>{
    const n=Number(v);
    if(!Number.isFinite(n)) return null;
    return String(stat)==="TOV_per75"||String(stat)==="TOV_pct" ? 100-n : n;
  };
  const formatBoardValue=(stat,v)=>{
    if(v==null||!Number.isFinite(Number(v))) return "—";
    const n=Number(v);
    if(percentStats.has(stat)) return `${(Math.abs(n)<=1?n*100:n).toFixed(1)}%`;
    if(stat==="AST_TOV") return n.toFixed(2);
    if(["WOWY_Offense","WOWY_Defense","WOWY_Net"].includes(stat) && n>0) return `+${n.toFixed(1)}`;
    return n.toFixed(1);
  };
  const secondaryValueRows=rows.map(r=>({row:r,value:Number(findSecondary(r)?.value)})).filter(x=>Number.isFinite(x.value));
  const secondaryLowerBetter=new Set(["TOV_per75","PF_per75","TOV_pct"]);
  const secondaryPercentileMap=new Map();
  if(secondaryValueRows.length){
    const ordered=[...secondaryValueRows].sort((a,b)=>a.value-b.value);
    const n=ordered.length;
    ordered.forEach((x,i)=>{
      const rawPct=n===1?100:(100*i/(n-1));
      secondaryPercentileMap.set(x.row,secondaryLowerBetter.has(companion)?100-rawPct:rawPct);
    });
  }
  const displayedRows=[...rows].sort((a,b)=>{
    if(secondarySort==="none") return Number(a.rank||0)-Number(b.rank||0);
    const av=Number(findSecondary(a)?.value),bv=Number(findSecondary(b)?.value);
    if(!Number.isFinite(av)&&!Number.isFinite(bv)) return Number(a.rank||0)-Number(b.rank||0);
    if(!Number.isFinite(av)) return 1;
    if(!Number.isFinite(bv)) return -1;
    return secondarySort==="desc" ? bv-av : av-bv;
  });
  return <main className="page">
    <div className="eyebrow">ALL-TIME BIG BOARD</div><h1>Big Board</h1><p className="sub">Rank historical seasons by the statistic you choose, with useful companion context shown beside it.</p>
    <div className="panel controls section big-board-controls">
      <div className="bb-control-group bb-stat-group">
        <div className="bb-control-group-title">STATISTIC</div>
        <div className="bb-control-group-fields">
          <select className="control bb-control" value={statistic} onChange={e=>setStatistic(e.target.value)}>{orderedBigBoardStats.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select>
          <select className="control bb-control" value={sort} onChange={e=>setSort(e.target.value)}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select>
          <select className="control bb-control board-size-select" value={boardLimit} onChange={e=>setBoardLimit(Number(e.target.value))}><option value="50">T50</option><option value="100">T100</option><option value="250">T250</option><option value="500">T500</option></select>
        </div>
      </div>
      <div className="bb-control-group bb-season-group">
        <div className="bb-control-group-title">SEASON &amp; CONTEXT</div>
        <div className="bb-control-group-fields">
          <select className="control bb-control" value={seasonType} onChange={e=>setSeasonType(e.target.value)}><option>Regular Season</option><option>Playoffs</option></select>
          <select className="control bb-control" value={season} onChange={e=>setSeason(e.target.value)}><option value="Historical Percentile">All Seasons</option>{(()=>{const seen=new Set();const opts=[...seasonOptions,...(Array.isArray(board?.season_options)?board.season_options:[]),...(Array.isArray(board?.seasons)?board.seasons:[])].filter(e=>{const v=String(e?.value??e??"");if(!v||seen.has(v))return false;seen.add(v);return true;}).sort((a,b)=>{const seasonYear=v=>{const text=String(v?.value??v??"").trim();const m=text.match(/(\d{4})\s*[-–—]/);return m?Number(m[1]):Number(text.match(/\d{4}/)?.[0]||0);};return seasonYear(a)-seasonYear(b);});return opts.map(e=><option key={e.value||e} value={e.value||e}>{e.label||e.value||e}</option>);})()}</select>
          {scope==="single"&&<select className="control bb-control" value={context} onChange={e=>setContext(e.target.value)}><option>Season</option><option>Era</option><option>Historical</option></select>}
          {scope==="era_average"?<select className="control bb-control" value={era||"1952-1969"} onChange={e=>{setEra(e.target.value);setContext("Era");setSeason("Historical Percentile");}}><option value="1952-1969">1952–1969 · Shot Clock Era</option><option value="1970-1979">1970–1979 · Merger Era</option><option value="1980-1990">1980–1990 · Showtime Era</option><option value="1991-1998">1991–1998 · Jordan Era</option><option value="1999-2006">1999–2006 · Deadball Era</option><option value="2007-2013">2007–2013 · Superteam Era</option><option value="2014-2020">2014–2020 · Moreyball Era</option><option value="2021-2026">2021–2026 · Positionless Era</option></select>:<select className="control bb-control" value={era} onChange={e=>{setEra(e.target.value);if(e.target.value){setContext("Era");setSeason("Historical Percentile");}}}><option value="">All Eras</option><option value="1952-1969">1952–1969 · Shot Clock Era</option><option value="1970-1979">1970–1979 · Merger Era</option><option value="1980-1990">1980–1990 · Showtime Era</option><option value="1991-1998">1991–1998 · Jordan Era</option><option value="1999-2006">1999–2006 · Deadball Era</option><option value="2007-2013">2007–2013 · Superteam Era</option><option value="2014-2020">2014–2020 · Moreyball Era</option><option value="2021-2026">2021–2026 · Positionless Era</option></select>}
        </div>
      </div>
      <div className="bb-control-group bb-scope-group">
        <div className="bb-control-group-title">BOARD SCOPE</div>
        <div className="bb-control-group-fields">
          <select className="control bb-control" value={scope} onChange={e=>{const x=e.target.value;setScope(x);if(x==="career"){setEra("");setContext("Career");}else if(x==="era_average"){setContext("Era");if(!era)setEra("1952-1969");setSeason("Historical Percentile");}else{setContext(era?"Era":"Historical");setSeason("Historical Percentile");}}}><option value="single">Single Season</option><option value="five_year_peak">5-Year Peak</option><option value="era_average">Era Average</option><option value="career">Career</option></select>
          {hasSecondary&&<select className="control bb-control secondary-sort" value={secondarySort} onChange={e=>setSecondarySort(e.target.value)}><option value="none">Secondary sort: Off</option><option value="desc">Secondary sort: Highest</option><option value="asc">Secondary sort: Lowest</option></select>}
        </div>
      </div>
      <div className="bb-control-group bb-player-filter-group">
        <div className="bb-control-group-title">PLAYER FILTER</div>
        <div className="bb-control-group-fields"><input className="control bb-control bb-player-filter" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter players..."/></div>
      </div>
    </div>
    <div className="panel board-table section"><table><thead><tr><th>RANK</th><th>PLAYER</th><th>SEASON</th><th>{label(statLabel)}</th>{hasSecondary&&<th><button type="button" className="bb-secondary-header" onClick={()=>setSecondarySort(x=>x==="none"?"desc":x==="desc"?"asc":"none")} title="Click to sort by this statistic">{label(companion)}{secondarySort!=="none"?<span className="bb-sort-arrow">{secondarySort==="desc"?"↑":"↓"}</span>:null}</button></th>}</tr></thead><tbody>
      {displayedRows.map((r,rowIndex)=>{const sr=findSecondary(r),cv=sr?.value;const playerId=r.player_id||r.player_name;const secondaryPct=secondaryPercentileMap.get(r);const rowStyle=hasSecondary&&Number.isFinite(Number(cv))?secondaryPercentileStyle(secondaryPct,companion,cv):undefined;return <tr key={`${playerId}-${r.rank}`} className="bb-secondary-percentile-row bb-clickable-row" style={rowStyle} onMouseEnter={()=>playerId&&prefetchPlayerProfile(playerId,"hover")} onPointerDown={()=>playerId&&prefetchPlayerProfile(playerId)} onClick={()=>playerId&&navigate(`/players/${encodeURIComponent(playerId)}`)} role="link" tabIndex="0" onKeyDown={e=>{if((e.key==="Enter"||e.key===" ")&&playerId){e.preventDefault();navigate(`/players/${encodeURIComponent(playerId)}`);}}}><td>{rowIndex+1}</td><td><Link to={`/players/${encodeURIComponent(playerId)}`} onMouseEnter={()=>prefetchPlayerProfile(playerId,"hover")} onPointerDown={()=>prefetchPlayerProfile(playerId)} onClick={e=>{e.stopPropagation();navigate(`/players/${encodeURIComponent(playerId)}`);}}>{playerDisplayName(r.player_name||"Unknown")}</Link></td><td>{r.season_label||r.season||"—"}</td><td><div className="bb-primary-stack"><b className="bb-primary-value">{formatBoardValue(statistic,r.value)}</b><span className="pct percentile-badge" style={displayPercentile(statistic,r.percentile)==null?undefined:percentileTextStyle(displayPercentile(statistic,r.percentile))}>{displayPercentile(statistic,r.percentile)==null?"—":`${Math.round(displayPercentile(statistic,r.percentile))}%`}</span></div></td>{hasSecondary&&<td className="context"><b className="bb-secondary-value">{formatBoardValue(companion,cv)}</b></td>}</tr>})}
      {!loading&&!rows.length&&<tr><td colSpan={hasSecondary?5:4}>No Big Board rows for this selection.</td></tr>}
    </tbody></table></div>
    {loading&&<div className="note section">Loading…</div>}
  </main>;
}

function ComparisonSpider({axesA, axesB, labels, title, nameA="Player A", nameB="Player B"}) {
  const size=700, center=size/2, radius=275, n=Math.max(labels.length,1);
  const point=(i,v,r=radius)=>{
    const angle=-Math.PI/2+(i*2*Math.PI/n);
    const rr=r*Math.max(0,Math.min(100,Number(v)||0))/100;
    return [center+Math.cos(angle)*rr,center+Math.sin(angle)*rr];
  };
  const poly=vals=>vals.map((v,i)=>point(i,v).join(",")).join(" ");
  return <div className="comparison-spider-card">
    <div className="comparison-visual-title">{title}</div>
    <svg viewBox={`0 0 ${size} ${size}`} className="comparison-spider-svg" role="img" aria-label="Six-dimension percentile comparison">
      {[20,40,60,80,100].map(level=><polygon key={level} points={labels.map((_,i)=>point(i,level,radius).join(",")).join(" ")} className="comparison-spider-grid"/>) }
      {labels.map((label,i)=>{
        const [x,y]=point(i,100),[lx,ly]=point(i,114);
        return <g key={label}>
          <line x1={center} y1={center} x2={x} y2={y} className="comparison-spider-axis"/>
          <text x={lx} y={ly} textAnchor={lx<center-8?"end":lx>center+8?"start":"middle"} className="comparison-spider-label">{String(label||"")}</text>
        </g>;
      })}
      {[20,40,60,80,100].map(level=>{const y=center-radius*level/100;const dy=level===100?12:3;return <text key={`scale-${level}`} x={center+7} y={y+dy} textAnchor="start" className="comparison-spider-scale-label">{level}</text>;})}
      <text x={center+7} y={center+11} textAnchor="start" className="comparison-spider-scale-label">0</text>
      <polygon points={poly(axesA)} className="comparison-spider-a"/>
      <polygon points={poly(axesB)} className="comparison-spider-b"/>
      {axesA.map((v,i)=>{const [x,y]=point(i,v);return <circle key={`a-${i}`} cx={x} cy={y} r="5" className="comparison-spider-dot-a"/>;})}
      {axesB.map((v,i)=>{const [x,y]=point(i,v);return <circle key={`b-${i}`} cx={x} cy={y} r="5" className="comparison-spider-dot-b"/>;})}
    </svg>
    <div className="comparison-legend">
      <span><i className="legend-a"/>{nameA}</span>
      <span><i className="legend-b"/>{nameB}</span>
      <small>100% = top of the percentile scale · 0% = bottom</small>
    </div>
  </div>;
}

class ComparisonErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error("Comparison render error", error, info);
  }
  render() {
    if (this.state.error) {
      return <PageShell eyebrow="PLAYER COMPARISON" title="Comparison render error">
        <Placeholder
          title="The comparison data loaded, but the visual layer could not render."
          text={`Render error: ${this.state.error?.message || "Unknown error"}. The API data is preserved; refresh or change the comparison to try again.`}
        />
      </PageShell>;
    }
    return this.props.children;
  }
}

function Compare() {
  const [aQuery,setAQuery]=useState("");
  const [bQuery,setBQuery]=useState("");
  const [aResults,setAResults]=useState([]);
  const [bResults,setBResults]=useState([]);
  const [playerA,setPlayerA]=useState(null);
  const [playerB,setPlayerB]=useState(null);
  const [seasonType,setSeasonType]=useState("Regular Season");
  const [context,setContext]=useState("Season");
  const [startA,setStartA]=useState("");
  const [endA,setEndA]=useState("");
  const [startB,setStartB]=useState("");
  const [endB,setEndB]=useState("");
  const [seasonsA,setSeasonsA]=useState([]);
  const [seasonsB,setSeasonsB]=useState([]);
  const [result,setResult]=useState(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [registry,setRegistry]=useState([]);
  const [selectedPercentileStats,setSelectedPercentileStats]=useState([]);
  const [percentileStatSearch,setPercentileStatSearch]=useState("");
  const abortRef=useRef(null);

  useEffect(()=>{getStatisticRegistry().then(r=>setRegistry(r.statistics||[])).catch(()=>setRegistry([]));},[]);

  useEffect(()=>{
    const t=setTimeout(()=>{
      if(!aQuery.trim()){setAResults([]);return;}
      searchPlayers(aQuery).then(r=>setAResults((r.players||[]).slice(0,8))).catch(()=>setAResults([]));
    },220); return()=>clearTimeout(t);
  },[aQuery]);

  useEffect(()=>{
    const t=setTimeout(()=>{
      if(!bQuery.trim()){setBResults([]);return;}
      searchPlayers(bQuery).then(r=>setBResults((r.players||[]).slice(0,8))).catch(()=>setBResults([]));
    },220); return()=>clearTimeout(t);
  },[bQuery]);

  const choose=(which,p)=>{
    const pid=p.player_id||p.player_name||p.Player;
    if(which==="a"){setPlayerA(p);setAQuery(p.player_name||p.Player||"");setAResults([]);setStartA("");setEndA("");}
    else {setPlayerB(p);setBQuery(p.player_name||p.Player||"");setBResults([]);setStartB("");setEndB("");}
  };

  useEffect(()=>{
    if(!playerA)return;
    getPlayerSeasons(playerA.player_id||playerA.player_name||playerA.Player,seasonType).then(r=>setSeasonsA((r?.seasons||[]).map(x=>typeof x==="object"?(x.season||x.Season||x.value||x.label):x).filter(Boolean))).catch(()=>setSeasonsA([]));
  },[playerA,seasonType]);
  useEffect(()=>{
    if(!playerB)return;
    getPlayerSeasons(playerB.player_id||playerB.player_name||playerB.Player,seasonType).then(r=>setSeasonsB((r?.seasons||[]).map(x=>typeof x==="object"?(x.season||x.Season||x.value||x.label):x).filter(Boolean))).catch(()=>setSeasonsB([]));
  },[playerB,seasonType]);

  const runComparison=async()=>{
    if(!playerA||!playerB){setError("Select both players before comparing.");return;}
    if(abortRef.current) abortRef.current.abort();
    const controller=new AbortController(); abortRef.current=controller;
    setLoading(true);setError("");
    try{
      const timeoutId=setTimeout(()=>controller.abort(),90000);
      const r=await getPlayerComparison(
        playerA.player_id||playerA.player_name,
        playerB.player_id||playerB.player_name,
        startA,endA,startB,endB,seasonType,context,controller.signal
      );
      clearTimeout(timeoutId);
      if(!r || !r.found) throw new Error(r?.error||"Comparison could not be built.");
      if(!Array.isArray(r.players) || r.players.length<2) throw new Error("Comparison API returned an incomplete player result.");
      setResult(r);
    }catch(e){
      if(e?.name==="AbortError") setError("Comparison timed out after 90 seconds. The API may still be warming its data cache.");
      else setError(e.message||"Comparison request failed.");
    }finally{setLoading(false);}
  };

  const pa=result?.players?.[0]||null,pb=result?.players?.[1]||null;
  const stats=Array.isArray(result?.statistics)?result.statistics.filter(s=>typeof s==="string"&&s.trim()):[];
  const fmt=v=>v==null?"—":Number(v).toFixed(2);
  const isPercentStat=stat=>/%|_pct$/.test(String(stat||""));
  const formatComparisonValue=(stat,v)=>{if(v==null||!Number.isFinite(Number(v)))return"—";const n=Number(v);if(stat==="BLK_pct")return `${n.toFixed(1)}%`;if(isPercentStat(stat))return `${Math.round((Math.abs(n)<=1?n*100:n))}%`;const signed=["WOWY_Net","WOWY_Offense","WOWY_Defense"].includes(stat);const text=(stat==="FTr"||stat==="3PAr"||stat==="AST_TOV"||stat==="WS/48"||stat==="WS48"||stat==="WS_per48")?n.toFixed(2):n.toFixed(1);return signed&&n>0?`+${text}`:text;};
  const formatComparisonDiff=(stat,d)=>{if(d==null||!Number.isFinite(Number(d)))return"—";const n=Number(d);return isPercentStat(stat)?`${Math.round((Math.abs(n)<=1?Math.abs(n)*100:Math.abs(n)))}%`:Math.abs(n).toFixed(1);};
  const pct=v=>v==null?"—":Number(v).toFixed(1);

  // Canonical six dominance dimensions used elsewhere in the website.
  const categoryRules=[
    ["Scoring Volume",["PTS","FGA","FTA","2PA","3PA","FGA_per75","FTA_per75","2PA_per75","3PA_per75","FTr","3PAr"]],
    ["Scoring Efficiency",["TS","TS_pct","rTS","FG_pct","2P_pct","3P_pct","FT_pct","PTS_per75"]],
    ["Engine & Playmaking",["AST","TOV","AST_pct","TOV_pct","USG","USG_pct","OBPM","WOWY_Offense","AST_TOV"]],
    ["Rebounding",["TRB","TRB_pct","ORB","ORB_pct","DRB","DRB_pct","DREB_pct","OREB_pct"]],
    ["Defense",["STL","BLK","STL_pct","BLK_pct","DBPM","WOWY_Defense","PF"]],
    ["Impact & Value",["PER","VORP","WOWY_Net","WS/48","OWS","DWS"]]
  ];
  const cleanStat=s=>String(s||"").toLowerCase().replace(/[^a-z0-9]/g,"");
  const matches=(stat,rule)=>{
    const s=cleanStat(stat);
    return rule.some(k=>s===cleanStat(k)||s.includes(cleanStat(k)));
  };
  const categoryScore=(player,rule)=>{
    if(!player)return null;
    const vals=stats.map(metric=>player?.percentiles && player.percentiles[metric]).filter((v,i)=>v!=null && matches(stats[i],rule)).map(Number).filter(Number.isFinite);
    return vals.length?vals.reduce((x,y)=>x+y,0)/vals.length:null;
  };
  const categoryRaw=(player,rule)=>{
    if(!player)return null;
    const vals=stats.map(metric=>player?.statistics && player.statistics[metric]).filter((v,i)=>v!=null && matches(stats[i],rule)).map(Number).filter(Number.isFinite);
    if(!vals.length)return null;
    // Relative A/B scale for cases where percentile data has not returned yet.
    return vals.reduce((x,y)=>x+y,0)/vals.length;
  };

  const pctAvailable=pa&&pb&&stats.some(s=>pa.percentiles?.[s]!=null||pb.percentiles?.[s]!=null);
  const categoryValues=categoryRules.map(([label,rule])=>[
    label,categoryScore(pa,rule),categoryScore(pb,rule),categoryRaw(pa,rule),categoryRaw(pb,rule)
  ]);
  const radarLabels=categoryValues.map(x=>x[0].replace("Scoring ","").replace("Engine & ",""));
  const normalizePair=(a,b)=>[
    Math.max(0,Math.min(100,Number(a)||0)),
    Math.max(0,Math.min(100,Number(b)||0))
  ];
  const radarA=[],radarB=[];
  categoryValues.forEach(x=>{
    const pair=pctAvailable?normalizePair(x[1],x[2]):normalizePair(x[3],x[4]);
    radarA.push(pair[0]);radarB.push(pair[1]);
  });

  useEffect(()=>{
    if(!stats.length){setSelectedPercentileStats([]);return;}
    setSelectedPercentileStats(current=>{
      const valid=current.filter(s=>stats.includes(s));
      // First comparison defaults to a manageable 12-stat view, while every
      // statistic returned by the comparison remains available to select.
      if(!valid.length) return stats.slice(0,12);
      return valid;
    });
  },[stats.join("|")]);

  const filteredPercentileStats=stats.filter(stat=>
    String(stat).toLowerCase().includes(percentileStatSearch.toLowerCase().trim())
  );
  const togglePercentileStat=(stat)=>{
    setSelectedPercentileStats(current=>
      current.includes(stat) ? current.filter(s=>s!==stat) : [...current,stat]
    );
  };
  const selectAllPercentiles=()=>setSelectedPercentileStats([...stats]);
  const clearPercentiles=()=>setSelectedPercentileStats([]);
  const resetPercentiles=()=>setSelectedPercentileStats(stats.slice(0,12));
  const topStats=selectedPercentileStats;

  const lowerIsBetter=new Set([
    "TOV_pct","TOV%","TOV_per75","TOV","PF","PF_per75"
  ]);
  const statLeader=(stat,av,bv)=>{
    if(av==null||bv==null||Number.isNaN(Number(av))||Number.isNaN(Number(bv))) return "—";
    const aa=Number(av),bb=Number(bv);
    if(aa===bb)return "Tie";
    const lower=lowerIsBetter.has(stat);
    return lower ? (aa<bb?"A":"B") : (aa>bb?"A":"B");
  };
  const percentileLeader=(av,bv)=>{
    if(av==null||bv==null)return "—";
    const aa=Number(av),bb=Number(bv);
    if(!Number.isFinite(aa)||!Number.isFinite(bb))return "—";
    return aa===bb?"Tie":aa>bb?"A":"B";
  };
  const seasonList=(player)=>Array.isArray(player?.seasons)?player.seasons:[];
  const methodology=result?.weighting||{};
  const pctDelta=(av,bv)=>{
    if(av==null||bv==null)return null;
    const d=Number(av)-Number(bv);
    return Number.isFinite(d)?d:null;
  };
  const playerCard=(which,p,q,setQ,results)=>{
    return <div className="compare-player-card">
      <span className="compare-label">PLAYER {which}</span>
      <input value={q} onChange={e=>{setQ(e.target.value);which==="A"?setPlayerA(null):setPlayerB(null);}} placeholder="Search player..." />
      {results.length>0&&<div className="compare-results">{results.map(x=>
        <button key={x.player_id||x.player_name} onClick={()=>choose(which.toLowerCase(),x)}>{x.player_name||x.Player}</button>
      )}</div>}
      {p&&<div className="selected-player">{p.player_name||p.Player}</div>}
    </div>;
  };

  const [activeCategory,setActiveCategory]=useState("Scoring Volume");
  const categoryStats={"Scoring Volume":["PTS_per75","FGA_per75","FTA_per75","2PA_per75","3PA_per75","FTr","3PAr"],"Scoring Efficiency":["TS_pct","rTS","FG_pct","2P_pct","3P_pct","FT_pct","PTS_per75"],"Engine & Playmaking":["AST","TOV","AST_TOV","WOWY_Offense","AST_pct","TOV_pct","USG","USG_pct","OBPM"],"Rebounding":["TRB","TRB_pct","ORB","ORB_pct","DRB","DRB_pct","DREB_pct","OREB_pct"],"Defense":["STL","BLK","STL_pct","BLK_pct","DBPM","WOWY_Defense","PF"],"Impact & Value":["PER","VORP","WOWY_Net","WS/48","OWS","DWS"]};
  const orderedCategoryStats=(categoryStats[activeCategory]||[]).map(key=>{
    const exact=stats.find(stat=>cleanStat(stat)===cleanStat(key));
    if(exact)return exact;
    return stats.find(stat=>cleanStat(stat).startsWith(cleanStat(key)+"per75")||cleanStat(stat).startsWith(cleanStat(key)+"pct"))||null;
  }).filter(Boolean);
  const visibleCategoryStats=[...new Set(orderedCategoryStats)];
  const shownCompareStats=visibleCategoryStats.length?visibleCategoryStats:stats.slice(0,8);

  return <main className="page"><div className="eyebrow">PLAYER COMPARISON</div><h1>Head-to-Head</h1><div className="compare-players">
    <div className="playerhead playerhead-a"><div className="avatar"><Headshot player={playerA||pa} name={pa?.player_name||playerA?.player_name||"A"}/></div><div className="playerhead-content"><div className="playerhead-identity"><h3>{pa?.player_name||"Player A"}</h3><small>{!pa?"Select a player":(!startA?"Career":`${startA}${endA?` to ${endA}`:""}`)}</small></div><input className="control player-search" value={aQuery} onChange={e=>{setAQuery(e.target.value);setPlayerA(null);}} placeholder="Search player..."/>{aResults.length>0&&<div className="v13-search-results">{aResults.map(x=><button key={x.player_id||x.player_name} onClick={()=>choose("a",x)}>{x.player_name||x.Player}</button>)}</div>}<div className="player-card-range"><span>SEASON RANGE</span><div className="compare-range"><select className="control" value={startA} onChange={e=>setStartA(e.target.value)} disabled={!playerA}><option value="">Career</option>{seasonsA.map(s=><option key={s} value={s}>{s}</option>)}</select><i>to</i><select className="control" value={endA} onChange={e=>setEndA(e.target.value)} disabled={!playerA||!startA}><option value="">{startA?startA:"Career"}</option>{seasonsA.map(s=><option key={s} value={s}>{s}</option>)}</select></div></div></div></div>
    <div className="vs">VS</div>
    <div className="playerhead playerhead-b"><div className="avatar"><Headshot player={playerB||pb} name={pb?.player_name||playerB?.player_name||"B"}/></div><div className="playerhead-content"><div className="playerhead-identity"><h3>{pb?.player_name||"Player B"}</h3><small>{!pb?"Select a player":(!startB?"Career":`${startB}${endB?` to ${endB}`:""}`)}</small></div><input className="control player-search" value={bQuery} onChange={e=>{setBQuery(e.target.value);setPlayerB(null);}} placeholder="Search player..."/>{bResults.length>0&&<div className="v13-search-results">{bResults.map(x=><button key={x.player_id||x.player_name} onClick={()=>choose("b",x)}>{x.player_name||x.Player}</button>)}</div>}<div className="player-card-range"><span>SEASON RANGE</span><div className="compare-range"><select className="control" value={startB} onChange={e=>setStartB(e.target.value)} disabled={!playerB}><option value="">Career</option>{seasonsB.map(s=><option key={s} value={s}>{s}</option>)}</select><i>to</i><select className="control" value={endB} onChange={e=>setEndB(e.target.value)} disabled={!playerB||!startB}><option value="">{startB?startB:"Career"}</option>{seasonsB.map(s=><option key={s} value={s}>{s}</option>)}</select></div></div></div></div>
  </div><div className="panel controls comparison-range-controls"><div className="comparison-global-controls"><select className="control" value={seasonType} onChange={e=>setSeasonType(e.target.value)}><option>Regular Season</option><option>Playoffs</option></select><select className="control" value={context} onChange={e=>setContext(e.target.value)}><option>Season</option><option>Era</option><option>Historical</option></select><button className="btn" onClick={runComparison} disabled={loading}>{loading?"COMPARING…":"COMPARE PLAYERS"}</button></div></div>{error&&<div className="comparison-error">{error}</div>}
  {result&&pa&&pb&&<><div className="compare-visuals"><div className="cat-tabs">{[...Object.keys(categoryStats),"Spider Chart"].map(cat=><button key={cat} className={activeCategory===cat?"active":""} onClick={()=>setActiveCategory(cat)}>{cat==="Spider Chart"?"SPIDER CHART":cat.toUpperCase()}</button>)}</div>{activeCategory==="Spider Chart"?<div className="panel section comparison-spider-section"><h3 style={{textAlign:"center"}}>SIX-DIMENSION PROFILE</h3><div className="six-radar-wrap"><ComparisonSpider axesA={radarA} axesB={radarB} labels={radarLabels} title="" nameA={pa?.player_name||"Player A"} nameB={pb?.player_name||"Player B"}/></div></div>:<div className="panel stat-compare section">{shownCompareStats.map(stat=>{const av=pa.statistics?.[stat],bv=pb.statistics?.[stat],leader=statLeader(stat,av,bv),diff=av!=null&&bv!=null?Number(av)-Number(bv):null;return <div className={`compare-row leader-${leader.toLowerCase()}`} key={stat}><div className={`val left ${leader==="A"?"win":""}`}>{formatComparisonValue(stat,av)}</div><div className="label">{stat==="ORtg"?"On-Court ORtg":stat==="DRtg"?"On-Court DRtg":stat==="FTr"?"FTr":stat==="3PAr"?"3PAr":({WOWY_Offense:"WOWY Offense",WOWY_Defense:"WOWY Defense",WOWY_Net:"WOWY Net"}[stat]||stat.replaceAll("_per75","/75").replaceAll("_pct","%").replace("AST_TOV","AST:TOV"))}<div className={`diff ${leader==="A"?"leader-a-text":leader==="B"?"leader-b-text":""}`}>{diff==null?"—":leader==="Tie"?"Tie":<>{leader==="A"?pa.player_name:pb.player_name} {formatComparisonDiff(stat,diff)}</>}</div></div><div className={`val right ${leader==="B"?"win":""}`}>{formatComparisonValue(stat,bv)}</div></div>})}</div>}<div className="panel" style={{padding:20}}><div className="dimension-grid">{categoryValues.map(([label,a,b])=><div className="dimension" key={label}><h3>{label.toUpperCase()}</h3><p className="note">Percentile-based comparison for the selected player ranges.</p><div className="dimension-bars"><div className="dimension-bar-line"><span>A</span><div className="bar"><div className="fill player-a-fill" style={{width:`${Math.max(0,Math.min(100,Number(a)||0))}%`}}/></div><b>{a==null?"—":Math.round(Number(a))}</b></div><div className="dimension-bar-line"><span>B</span><div className="bar"><div className="fill player-b-fill" style={{width:`${Math.max(0,Math.min(100,Number(b)||0))}%`}}/></div><b>{b==null?"—":Math.round(Number(b))}</b></div></div><small>A = {pa.player_name} · B = {pb.player_name}</small></div>)}</div></div></div></>}</main>;
}

function Explorer() {
  const navigate = useNavigate();
  const [registry,setRegistry]=useState([]);
  const [statistic,setStatistic]=useState("PTS_per75");
  const [scatterX,setScatterX]=useState("PTS_per75");
  const [scatterY,setScatterY]=useState("rTS");
  const [seasonType,setSeasonType]=useState("Regular Season");
  const [season,setSeason]=useState("Historical Percentile");
  const [context,setContext]=useState("Historical");
  const [scope,setScope]=useState("single");
  const [era,setEra]=useState("");
  const [board,setBoard]=useState(null);
  const [scatterData,setScatterData]=useState(null);
  const [scatterRefresh,setScatterRefresh]=useState(0);
  const [loading,setLoading]=useState(false);
  const [scatterLoading,setScatterLoading]=useState(false);
  const [error,setError]=useState("");
  const [scatterError,setScatterError]=useState("");
  const scatterRequestRef=useRef(0);
  const [search,setSearch]=useState("");
  const [populationLimit,setPopulationLimit]=useState(100);
  const [xMin,setXMin]=useState(""); const [xMax,setXMax]=useState("");
  const [yMin,setYMin]=useState(""); const [yMax,setYMax]=useState("");
  const [availableBounds,setAvailableBounds]=useState({xmin:null,xmax:null,ymin:null,ymax:null});

  const eras=[
    ["1952-1969","1952–1969 · Shot Clock Era"],["1970-1979","1970–1979 · Merger Era"],
    ["1980-1990","1980–1990 · Showtime Era"],["1991-1998","1991–1998 · Jordan Era"],
    ["1999-2006","1999–2006 · Deadball Era"],["2007-2013","2007–2013 · Superteam Era"],
    ["2014-2020","2014–2020 · Moreyball Era"],["2021-2026","2021–2026 · Positionless Era"],
  ];
  const statKeys=registry.map(s=>typeof s==="string"?s:(s?.statistic||s?.Statistic||s?.Stat||s?.key||s?.name||"")).filter(Boolean);
  const explorerStatOrder=[
    ["SDI","SDI"],["PTS_per75","PTS/75"],["TRB_per75","TRB/75"],["DRB_per75","DRB/75"],["ORB_per75","ORB/75"],
    ["AST_per75","AST/75"],["AST_TOV","AST:TOV"],["STL_per75","STL/75"],["BLK_per75","BLK/75"],["TOV_per75","TOV/75"],
    ["FTA_per75","FTA/75"],["2PA_per75","2PA/75"],["3PA_per75","3PA/75"],["FGA_per75","FGA/75"],["rTS","rTS"],
    ["TS_pct","TS%"],["FT_pct","FT%"],["2P_pct","2P%"],["3P_pct","3P%"],["FG_pct","FG%"],
    ["FT_per75","FT/75"],["2P_per75","2P/75"],["3P_per75","3P/75"],["FG_per75","FG/75"],
    ["WOWY_Offense","WOWY Offense"],["WOWY_Defense","WOWY Defense"],["WOWY_Net","WOWY Net"],["3PAr","3PAr"],["FTr","FTr"],
    ["DREB_pct","DREB%"],["OREB_pct","OREB%"],["AST_pct","AST%"],["STL_pct","STL%"],["BLK_pct","BLK%"],["TOV_pct","TOV%"],
    ["PF_per75","PF/75"],["PER","PER"],["BPM","BPM"],["OBPM","OBPM"],["DBPM","DBPM"],["VORP","VORP"],["WS/48","WS/48"],["OWS","OWS"],["DWS","DWS"]
  ];
  const availableSet=new Set(statKeys);
  const orderedExplorerStats=explorerStatOrder.filter(([k])=>availableSet.has(k) || !statKeys.length);
  const availableStats=orderedExplorerStats.length?orderedExplorerStats.map(([k])=>k):["PTS_per75","rTS","PER","BPM","TS_pct","AST_pct"];
  const statLabel=s=>String(s||"").replaceAll("_per75","/75").replaceAll("_pct","%").replaceAll("AST_TOV","AST:TOV").replace("WS/48","WS/48");

  useEffect(()=>{ getStatisticRegistry().then(r=>setRegistry(Array.isArray(r.statistics)?r.statistics:[])).catch(()=>setRegistry([])); },[]);

  useEffect(()=>{
    let active=true; setLoading(true); setError("");
    const requestedSeason=scope==="single"?season:undefined;
    const requestedContext=scope==="career"?"Career":(scope==="five_year_peak"?"Historical":(scope==="era"?"Era":(era?"Era":context)));
    const requestedScope=scope==="career"?"career":(scope==="five_year_peak"?"five_year_peak":(scope==="era"?"era":"single"));
    getBigBoard(requestedSeason,requestedContext,statistic,"desc",search,Math.max(populationLimit,100),requestedScope,seasonType,era)
      .then(r=>{if(active)setBoard(r);}).catch(e=>{if(active){setError(e.message||"Explorer data could not be loaded.");setBoard(null);}})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[season,context,scope,seasonType,statistic,search,era,populationLimit]);

  useEffect(()=>{
    let active=true; const requestId=++scatterRequestRef.current;
    setScatterLoading(true);setScatterError("");setScatterData(null);
    const requestedSeason=scope==="single"?season:"Historical Percentile";
    const opts={season:requestedSeason,seasonType,scope,era,search,x_min:xMin,x_max:xMax,y_min:yMin,y_max:yMax,limit:100};
    getExplorerPopulation(scatterX,scatterY,opts)
      .then(r=>{if(!active||requestId!==scatterRequestRef.current)return; if(r?.fallback){setScatterError("This Explorer view is not yet available on the indexed population layer.");setScatterData(null);return;} setScatterData(r); setAvailableBounds({xmin:r?.available_bounds?.xmin??null,xmax:r?.available_bounds?.xmax??null,ymin:r?.available_bounds?.ymin??null,ymax:r?.available_bounds?.ymax??null});})
      .catch(e=>{if(active&&requestId===scatterRequestRef.current){setScatterError(e.message||"Scatter data could not be loaded.");setScatterData(null);}})
      .finally(()=>{if(active&&requestId===scatterRequestRef.current)setScatterLoading(false);});
    return()=>{active=false;};
  },[scope,season,seasonType,era,search,scatterX,scatterY,xMin,xMax,yMin,yMax,scatterRefresh]);

  const rows=Array.isArray(board?.rows)?board.rows:[];
  const seasonOptions=(Array.isArray(scatterData?.season_options)&&scatterData.season_options.length?scatterData.season_options:(Array.isArray(board?.season_options)?board.season_options:[])).slice().sort((a,b)=>{const av=Number(String(a?.value??a??"").match(/\d{4}/)?.[0]||0),bv=Number(String(b?.value??b??"").match(/\d{4}/)?.[0]||0);return av-bv;});
  const values=rows.map(r=>Number(r.value)).filter(Number.isFinite);
  const fmt=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toFixed(2);
  const histogram=(()=>{if(!values.length)return Array.from({length:8},()=>({label:"—",count:0}));const min=Math.min(...values),max=Math.max(...values),bins=8;return Array.from({length:bins},(_,i)=>{if(max===min)return {label:fmt(min),count:values.length};const lo=min+(max-min)*i/bins,hi=i===bins-1?max:min+(max-min)*(i+1)/bins;return {label:`${fmt(lo)}–${fmt(hi)}`,count:values.filter(v=>i===bins-1?v>=lo:v>=lo&&v<hi).length};});})();
  const maxBin=Math.max(...histogram.map(x=>x.count),1);

  const commonRows=Array.isArray(scatterData?.rows)?scatterData.rows:[];
  const scatterRows=commonRows.map(r=>({...r,xValue:Number(r.xValue),yValue:Number(r.yValue)})).filter(r=>Number.isFinite(r.xValue)&&Number.isFinite(r.yValue));
  const scatterDisplayRows=scatterRows.slice(0,populationLimit);
  const scatterTotal=Number(scatterData?.total ?? scatterData?.population_total ?? scatterRows.length)||0;
  const scatterBounds=(()=>{if(!scatterDisplayRows.length)return {xmin:0,xmax:1,ymin:0,ymax:1};const padRange=arr=>{const min=Math.min(...arr),max=Math.max(...arr);if(min===max){const p=Math.max(Math.abs(min)*.05,1);return[min-p,max+p];}const span=max-min;return[min-span*.04,max+span*.04];};const [xmin,xmax]=padRange(scatterDisplayRows.map(r=>r.xValue));const [ymin,ymax]=padRange(scatterDisplayRows.map(r=>r.yValue));return{xmin,xmax,ymin,ymax};})();
  const axisTicks=(min,max)=>{
    const lo=Number(min),hi=Number(max);
    if(!Number.isFinite(lo)||!Number.isFinite(hi)||hi<=lo)return [lo,hi];
    const raw=(hi-lo)/5;
    const step=Math.max(.5,Math.ceil(raw/.5)*.5);
    const start=Math.floor(lo/step)*step;
    const end=Math.ceil(hi/step)*step;
    const ticks=[];
    for(let v=start;v<=end+step*.001;v+=step) ticks.push(Number(v.toFixed(1)));
    return ticks.length>1?ticks:[Number(lo.toFixed(1)),Number(hi.toFixed(1))];
  };
  const xAxisTicks=axisTicks(scatterBounds.xmin,scatterBounds.xmax);
  const yAxisTicks=axisTicks(scatterBounds.ymin,scatterBounds.ymax);
  // The player layer is positioned in CSS percentages while the grid is an SVG.
  // Keep both layers on the exact same 40..690 / 45..345 plot rectangle.
  const scatterLeft=v=>5.405+(v-scatterBounds.xmin)/(scatterBounds.xmax-scatterBounds.xmin||1)*87.838;
  const scatterTop=v=>11.538+(scatterBounds.ymax-v)/(scatterBounds.ymax-scatterBounds.ymin||1)*76.923;
  const scatterSvgX=v=>scatterLeft(v)*7.4;
  const scatterSvgY=v=>scatterTop(v)*3.9;
  const trendLine=(()=>{
    if(scatterDisplayRows.length<2)return null;
    const xs=scatterDisplayRows.map(r=>r.xValue), ys=scatterDisplayRows.map(r=>r.yValue);
    const mx=xs.reduce((a,b)=>a+b,0)/xs.length, my=ys.reduce((a,b)=>a+b,0)/ys.length;
    const den=xs.reduce((a,x)=>a+(x-mx)*(x-mx),0);
    if(!Number.isFinite(den)||den===0)return null;
    const slope=xs.reduce((a,x,i)=>a+(x-mx)*(ys[i]-my),0)/den;
    const intercept=my-slope*mx;
    const y1=Math.max(scatterBounds.ymin,Math.min(scatterBounds.ymax,slope*scatterBounds.xmin+intercept));
    const y2=Math.max(scatterBounds.ymin,Math.min(scatterBounds.ymax,slope*scatterBounds.xmax+intercept));
    return {x1:40,y1:345-(y1-scatterBounds.ymin)/(scatterBounds.ymax-scatterBounds.ymin||1)*300,x2:690,y2:345-(y2-scatterBounds.ymin)/(scatterBounds.ymax-scatterBounds.ymin||1)*300};
  })();
  const formatAxisTick=v=>{const n=Number(v);if(!Number.isFinite(n))return "—";const rounded=Math.round(n*10)/10;return Number.isInteger(rounded)?String(rounded):rounded.toFixed(1);};
  const viewLabel=(()=>{
    if(scope==="career") return `${seasonType} Career`;
    if(scope==="five_year_peak") return `${seasonType} 5-Year Peak`;
    if(scope==="era") return `${era ? (eras.find(([k])=>k===era)?.[1]?.split(" · ")[1]||"Era Average") : "Era Average"} ${seasonType}`;
    const seasonText=String(season||"");
    const yearMatch=seasonText.match(/(\d{4})/);
    return `${yearMatch ? yearMatch[1] : "All-Time"} ${seasonType}`;
  })();
  const chartTitle=`${viewLabel} ${statLabel(scatterX)} vs ${statLabel(scatterY)}`;
  const openPlayer=r=>{const id=r?.player_id||r?.player_name;if(id)navigate(`/players/${encodeURIComponent(id)}`);};
  const sliderBounds=(min,max)=>{
    const lo=Number(min),hi=Number(max);
    if(!Number.isFinite(lo)||!Number.isFinite(hi)||hi<=lo)return null;
    const span=hi-lo;
    const step=span>=100?1:span>=20?.5:span>=5?.1:span>=1?.05:.01;
    return {min:lo,max:hi,step};
  };
  const xSlider=sliderBounds(availableBounds.xmin,availableBounds.xmax);
  const ySlider=sliderBounds(availableBounds.ymin,availableBounds.ymax);
  const xRangeMin=xMin!==""&&Number.isFinite(Number(xMin))?Number(xMin):(xSlider?.min??0);
  const xRangeMax=xMax!==""&&Number.isFinite(Number(xMax))?Number(xMax):(xSlider?.max??1);
  const yRangeMin=yMin!==""&&Number.isFinite(Number(yMin))?Number(yMin):(ySlider?.min??0);
  const yRangeMax=yMax!==""&&Number.isFinite(Number(yMax))?Number(yMax):(ySlider?.max??1);
  const resetRanges=()=>{setXMin("");setXMax("");setYMin("");setYMax("");setScatterRefresh(x=>x+1);};
  return <main className="page">
    <div className="eyebrow">CHART EXPLORER</div><h1>Explore the Data</h1><p className="sub">Choose a primary variable to rank the population, then use a secondary variable to see how those same player-seasons relate.</p>
    <div className="explorer-grid section">
      <div className="panel axisbox"><h3>CHART CONTROLS</h3><br/>
        <label>VIEW</label><select value={scope} onChange={e=>{const v=e.target.value;setScope(v);setSeason("Historical Percentile");if(v==="era")setEra("1952-1969");resetRanges();}}><option value="single">Single Season</option><option value="five_year_peak">5-Year Peak</option><option value="era">Era Average</option><option value="career">Career</option></select>
        <label>PRIMARY VARIABLE · X-AXIS</label><select value={scatterX} onChange={e=>{const v=e.target.value;setScatterX(v);setStatistic(v);resetRanges();}}>{availableStats.map(s=><option key={s} value={s}>{statLabel(s)}</option>)}</select>
        <label>SECONDARY VARIABLE · Y-AXIS</label><select value={scatterY} onChange={e=>{setScatterY(e.target.value);resetRanges();}}>{availableStats.map(s=><option key={s} value={s}>{statLabel(s)}</option>)}</select>
        <label>POPULATION · RANKED BY X</label><div className="explorer-population-buttons">{[25,50,100].map(n=><button key={n} className={`btn explorer-pop-btn ${populationLimit===n?"active":""}`} onClick={()=>setPopulationLimit(n)}>T{n}</button>)}</div><div className="explorer-population-status">Showing <strong>{scatterDisplayRows.length}</strong> of <strong>{scatterTotal}</strong> qualifying observations</div>
        <div className="explorer-range-heading"><span>X-AXIS RANGE</span><button type="button" onClick={resetRanges}>RESET</button></div>
        <div className="explorer-dual-range" aria-label="X-axis range slider">
          <div className="explorer-range-track"><span className="explorer-range-fill" style={{left:`${xSlider?((xRangeMin-xSlider.min)/(xSlider.max-xSlider.min))*100:0}%`,right:`${xSlider?100-((xRangeMax-xSlider.min)/(xSlider.max-xSlider.min))*100:0}%`}}/></div>
          <input className="explorer-range-input explorer-range-input-min" type="range" min={xSlider?.min??0} max={xSlider?.max??1} step={xSlider?.step??.01} value={xRangeMin} disabled={!xSlider} onChange={e=>{const n=Number(e.target.value);if(n<xRangeMax)setXMin(String(n));}}/>
          <input className="explorer-range-input explorer-range-input-max" type="range" min={xSlider?.min??0} max={xSlider?.max??1} step={xSlider?.step??.01} value={xRangeMax} disabled={!xSlider} onChange={e=>{const n=Number(e.target.value);if(n>xRangeMin)setXMax(String(n));}}/>
        </div>
        <div className="explorer-range-values"><span>{fmt(xRangeMin)}</span><span>{fmt(xRangeMax)}</span></div>
        <div className="explorer-range-heading"><span>Y-AXIS RANGE</span></div>
        <div className="explorer-dual-range" aria-label="Y-axis range slider">
          <div className="explorer-range-track"><span className="explorer-range-fill" style={{left:`${ySlider?((yRangeMin-ySlider.min)/(ySlider.max-ySlider.min))*100:0}%`,right:`${ySlider?100-((yRangeMax-ySlider.min)/(ySlider.max-ySlider.min))*100:0}%`}}/></div>
          <input className="explorer-range-input explorer-range-input-min" type="range" min={ySlider?.min??0} max={ySlider?.max??1} step={ySlider?.step??.01} value={yRangeMin} disabled={!ySlider} onChange={e=>{const n=Number(e.target.value);if(n<yRangeMax)setYMin(String(n));}}/>
          <input className="explorer-range-input explorer-range-input-max" type="range" min={ySlider?.min??0} max={ySlider?.max??1} step={ySlider?.step??.01} value={yRangeMax} disabled={!ySlider} onChange={e=>{const n=Number(e.target.value);if(n>yRangeMin)setYMax(String(n));}}/>
        </div>
        <div className="explorer-range-values"><span>{fmt(yRangeMin)}</span><span>{fmt(yRangeMax)}</span></div>
        <label>ERA</label><select value={era} onChange={e=>{setEra(e.target.value);if(e.target.value)setContext("Era");}}><option value="">All Eras</option>{eras.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>
        {scope==="single"&&<><label>SEASON</label><select value={season} onChange={e=>{setSeason(e.target.value);if(e.target.value!=="Historical Percentile")setContext("Season");}}><option value="Historical Percentile">All Seasons</option>{seasonOptions.map(x=><option key={x.value||x} value={x.value||x}>{x.label||x.value||x}</option>)}</select></>}
        <label>SEASON TYPE</label><select value={seasonType} onChange={e=>{setSeasonType(e.target.value);resetRanges();}}><option>Regular Season</option><option>Playoffs</option></select>
        <button className="btn" style={{width:"100%"}} onClick={()=>setScatterRefresh(x=>x+1)}>UPDATE CHART</button>
        <div className="explorer-population-note">T25, T50, or T100 are the highest-X qualifying observations after the selected ranges. Y simply describes those same observations.</div>
      </div>
      <div className="explorer-main-stack">
      <div className="scatter">
        {scatterLoading&&<div className="scatter-chart-loading">Updating chart…</div>}
        {scatterError&&<div className="scatter-chart-loading">{scatterError}</div>}
        <div className="explorer-chart-title">{chartTitle}</div>
        <svg className="scatter-grid-svg" viewBox="0 0 740 390" preserveAspectRatio="none" aria-hidden="true">
          {xAxisTicks.map((tick,i)=>{const x=scatterSvgX(tick);return <g key={`x-${i}`}><line x1={x} y1="45" x2={x} y2="345" className="scatter-grid-line"/><text x={x} y="365" textAnchor="middle" className="scatter-tick-label">{formatAxisTick(tick)}</text></g>})}
          {yAxisTicks.map((tick,i)=>{const y=scatterSvgY(tick);return <g key={`y-${i}`}><line x1="40" y1={y} x2="690" y2={y} className="scatter-grid-line"/><text x="28" y={y+3} textAnchor="end" className="scatter-tick-label">{formatAxisTick(tick)}</text></g>})}
          {trendLine&&<line x1={trendLine.x1} y1={trendLine.y1} x2={trendLine.x2} y2={trendLine.y2} className="scatter-trend-line"/>}
        </svg>
        <span className="scatter-axis-title-x">{statLabel(scatterX)}</span><span className="scatter-axis-title-y">{statLabel(scatterY)}</span>
        {!scatterLoading&&!scatterError&&!scatterDisplayRows.length&&<div className="scatter-empty-state">No qualifying player-seasons match the current Explorer filters.</div>}
        {scatterDisplayRows.map((r,i)=>{const pname=r.player_name||"Player",seasonLabel=r.season_label||r.season||"";const displayedPopulation=scatterDisplayRows.length;const markerSize=Math.max(42,Math.min(58,42+(100-Math.min(displayedPopulation,100))*0.20));return <button key={`${r.player_id||r.player_name}-${r.season}-${i}`} className="dot explorer-player-dot" style={{left:`${scatterLeft(r.xValue)}%`,top:`${scatterTop(r.yValue)}%`,transform:"translate(-50%,-50%)",width:`${markerSize}px`,height:`${markerSize}px`,"--explorer-dot-size":`${markerSize}px`}} onClick={()=>openPlayer(r)}><span className="explorer-headshot-frame"><Headshot player={r} name={pname} preferCanonicalApi/></span><span className="scatter-player-tooltip"><strong>{pname}</strong><span>{seasonLabel}</span><span><b>{statLabel(scatterX)}:</b> {Number(r.xValue).toFixed(2)}</span><span><b>{statLabel(scatterY)}:</b> {Number(r.yValue).toFixed(2)}</span></span></button>})}
      </div>
      <div className="panel distribution explorer-distribution"><h2>{statLabel(scatterX)} Distribution</h2><div className="distribution-chart" aria-label="Distribution bar chart">{histogram.map((b,i)=><div className="distribution-bar-col" key={i}><span className="distribution-bar-value">{b.count}</span><div className="distribution-bar" style={{height:`${Math.max(1,b.count/maxBin*145)}px`}}/><span className="distribution-bar-label">{b.label}</span></div>)}</div><div className="board-table"><table><thead><tr><th>RANGE</th><th>PLAYER-SEASONS</th><th>SHARE</th></tr></thead><tbody>{histogram.map((b,i)=><tr key={i}><td>{b.label}</td><td>{b.count}</td><td>{values.length?`${(b.count/values.length*100).toFixed(1)}%`:"—"}</td></tr>)}</tbody></table></div></div>
      </div>
    </div>
  </main>;
}

function TeamLogo({row}) {
  const [attempt,setAttempt]=useState(0);
  const [failed,setFailed]=useState(false);
  const [processedSrc,setProcessedSrc]=useState("");
  const [processing,setProcessing]=useState(false);
  const logoId=String(row?.logo_id||row?.Logo_ID||row?.LogoId||"").trim();
  const rawFile=String(row?.Logo_File||row?.logo_file||"").trim();
  const direct=rawFile && (/^https?:\/\//i.test(rawFile)?rawFile:`/${rawFile.replace(/^\\+/ ,"").replace(/^\/+/,"")}`);
  const teamName=String(row?.team||row?.Team||"").replace(/\*+$/," ").trim().toLowerCase();
  const seasonText=String(row?.season||row?.Season||"");
  const seasonMatch=seasonText.match(/^(\d{4})-(\d{2,4})/);
  const seasonEnd=Number(row?.SeasonEndYear||row?.season_end_year||(seasonMatch ? Number(seasonMatch[1]) + (seasonMatch[2].length===2 ? 1 : 0) : NaN));
  const fallbackMap={"atlanta hawks":"ATL","boston celtics":"BOS","brooklyn nets":"BKN","charlotte hornets":"CHA","charlotte bobcats":"CHA","chicago bulls":"CHI","cleveland cavaliers":"CLE","dallas mavericks":"DAL","denver nuggets":"DEN","detroit pistons":"DET","golden state warriors":"GSW","houston rockets":"HOU","indiana pacers":"IND","los angeles clippers":"LAC","los angeles lakers":"LAL","memphis grizzlies":"MEM","miami heat":"MIA","milwaukee bucks":"MIL","minnesota timberwolves":"MIN","new orleans pelicans":"NOP","new york knicks":"NYK","oklahoma city thunder":"OKC","orlando magic":"ORL","philadelphia 76ers":"PHI","phoenix suns":"PHX","portland trail blazers":"POR","sacramento kings":"SAC","san antonio spurs":"SAS","toronto raptors":"TOR","utah jazz":"UTA","washington wizards":"WAS","minneapolis lakers":"MNL","syracuse nationals":"SYR","rochester royals":"ROC","philadelphia warriors":"PHW","fort wayne pistons":"FTW","baltimore bullets":"BAL","milwaukee hawks":"MLH","st louis hawks":"STL","cincinnati royals":"CIN","seattle supersonics":"SEA","new jersey nets":"NJN","vancouver grizzlies":"VAN","new orleans hornets":"NOH","new orleans okc":"NOK","washington bullets":"WSB","washington capitols":"WSC","san diego clippers":"SDC","kansas city omaha kings":"KCO","kansas city kings":"KCK","buffalo braves":"BUF","san francisco warriors":"SFW","anderson packers":"AND","tri cities blackhawks":"TCW","chicago stags":"CHS","indianapolis olympians":"INJ"};
  const slug=logoId.replace(/^nba-/i,"").replace(/-\d{4}$/i,"");
  const slugMap={"minneapolis-lakers":"MNL","syracuse-nationals":"SYR","rochester-royals":"ROC","philadelphia-warriors":"PHW","fort-wayne-pistons":"FTW","baltimore-bullets":"BAL","milwaukee-hawks":"MLH","st-louis-hawks":"STL","cincinnati-royals":"CIN","seattle-supersonics":"SEA","new-jersey-nets":"NJN","vancouver-grizzlies":"VAN","new-orleans-hornets":"NOH","new-orleans-oklahoma-city-hornets":"NOK","washington-bullets":"WSB","san-diego-clippers":"SDC","kansas-city-omaha-kings":"KCO","kansas-city-kings":"KCK","buffalo-braves":"BUF","san-francisco-warriors":"SFW","anderson-packers":"AND","tri-cities-blackhawks":"TCW","chicago-stags":"CHS","indianapolis-olympians":"INJ"};
  const abbr=fallbackMap[teamName]||slugMap[slug]||"";
  const historical=abbr&&Number.isFinite(seasonEnd)?`https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/img/team/${abbr}_${seasonEnd}.png`:"";
  const nbaIds={ATL:"1610612737",BOS:"1610612738",BKN:"1610612751",CHA:"1610612766",CHI:"1610612741",CLE:"1610612739",DAL:"1610612742",DEN:"1610612743",DET:"1610612765",GSW:"1610612744",HOU:"1610612745",IND:"1610612754",LAC:"1610612746",LAL:"1610612747",MEM:"1610612763",MIA:"1610612748",MIL:"1610612749",MIN:"1610612750",NOP:"1610612740",NYK:"1610612752",OKC:"1610612760",ORL:"1610612753",PHI:"1610612755",PHX:"1610612756",POR:"1610612757",SAC:"1610612758",SAS:"1610612759",TOR:"1610612761",UTA:"1610612762",WAS:"1610612764"};
  const current=nbaIds[abbr]?`https://cdn.nba.com/logos/nba/${nbaIds[abbr]}/primary/L/logo.svg`:"";
  const espnMap={ATL:"atl",BOS:"bos",BKN:"bkn",CHA:"cha",CHI:"chi",CLE:"cle",DAL:"dal",DEN:"den",DET:"det",GSW:"gs",HOU:"hou",IND:"ind",LAC:"lac",LAL:"lal",MEM:"mem",MIA:"mia",MIL:"mil",MIN:"min",NOP:"no",NYK:"ny",OKC:"okc",ORL:"orl",PHI:"phi",PHX:"phx",POR:"por",SAC:"sac",SAS:"sa",TOR:"tor",UTA:"utah",WAS:"wsh"};
  const espn=espnMap[abbr]?`https://a.espncdn.com/i/teamlogos/nba/500/${espnMap[abbr]}.png`:"";
  const canonicalHistorical=logoId?`https://raw.githubusercontent.com/TGOlson/nba-logos/main/data/img/team/${encodeURIComponent(logoId)}.png`:"";
  const preferCurrent=Number.isFinite(seasonEnd)&&seasonEnd>=2020; const candidates=(Number.isFinite(seasonEnd)?[historical,direct,current,espn,canonicalHistorical]:[direct,current,espn,canonicalHistorical]).filter(Boolean);
  const src=candidates[attempt]||"";
  useEffect(()=>{setAttempt(0);setFailed(false);setProcessedSrc("");setProcessing(false);},[row?.team,row?.Team,row?.season,row?.Season,row?.Logo_ID,row?.logo_id]);

  const processWhiteBackground=img=>{
    try{
      if(!img.naturalWidth||!img.naturalHeight)return false;
      const canvas=document.createElement("canvas");
      canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
      const ctx=canvas.getContext("2d",{willReadFrequently:true});
      if(!ctx)return false;
      ctx.drawImage(img,0,0);
      const image=ctx.getImageData(0,0,canvas.width,canvas.height);
      const d=image.data,w=canvas.width,h=canvas.height;
      const nearWhite=(idx)=>{
        const a=d[idx+3]; if(a<8)return false;
        const r=d[idx],g=d[idx+1],b=d[idx+2];
        const max=Math.max(r,g,b),min=Math.min(r,g,b);
        return min>=224 && max-min<=22 && max>=238;
      };
      const seen=new Uint8Array(w*h);
      const qx=new Int32Array(w*h),qy=new Int32Array(w*h);
      let head=0,tail=0;
      const push=(x,y)=>{const p=y*w+x;if(seen[p])return;seen[p]=1;qx[tail]=x;qy[tail]=y;tail++;};
      for(let x=0;x<w;x++){if(nearWhite(x*4))push(x,0);if(nearWhite(((h-1)*w+x)*4))push(x,h-1);}
      for(let y=0;y<h;y++){if(nearWhite((y*w)*4))push(0,y);if(nearWhite((y*w+w-1)*4))push(w-1,y);}
      while(head<tail){
        const x=qx[head],y=qy[head++];
        const idx=(y*w+x)*4;
        d[idx+3]=0;
        if(x>0 && nearWhite(idx-4))push(x-1,y);
        if(x<w-1 && nearWhite(idx+4))push(x+1,y);
        if(y>0 && nearWhite(idx-w*4))push(x,y-1);
        if(y<h-1 && nearWhite(idx+w*4))push(x,y+1);
      }
      ctx.putImageData(image,0,0);
      const dataUrl=canvas.toDataURL("image/png");
      setProcessedSrc(dataUrl);
      return true;
    }catch{return false;}
  };

  useEffect(()=>{
    if(!src||failed)return;
    setProcessedSrc("");setProcessing(true);
  },[src,failed]);

  if(!src||failed)return <span className="team-logo-fallback" aria-hidden="true">{teamName.split(/\s+/).filter(Boolean).slice(0,3).map(x=>x[0]).join("").toUpperCase()||"NBA"}</span>;
  return <img loading="lazy" decoding="async" fetchPriority="low" className="team-logo" src={processedSrc||src} alt="" crossOrigin="anonymous" onLoad={e=>{if(processedSrc){setProcessing(false);return;}const ok=processWhiteBackground(e.currentTarget);if(!ok){if(attempt<candidates.length-1){setAttempt(x=>x+1);setProcessedSrc("");setProcessing(false);}else{setFailed(true);setProcessing(false);}}else setProcessing(false);}} onError={()=>{if(attempt<candidates.length-1){setAttempt(x=>x+1);setProcessedSrc("");}else setFailed(true);}} />;
}

function Teams() {
  const [search,setSearch]=useState("");
  const [season,setSeason]=useState("");
  const [era,setEra]=useState("");
  const [seasonType,setSeasonType]=useState("Regular Season");
  const [statistic,setStatistic]=useState("Default Overview");
  const [direction,setDirection]=useState("desc");
  const [data,setData]=useState(null);
  const [overview,setOverview]=useState({rORtg:null,rDRtg:null,NRtg:null});
  const [playoffData,setPlayoffData]=useState(null);
  const [database,setDatabase]=useState(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [selected,setSelected]=useState(null);
  const [profile,setProfile]=useState(null);
  const [profileLoading,setProfileLoading]=useState(false);
  const [profileScope,setProfileScope]=useState("season");

  const statOptions=[
    ["rDRtg","Relative DRtg"],["rORtg","Relative ORtg"],["NRtg","NRtg"],["Pace","Pace"],["rPace","Relative Pace"],
    ["ORtg","ORtg"],["DRtg","DRtg"],["TS%","TS%"],["eFG%","eFG%"],
    ["3PAr","3PAr"],["TOV%","TOV%"],["ORB%","ORB%"],["FTr","FTr"],
    ["Opp TOV%","Opponent TOV%"],["Opp eFG%","Opponent eFG%"]
  ];
  const keyMap={"rDRtg":"rdrtg","rORtg":"rortg","NRtg":"nrtg","Pace":"pace","rPace":"rpace","ORtg":"ortg","DRtg":"drtg",
    "TS%":"tspct","eFG%":"efgpct","3PAr":"threepar","TOV%":"tovpct","ORB%":"orbpct","FTr":"ftr","Opp TOV%":"opp_tovpct","Opp eFG%":"opp_efgpct"};
  const labelFor=(key)=>{const x=statOptions.find((v)=>v[0]===key);return x?x[1]:key;};
  const fmt=(v,key)=>{
    if(v==null||!Number.isFinite(Number(v)))return "—";
    const n=Number(v);
    if(["TS%","eFG%","3PAr","TOV%","ORB%","FTr","Opp TOV%","Opp eFG%","rTS%","reFG%","r3PAr","rTOV%","rORB%","rFTr","rOpponent TOV%","rOpponent eFG%"].includes(key)){
      if(String(key).startsWith("r")){const txt=Math.abs(n).toFixed(1);return `${n>0?"+":n<0?"−":""}${txt}%`;}
      return `${(n<=1? n*100:n).toFixed(1)}%`;
    }
    if(["NRtg","rORtg","rDRtg","rPace"].includes(key))return `${n>0?"+":n<0?"−":""}${Math.abs(n).toFixed(1)}`;
    return n.toFixed(1);
  };

  useEffect(()=>{
    setDirection((statistic==="rDRtg" || statistic==="DRtg") ? "asc" : "desc");
  },[statistic]);

  useEffect(()=>{
    let active=true; setLoading(true); setError("");
    if(statistic==="Default Overview" && !search && !season && !era){
      Promise.all([
        getTeamAnalytics("","","Regular Season","rORtg","desc",1000,""),
        getTeamAnalytics("","","Regular Season","rDRtg","asc",1000,""),
        getTeamAnalytics("","","Regular Season","NRtg","desc",1000,"")
      ]).then(([a,b,c])=>{
        if(!active)return;
        setOverview({rORtg:a?.rows||[],rDRtg:b?.rows||[],NRtg:c?.rows||[]});
      }).catch(()=>{if(active)setOverview({rORtg:null,rDRtg:null,NRtg:null});});
    } else {
      setOverview({rORtg:null,rDRtg:null,NRtg:null});
    }
    getTeamAnalytics(search,season,seasonType,statistic==="Default Overview"?"rORtg":statistic,direction,100,era).then((r)=>{
      if(!active)return;
      if(!r||r.ready===false)throw new Error(r&&r.error?r.error:"Team analytics could not be loaded.");
      setData(r);setLoading(false);
    }).catch((e)=>{if(active){setData(null);setError(e?.message||"Team analytics could not be loaded.");setLoading(false);}});
    getTeams(search,season,seasonType,era,statistic==="Default Overview"?"rORtg":statistic,direction).then((r)=>{
      if(active) setDatabase(r);
    }).catch(()=>{if(active)setDatabase(null);});
    getTeamAnalytics(search,season,"Playoffs","rORtg","desc",1000,era).then((r)=>{
      if(active) setPlayoffData(r);
    }).catch(()=>{if(active)setPlayoffData(null);});
    return()=>{active=false;};
  },[search,season,seasonType,statistic,direction,era]);

  const rows=Array.isArray(data?.rows)?data.rows:[];
  const seasons=Array.isArray(data?.seasons)?data.seasons:[];
  const playoffRows=Array.isArray(playoffData?.rows)?playoffData.rows:[];
  const cleanTeamName=(x)=>String(x||"").replace(/\*$/g,"").trim().toLowerCase();
  const successFor=(row)=>{
    if(row?.playoff_status) {
      if(row.playoff_status==="CHAMPION") return "CHAMPION";
      if(row.playoff_status==="MADE FINALS") return "MADE FINALS";
      if(row.playoff_status==="LOST CONFERENCE FINALS") return "LOST CONFERENCE FINALS";
      if(row.playoff_status==="PLAY-IN / MISSED PLAYOFFS") return "PLAY-IN / MISSED PLAYOFFS";
      return row.playoff_status;
    }
    if(row?.playoff_finish) {
      if(row.playoff_finish==="CHAMPION") return "CHAMPION";
      return row.playoff_finish;
    }
    const tm=cleanTeamName(row?.team), se=String(row?.season||"");
    const seasonPO=playoffRows.filter(x=>String(x?.season||"")===se && Number(x?.w??x?.W??0)+Number(x?.l??x?.L??0)>0);
    const po=seasonPO.find(x=>cleanTeamName(x?.team)===tm);
    if(!po)return "MISSED PLAYOFFS";
    return "PLAYOFF DATA PENDING";
  };
  const successBadge=(value)=>{
    const text=String(value||"");
    const key=text.toUpperCase();
    let cls="team-success-standard";
    if(key.includes("CHAMPION")) cls="team-success-champion";
    else if(key.includes("MADE FINALS")) cls="team-success-finals";
    else if(key.includes("LOST CONFERENCE FINALS")) cls="team-success-conference";
    return <span className={`team-success-badge ${cls}`}>{key.includes("CHAMPION") ? <span className="team-success-trophy" aria-hidden="true">🏆</span> : null}{text}</span>;
  };
  const seasonLong=(seasonValue)=>{
    const s=String(seasonValue||"");
    const m=s.match(/^(\d{4})-(\d{2})$/);
    return m ? `${m[1]}-${Number(m[1].slice(0,2)+m[2])}` : s;
  };
  const profilePercentile=(item)=>Number(item?.percentiles?.historical);
  const teamProfileStatRecorded=(key,seasonValue)=>{
    const m=String(seasonValue||"").match(/^(\d{4})-(\d{2,4})$/);
    const endYear=m ? Number(m[1])+(m[2].length===2?1:0) : NaN;
    if(!Number.isFinite(endYear)) return true;
    const starts={"rTS%":1974,"reFG%":1974,"rTOV%":1974,"rORB%":1974,"rFTr":1974,"rOpponent TOV%":1974,"rOpponent eFG%":1974,"r3PAr":1980};
    return starts[key]==null || endYear>=starts[key];
  };
  const profileBuckets=(stats,seasonValue)=>{
    const excluded=new Set();
    const usable=(Array.isArray(stats)?stats:[]).map(st=>({...st,_profilePercentile:profilePercentile(st)})).filter(st=>!excluded.has(st?.key) && teamProfileStatRecorded(st?.key,seasonValue) && Number.isFinite(Number(st?.value)) && Number.isFinite(Number(st?._profilePercentile)));
    const strengths=usable.filter(st=>Number(st._profilePercentile)>50).sort((a,b)=>Number(b._profilePercentile)-Number(a._profilePercentile));
    const weaknesses=usable.filter(st=>Number(st._profilePercentile)<=50).sort((a,b)=>Number(a._profilePercentile)-Number(b._profilePercentile));
    return {strengths,weaknesses};
  };
  const profileItem=(item,type)=> {
    const pct=Number(item._profilePercentile);
    return <div className={`team-profile-strength-item ${type}`}>
      <span className="team-profile-strength-icon" aria-hidden="true">{type==="strength"?"+":"−"}</span>
      <div className="team-profile-strength-copy">
        <div><span className="team-profile-strength-label">{item.label}</span><strong>{fmt(item.value,item.key)}</strong></div>
        <span className="team-profile-strength-percentile" style={percentileTextStyle(pct)}>{Math.round(pct)}%</span>
      </div>
    </div>;
  };
  const meanFor=(key)=>{const v=rows.map(r=>Number(r[key])).filter(Number.isFinite);return v.length?fmt(v.reduce((x,y)=>x+y,0)/v.length,key):"—";};

  const openProfile=(r)=>{
    setSelected(r);setProfile(null);setProfileLoading(true);setProfileScope("season");
    getTeamAnalyticsProfile(r.team,r.season,seasonType,"season").then((p)=>{setProfile(p);setProfileLoading(false);})
      .catch((e)=>{setProfile({ready:false,error:e?.message||"Profile could not be loaded."});setProfileLoading(false);});
  };
  const reloadProfileScope=(scope)=>{
    if(!selected)return;
    setProfileScope(scope);setProfileLoading(true);
    getTeamAnalyticsProfile(selected.team,selected.season,seasonType,scope).then((p)=>{setProfile(p);setProfileLoading(false);})
      .catch((e)=>{setProfile({ready:false,error:e?.message||"Profile could not be loaded."});setProfileLoading(false);});
  };

  const teamPanel=(title,metric,key,direction="desc",sourceRows=null)=>{
    const base=Array.isArray(sourceRows)?sourceRows:rows;
    const list=base.slice().sort((a,b)=>{const av=Number(a[key]),bv=Number(b[key]);return direction==="asc"?av-bv:bv-av;}).slice(0,10);
    return <div className="panel team-panel"><h3>{title}</h3>{list.map((r,i)=><div className="teamrow teamrow-clickable" role="button" tabIndex={0} key={`${title}-${r.team}-${r.season}-${i}`} onClick={()=>openProfile(r)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();openProfile(r);}}}><b>{i+1}</b><div className="logo"><TeamLogo row={r}/></div><div className="team-info"><b>{r.team}</b><small>{r.season}</small><div className="success">{successBadge(successFor(r))}</div></div><div className="team-value">{fmt(r[key],metric)}</div></div>)}</div>;
  };
  return <main className="page">
    <div className="eyebrow">TEAM DATABASE</div><h1>Teams</h1>
    <div className="panel controls"><select className="control" value={statistic} onChange={e=>setStatistic(e.target.value)}><option value="Default Overview">Default Overview</option>{statOptions.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select><select className="control" value={era} onChange={e=>setEra(e.target.value)}><option value="">All Eras</option>{(Array.isArray(data?.eras)?data.eras:[]).map(e=><option key={e.value||e} value={e.value||e}>{e.label||e.value||e}</option>)}</select><select className="control" value={season} onChange={e=>setSeason(e.target.value)}><option value="">All Seasons</option>{seasons.map(e=><option key={e.value||e} value={e.value||e}>{e.label||e.value||e}</option>)}</select><select className="control" value={seasonType} onChange={e=>setSeasonType(e.target.value)}><option>Regular Season</option><option>Playoffs</option></select><select className="control" value={direction} onChange={e=>setDirection(e.target.value)}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select><input className="control" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search teams..."/></div>
    {!loading&&!error&&(statistic==="Default Overview"&&!search&&!season&&!era?<div className="team-panels section">{teamPanel("RELATIVE ORtg","rORtg","rortg","desc",overview.rORtg)}{teamPanel("RELATIVE DRtg","rDRtg","rdrtg","asc",overview.rDRtg)}{teamPanel("NRtg","NRtg","nrtg","desc",overview.NRtg)}</div>:<div className="panel board-table section team-t50-table"><table><thead><tr><th>RANK</th><th>SEED</th><th>TEAM</th><th>SEASON</th><th>{labelFor(statistic)}</th><th>SUCCESS</th></tr></thead><tbody>{rows.slice().sort((a,b)=>{const av=Number(a[keyMap[statistic]||"nrtg"]),bv=Number(b[keyMap[statistic]||"nrtg"]);return direction==="asc"?av-bv:bv-av;}).slice(0,50).map((r,i)=><tr key={`${r.team}-${r.season}-${i}`} className="team-data-row" role="button" tabIndex={0} onClick={()=>openProfile(r)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();openProfile(r);}}}><td>{i+1}</td><td className="team-seed-cell">{(r.seed??r.Seed??r.seed_fallback_rank??r.Rk)!=null?`#${r.seed??r.Seed??r.seed_fallback_rank??r.Rk}`:"—"}</td><td><span className="team-table-link"><span className="team-table-logo"><TeamLogo row={r}/></span>{r.team}</span></td><td>{r.season}</td><td className="team-selected-stat"><strong>{fmt(r[keyMap[statistic]||"nrtg"],statistic)}</strong></td><td>{successBadge(successFor(r))}</td></tr>)}</tbody></table></div>)}
    {loading&&<div className="panel" style={{padding:20}}>Loading team data…</div>}{error&&<div className="comparison-error">{error}</div>}
    {selected&&<div className="team-profile-overlay" onClick={()=>setSelected(null)}>
      <div className={`team-profile-card team-profile-concept ${String(successFor(profile?.row||selected)||"").toUpperCase().includes("CHAMPION")?"team-profile-champion":""}`} onClick={e=>e.stopPropagation()}>
        <button className="team-profile-close" onClick={()=>setSelected(null)} aria-label="Close team profile">×</button>
        {profileLoading?<div className="explorer-loading">Loading team profile…</div>:profile?.ready?(()=>{
          const buckets=profileBuckets(profile.stats,profile.season);
          const status=successFor(profile.row||selected);
          return <>
            <div className="team-profile-concept-header">
              <div className="team-profile-concept-logo"><TeamLogo row={selected}/></div>
              <div className="team-profile-concept-title"><span className="section-label">TEAM PROFILE</span><h2>{seasonLong(profile.season)} {profile.team}</h2><p>{profile.season_type}</p></div>
              <div className="team-profile-concept-status">{successBadge(status)}</div>
            </div>
            <div className="team-profile-strength-grid">
              <section className="team-profile-strength-column"><h3>Strengths</h3>{buckets.strengths.map(st=>profileItem(st,"strength"))}</section>
              <section className="team-profile-strength-column"><h3>Weaknesses</h3>{buckets.weaknesses.map(st=>profileItem(st,"weakness"))}</section>
            </div>
          </>;
        })():<div className="comparison-error">{profile?.error||"Team profile could not be loaded."}</div>}
      </div>
    </div>}
  </main>;
}

function Methodology() {
  return <PageShell eyebrow="HOW IT WORKS" title="Methodology" description="Transparent definitions for the PER-75 statistical system.">
    <div className="method-grid">
      {[
        ["PER-75", "Production is normalized to 75 possessions to make scoring and counting-stat volume more comparable across eras."],
        ["Percentile Context", "Every statistic can be viewed relative to the player's season, era, or the full historical qualified population."],
        ["5-Year Peak", "The peak is the best five qualifying regular-season seasons contained within a maximum six-calendar-season span. One skipped/non-qualifying season is allowed; two consecutive skipped seasons are not. The five seasons are aggregated from underlying data rather than averaged as season averages."],
        ["Six Dimensions", "The dominance profile organizes 38 dominance statistics into six configurable performance categories."],
        ["Context", "Usage, shot profile, availability/foul context, and related descriptive statistics remain separate from the Dominance Index."]
      ].map(([t,d])=><div className="method-card" key={t}><span>{t}</span><h2>{t}</h2><p>{d}</p></div>)}
    </div>
  </PageShell>;
}


function PlayerSearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      searchPlayers(query).then((data) => setResults(data.players || [])).catch(() => setResults([]));
    }, 180);
    return () => clearTimeout(timer);
  }, [query]);

  return <PageShell eyebrow="PLAYER DATABASE" title="Players" description="Search the complete historical player universe.">
    <div className="search-panel">
      <Search size={20}/>
      <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search 4,896 players..." />
    </div>
    <div className="player-results">
      {results.map((p) => (
        <Link className="player-result" key={p.player_id || p.player_name}
           onMouseEnter={()=>prefetchPlayerProfile(p.player_id || p.player_name,"hover")}
           onPointerDown={()=>prefetchPlayerProfile(p.player_id || p.player_name,"full")}
           to={`/players/${encodeURIComponent(p.player_id || p.player_name)}`}>
          <div className="result-avatar"><Headshot player={p} name={playerDisplayName(p.player_name)} /></div>
          <div><strong>{playerDisplayName(p.player_name)}</strong><small>{p.player_id || "Canonical identity"}</small></div>
          <ChevronRight size={16}/>
        </Link>
      ))}
      {query && !results.length && <div className="empty-search">No results, or the local API is not running.</div>}
    </div>
  </PageShell>;
}


function SpiderChart({ axes, title, labelRadius = 248, configurable = false }) {
  // Keep the normal profile spider unchanged. The configurable version uses a
  // larger SVG coordinate space so the radar stays at least as large while
  // giving its statistic labels substantially more room around the perimeter.
  const size = configurable ? 1100 : 500;
  const center = size / 2;
  const radius = configurable ? 390 : 180;
  const count = axes.length;
  if (!count) return <Placeholder title="Spider data unavailable" text="No axes were returned for this player-season."/>;

  const point = (i, value, r = radius) => {
    const angle = (-Math.PI / 2) + (i * 2 * Math.PI / count);
    const rr = r * Math.max(0, Math.min(100, Number(value) || 0)) / 100;
    return [center + Math.cos(angle) * rr, center + Math.sin(angle) * rr];
  };
  const pointAtRadius = (i, r) => {
    const angle = (-Math.PI / 2) + (i * 2 * Math.PI / count);
    return [center + Math.cos(angle) * r, center + Math.sin(angle) * r];
  };
  const polygon = (r, values) => values.map((v,i) => point(i,v,r)).map(([x,y]) => `${x},${y}`).join(" ");
  const grid = [20,40,60,80,100];
  // IMPORTANT: labels use a true SVG radius. The old implementation passed
  // the radius through `point()`, which interprets its second argument as a
  // percentile and clamps it to 100. That silently put every label at the
  // radar perimeter no matter how large labelRadius was.
  const effectiveLabelRadius = configurable ? 405 : labelRadius;

  return <div className={`spider-wrap${configurable ? " spider-wrap-configurable" : ""}`}> 
    {!configurable && <div className="spider-title">{title}</div>}
    <svg viewBox={`0 0 ${size} ${size}`} className="spider-svg" role="img" aria-label={title}>
      {configurable && <text x={center} y={55} textAnchor="middle" className="spider-config-player-name-svg">{title}</text>}
      {grid.map(level => {
        const pts = axes.map((_,i) => {
          const [x,y] = point(i,100, radius * level/100);
          return `${x},${y}`;
        }).join(" ");
        return <polygon key={level} points={pts} className="spider-grid"/>;
      })}
      {axes.map((a,i) => {
        const [x,y] = point(i,100);
        return <line key={`line-${i}`} x1={center} y1={center} x2={x} y2={y} className="spider-axis"/>;
      })}
      {grid.map(level=>{const y=center-radius*level/100;return <text key={`scale-${level}`} x={center+10} y={y+4} textAnchor="start" className="spider-scale-label">{level}</text>;})}
      <text x={center+10} y={center+14} textAnchor="start" className="spider-scale-label">0</text>
      <polygon points={polygon(radius, axes.map(a => a.value))} className="spider-fill"/>
      <polyline points={polygon(radius, axes.map(a => a.value))} className="spider-line"/>
      {axes.map((a,i) => {
        const [x,y] = point(i, a.value);
        const [lx,ly] = pointAtRadius(i, effectiveLabelRadius);
        const anchor = lx < center - 8 ? "end" : lx > center + 8 ? "start" : "middle";
        return <g key={`label-${i}`}>
          <circle cx={x} cy={y} r="3.5" className="spider-dot"/>
          <text x={lx} y={ly} textAnchor={anchor} className="spider-label">{a.axis}</text>
        </g>;
      })}
    </svg>
    <div className="spider-scale">Percentile scale · 0–100</div>
  </div>;
}

function SpiderAxisSelector({ registry, selected, setSelected }) {
  const [filter, setFilter] = useState("");
  const available=(registry||[]).filter(s=>{
    const stat=String(s.statistic||s.Statistic||s.Stat||"");
    return !filter || stat.toLowerCase().includes(filter.toLowerCase());
  });
  const toggle=(stat)=>{
    if(selected.includes(stat)) setSelected(selected.filter(x=>x!==stat));
    else setSelected([...selected,stat]);
  };
  return <div className="axis-selector">
    <div className="axis-selector-head"><div><strong>Custom axes</strong><small>Choose any number of the registered statistics, including Context statistics.</small></div><span>{selected.length}/{registry.length || 46}</span></div>
    <input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter statistics..." />
    <div className="axis-chips">{available.map((s,i)=>{
      const stat=String(s.statistic||s.Statistic||s.Stat||""); if(!stat) return null;
      const active=selected.includes(stat);
      return <button key={stat+i} className={active?"axis-chip active":"axis-chip"} onClick={()=>toggle(stat)}>{active?"✓ ":""}{stat}</button>;
    })}</div>
  </div>;
}

class PlayerProfileErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error) { console.error("Player profile render error", error); }
  render() {
    if (this.state.error) return <PageShell eyebrow="PLAYER PROFILE" title="Profile data error"><Placeholder title="This player-season could not be rendered" text={`Unexpected profile render error: ${this.state.error?.message || "Unknown error"}. The error is isolated to this view; refresh or select another season.`}/></PageShell>;
    return this.props.children;
  }
}

function PlayerProfile() {
  const { playerId } = useParams();
  const location = useLocation();
  const initialPlayer = location.state?.player || null;
  const id = playerId;
  const [data,setData]=useState(null),[careerData,setCareerData]=useState(null),[careerDataSeasonType,setCareerDataSeasonType]=useState(""),[season,setSeason]=useState("Career"),[seasonType,setSeasonType]=useState("Regular Season"),[cardLifted,setCardLifted]=useState(false),[cardFlipped,setCardFlipped]=useState(false);
  const [seasonRows,setSeasonRows]=useState([]),[spiderData,setSpiderData]=useState(null),[seasonSpiderData,setSeasonSpiderData]=useState(null),[selectedSeason,setSelectedSeason]=useState(""),[registry,setRegistry]=useState([]);
  const [selectedStats,setSelectedStats]=useState([]),[spiderConfigOpen,setSpiderConfigOpen]=useState(false),[error,setError]=useState("");
  const [profileLoading,setProfileLoading]=useState(true),[profileLoadStage,setProfileLoadStage]=useState("Loading player profile…");
  const profileRequestRef=useRef(0),profileAbortRef=useRef(null),profileCacheRef=useRef(new Map()),seasonCacheRef=useRef(new Map()),canonicalHeadshotRef=useRef("");
  // Once a valid payload has rendered for an exact profile context, never let a
  // later stale/negative response replace it. This is especially important for
  // Regular Season 5-Year Peak, where background warmups can finish after the
  // visible request and may otherwise overwrite a valid peak with found:false.
  const validProfileContextRef=useRef(new Set());
  const profileScrollRef=useRef(null),profileTableScrollRefs=useRef([]),profileHeaderRef=useRef(null);
  const spiderCacheRef=useRef(new Map());
  const seasonSpiderContextRef=useRef({key:"",data:null});
  const bundleReadyRef=useRef(new Set());
  const pendingSpiderRef=useRef(new Map());

  // Keep the last known spider context isolated by season type. A playoff
  // transition must never temporarily reuse the regular-season spider, even
  // while the new payload is arriving. The profile card itself remains visible
  // during the transition, but its SDI header is switched only from the exact
  // requested context.
  const spiderContextRef=useRef({key:"",data:null});
  const warmPlayoffContext=()=>{
    if(!id)return;
    prefetchPlayerProfile(id,"playoffs");
  };
  const warmRegularContext=()=>{
    if(!id)return;
    prefetchPlayerProfile(id,"full");
  };

  useEffect(()=>{
    if(!id)return;
    const requestId=++profileRequestRef.current;
    profileAbortRef.current?.abort();
    const controller=new AbortController(); profileAbortRef.current=controller;
    const requestedContext=season==="Career"?"Career":season==="5-Year Peak"?"Peak":"Historical";
    const cacheKey=`${id}|${seasonType}|${season}|${requestedContext}`;
    const spiderKey=`${id}|${seasonType}|${season}|${requestedContext}`;
    spiderContextRef.current={key:spiderKey,data:null};
    if(!selectedSeason) seasonSpiderContextRef.current={key:"",data:null};
    setError("");setProfileLoadStage("");setSelectedSeason("");
    // Never blank a populated profile while another view is being fetched.
    // The previous implementation reset the rendered data to null here, which
    // produced the visible NQ frame during every cache miss. Keep the current
    // payload on screen until the replacement payload is ready.
    const cached=profileCacheRef.current.get(cacheKey);
    if(cached){
      if(cached.profile) setData(cached.profile);
      if(cached.spider){
        spiderContextRef.current={key:spiderKey,data:cached.spider};
        setSpiderData(cached.spider);
      }
      setProfileLoading(false);setProfileLoadStage("");
      // Do NOT return here. A cached profile and a cached spider are separate
      // payloads. If the profile was warmed but its exact SDI spider was not,
      // the old early-return path skipped the spider request entirely. That is
      // what caused Career/Peak SDI to disappear after context switches.
    }
    if(!cached){
    // The profile payload is the critical path. Do not hold the Career row or
    // the rest of the profile behind the optional spider request. The spider
    // is intentionally allowed to arrive independently.
    getPlayerProfileBundle(id,seasonType,season,requestedContext,controller.signal)
      .then(profileResult=>{
        if(requestId!==profileRequestRef.current)return;
        if(!profileResult)throw new Error("Player profile response was empty.");
        // A Peak payload may already have rendered successfully while a stale
        // duplicate/background request is still finishing. Never replace that
        // valid payload with a later found:false response for the same exact
        // context. This is a render-state guard only; it does not alter data or
        // the canonical Peak calculation.
        // A valid profile payload is identified by its actual player/profile
        // objects, not only by the optional `found` flag. Some canonical Peak
        // responses are enriched payloads whose `found` field is absent, while
        // a later duplicate request can return the generic found:false shell.
        // Once this exact context has produced a real profile, that negative
        // response must never replace it.
        const hasValidProfilePayload=Boolean(
          profileResult?.player &&
          profileResult?.profile &&
          typeof profileResult.profile==="object"
        );
        if(profileResult?.found===false && validProfileContextRef.current.has(cacheKey)){
          return;
        }
        if(profileResult?.found===true || hasValidProfilePayload){
          validProfileContextRef.current.add(cacheKey);
        }
        setData(profileResult);
        // When the initial view is Career, the main profile response already
        // contains the career aggregate. Use it immediately instead of waiting
        // for the secondary Career request below.
        if(season==="Career"){ setCareerData(profileResult); setCareerDataSeasonType(seasonType); }
        setProfileLoading(false);setProfileLoadStage("");
        const cached=profileCacheRef.current.get(cacheKey)||{};
        profileCacheRef.current.set(cacheKey,{...cached,profile:profileResult});
        // Once the visible profile is ready, quietly warm the alternate
        // season/peak contexts. This removes the wait from the user's next
        // transition without adding contention to the initial render.
      })
      .catch(e=>{if(e?.name==="AbortError"||requestId!==profileRequestRef.current)return;setProfileLoading(false);setProfileLoadStage("");setError(e.message||"Unable to load player profile.");});
    }
    const cachedSpider=spiderCacheRef.current.get(spiderKey);
    if(cachedSpider){
      // Restore the exact requested context immediately. The bundle readiness
      // gate is only relevant to table synchronization; it must never suppress
      // an already-complete SDI payload when returning from another context.
      spiderContextRef.current={key:spiderKey,data:cachedSpider};
      setSpiderData(cachedSpider);
      if(season==="Career" && !bundleReadyRef.current.has(`${id}|${seasonType}`)) pendingSpiderRef.current.set(spiderKey,cachedSpider);
      if(!data && initialPlayer) setData(prev=>prev||{player:initialPlayer,profile:{},statistic_registry:registry});
    }
    // Do not tie the SDI request to the profile/table request. The spider is the
    // lightweight, navigation-critical payload and must be allowed to populate
    // the header even when the large season-bundles request takes several seconds.
    getPlayerSpider(id,season,requestedContext,[],seasonType)
      .then(spiderResult=>{
        spiderCacheRef.current.set(spiderKey,spiderResult);
        if(requestId!==profileRequestRef.current || spiderContextRef.current.key!==spiderKey)return;
        if(season==="Career" && !bundleReadyRef.current.has(`${id}|${seasonType}`)){
          pendingSpiderRef.current.set(spiderKey,spiderResult);
        } else {
          spiderContextRef.current={key:spiderKey,data:spiderResult};
          setSpiderData(spiderResult);
        }
        setData(prev=>prev||((initialPlayer)?{player:initialPlayer,profile:{},statistic_registry:registry}:prev));
        const cached=profileCacheRef.current.get(cacheKey)||{};
        profileCacheRef.current.set(cacheKey,{...cached,spider:spiderResult});
      })
      .catch(e=>{if(e?.name!=="AbortError")console.warn("Profile spider unavailable",e);});
    return()=>controller.abort();
  },[id,season,seasonType]);

  useEffect(()=>{
    const known=initialPlayer?.headshot_url || data?.player?.headshot_url || data?.player?.Headshot_URL || "";
    if(known) canonicalHeadshotRef.current=known;
  },[initialPlayer?.headshot_url,data?.player?.headshot_url,data?.player?.Headshot_URL]);

  useEffect(()=>{getStatisticRegistry().then(r=>setRegistry(r.statistics||[])).catch(()=>setRegistry([]));},[]);
  useEffect(()=>{setCardLifted(true);const t=setTimeout(()=>setCardFlipped(true),150);return()=>clearTimeout(t);},[id]);

  const seasonRowsCacheRef=useRef(new Map());
  useEffect(()=>{
    if(!id)return;
    let active=true;
    const bundleKey=`${id}|${seasonType}`;
    const cachedRows=seasonRowsCacheRef.current.get(bundleKey);
    // Keep the previously proven instant-switch behavior: once a season-type
    // bundle has been seen, render its rows immediately while the background
    // request revalidates. Never clear an already-rendered table on a transient
    // request failure.
    if(cachedRows?.rows?.length){
      bundleReadyRef.current.add(bundleKey);
      setSeasonRows(cachedRows.rows);
      if(cachedRows.career){ setCareerData(cachedRows.career); setCareerDataSeasonType(seasonType); }
      const cachedCareerSpiderKey=`${id}|${seasonType}|Career|Career`;
      const pendingCached=pendingSpiderRef.current.get(cachedCareerSpiderKey) || spiderCacheRef.current.get(cachedCareerSpiderKey);
      if(pendingCached){
        spiderContextRef.current={key:cachedCareerSpiderKey,data:pendingCached};
        setSpiderData(pendingCached);
        pendingSpiderRef.current.delete(cachedCareerSpiderKey);
      }
      setProfileLoadStage("");
    } else {
      setProfileLoadStage("Loading season-by-season statistics…");
    }
    const loadBundles=()=>getPlayerSeasonBundles(id,seasonType).then(result=>{
      if(!active)return;
      const rows=Array.isArray(result?.rows)?result.rows:[];
      if(rows.length){
        seasonRowsCacheRef.current.set(bundleKey,{rows,career:result?.career||null});
        setSeasonRows(rows);
      }
      if(result?.career){ setCareerData(result.career); setCareerDataSeasonType(seasonType); }
      bundleReadyRef.current.add(bundleKey);
      const careerSpiderKey=`${id}|${seasonType}|Career|Career`;
      const pending=pendingSpiderRef.current.get(careerSpiderKey) || spiderCacheRef.current.get(careerSpiderKey);
      if(pending){
        spiderContextRef.current={key:careerSpiderKey,data:pending};
        setSpiderData(pending);
        pendingSpiderRef.current.delete(careerSpiderKey);
      }
      setProfileLoadStage("");

      // Once the initial regular-season bundle is actually ready, the browser
      // is no longer competing with it. Warm the exact playoff bundle/profile/
      // spider and peak contexts in the background so later context switches
      // are cache hits instead of multi-second waits. All requests use the same
      // canonical endpoints and shared request cache; no data is recalculated.
      if(seasonType==="Regular Season") {
        // The regular-season bundle is now complete, so immediately warm the
        // already-locked playoff bundle/profile/spider in the background. This
        // moves the playoff transition off the click path without changing any
        // data, formulas, sources, or rendered regular-season values. The shared
        // API prefetch map dedupes this work with a later hover/click.
        prefetchPlayerProfile(id,"playoffs");
      }
    }).catch(()=>{if(active)setProfileLoadStage("");});

    // Start the table request immediately alongside the exact profile/spider
    // requests. There is no artificial delay that can let SDI visibly arrive
    // ahead of the season rows. The header still waits for the exact spider
    // payload before showing any SDI text.
    loadBundles();
    return()=>{active=false;};
  },[id,seasonType]);

  useEffect(()=>{
    if(!id||!selectedSeason)return;
    const controller=new AbortController();
    const seasonSpiderKey=`${id}|${seasonType}|${selectedSeason}|Season`;
    seasonSpiderContextRef.current={key:seasonSpiderKey,data:null};

    // Playoff individual-season rows already carry the canonical SDI category
    // axes in their season-bundle payload. Use those axes directly, exactly as
    // the regular-season response-ready cache does, instead of making a second
    // /spider request. This keeps the playoff individual-season SDI path
    // identical in behavior to the working regular-season path and avoids a
    // second expensive calculation on every playoff row click.
    const selectedRow=seasonRows.find(r=>String(r?.season||"")===String(selectedSeason));
    const bundleAxes=selectedRow?.bundle?.sdi_category_axes
      || selectedRow?.bundle?.profile?.sdi_category_axes
      || selectedRow?.sdi_category_axes
      || selectedRow?.bundle?.spider?.category_axes
      || null;
    const bundleSeasonType=selectedRow?.bundle?.season_type || selectedRow?.bundle?.profile?.Season_Type || selectedRow?.season_type || seasonType;
    if(seasonType==="Playoffs" && String(bundleSeasonType).toLowerCase().includes("playoff") && Array.isArray(bundleAxes) && bundleAxes.length){
      const payload={
        found:true,
        player:{player_id:id,player_name:selectedRow?.bundle?.player?.player_name || selectedRow?.bundle?.player?.Player_Name || id},
        season:selectedSeason,
        context:"Season",
        available_contexts:{Season:true,Era:false,Historical:false,Career:false},
        category_axes:bundleAxes,
        stat_axes:[]
      };
      spiderCacheRef.current.set(`${id}|spider|${seasonType}|${selectedSeason}`,payload);
      seasonSpiderContextRef.current={key:seasonSpiderKey,data:payload};
      setSeasonSpiderData(payload);
      return()=>controller.abort();
    }

    const cachedSeasonSpider=spiderCacheRef.current.get(`${id}|spider|${seasonType}|${selectedSeason}`);
    if(cachedSeasonSpider){
      seasonSpiderContextRef.current={key:seasonSpiderKey,data:cachedSeasonSpider};
      setSeasonSpiderData(cachedSeasonSpider);
      return()=>controller.abort();
    }
    getPlayerSpider(id,selectedSeason,"Season",[],seasonType,controller.signal)
      .then(r=>{spiderCacheRef.current.set(`${id}|spider|${seasonType}|${selectedSeason}`,r); if(seasonSpiderContextRef.current.key===seasonSpiderKey){seasonSpiderContextRef.current={key:seasonSpiderKey,data:r};setSeasonSpiderData(r);}}).catch(()=>{});
    return()=>controller.abort();
  },[id,selectedSeason,seasonType,seasonRows]);

  useEffect(()=>{
    if(!spiderConfigOpen||selectedStats.length<3)return;
    const controller=new AbortController();
    getPlayerSpider(id,selectedSeason||season,(selectedSeason?"Historical":season==="Career"?"Career":"Historical"),selectedStats,seasonType,controller.signal).then(r=>setSpiderData(r)).catch(()=>{});
    return()=>controller.abort();
  },[id,selectedSeason,season,seasonType,spiderConfigOpen,selectedStats.join("|")]);

  const p={...(initialPlayer||{}),...(data?.player||{})}; if(!p.player_id)p.player_id=id; if(!p.player_name)p.player_name=id; if(!p.headshot_url)p.headshot_url=canonicalHeadshotRef.current || initialPlayer?.headshot_url || ""; const profile=data?.profile||{};
  // Isolated V23 fix: preserve the V16 headshot behavior everywhere except Kareem's 5-Year Peak, where the added PNG is authoritative.
  const profileHeadshotPlayer=(String(id)==="P002997" && season==="5-Year Peak") ? {...p,headshot_url:"/player_headshots_final_v1/P002997.png"} : p;
  const normalizeStat=v=>String(v??"").toLowerCase().replace(/[^a-z0-9]/g,"");
  const statEntries=(data?.statistic_registry||registry||[]).map(e=>typeof e==="object"?String(e.statistic||e.Statistic||e.Stat||e.stat_name||e.name||""):String(e)).filter(Boolean);
  const configurableExcludedStats=new Set(["ORtg","DRtg","rORtg","rDRtg","NRtg","rORTG","rDRTG"]);
  const configurableStatEntries=statEntries.filter(stat=>!configurableExcludedStats.has(stat));
  const statLookup=Object.fromEntries(statEntries.map(x=>[normalizeStat(x),x]));
  const resolveStat=(wanted)=>statLookup[normalizeStat(wanted)]||wanted;
  const profileAliases={"rORTG":"WOWY_Offense","rDRTG":"WOWY_Defense","NRtg":"WOWY_Net","REB_per75":"TRB_per75","OREB_per75":"ORB_per75","DREB_per75":"DRB_per75","WS48":"WS/48","WS_per48":"WS/48"};
  const resolveProfileStat=(wanted)=>resolveStat(profileAliases[wanted]||wanted);
  const per75Names=["PTS_per75","REB_per75","AST_per75","rTS","TS_pct","TOV_per75","AST_TOV","STL_per75","BLK_per75","2P_pct","3P_pct","FT_pct","FTA_per75","2PA_per75","3PA_per75","OREB_per75","DREB_per75","PF_per75"].map(resolveProfileStat);
  const advancedNames=["WOWY_Net","WOWY_Offense","WOWY_Defense","FTr","3PAr","AST_pct","TOV_pct","OREB_pct","DREB_pct","STL_pct","BLK_pct","BPM","WS48","PER","OBPM","DBPM","OWS","DWS","VORP"].map(resolveProfileStat);
  const fmtName=x=>{const n=String(x);const aliases={"TRB_per75":"REB/75","ORB_per75":"OREB/75","DRB_per75":"DREB/75","WOWY_Offense":"WOWY Offense","WOWY_Defense":"WOWY Defense","WOWY_Net":"WOWY Net","WS/48":"WS/48"};return aliases[n]||n.replaceAll("_per75","/75").replaceAll("_pct","%").replace("AST_TOV","AST:TOV");};
  const readBundleStat=(bundle,stat)=>{
    const vals=bundle?.statistic_values||bundle?.playoff_statistics||{}; const k=Object.keys(vals).find(x=>normalizeStat(x)===normalizeStat(stat));
    if(k)return vals[k];
    const pr=bundle?.profile||{}; const pk=Object.keys(pr).find(x=>normalizeStat(x)===normalizeStat(stat));
    return pk?pr[pk]:null;
  };
  const percentileFromBundle=(bundle,stat)=>{
    const rows=bundle?.percentiles||[];
    const row=rows.find(r=>normalizeStat(r?.Statistic||r?.statistic||r?.Stat||r?.stat_name||"")===normalizeStat(stat));
    if(!row)return null;
    // Prefer the explicitly named season percentile. Do not rely on object
    // key order because playoff rows also contain Era/Historical percentiles.
    const preferred=["Season_Percentile","SeasonPercentile","Season_Pctl","SeasonPctl","Percentile","percentile"];
    const k=preferred.find(x=>row[x]!=null) || Object.keys(row).find(x=>/percentile/i.test(x));
    return k?row[k]:null;
  };
  const formatValue=(v,stat="")=>{
    if(v==null||v===""||!Number.isFinite(Number(v)))return"—";
    const n=Number(v);
    if(String(stat)==="G"||String(stat).toLowerCase()==="games"||String(stat).toLowerCase()==="games_played")return String(Math.round(n));
    const pct=/(_pct$|%$|^FTr$|^3PAr$)/.test(String(stat));
    const signed=["WOWY_Net","WOWY_Offense","WOWY_Defense","Relative_NRtg"].some(k=>String(stat).toLowerCase()===k.toLowerCase()); const text=(String(stat)==="FTr"||String(stat)==="3PAr"||String(stat)==="AST_TOV")?n.toFixed(2):((String(stat)==="WS/48"||String(stat)==="WS48"||String(stat)==="WS_per48")?n.toFixed(2):n.toFixed(1)); if(String(stat)==="BLK_pct")return `${n.toFixed(1)}%`; return pct?`${(n<=1?n*100:n).toFixed(1)}%`:signed&&n>0?`+${text}`:text;
  };
  const pctClass=v=>{const n=Number(v);return n>=90?"elite":n>=75?"verygood":n>=40?"average":n>=20?"below":"poor";};
  const pctSpan=(v)=>v==null?<span className="pct percentile-badge pct-nq">NQ</span>:<span className={`pct percentile-badge ${pctClass(v)}`} style={percentileTextStyle(v)}>{Math.round(Number(v))}%</span>;
  const sdiBoxStyle=v=>{
    if(v==null||!Number.isFinite(Number(v))) return {
      borderColor:"#0b0d10",
      boxShadow:"none"
    };
    const n=Math.max(0,Math.min(100,Number(v)));
    const midpoint=68;
    const stops=n<=midpoint?[[174,48,66],[247,245,241],n/midpoint]:[[247,245,241],[102,185,232],(n-midpoint)/(100-midpoint)];
    const [a,b,t]=stops;
    const rgb=a.map((x,i)=>Math.round(x+(b[i]-x)*t));
    return {
      borderColor:`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`,
      boxShadow:`0 4px 12px rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, .48), 0 0 0 1px rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, .20)`
    };
  };
  const sdiContextLabel=()=>{
    if(selectedSeason){
      const m=/^(\d{4})-(\d{2})$/.exec(String(selectedSeason));
      const label=m?`${m[1]}-${Number(m[1])+1} Season`:String(selectedSeason);
      return <><span>SDI PERCENTILE:</span> <b>{label}</b></>;
    }
    const label=season==="Career"?"Career":season==="5-Year Peak"?"5-Year Peak":season;
    return <><span>SDI PERCENTILE:</span> <b>{label}</b></>;
  };
  const rowsForTable=[
    ...seasonRows,
  ];
  const careerBundleMatchesContext=careerData && String(careerDataSeasonType||"").toLowerCase()===String(seasonType||"").toLowerCase();
  const directCareerMatchesContext=data && String(data?.season_type||data?.Season_Type||"").toLowerCase()===String(seasonType||"").toLowerCase();
  const summaryRows=[
    {season:"CAREER",bundle:careerBundleMatchesContext?careerData:(season==="Career"&&directCareerMatchesContext?data:null)},
    {season:"5-YEAR PEAK",bundle:season==="5-Year Peak"?data:null}
  ].filter(x=>x.bundle);
  const displayRows=[...summaryRows,...rowsForTable];
  const sixLabels=["SCORING","EFFICIENCY","ENGINE / PLAYMAKING","REBOUNDING","DEFENSE","IMPACT / VALUE"];
  // Playoff SDI is a four-category model. Impact / Value is WOWY-based and
  // Defense is historically inconsistent because STL/BLK tracking is
  // incomplete, so neither category is rendered for playoff SDI.
  const sdiLabels=seasonType==="Playoffs"?sixLabels.slice(0,4):sixLabels;
  const axisMap={"Scoring Volume":"SCORING","Scoring":"SCORING","Scoring Efficiency":"EFFICIENCY","Efficiency":"EFFICIENCY","Creation & Playmaking":"ENGINE / PLAYMAKING","Creation / Playmaking":"ENGINE / PLAYMAKING","Creation and Playmaking":"ENGINE / PLAYMAKING","Engine / Playmaking":"ENGINE / PLAYMAKING","Rebounding":"REBOUNDING","Defense":"DEFENSE","Impact & Value":"IMPACT / VALUE","Impact / Value":"IMPACT / VALUE"};
  const normalizeSdiAxis=v=>String(v??"").toLowerCase().replace(/&/g,"and").replace(/[^a-z0-9]/g,"");
  const sdiAxisAliases={scoring:"SCORING",scoringvolume:"SCORING",efficiency:"EFFICIENCY",scoringefficiency:"EFFICIENCY",engineplaymaking:"ENGINE / PLAYMAKING",creationplaymaking:"ENGINE / PLAYMAKING",creationandplaymaking:"ENGINE / PLAYMAKING",rebounding:"REBOUNDING",defense:"DEFENSE",impactvalue:"IMPACT / VALUE"};
  // Spider category payloads use `value` for the canonical percentile score.
  // Accept explicit percentile aliases too, but never invent a value.
  const axisValue=a=>a?.percentile??a?.Percentile??a?.score_percentile??a?.value??null;
  const activeSpiderKey=`${id}|${seasonType}|${selectedSeason||season}|${selectedSeason?"Season":season==="Career"?"Career":"Peak"}`;
  const selectedSeasonRow=selectedSeason?seasonRows.find(r=>String(r?.season||"")===String(selectedSeason)):null;
  const selectedSeasonBundleSdi=(seasonType==="Playoffs" && Array.isArray(selectedSeasonRow?.bundle?.sdi_category_axes) && selectedSeasonRow.bundle.sdi_category_axes.length)
    ? {found:true,season:selectedSeason,context:"Season",category_axes:selectedSeasonRow.bundle.sdi_category_axes,stat_axes:[]}
    : null;
  const activeSpiderData=selectedSeason
    ? (selectedSeasonBundleSdi || (seasonSpiderContextRef.current.key===activeSpiderKey ? seasonSpiderContextRef.current.data : spiderCacheRef.current.get(`${id}|spider|${seasonType}|${selectedSeason}`) || null))
    : (spiderContextRef.current.key===activeSpiderKey ? spiderContextRef.current.data : spiderCacheRef.current.get(activeSpiderKey) || null);
  const sdiAxes=(activeSpiderData?.category_axes||[]).map(a=>{const raw=a.axis??a.label??"";const mapped=axisMap[raw]||sdiAxisAliases[normalizeSdiAxis(raw)]||String(raw).toUpperCase();return {...a,value:axisValue(a),label:mapped};}).filter(a=>a.value!=null);
  // NQ is a data-state, not a loading state. Until the exact requested spider
  // payload exists, render no SDI text at all. Once it exists, a missing axis
  // is allowed to display NQ because that then reflects the canonical payload.
  const sdiReady=!!activeSpiderData;
  const sdiValue=label=>{const a=sdiAxes.find(x=>x.label===label)||sdiAxes.find(x=>String(x.axis||"").toUpperCase().includes(label.split("/")[0].trim()));return a?.value??null;};
  const sdiFixedAxes=sdiLabels.map(label=>({axis:label,label,value:sdiValue(label)??0}));
  const radarPoints=(axes,size=155)=>{const n=Math.max(axes.length,1),c=size/2,r=size===240?91:size*.42;return axes.map((a,i)=>{const angle=-Math.PI/2+i*2*Math.PI/n;const rr=r*Math.max(0,Math.min(100,Number(a.value)||0))/100;return `${c+Math.cos(angle)*rr},${c+Math.sin(angle)*rr}`;}).join(" ");};
  const defaultStats=selectedStats.length?selectedStats:statEntries.slice(0,6);
  const customAxes=(activeSpiderData?.stat_axes||[]).filter(a=>a.value!=null);
  const flip=()=>{if(cardFlipped)return;setCardLifted(true);setTimeout(()=>setCardFlipped(true),90);};
  const gamesFor=(row)=>{if(row.season==="5-YEAR PEAK"){const prof=row.bundle?.profile||{};const start=Number(prof.Peak_Start_Year??row.bundle?.peak?.start);const end=Number(prof.Peak_End_Year??row.bundle?.peak?.end);if(Number.isFinite(start)&&Number.isFinite(end)){const yy=y=>String(y).slice(-2);return `${yy(start)}-${yy(end)}`;}}return readBundleStat(row.bundle,"G") ?? readBundleStat(row.bundle,"Games") ?? null;};
  const seasonCell=(row,stat)=>{
    let value=readBundleStat(row.bundle,stat),pct=percentileFromBundle(row.bundle,stat);
    // Pre-1979-80 NBA seasons had no recorded 3-point attempts, so 2PA is
    // literally identical to FGA. Enforce that at the final display layer so
    // historical 2PA/75 can never disappear because an upstream legacy field
    // is blank. Its percentile is likewise the FGA/75 percentile.
    const y=/^(\d{4})-\d{2}$/.exec(String(row.season||""));
    const historicalPre3=(y && Number(y[1])<1979);
    if(normalizeStat(stat)==="2paper75" && historicalPre3){
      const fga=readBundleStat(row.bundle,"FGA_per75");
      const fgaPct=percentileFromBundle(row.bundle,"FGA_per75");
      if(value==null && fga!=null)value=fga;
      if(pct==null && fgaPct!=null)pct=fgaPct;
    }
    const norm=normalizeStat(stat);const rel=["WOWY_Offense","WOWY_Defense","WOWY_Net"].some(k=>normalizeStat(k)===norm);let relClass="";if(rel){const n=Number(value);if(Number.isFinite(n)&&n!==0){const good=(String(stat).toLowerCase().includes("rdrtg") || String(stat).toLowerCase().includes("relative_drtg"))?n<0:n>0;relClass=good?"relative-positive":"relative-negative";}}return <td key={stat}><span className={relClass}>{formatValue(value,stat)}</span>{pctSpan(pct)}</td>;};
  const syncProfileScroll=(source,scrollLeft)=>{
    profileTableScrollRefs.current.forEach(el=>{if(el){el.style.setProperty("--profile-scroll-left",`${scrollLeft}px`);}});
    if(profileScrollRef.current&&profileScrollRef.current!==source)profileScrollRef.current.scrollLeft=scrollLeft;
  };
  useEffect(()=>{
    const header=profileHeaderRef.current;
    if(!header)return;
    const update=()=>header.parentElement?.style.setProperty("--profile-header-height",`${header.offsetHeight}px`);
    update();
    const ro=new ResizeObserver(update);
    ro.observe(header);
    return()=>ro.disconnect();
  });
  const registerProfileTableScroll=el=>{if(el&&!profileTableScrollRefs.current.includes(el))profileTableScrollRefs.current.push(el);};
  if(error&&!data&&!initialPlayer)return <PageShell eyebrow="PLAYER PROFILE" title="Unable to load profile"><Placeholder title="Start the local API" text={`${error}. Run local_api/nba_per75_local_api.py in a second PowerShell window, then refresh.`}/></PageShell>;
  if(!data && !initialPlayer) return <PageShell eyebrow="PLAYER PROFILE" title="Loading player profile…"><div className="website78-profile-loading" aria-label="Loading player profile"><span className="website78-profile-loading-dot"/><span className="website78-profile-loading-dot"/><span className="website78-profile-loading-dot"/></div></PageShell>;
  if(data?.found===false)return <PageShell eyebrow="PLAYER PROFILE" title="Player not found"><Placeholder title="No matching player" text="Return to Players and select a player from the canonical search results."/></PageShell>;
  const renderTable=(names,title)=> <section className="profile-section"><h3 className="profile-table-title">{title}</h3><div className="tablewrap" ref={registerProfileTableScroll} onScroll={e=>syncProfileScroll(e.currentTarget,e.currentTarget.scrollLeft)}><table><thead><tr><th>YEAR</th>{title.startsWith("PER 75")&&<th>GAMES PLAYED</th>}{names.map(x=><th key={x}>{fmtName(x)}</th>)}</tr></thead><tbody>{displayRows.map((row,i)=>{
    const individual=!['CAREER','5-YEAR PEAK'].includes(row.season);
    return <tr key={`${row.season}-${i}`} className={`${individual?'season-selectable ':''}${selectedSeason===row.season?'season-selected':''}`} onMouseEnter={()=>individual&&prefetchPlayerSpider(id,row.season,seasonType)} onClick={()=>{if(!individual)return;setSelectedSeason(row.season);setSeasonSpiderData(null);}} aria-selected={individual&&selectedSeason===row.season}>
      <td>{row.season}{individual&&selectedSeason===row.season?<span className="season-selected-mark">●</span>:null}</td>{title.startsWith("PER 75")&&<td>{row.season==="5-YEAR PEAK"?gamesFor(row):formatValue(gamesFor(row),"G")}</td>}{names.map(stat=>seasonCell(row,stat))}
    </tr>;
  })}</tbody></table></div></section>;

  return <main className="page player-profile">
    <div className="eyebrow">PLAYER PROFILE</div>
    <div className="profile-stage">
      <div className={`profile-card-wrap ${cardLifted?"lifted":""} ${cardFlipped?"flipped":""}`}>
        <div className="profile-card">
          <div className="cardface frontface" onClick={flip} role="button" tabIndex={0} onKeyDown={e=>{if(e.key==="Enter"||e.key===" ")flip();}}>
            <div className="frontphoto"><Headshot player={profileHeadshotPlayer} name={playerDisplayName(profileHeadshotPlayer.player_name||id)} preferDirect={String(id)==="P002997" && season==="5-Year Peak"}/></div>
            <div className="frontname">{playerDisplayName(p.player_name)}</div>
          </div>
          <div className="cardface backface">
            <div className="profile-back-top" ref={profileHeaderRef}>
              <div className="profile-identity">
                <div className="profile-headshot"><Headshot player={profileHeadshotPlayer} name={playerDisplayName(profileHeadshotPlayer.player_name||id)} preferDirect={String(id)==="P002997" && season==="5-Year Peak"}/></div>
                <div className="back-title">{playerDisplayName(p.player_name)}</div>
                <div className="profile-teams">{Array.isArray(p.teams)?p.teams.join(" · "):Array.isArray(p.team_history)?p.team_history.join(" · "):"NBA HISTORY"}</div>
              </div>
              <div className="profile-controls-area">
                <div className="profile-control-label">PROFILE CONTEXT</div>
                <div className="back-tabs">
                  <button className={seasonType==="Regular Season"?"active":""} onMouseEnter={()=>id&&prefetchPlayerProfile(id,"full")} onClick={()=>{if(id)prefetchPlayerProfile(id,"full");setSeasonType("Regular Season");setSelectedSeason("")}}>REGULAR SEASON</button>
                  <button className={seasonType==="Playoffs"?"active":""} onMouseEnter={()=>id&&prefetchPlayerProfile(id,"playoffs")} onClick={()=>{if(id)prefetchPlayerProfile(id,"playoffs");setSeasonType("Playoffs");setSelectedSeason("")}}>PLAYOFFS</button>
                  <button className={season==="Career"?"active":""} onMouseEnter={()=>{if(seasonType==="Playoffs")warmPlayoffContext();else warmRegularContext();}} onClick={()=>{if(seasonType==="Playoffs")warmPlayoffContext();else warmRegularContext();setSeason("Career");setSelectedSeason("")}}>CAREER</button>
                  <button className={season==="5-Year Peak"?"active":""} onMouseEnter={()=>id&&prefetchPlayerProfile(id,"background")} onClick={()=>{if(id)prefetchPlayerProfile(id,"background");setSeason("5-Year Peak");setSelectedSeason("")}}>5-YEAR PEAK</button>
                </div>
                <p className="profile-context-note">{selectedSeason?`Selected season: ${selectedSeason}`:season==="Career"?"Career context":season==="5-Year Peak"?"Canonical five-year peak context":"Season-by-season historical context"}. Click any individual season below to update the profile dimensions.</p>
                <div className="profile-header-sdi">
                  <div className="profile-header-sdi-label">{sdiContextLabel()}</div>
                  <div className="profile-header-sdi-values">
                    {sdiLabels.map(label=>{const value=sdiValue(label);const showNQ=sdiReady&&value==null;return <div key={label} className="profile-header-sdi-value" style={sdiBoxStyle(showNQ?null:value)}><span>{label}</span><b className={showNQ?"sdi-nq":""}>{showNQ?"NQ":(value==null?"":Math.round(Number(value)))}</b></div>;})}
                  </div>
                </div>
              </div>
              <button type="button" className="sixbox" onClick={()=>{setSpiderConfigOpen(true);if(!selectedStats.length)setSelectedStats(statEntries.slice(0,6));}}>
                <div className="sixbox-head"><strong>{seasonType==="Playoffs"?"FOUR-DIMENSION PROFILE":"SIX-DIMENSION PROFILE"}</strong><span>↗</span></div>
                <div className="fake-radar">
                  <svg viewBox="0 0 240 240" className="sdi-radar-svg">
                    {[20,40,60,80,100].map(level=><polygon key={level} points={radarPoints(sdiFixedAxes.map(a=>({...a,value:level})),240).replaceAll("120,","120,")} className="sdi-radar-grid"/>) }
                    {sdiLabels.map((label,i)=>{const n=sdiLabels.length,a=-Math.PI/2+i*2*Math.PI/n,x=120+Math.cos(a)*91,y=120+Math.sin(a)*91;return <line key={`axis-${label}`} x1="120" y1="120" x2={x} y2={y} className="sdi-radar-axis"/>;})}
                    <polygon points={radarPoints(sdiFixedAxes,240)} className="sdi-radar-fill"/>
                    <polyline points={`${radarPoints(sdiFixedAxes,240)} ${radarPoints(sdiFixedAxes,240).split(" ")[0]}`} className="sdi-radar-line"/>
                    {sdiLabels.map((label,i)=>{const n=sdiLabels.length,a=-Math.PI/2+i*2*Math.PI/n;const v=sdiValue(label);const rr=91*Math.max(0,Math.min(100,Number(v)||0))/100;const x=120+Math.cos(a)*rr,y=120+Math.sin(a)*rr;const lx=120+Math.cos(a)*106,ly=120+Math.sin(a)*106;return <g key={label}><circle cx={x} cy={y} r="4.5" className="sdi-radar-dot"/><text x={lx} y={ly+3} textAnchor={lx<112?"end":lx>128?"start":"middle"} className="sdi-radar-label">{label}</text></g>;})}
                  </svg>
                </div>
                <div className="sixbox-hint">CLICK TO EXPAND + CONFIGURE</div>
              </button>
            </div>

            {season==="5-Year Peak"&&<div className="career-note">Canonical 5-Year Peak is selected above; the season-by-season tables below remain visible for historical reference.</div>}

            {renderTable(per75Names,"PER 75 STATISTICS")}
            {renderTable(advancedNames,"ADVANCED / IMPACT STATISTICS")}
            <div className="profile-horizontal-scrollbar" ref={profileScrollRef} onScroll={e=>syncProfileScroll(e.currentTarget,e.currentTarget.scrollLeft)} aria-label="Horizontal table scroll">
              <div className="profile-horizontal-scrollbar-spacer" aria-hidden="true" />
            </div>

            {spiderConfigOpen&&<div className="spider-config">
              <div className="spider-config-panel">
                <div className="spider-config-head"><div><div className="eyebrow">CONFIGURABLE PROFILE</div><h3>SIX-DIMENSION PROFILE</h3><p>Choose any registered statistic and any number of statistics for the radar.</p></div><button className="config-close" onClick={()=>setSpiderConfigOpen(false)}>CLOSE</button></div>
                <div className="spider-config-body">
                  <div className="config-radar"><SpiderChart axes={customAxes.length?customAxes:defaultStats.map(stat=>({axis:fmtName(stat),value:percentileFromBundle(data,stat)??0}))} title={playerDisplayName(p.player_name)} configurable/></div>
                  <div className="config-options">
                    <div className="config-count"><span>NUMBER OF STATISTICS</span><button onClick={()=>setSelectedStats(x=>x.length>3?x.slice(0,-1):x)}>−</button><b>{defaultStats.length}</b><button onClick={()=>{const names=configurableStatEntries;const next=names.find(x=>!defaultStats.includes(x));if(next)setSelectedStats([...defaultStats,next]);}}>+</button></div>
                    {defaultStats.map((stat,i)=><div className="axis-row-v12" key={`${stat}-${i}`}><label>STATISTIC {i+1}</label><select value={stat} onChange={e=>setSelectedStats(defaultStats.map((x,j)=>j===i?e.target.value:x))}>{configurableStatEntries.map((n,j)=><option key={`${n}-${j}`} value={n}>{fmtName(n)}</option>)}</select></div>)}
                  </div>
                </div>
              </div>
            </div>}
          </div>
        </div>
      </div>
    </div>
  </main>;
}

const T50_TIERS = {
  T10: ["LeBron James","Michael Jordan","Kareem Abdul-Jabbar","Magic Johnson","Tim Duncan","Hakeem Olajuwon","Shaquille O’Neal","Stephen Curry","Bill Russell","Larry Bird","Wilt Chamberlain","Kevin Durant","Nikola Jokic","Kobe Bryant","Kevin Garnett"],
  T25: ["LeBron James","Michael Jordan","Kareem Abdul-Jabbar","Magic Johnson","Tim Duncan","Hakeem Olajuwon","Shaquille O’Neal","Stephen Curry","Bill Russell","Larry Bird","Wilt Chamberlain","Kevin Durant","Nikola Jokic","Giannis Antetokounmpo","Kobe Bryant","Kevin Garnett","Jerry West","Dirk Nowitzki","Oscar Robertson","Julius Erving","Dwyane Wade","Chris Paul","David Robinson","Moses Malone","Steve Nash","Karl Malone","Kawhi Leonard","Charles Barkley","James Harden","Isiah Thomas","John Havlicek","Luka Dončić","Shai Gilgeous-Alexander","Russell Westbrook","Jason Kidd","Elgin Baylor","Scottie Pippen","John Stockton","Allen Iverson"],
  T50: ["LeBron James","Michael Jordan","Kareem Abdul-Jabbar","Magic Johnson","Tim Duncan","Hakeem Olajuwon","Shaquille O’Neal","Stephen Curry","Bill Russell","Larry Bird","Wilt Chamberlain","Kevin Durant","Nikola Jokic","Giannis Antetokounmpo","Kobe Bryant","Kevin Garnett","Jerry West","Dirk Nowitzki","Oscar Robertson","Julius Erving","Dwyane Wade","Chris Paul","David Robinson","Moses Malone","Steve Nash","Karl Malone","Kawhi Leonard","Charles Barkley","James Harden","Isiah Thomas","Patrick Ewing","Anthony Davis","Clyde Drexler","Dwight Howard","John Havlicek","Luka Dončić","Shai Gilgeous-Alexander","Russell Westbrook","Jason Kidd","Bob Cousy","Bob Pettit","Elgin Baylor","Scottie Pippen","John Stockton","Allen Iverson","Dolph Schayes","Bob McAdoo","Rick Barry","Willis Reed","Sam Jones","Elvin Hayes","George Gervin","Kevin McHale","Bill Walton","Joel Embiid","Victor Wembanyama","Jalen Brunson","Gary Payton","Ray Allen","Draymond Green","Walt Frazier","Dominique Wilkins","Paul Pierce","Paul George","Tracy McGrady","Reggie Miller","Damian Lillard","Jayson Tatum","Carmelo Anthony","Artis Gilmore","Vince Carter","Kyrie Irving","Klay Thompson","Dennis Rodman","Dikembe Mutombo","Manu Ginobili","Jimmy Butler","George Mikan","James Worthy","Tony Parker"],
  T75: ["LeBron James","Michael Jordan","Kareem Abdul-Jabbar","Magic Johnson","Tim Duncan","Hakeem Olajuwon","Shaquille O’Neal","Stephen Curry","Bill Russell","Larry Bird","Wilt Chamberlain","Kevin Durant","Nikola Jokic","Giannis Antetokounmpo","Kobe Bryant","Kevin Garnett","Jerry West","Dirk Nowitzki","Oscar Robertson","Julius Erving","Dwyane Wade","Chris Paul","David Robinson","Moses Malone","Steve Nash","Karl Malone","Kawhi Leonard","Charles Barkley","James Harden","Isiah Thomas","Patrick Ewing","Anthony Davis","Clyde Drexler","Dwight Howard","John Havlicek","Luka Dončić","Shai Gilgeous-Alexander","Russell Westbrook","Jason Kidd","Bob Cousy","Bob Pettit","Elgin Baylor","Scottie Pippen","John Stockton","Allen Iverson","Dolph Schayes","Bob McAdoo","Rick Barry","Willis Reed","Sam Jones","Elvin Hayes","George Gervin","Kevin McHale","Bill Walton","Joel Embiid","Victor Wembanyama","Jalen Brunson","Gary Payton","Ray Allen","Draymond Green","Walt Frazier","Dominique Wilkins","Paul Pierce","Paul George","Tracy McGrady","Reggie Miller","Damian Lillard","Jayson Tatum","Carmelo Anthony","Artis Gilmore","Vince Carter","Kyrie Irving","Klay Thompson","Dennis Rodman","Dikembe Mutombo","Manu Ginobili","Jimmy Butler","George Mikan","James Worthy","Tony Parker","Nate Thurmond","Alex English","Alonzo Mourning","Ben Wallace","Joe Dumars","Sidney Moncrief","Bernard King","Dave Cowens","Chris Webber","Wes Unseld","Robert Parish","Hal Greer","Pau Gasol","Shawn Kemp","Chris Bosh","Dave DeBusschere","Rudy Gobert","Marc Gasol","Billy Cunningham","Nate \"Tiny\" Archibald","Spencer Haywood","Bob Lanier","Chris Mullin","Amar’e Stoudemire","Grant Hill","LaMarcus Aldridge","Penny Hardaway","Karl-Anthony Towns","Derrick Rose","Chauncey Billups","Adrian Dantley","Andre Iguodala","Pete Maravich","Paul Arizin"]
};

const T50_MODE_INFO = {
  // Smaller candidate fields allow the engine to spend substantially more
  // comparisons establishing the actual order.
  T10:{title:"Make a T10",subtitle:"15 candidates · adaptive decisions",target:10,max:999},
  T25:{title:"Make a T25",subtitle:"39 candidates · adaptive decisions",target:25,max:999},
  T50:{title:"Make a T50",subtitle:"80 candidates · adaptive decisions",target:50,max:999},
  T75:{title:"Make a T75",subtitle:"114 candidates · adaptive decisions",target:75,max:999}
};

function T50Headshot({name, player, className=""}) {
  const direct=player?.headshot_url || player?.Headshot_URL || player?.headshot || "";
  const pid=player?.player_id || player?.Player_ID || "";
  const historical=_canonicalHistoricalHeadshot(player,name);
  const identity=pid || name;
  const endpoint=`/api/v1/players/${encodeURIComponent(identity)}/headshot`;
  const rawCandidates=_headshotCandidates(player,name,direct,endpoint);
  // Historical/manual PNGs are canonical and must win over remote CDN values.
  const candidates=historical ? [historical,...rawCandidates.filter(x=>x!==historical)] : rawCandidates;
  const [attempt,setAttempt]=useState(0),[loaded,setLoaded]=useState(false);
  useEffect(()=>{setAttempt(0);setLoaded(false);},[direct,endpoint,name]);
  const src=candidates[attempt];
  if(!src)return <span className="t50-headshot-fallback">{String(name||"75").split(/\s+/).map(x=>x[0]).join("").slice(0,2).toUpperCase()}</span>;
  const specialClass = _nameKey(name)==="bob cousy" ? " t50-headshot-cousy" : (_nameKey(name)==="jason kidd" ? " t50-headshot-kidd" : "");
  const isHistoricalLocal=String(src||"").startsWith("/player_headshots_final_v1/");
  return <img loading="lazy" decoding="async" fetchPriority="low" className={`${className}${src===endpoint ? " headshot-proxy" : ""}${isHistoricalLocal ? " historical-headshot" : ""}${specialClass}`} src={src} alt="" onLoad={()=>setLoaded(true)} onError={()=>{if(!loaded)setAttempt(a=>a+1);}}/>;
}

const CREATE_TEAM_COLORS={
  ATL:"#e03a3e",BOS:"#007a33",BKN:"#707070",CHA:"#1d1160",CHI:"#ce1141",CLE:"#860038",DAL:"#00538c",DEN:"#0e2240",DET:"#c8102e",GSW:"#1d428a",HOU:"#ce1143",IND:"#002d62",LAC:"#c8102e",LAL:"#552583",MEM:"#5d76a9",MIA:"#98002e",MIL:"#00471b",MIN:"#236192",NOP:"#0c2340",NYK:"#006bb6",OKC:"#007ac1",ORL:"#0077c0",PHI:"#006bb6",PHX:"#1d1160",POR:"#e03a3e",SAC:"#5a2d81",SAS:"#c4ced4",TOR:"#ce1141",UTA:"#002b5c",WAS:"#002b5c"
};
const CREATE_TEAM_ABBR={
  "atlanta hawks":"ATL","boston celtics":"BOS","brooklyn nets":"BKN","charlotte hornets":"CHA","charlotte bobcats":"CHA","chicago bulls":"CHI","cleveland cavaliers":"CLE","dallas mavericks":"DAL","denver nuggets":"DEN","detroit pistons":"DET","golden state warriors":"GSW","houston rockets":"HOU","indiana pacers":"IND","los angeles clippers":"LAC","los angeles lakers":"LAL","memphis grizzlies":"MEM","miami heat":"MIA","milwaukee bucks":"MIL","minnesota timberwolves":"MIN","new orleans pelicans":"NOP","new york knicks":"NYK","oklahoma city thunder":"OKC","orlando magic":"ORL","philadelphia 76ers":"PHI","phoenix suns":"PHX","portland trail blazers":"POR","sacramento kings":"SAC","san antonio spurs":"SAS","toronto raptors":"TOR","utah jazz":"UTA","washington wizards":"WAS"
};
function createTeamMeta(player){
  const rawAbbr=String(player?.team_abbr||player?.Team_Abbr||player?.abbreviation||player?.Abbreviation||"").trim().toUpperCase();
  const rawTeam=String(player?.team||player?.Team||player?.team_name||player?.Team_Name||"").replace(/\*+$/," ").trim();
  const abbr=CREATE_TEAM_COLORS[rawAbbr]?rawAbbr:(CREATE_TEAM_ABBR[rawTeam.toLowerCase()]||"");
  const color=CREATE_TEAM_COLORS[abbr]||"#b94b5d";
  const position=String(player?.position||player?.Position||player?.pos||player?.POS||"").trim();
  return {abbr,team:rawTeam,color,position};
}

function CreateT50() {
  const [mode,setMode]=useState(null);
  const [buildMethod,setBuildMethod]=useState(null);
  const [players,setPlayers]=useState({});
  const [previewPlayers,setPreviewPlayers]=useState({});
  const [wins,setWins]=useState({});
  const [comparisons,setComparisons]=useState([]);
  const comparisonsRef=useRef([]);
  const [pair,setPair]=useState(null);
  const [started,setStarted]=useState(false);
  const [done,setDone]=useState(false);
  const [search,setSearch]=useState("");
  const [directSearch,setDirectSearch]=useState("");
  const [directSelected,setDirectSelected]=useState([]);
  const [packOpen,setPackOpen]=useState(false);
  const packPlayedRef=useRef(false);
  const [matchStatData,setMatchStatData]=useState({});
  const [shareStatus,setShareStatus]=useState("");
  const navigate=useNavigate();
  const location=useLocation();

  const PREVIEW_BY_METHOD={
    head_to_head:{T10:"LeBron James",T25:"Kevin Garnett",T50:"Shai Gilgeous-Alexander",T75:"Allen Iverson"},
    direct:{T10:"Michael Jordan",T25:"Wilt Chamberlain",T50:"Jerry West",T75:"Russell Westbrook"}
  };

  useEffect(()=>{
    let active=true;
    const previews=["Michael Jordan","LeBron James","Kareem Abdul-Jabbar","Stephen Curry","Kevin Garnett","Wilt Chamberlain","Shai Gilgeous-Alexander","Jerry West","Allen Iverson","Russell Westbrook"];
    Promise.all(previews.map(async name=>{
      try{const r=await searchPlayers(name);const arr=Array.isArray(r)?r:(r?.rows||r?.players||[]);return [name,arr.find(x=>playerDisplayName(x.player_name||x.name||"").toLowerCase()===name.toLowerCase())||arr[0]||null];}
      catch{return [name,null];}
    })).then(e=>{if(active)setPreviewPlayers(Object.fromEntries(e));});
    return()=>{active=false;};
  },[]);

  useEffect(()=>{
    let active=true;
    const names=[...new Set(Object.values(T50_TIERS).flat())];
    Promise.all(names.map(async name=>{
      try{
        const r=await searchPlayers(name);
        const arr=Array.isArray(r)?r:(r?.rows||r?.players||[]);
        const p=arr.find(x=>playerDisplayName(x.player_name||x.name||"").toLowerCase()===name.toLowerCase()) || arr[0];
        return [name,p||null];
      }catch{return [name,null];}
    })).then(entries=>{if(active)setPlayers(Object.fromEntries(entries));});
    return()=>{active=false;};
  },[]);

  const info=mode?T50_MODE_INFO[mode]:null;
  const pool=mode?T50_TIERS[mode]:[];

  useEffect(()=>{
    if(!mode || buildMethod!=="head_to_head")return;
    const key=`nba-per75-t50-${mode}`;
    try{
      const saved=JSON.parse(localStorage.getItem(key)||"null");
      if(saved && saved.done){
        const savedComparisons=saved.comparisons||[];
        comparisonsRef.current=savedComparisons;
        setWins(saved.wins||{});
        setComparisons(savedComparisons);
        setStarted(true);setDone(true);
      }else{
        localStorage.removeItem(key);
        comparisonsRef.current=[];setWins({});setComparisons([]);setStarted(false);setDone(false);
      }
    }catch{}
  },[mode,buildMethod]);

  // Allow finished lists to be shared as a URL without requiring the recipient
  // to reconstruct the underlying matchup session.
  useEffect(()=>{
    const params=new URLSearchParams(location.search);
    const sharedMode=params.get("mode");
    const sharedMethod=params.get("method");
    const encoded=params.get("list");
    if(!sharedMode || !sharedMethod || !encoded || !T50_MODE_INFO[sharedMode] || !["head_to_head","direct"].includes(sharedMethod))return;
    try{
      const list=JSON.parse(decodeURIComponent(encoded));
      const valid=T50_TIERS[sharedMode].filter(n=>list.includes(n));
      const ordered=list.filter(n=>valid.includes(n)).slice(0,T50_MODE_INFO[sharedMode].target);
      if(ordered.length<Math.min(3,T50_MODE_INFO[sharedMode].target))return;
      setMode(sharedMode);setBuildMethod(sharedMethod);setDone(true);setStarted(true);
      if(sharedMethod==="direct")setDirectSelected(ordered);
      else setWins(Object.fromEntries(ordered.map((n,i)=>[n,ordered.length-i])));
    }catch{}
  },[location.search]);

  useEffect(()=>{
    if(!pair||pair.length<2)return;
    let active=true;
    const entries=pair.map(async name=>{
      if(matchStatData[name])return [name,matchStatData[name]];
      try{
        const p=players[name];
        const pid=p?.player_id||p?.Player_ID||name;
        const bundle=await getPlayerProfileBundle(pid,"Regular Season","Career","Historical");
        const vals=bundle?.profile||bundle?.statistic_values||{};
        const num=(...keys)=>{for(const k of keys){const key=Object.keys(vals||{}).find(x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,"")===String(k).toLowerCase().replace(/[^a-z0-9]/g,""));if(key!=null&&Number.isFinite(Number(vals[key])))return Number(vals[key]);}return null;};
        const stats={pts:num("PTS_per75"),reb:num("TRB_per75"),ast:num("AST_per75"),stl:num("STL_per75"),blk:num("BLK_per75"),rts:num("rTS")};
        stats.stocks=stats.stl!=null&&stats.blk!=null?stats.stl+stats.blk:null;
        return [name,stats];
      }catch{return [name,null];}
    });
    Promise.all(entries).then(e=>{if(active)setMatchStatData(prev=>({...prev,...Object.fromEntries(e.filter(([,v])=>v))}));});
    return()=>{active=false;};
  },[pair,players]);

  const score=(n)=>Number(wins[n]||0);

  // The old engine used a fixed comparison budget plus an Elo-style estimate.
  // That can produce a plausible ranking, but it cannot prove the order. The
  // adaptive engine below instead treats every answer as a directed relation
  // (winner > loser), uses transitivity for free, and only asks for another
  // comparison when the next place in the requested list is still ambiguous.
  const deriveAdaptiveOrder=()=>{
    const nodes=pool.slice();
    const edges=new Map(nodes.map(n=>[n,new Set()]));
    const indegree=new Map(nodes.map(n=>[n,0]));
    for(const {a,b} of comparisonsRef.current){
      if(!edges.has(a)||!edges.has(b)||a===b)continue;
      if(!edges.get(a).has(b)){
        edges.get(a).add(b);
        indegree.set(b,(indegree.get(b)||0)+1);
      }
    }
    const originalIndex=new Map(nodes.map((n,i)=>[n,i]));
    const remaining=new Set(nodes);
    const order=[];
    let uniqueTopTarget=true;
    for(let place=0; place<nodes.length; place++){
      const available=[...remaining].filter(n=>(indegree.get(n)||0)===0).sort((a,b)=>(originalIndex.get(a)-originalIndex.get(b)));
      if(!available.length){
        return {order,unique:false,cycle:true,available:[]};
      }
      if(place<info.target && available.length!==1){
        uniqueTopTarget=false;
        break;
      }
      const next=available[0];
      order.push(next);
      remaining.delete(next);
      for(const loser of edges.get(next)||[]){
        indegree.set(loser,(indegree.get(loser)||0)-1);
      }
    }
    return {order,unique:uniqueTopTarget,cycle:false,available:[]};
  };

  const fallbackRankings=pool.slice().sort((a,b)=>score(b)-score(a)||a.localeCompare(b));
  const adaptiveState=deriveAdaptiveOrder();
  const rankings=adaptiveState.unique ? adaptiveState.order : fallbackRankings;

  const profileFor=(name)=>{
    const p=players[name];
    const id=p?.player_id||p?.Player_ID||name;
    return `/players/${encodeURIComponent(id)}`;
  };

  const shareList=async(list,method=buildMethod,target=info?.target)=>{
    if(!list?.length||!mode)return;
    const url=`${window.location.origin}${window.location.pathname}?method=${encodeURIComponent(method)}&mode=${encodeURIComponent(mode)}&list=${encodeURIComponent(JSON.stringify(list))}`;
    try{
      if(navigator.share){await navigator.share({title:`NBA PER-75 T${target} List`,text:`My custom NBA PER-75 T${target} list`,url});setShareStatus("SHARED");}
      else{await navigator.clipboard.writeText(url);setShareStatus("LINK COPIED");}
    }catch(err){
      if(err?.name!=="AbortError"){
        try{await navigator.clipboard.writeText(url);setShareStatus("LINK COPIED");}catch{setShareStatus("COPY FAILED");}
      }
    }
    setTimeout(()=>setShareStatus(""),2200);
  };

  const persist=(w,c,s,d)=>{if(!mode)return;localStorage.setItem(`nba-per75-t50-${mode}`,JSON.stringify({wins:w,comparisons:c,started:s,done:d}));};

  const choosePair=()=>{
    if(!mode||done||buildMethod!=="head_to_head")return;
    const history=comparisonsRef.current;
    const state=deriveAdaptiveOrder();
    if(state.unique){
      setDone(true);
      persist(wins,history,started,true);
      return;
    }
    if(state.cycle){
      // A directed cycle means the answers themselves are contradictory. There
      // is no mathematically exact ordering until the user supplies a new
      // preference. Pick an unasked pair to continue gathering information.
    }

    const asked=new Set(history.map(x=>`${x.a}|||${x.b}`));
    const askedEither=(a,b)=>asked.has(`${a}|||${b}`)||asked.has(`${b}|||${a}`);
    const index=new Map(pool.map((n,i)=>[n,i]));

    // First priority: candidates currently capable of occupying the next
    // unresolved slot. Compare the two closest candidates in the canonical
    // pool order. This tends to resolve a near-sorted pool in roughly one
    // pass instead of repeatedly sampling arbitrary players.
    const nodes=pool.slice();
    const edges=new Map(nodes.map(n=>[n,new Set()]));
    const indegree=new Map(nodes.map(n=>[n,0]));
    for(const {a,b} of history){
      if(!edges.has(a)||!edges.has(b)||a===b)continue;
      if(!edges.get(a).has(b)){edges.get(a).add(b);indegree.set(b,(indegree.get(b)||0)+1);}
    }
    const available=nodes.filter(n=>(indegree.get(n)||0)===0);
    const unresolved=[];
    for(let i=0;i<available.length;i++)for(let j=i+1;j<available.length;j++){
      const a=available[i],b=available[j];
      if(!askedEither(a,b)) unresolved.push([a,b,Math.abs(index.get(a)-index.get(b))]);
    }
    if(unresolved.length){
      unresolved.sort((a,b)=>a[2]-b[2] || Math.min(index.get(a[0]),index.get(a[1]))-Math.min(index.get(b[0]),index.get(b[1])));
      setPair([unresolved[0][0],unresolved[0][1]]);
      return;
    }

    // If the next-slot candidates have all been compared, find the closest
    // remaining unasked pair around the projected top-X boundary.
    const rankedGuess=state.order.length?state.order:pool.slice();
    let best=null,bestScore=Infinity;
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j];
      if(askedEither(a,b))continue;
      const ra=rankedGuess.indexOf(a), rb=rankedGuess.indexOf(b);
      const gap=Math.abs((ra<0?nodes.length:ra)-(rb<0?nodes.length:rb));
      const boundary=Math.min(Math.abs((ra<0?nodes.length:ra+1)-info.target),Math.abs((rb<0?nodes.length:rb+1)-info.target));
      const priority=gap*1.4+boundary*0.55+Math.min(index.get(a),index.get(b))*0.01;
      if(priority<bestScore){bestScore=priority;best=[a,b];}
    }
    if(best){setPair(best);return;}

    // No unasked pair remains: with a finite candidate pool, this can only
    // happen when the user's preferences contain a cycle. Keep the UI alive.
    setPair(null);
  };

  // Keep the head-to-head processing independent from the pack visual.
  // The first valid pair is seeded immediately, and the adaptive engine
  // continues from there exactly as the original working flow did.
  useEffect(()=>{
    if(!(mode&&buildMethod==="head_to_head"&&started)||done||pair)return;
    const t=setTimeout(()=>choosePair(),40);
    return()=>clearTimeout(t);
  },[mode,buildMethod,started,done,pair,comparisons.length]);

  // The pack is presentation only. It closes after the opening animation
  // without changing the matchup state underneath it.
  useEffect(()=>{
    if(!(mode&&buildMethod==="head_to_head"&&started&&packOpen))return;
    const t=setTimeout(()=>setPackOpen(false),1550);
    return()=>clearTimeout(t);
  },[mode,buildMethod,started,packOpen]);

  const start=()=>{
    comparisonsRef.current=[];setStarted(true);setDone(false);setWins({});setComparisons([]);setPair(null);if(!packPlayedRef.current){packPlayedRef.current=true;setPackOpen(true);}
    if(mode)localStorage.removeItem(`nba-per75-t50-${mode}`);
  };

  const vote=(winner,loser)=>{
    // The pack is a one-time entry animation for the selected player pool.
    // Once the user makes the first head-to-head choice, it must never be
    // allowed to reappear during subsequent matchup transitions.
    if(packOpen)setPackOpen(false);
    const nw={...wins,[winner]:score(winner)+1,[loser]:score(loser)};
    const nc=[...comparisonsRef.current,{a:winner,b:loser}];
    comparisonsRef.current=nc;setWins(nw);setComparisons(nc);
    if(nc.length>=info.max){setDone(true);setPair(null);persist(nw,nc,true,true);return;}
    persist(nw,nc,true,false);setPair(null);setTimeout(()=>choosePair(),0);
  };

  const reset=()=>{
    if(!mode)return;
    localStorage.removeItem(`nba-per75-t50-${mode}`);
    comparisonsRef.current=[];setWins({});setComparisons([]);setStarted(false);setDone(false);setPair(null);setDirectSelected([]);setBuildMethod(null);setMode(null);setDirectSearch("");setShareStatus("");
    if(location.search)navigate(location.pathname,{replace:true});
  };

  const selectMethod=(method,key)=>{
    setBuildMethod(method);setMode(key);setDone(false);setPair(null);setDirectSelected([]);setDirectSearch("");setShareStatus("");
    if(method==="head_to_head") {
      // Same state initialization used by the working head-to-head flow.
      comparisonsRef.current=[];setStarted(true);setWins({});setComparisons([]);
      packPlayedRef.current=false;
      const initialPool=T50_TIERS[key]||[];
      setPair(initialPool.length>=2?[initialPool[0],initialPool[1]]:null);
      if(!packPlayedRef.current){packPlayedRef.current=true;setPackOpen(true);}
      if(key)localStorage.removeItem(`nba-per75-t50-${key}`);
    } else {
      setStarted(false);setPackOpen(false);
    }
  };

  const toggleDirect=(name)=>{
    setDirectSelected(prev=>prev.includes(name)?prev.filter(x=>x!==name):(prev.length<info.target?[...prev,name]:prev));
  };
  const moveDirect=(name,delta)=>{
    setDirectSelected(prev=>{
      const i=prev.indexOf(name),j=i+delta;if(i<0||j<0||j>=prev.length)return prev;
      const next=prev.slice();[next[i],next[j]]=[next[j],next[i]];return next;
    });
  };
  const buildDirect=()=>{if(directSelected.length===info.target)setDone(true);};

  const filteredPool=pool.filter(name=>name.toLowerCase().includes(directSearch.trim().toLowerCase()));

  if(!mode) return <PageShell className="create-t75-page" eyebrow="CUSTOM ALL-TIME LIST" title="CREATE YOUR TOP 75" description="Choose how you want to build your custom all-time list.">
    <div className="create-methods">
      <section className="create-method create-method-duel">
        <div className="create-method-heading"><span className="create-method-icon">⚔</span><div><h2>BUILD THROUGH <em>HEAD-TO-HEAD</em></h2><p>Go head-to-head with players and let the matchups build your ranking.</p></div></div>
        <div className="create-method-grid">
          {Object.keys(T50_MODE_INFO).map(key=>{const x=T50_MODE_INFO[key];const art=({T10:"lebron",T25:"garnett",T50:"shai",T75:"iverson"})[key];return <button className={`create-method-card create-art-${art}`} key={key} onClick={()=>selectMethod("head_to_head",key)} aria-label={`Build a T${x.target} through head-to-head matchups`}><div className="create-card-number"><span>{x.target}</span></div><img src={`/create-t75/${art}.png`} alt=""/><div className="create-card-overlay"></div><div className="create-card-copy"><b>T{key.slice(1)}</b><span>HEAD-TO-HEAD</span><small>{({T10:"Rank the 10 greatest through head-to-head matchups.",T25:"Rank the 25 greatest through head-to-head matchups.",T50:"Rank the 50 greatest through head-to-head matchups.",T75:"Rank the 75 greatest through head-to-head matchups."})[key]}</small></div><i>›</i></button>;})}
        </div>
      </section>
      <section className="create-method create-method-direct">
        <div className="create-method-heading"><span className="create-method-icon">✎</span><div><h2>BUILD YOUR <em>LIST</em></h2><p>Browse the full player pool and select your players directly.</p></div></div>
        <div className="create-method-grid">
          {Object.keys(T50_MODE_INFO).map(key=>{const x=T50_MODE_INFO[key];const art=({T10:"jordan",T25:"wilt",T50:"west",T75:"westbrook"})[key];return <button className={`create-method-card create-art-${art}`} key={key} onClick={()=>selectMethod("direct",key)} aria-label={`Build a T${x.target} by selecting players directly`}><div className="create-card-number"><span>{x.target}</span></div><img src={`/create-t75/${art}.png`} alt=""/><div className="create-card-overlay"></div><div className="create-card-copy"><b>T{key.slice(1)}</b><span>SELECT PLAYERS</span><small>{({T10:"Choose the 10 greatest from the full player pool.",T25:"Choose the 25 greatest from the full player pool.",T50:"Choose the 50 greatest from the full player pool.",T75:"Choose the 75 greatest from the full player pool."})[key]}</small></div><i>›</i></button>;})}
        </div>
      </section>
    </div>
  </PageShell>;

  if(buildMethod==="direct"&&!done) return <PageShell eyebrow="BUILD YOUR LIST" title={`CHOOSE YOUR T${info.target}`} description={`Select exactly ${info.target} players from the ${pool.length}-player pool. Your selection order becomes your initial list order, and you can reorder the chosen players before publishing.`}>
    <div className="direct-builder">
      <div className="direct-builder-main">
        <div className="direct-toolbar"><input value={directSearch} onChange={e=>setDirectSearch(e.target.value)} placeholder="Search the player pool…"/><span>{directSelected.length} / {info.target} SELECTED</span></div>
        <div className="direct-pool">{filteredPool.map((name,idx)=>{const selected=directSelected.includes(name);return <button type="button" key={name} className={`direct-player-card ${selected?"selected":""}`} onClick={()=>toggleDirect(name)} disabled={!selected&&directSelected.length>=info.target} aria-pressed={selected}><div className="direct-player-card-art"><T50Headshot name={name} player={players[name]}/><span className="direct-player-card-rank">{String(idx+1).padStart(2,"0")}</span><span className="direct-player-card-state">{selected?"✓ ADDED":"+ ADD"}</span></div><div className="direct-player-card-body"><b>{name}</b><small>{players[name]?.position||players[name]?.Position||"NBA HISTORY"}</small></div></button>})}</div>
      </div>
      <aside className="direct-selected-panel"><div className="direct-selected-head"><b>YOUR T{info.target}</b><span>{directSelected.length}/{info.target}</span></div><div className="direct-selected-list">{directSelected.map((name,i)=><div className="direct-selected-row" key={name}><span className="rank">{i+1}</span><span className="direct-avatar"><T50Headshot name={name} player={players[name]}/></span><b>{name}</b><button title="Move up" onClick={()=>moveDirect(name,-1)}>↑</button><button title="Move down" onClick={()=>moveDirect(name,1)}>↓</button><button title="Remove" onClick={()=>toggleDirect(name)}>×</button></div>)}</div><button className="btn direct-build-btn" disabled={directSelected.length!==info.target} onClick={buildDirect}>{directSelected.length===info.target?`BUILD MY T${info.target}`:`SELECT ${info.target-directSelected.length} MORE`}</button></aside>
    </div>
  </PageShell>;

  const packOverlay = packOpen ? (()=>{
    const packPreview=({T10:"lebron",T25:"garnett",T50:"shai",T75:"iverson"})[mode] || "lebron";
    return <div className="create-t75-pack-overlay" aria-hidden="true">
      <div className={`pack-stage animate pack-tier-${info.target}`}>
        <div className="pack open">
            <div className="pack-rip-panel"></div>
            <div className="pack-seal"></div>
            <div className="pack-tear"><span></span></div>
            <div className="pack-flap-left"></div><div className="pack-flap-right"></div>
            <div className="pack-gloss"></div>
            <div className="pack-mark">NBA PER-75</div>
            <div className="pack-number">TOP {info.target}</div>
            <div className="pack-hero"><div className="pack-hero-bg"></div><div className="pack-hero-number">{info.target}</div><img src={`/create-t75/${packPreview}.png`} alt="" /></div>
            <div className="pack-copy">MY TOP {info.target}<span>PLAYERS OF ALL-TIME</span></div>
            <div className="pack-bottom-foil"><span>HEAD-TO-HEAD EDITION</span><strong>NBA PER-75</strong></div>
        </div>
      </div>
    </div>;
  })() : null;

  if(!done&&pair) return <><PageShell eyebrow="HEAD-TO-HEAD SELECTION" title="Which player is better?" description={`Choose the player you prefer. ${comparisons.length} comparison${comparisons.length===1?"":"s"} completed · the engine only asks for comparisons needed to resolve your ranking.`}><div className="create-adaptive-meter"><span>{comparisons.length} COMPARISONS</span><em>ADAPTIVE · NO FIXED QUESTION COUNT</em></div><div className="matchup create-t75-card-grid">{[pair[0],pair[1]].map((name,i)=>{const tm=createTeamMeta(players[name]);return <React.Fragment key={name}><button className={`match-card ${i===0?"match-card-a":"match-card-b"}`} style={{"--team-color":tm.color,"--team-color-soft":`${tm.color}24`}} onClick={()=>vote(name,i===0?pair[1]:pair[0])}><div className="match-photo" data-team={tm.team} style={{"--team-color":tm.color,"--team-color-soft":`${tm.color}24`}}><div className="match-team-backdrop"></div><div className="match-photo-glow"></div>{tm.abbr&&<div className="match-team-watermark">{tm.abbr}</div>}<T50Headshot name={name} player={players[name]}/><div className="match-card-nameplate"><div className="match-name">{name}</div>{tm.position&&<div className="match-position">{tm.position.toUpperCase()}</div>}</div></div><div className="matchstats-card"><div><span>PTS/75</span><b>{matchStatData[name]?.pts==null?"—":matchStatData[name].pts.toFixed(1)}</b></div><div><span>REB/75</span><b>{matchStatData[name]?.reb==null?"—":matchStatData[name].reb.toFixed(1)}</b></div><div><span>AST/75</span><b>{matchStatData[name]?.ast==null?"—":matchStatData[name].ast.toFixed(1)}</b></div><div><span>STOCKS/75</span><b>{matchStatData[name]?.stocks==null?"—":matchStatData[name].stocks.toFixed(1)}</b></div><div><span>rTS</span><b>{matchStatData[name]?.rts==null?"—":`${matchStatData[name].rts>=0?"+":""}${matchStatData[name].rts.toFixed(1)}`}</b></div></div></button>{i===0&&<div className="matchvs">VS</div>}</React.Fragment>})}</div><div style={{textAlign:"center",marginTop:25}}><button className="btn alt" onClick={reset}>START OVER</button></div></PageShell>{packOverlay}</>;

  if(!done) return <PageShell eyebrow="HEAD-TO-HEAD SELECTION" title="Which player is better?" description="Choose the player you prefer."><div className="panel" style={{padding:25,textAlign:"center"}}>Select a player to continue.</div></PageShell>;

  const finalList=buildMethod==="direct"?directSelected:rankings.slice(0,info.target);
  return <PageShell eyebrow="GENERATED RESULT" title={`MY TOP ${info.target} PLAYERS OF ALL-TIME`} description={buildMethod==="direct"?"Your selected player pool, ordered by your selection and final adjustments.":"Your final ranking generated from the existing adaptive pairwise comparison algorithm."}>
    <div className={`list-poster list-poster-t${info.target} ${buildMethod==="direct"?"list-poster-direct":""}`}>
      <div className="list-poster-watermark">{info.target}</div>
      <div className="list-poster-header">
        <div className="list-poster-header-copy">
          <span className="list-poster-kicker">NBA PER-75 · CUSTOM ALL-TIME RANKING</span>
          <h2 className="list-poster-title"><span>MY TOP {info.target}</span><span>PLAYERS OF ALL-TIME</span></h2>
          <p>{buildMethod==="direct"?"Built by selecting players directly.":"Built through head-to-head player matchups."}</p>
        </div>
        <div className="list-poster-method">{buildMethod==="direct"?"SELECT PLAYERS":"HEAD-TO-HEAD"}<b>2026</b></div>
      </div>
      <div className="list-poster-feature"><span></span><b>{info.target} PLAYERS</b><small>ONE HISTORICAL LIST</small></div>
      <div className="list-poster-rule"></div>
      <div className="list-poster-grid" style={{gridTemplateColumns:`repeat(${Math.ceil(info.target/10)},minmax(0,1fr))`}}>{finalList.map((name,i)=><Link className={`list-poster-row rank-${i+1}`} key={name} to={profileFor(name)}>
        <span className="list-poster-rank">{i+1}</span><span className="list-poster-avatar"><T50Headshot name={name} player={players[name]}/></span><span className="list-poster-name-wrap"><span className="list-poster-name">{name}</span><small>ALL-TIME PLAYER</small></span><span className="list-poster-arrow">›</span>
      </Link>)}</div>
      {info.target>10 && <div className="list-poster-legacy" aria-hidden="true">{finalList.slice(0,5).map((name,i)=><div className="list-poster-legacy-player" key={name} style={{"--legacy-index":i}}><T50Headshot name={name} player={players[name]}/></div>)}</div>}
      <div className="list-poster-footer"><span>NBA PER-75</span><span>MY ALL-TIME LIST</span><span>T{info.target}</span></div>
    </div>
    <div className="result-actions"><button className="btn alt" onClick={()=>shareList(finalList)}>{shareStatus||"SHARE LIST"}</button><button className="btn alt" onClick={reset}>START OVER</button></div>
    <div className="missed"><h2>{buildMethod==="direct"?"EDIT YOUR LIST":"JUST MISSED THE LIST"}</h2>{buildMethod==="direct"?<div className="direct-result-edit"><button className="btn alt" onClick={()=>{setDone(false);setDirectSearch("");}}>EDIT SELECTION</button></div>:<div className="results-grid">{rankings.slice(info.target,info.target+5).map(name=><Link className="card result-card" key={name} to={profileFor(name)}><div className="photo"><T50Headshot name={name} player={players[name]}/></div><div className="name">{name}</div><div className="team">{score(name)} WINS</div></Link>)}</div>}</div>
  </PageShell>;
}

function App() {
  return <>
    <Header/>
    <Routes>
      <Route path="/" element={<Home/>}/>
      <Route path="/players" element={<Players/>}/>
      <Route path="/players/:playerId" element={<PlayerProfileErrorBoundary><PlayerProfile/></PlayerProfileErrorBoundary>}/>
      <Route path="/big-board" element={<BigBoard/>}/>
      <Route path="/compare" element={<ComparisonErrorBoundary><Compare/></ComparisonErrorBoundary>}/>
      <Route path="/explorer" element={<Explorer/>}/>
      <Route path="/teams" element={<Teams/>}/>
      <Route path="/teams/:team" element={<Teams/>}/>
      <Route path="/compare/teams" element={<TeamComparisonPage/>}/>
      <Route path="/create-t50" element={<CreateT50/>}/>
      <Route path="/methodology" element={<Methodology/>}/>
      <Route path="*" element={<Home/>}/>
    </Routes>
  </>;
}

export default App;
