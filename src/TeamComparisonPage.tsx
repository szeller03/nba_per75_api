
import React, { useEffect, useMemo, useState } from 'react';
import {
  compareTeams,
  getTeamSeasons,
  getTeams,
  teamLogoUrl,
  type TeamComparisonRow,
  type TeamIndexItem,
  type TeamSeason,
} from './teamComparisonApi';
import './team-comparison.css';

const STATS = [
  { key: 'ORtg', label: 'ORtg', direction: 'higher_is_better' },
  { key: 'DRtg', label: 'DRtg', direction: 'lower_is_better' },
  { key: 'rORTG', label: 'Relative ORtg', direction: 'higher_is_better' },
  { key: 'rDRTG', label: 'Relative DRtg', direction: 'lower_is_better' },
  { key: 'Pace_Final', label: 'Pace', direction: 'higher_is_better' },
] as const;

function number(v: unknown, digits = 1) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
}
function signed(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${n.toFixed(1)}` : '—';
}
function prettyStat(key: string) {
  return STATS.find(s => s.key === key)?.label ?? key;
}
function isBetter(row: TeamComparisonRow, side: 'A' | 'B') {
  const a = Number(row.Team_A_Value);
  const b = Number(row.Team_B_Value);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
  const lower = row.Direction === 'lower_is_better';
  return side === 'A' ? (lower ? a < b : a > b) : (lower ? b < a : b > a);
}

function TeamBadge({ item, large = false }: { item?: TeamIndexItem; large?: boolean }) {
  const [failed, setFailed] = useState(false);
  const src = teamLogoUrl(item);
  if (!src || failed) {
    return <div className={`tc-badge-fallback ${large ? 'large' : ''}`}>
      {(item?.Team || '?').slice(0, 2).toUpperCase()}
    </div>;
  }
  return <img className={`tc-badge ${large ? 'large' : ''}`} src={src} alt="" onError={() => setFailed(true)} />;
}

function SeasonPicker({
  label,
  seasons,
  selected,
  onChange,
}: {
  label: string;
  seasons: TeamSeason[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const all = seasons.map(s => s.Season).filter(Boolean);
  const toggle = (season: string) => {
    onChange(selected.includes(season)
      ? selected.filter(s => s !== season)
      : [...selected, season]);
  };
  return (
    <div className="tc-season-picker">
      <div className="tc-picker-label">{label}</div>
      <div className="tc-selected-seasons">
        {selected.length ? selected.map(s =>
          <button key={s} className="tc-chip" onClick={() => toggle(s)}>{s} ×</button>
        ) : <span className="tc-muted">Select one or more seasons</span>}
      </div>
      <select value="" onChange={e => e.target.value && toggle(e.target.value)}>
        <option value="">Add season…</option>
        {all.filter(s => !selected.includes(s)).map(s => <option key={s} value={s}>{s}</option>)}
      </select>
      <button className="tc-clear" onClick={() => onChange([])} disabled={!selected.length}>Clear</button>
    </div>
  );
}

export function TeamComparisonPage() {
  const [teams, setTeams] = useState<TeamIndexItem[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [seasonsA, setSeasonsA] = useState<TeamSeason[]>([]);
  const [seasonsB, setSeasonsB] = useState<TeamSeason[]>([]);
  const [selectedA, setSelectedA] = useState<string[]>([]);
  const [selectedB, setSelectedB] = useState<string[]>([]);
  const [rows, setRows] = useState<TeamComparisonRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<'overall' | 'details'>('overall');

  useEffect(() => {
    getTeams().then(t => {
      setTeams(t);
      if (t.length >= 2) {
        setTeamA(t[0].Team);
        setTeamB(t[1].Team);
      }
    }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!teamA) return;
    getTeamSeasons(teamA).then(s => {
      setSeasonsA(s);
      setSelectedA(s[0]?.Season ? [s[0].Season] : []);
    }).catch(e => setError(e.message));
  }, [teamA]);

  useEffect(() => {
    if (!teamB) return;
    getTeamSeasons(teamB).then(s => {
      setSeasonsB(s);
      setSelectedB(s[0]?.Season ? [s[0].Season] : []);
    }).catch(e => setError(e.message));
  }, [teamB]);

  const itemA = teams.find(t => t.Team === teamA);
  const itemB = teams.find(t => t.Team === teamB);

  const run = async () => {
    if (!teamA || !teamB || !selectedA.length || !selectedB.length) return;
    setRunning(true);
    setError('');
    try {
      setRows(await compareTeams(teamA, selectedA, teamB, selectedB));
    } catch (e: any) {
      setError(e?.message || 'Unable to compare teams.');
      setRows([]);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (teamA && teamB && selectedA.length && selectedB.length) run();
    // Intentionally triggered only by selected inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teamA, teamB, selectedA.join('|'), selectedB.join('|')]);

  const wins = useMemo(() => ({
    a: rows.filter(r => r.Statistical_Advantage === 'Team A').length,
    b: rows.filter(r => r.Statistical_Advantage === 'Team B').length,
  }), [rows]);

  if (loading) return <div className="tc-page"><div className="tc-loading">Loading teams…</div></div>;

  return (
    <div className="tc-page">
      <header className="tc-header">
        <div>
          <div className="tc-eyebrow">NBA PER-75</div>
          <h1>Team Comparison</h1>
          <p>Compare any two teams across independently selected seasons.</p>
        </div>
        <div className="tc-header-note">5 team statistics · games-weighted aggregation</div>
      </header>

      <section className="tc-setup">
        <div className="tc-side">
          <div className="tc-side-head">
            <TeamBadge item={itemA} large />
            <div>
              <div className="tc-eyebrow">TEAM A</div>
              <h2>{teamA || 'Select team'}</h2>
            </div>
          </div>
          <select className="tc-team-select" value={teamA} onChange={e => setTeamA(e.target.value)}>
            {teams.map(t => <option key={t.Team} value={t.Team}>{t.Team}</option>)}
          </select>
          <SeasonPicker label="Comparison period" seasons={seasonsA} selected={selectedA} onChange={setSelectedA} />
        </div>

        <div className="tc-vs">VS</div>

        <div className="tc-side">
          <div className="tc-side-head">
            <TeamBadge item={itemB} large />
            <div>
              <div className="tc-eyebrow">TEAM B</div>
              <h2>{teamB || 'Select team'}</h2>
            </div>
          </div>
          <select className="tc-team-select" value={teamB} onChange={e => setTeamB(e.target.value)}>
            {teams.map(t => <option key={t.Team} value={t.Team}>{t.Team}</option>)}
          </select>
          <SeasonPicker label="Comparison period" seasons={seasonsB} selected={selectedB} onChange={setSelectedB} />
        </div>
      </section>

      {error && <div className="tc-error">{error}</div>}

      <div className="tc-tabs">
        <button className={view === 'overall' ? 'active' : ''} onClick={() => setView('overall')}>Overall</button>
        <button className={view === 'details' ? 'active' : ''} onClick={() => setView('details')}>Statistic Detail</button>
      </div>

      <section className="tc-panel">
        <div className="tc-panel-head">
          <div>
            <div className="tc-eyebrow">HEAD-TO-HEAD</div>
            <h2>{itemA?.Team || teamA} <span>vs.</span> {itemB?.Team || teamB}</h2>
            <p>{selectedA.join(' · ') || '—'} <span>vs.</span> {selectedB.join(' · ') || '—'}</p>
          </div>
          <div className="tc-score">
            <strong>{wins.a}</strong><span>—</span><strong>{wins.b}</strong>
            <small>statistical edges</small>
          </div>
        </div>

        {running ? <div className="tc-loading">Calculating comparison…</div> :
          view === 'overall' ? (
            <div className="tc-compare-table">
              {rows.map(row => (
                <div className="tc-stat-row" key={row.Statistic}>
                  <div className={`tc-value ${isBetter(row, 'A') ? 'winner' : ''}`}>
                    <strong>{row.Statistic === 'DRtg' || row.Statistic === 'rDRTG' ? number(row.Team_A_Value) : (row.Statistic === 'rORTG' ? signed(row.Team_A_Value) : number(row.Team_A_Value))}</strong>
                    {isBetter(row, 'A') && <small>EDGE</small>}
                  </div>
                  <div className="tc-stat-label">
                    <strong>{prettyStat(row.Statistic)}</strong>
                    <span>{row.Direction === 'lower_is_better' ? 'Lower is better' : 'Higher is better'}</span>
                  </div>
                  <div className={`tc-value right ${isBetter(row, 'B') ? 'winner' : ''}`}>
                    <strong>{row.Statistic === 'DRtg' || row.Statistic === 'rDRTG' ? number(row.Team_B_Value) : (row.Statistic === 'rORTG' ? signed(row.Team_B_Value) : number(row.Team_B_Value))}</strong>
                    {isBetter(row, 'B') && <small>EDGE</small>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="tc-detail-table">
              <div className="tc-detail-head"><span>STATISTIC</span><span>TEAM A</span><span>TEAM B</span><span>DIFFERENCE</span><span>EDGE</span></div>
              {rows.map(row => <div className="tc-detail-row" key={row.Statistic}>
                <span>{prettyStat(row.Statistic)}</span>
                <span>{number(row.Team_A_Value)}</span>
                <span>{number(row.Team_B_Value)}</span>
                <span>{signed(row.Difference_A_minus_B)}</span>
                <span className={row.Statistical_Advantage === 'Team A' ? 'edge-a' : row.Statistical_Advantage === 'Team B' ? 'edge-b' : ''}>{row.Statistical_Advantage ?? '—'}</span>
              </div>)}
            </div>
          )
        }
      </section>

      <section className="tc-method-note">
        <strong>How the comparison works</strong>
        <span>Each selected season is weighted by season exposure when available. Directionality is respected: higher is better for ORtg, rORTG, and Pace; lower is better for DRtg and rDRTG.</span>
      </section>

      <button className="tc-run-button" onClick={run} disabled={running || !selectedA.length || !selectedB.length}>
        {running ? 'Comparing…' : 'Refresh comparison'}
      </button>
    </div>
  );
}
