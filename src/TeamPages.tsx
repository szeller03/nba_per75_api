import React, { useEffect, useMemo, useState } from 'react';
import {
  getTeam,
  getTeamLeaderboardFeed,
  getTeamProfile,
  getTeamSeasons,
  getTeams,
  teamLogoCandidates,
  type TeamIndexItem,
  type TeamSeason,
} from './teamApi';
import './team-pages.css';

const fmt = (v: unknown, digits = 1) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
};
const pct = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? `${(n <= 1 ? n * 100 : n).toFixed(1)}%` : '—';
};
const signed = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${n.toFixed(1)}` : '—';
};

function TeamMark({ item, large = false }: { item?: TeamIndexItem | TeamSeason; large?: boolean }) {
  const candidates = teamLogoCandidates(item);
  const [attempt, setAttempt] = useState(0);
  const src = candidates[attempt] || '';
  if (!src) return <div className={`team-mark-fallback ${large ? 'large' : ''}`}>{String(item?.Team || '?').replace(/\*$/,'').slice(0, 2).toUpperCase()}</div>;
  return <img className={`team-mark ${large ? 'large' : ''}`} src={src} alt="" onError={() => setAttempt(v => v + 1)} />;
}

export function TeamsPage({ onOpenTeam }: { onOpenTeam: (team: string) => void }) {
  const [teams, setTeams] = useState<TeamIndexItem[]>([]);
  const [feed, setFeed] = useState<Record<string, unknown>[]>([]);
  const [stat, setStat] = useState<'Relative_ORtg' | 'Relative_DRtg' | 'Relative_NRtg'>('Relative_NRtg');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getTeams(), getTeamLeaderboardFeed()])
      .then(([t, f]) => { setTeams(t); setFeed(f); })
      .finally(() => setLoading(false));
  }, []);

  const rows = useMemo(() => {
    const matching = feed.filter(r => String(r.Statistic ?? r.statistic ?? '').toLowerCase() === stat.toLowerCase());
    const source = matching.length ? matching : feed.filter(r => r[stat] != null);
    const sorted = [...source].sort((a, b) => Number(b.Value ?? b.value ?? b[stat] ?? -Infinity) - Number(a.Value ?? a.value ?? a[stat] ?? -Infinity));
    const filtered = sorted.filter(r => String(r.Team ?? r.team ?? '').toLowerCase().includes(query.toLowerCase()));
    return filtered.slice(0, 10);
  }, [feed, stat, query]);

  if (loading) return <div className="team-page"><div className="team-loading">Loading teams…</div></div>;

  return <div className="team-page">
    <header className="team-section-head">
      <div>
        <div className="eyebrow">NBA PER-75</div>
        <h1>Teams</h1>
        <p>Historical team performance, competitive context, and season profiles.</p>
      </div>
      <input className="team-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search teams…" />
    </header>

    <section className="team-panel">
      <div className="panel-head">
        <div><span className="eyebrow">ALL-TIME</span><h2>Team Leaders</h2></div>
        <div className="segmented">
          {([['Relative_NRtg','NRtg'], ['Relative_ORtg','ORtg'], ['Relative_DRtg','DRtg']] as const).map(([key,label]) =>
            <button className={stat === key ? 'active' : ''} onClick={() => setStat(key)} key={key}>{label}</button>)}
        </div>
      </div>
      <div className="team-table">
        <div className="team-row team-row-head"><span>#</span><span>TEAM</span><span>SEASON</span><span>VALUE</span><span>TEAM SUCCESS</span></div>
        {rows.map((r, i) => {
          const team = String(r.Team ?? r.team ?? '');
          const season = String(r.Season ?? r.season ?? '');
          const value = r.Value ?? r.value ?? r[stat];
          const item = teams.find(t => t.Team === team);
          return <button className="team-row team-row-button" key={`${team}-${season}-${i}`} onClick={() => onOpenTeam(team)}>
            <span className="rank">{i + 1}</span><span className="team-name"><TeamMark item={item} />{team}</span><span>{season}</span><strong>{signed(value)}</strong><span>{String(r.Team_Success ?? r.team_success ?? r.Success ?? r.success ?? r.Playoff_Finish ?? r.playoff_finish ?? (r.Made_Playoffs ? "PLAYOFFS" : "MISSED PLAYOFFS"))}</span>
          </button>;
        })}
      </div>
    </section>
  </div>;
}

export function TeamProfilePage({ team, onBack }: { team: string; onBack?: () => void }) {
  const [profile, setProfile] = useState<any>(null);
  const [seasons, setSeasons] = useState<TeamSeason[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [profileStats, setProfileStats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getTeam(team), getTeamSeasons(team)])
      .then(([p, s]) => { setProfile(p); setSeasons(s); setSelected(s[0]?.Season ?? ''); })
      .finally(() => setLoading(false));
  }, [team]);

  useEffect(() => {
    if (!selected) { setProfileStats([]); return; }
    getTeamProfile(team, selected)
      .then((p) => setProfileStats(Array.isArray(p?.stats) ? p.stats : []))
      .catch(() => setProfileStats([]));
  }, [team, selected]);

  const season = seasons.find(s => s.Season === selected) ?? seasons[0];
  const identity = profile?.identity ?? profile?.team ?? profile;

  if (loading) return <div className="team-page"><div className="team-loading">Loading {team}…</div></div>;
  if (!season) return <div className="team-page"><div className="team-empty">No season profile available.</div></div>;

  return <div className="team-page">
    <button className="back-button" onClick={onBack}>← Teams</button>
    <section className="team-hero">
      <div className="hero-logo"><TeamMark item={{ ...identity, Team: team, Logo_File: identity?.Logo_File }} large /></div>
      <div><div className="eyebrow">TEAM PROFILE</div><h1>{team}</h1><p>{identity?.First_Season ?? seasons[seasons.length - 1]?.Season} — {identity?.Last_Season ?? seasons[0]?.Season}</p></div>
    </section>

    <div className="season-toolbar">
      <div><span className="eyebrow">SEASON</span><strong>{season.Season}</strong></div>
      <select value={selected} onChange={e => setSelected(e.target.value)}>{seasons.map(s => <option key={s.Season} value={s.Season}>{s.Season}</option>)}</select>
    </div>

    <section className="metric-grid">
      <Metric label="Record" value={`${season.W ?? '—'}–${season.L ?? '—'}`} sub={pct(season.Win_Pct)} />
      <Metric label="ORtg" value={fmt(season.ORtg)} sub={`rORtg ${signed(season.rORTG ?? season.Relative_ORtg)}`} />
      <Metric label="DRtg" value={fmt(season.DRtg)} sub={`rDRtg ${signed(season.rDRTG ?? season.Relative_DRtg)}`} />
      <Metric label="NRtg" value={signed(season.NRtg)} sub={`rNRtg ${signed(season.Relative_NRtg)}`} />
    </section>

    <section className="team-panel percentile-panel">
      <div className="panel-head">
        <div><span className="eyebrow">HISTORICAL PERCENTILES</span><h2>Team Profile Rankings</h2></div>
        <span className="season-count">0–100</span>
      </div>
      <div className="percentile-grid">
        {profileStats.map((item) => {
          const percentile = Number(item?.percentiles?.historical);
          if (!Number.isFinite(percentile)) return null;
          const clamped = Math.max(0, Math.min(100, percentile));
          const tone = clamped >= 90 ? 'elite' : clamped >= 75 ? 'strong' : clamped >= 50 ? 'average' : clamped >= 25 ? 'below' : 'low';
          const rawValue = Number(item?.value);
          const displayValue = Number.isFinite(rawValue)
            ? (String(item?.key ?? '').includes('%') ? `${rawValue.toFixed(1)}%` : (rawValue > 0 ? '+' : '') + rawValue.toFixed(1))
            : '—';
          return (
            <div className="percentile-card" key={item.key}>
              <div className="percentile-card-head"><span>{item.label}</span><strong className={`percentile-value ${tone}`}>{clamped.toFixed(0)}</strong></div>
              <div className="percentile-meta"><span>{displayValue}</span><span>{item.direction === 'lower' ? 'LOWER IS BETTER' : 'HIGHER IS BETTER'}</span></div>
              <div className="percentile-track"><span className={tone} style={{ width: `${clamped}%` }} /></div>
            </div>
          );
        })}
      </div>
    </section>

    <section className="team-panel">
      <div className="panel-head"><div><span className="eyebrow">COMPETITIVE CONTEXT</span><h2>{season.Playoff_Finish ?? (season.Made_Playoffs ? 'Playoffs' : 'Missed Playoffs')}</h2></div>{season.Champion ? <span className="champion-pill">CHAMPION</span> : null}</div>
      <div className="context-grid">
        <Context label="Seed" value={season.Seed ?? '—'} />
        <Context label="Playoff round" value={season.Playoff_Round ?? '—'} />
        <Context label="Pace" value={fmt(season.Pace_Final)} />
        <Context label="Record" value={`${season.W ?? '—'}–${season.L ?? '—'}`} />
      </div>
    </section>

    <section className="team-panel">
      <div className="panel-head"><div><span className="eyebrow">HISTORY</span><h2>Season by Season</h2></div><span className="season-count">{seasons.length} seasons</span></div>
      <div className="team-table season-table">
        <div className="team-row team-row-head"><span>SEASON</span><span>W–L</span><span>ORtg</span><span>DRtg</span><span>NRtg</span><span>TEAM SUCCESS</span></div>
        {seasons.map(s => <button className={`team-row team-row-button ${s.Season === selected ? 'selected' : ''}`} key={s.Season} onClick={() => setSelected(s.Season)}>
          <span>{s.Season}</span><span>{s.W ?? '—'}–{s.L ?? '—'}</span><span>{fmt(s.ORtg)}</span><span>{fmt(s.DRtg)}</span><strong>{signed(s.NRtg)}</strong><span>{s.Champion ? 'Champion' : s.Playoff_Finish ?? (s.Made_Playoffs ? 'Playoffs' : '—')}</span>
        </button>)}
      </div>
    </section>
  </div>;
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) { return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>; }
function Context({ label, value }: { label: string; value: unknown }) { return <div className="context-card"><span>{label}</span><strong>{String(value)}</strong></div>; }
