
export function extractPeakProfile(profilePayload, seasonType = "Regular Season") {
  const root = profilePayload?.profile ?? profilePayload?.data ?? profilePayload ?? {};
  const peaks = root?.peaks ?? root?.peak_profiles ?? root?.five_year_peaks ?? root?.peak ?? null;
  if (!peaks) return null;

  if (Array.isArray(peaks)) {
    return peaks.find(p =>
      String(p?.Season_Type ?? p?.season_type ?? "").toLowerCase() === seasonType.toLowerCase()
    ) ?? peaks.find(p => String(p?.profile_scope ?? "").toLowerCase().includes("5-year")) ?? peaks[0] ?? null;
  }

  if (typeof peaks === "object") {
    const direct = peaks[seasonType] ?? peaks[seasonType.toLowerCase()] ??
      peaks[seasonType === "Playoffs" ? "playoffs" : "regular_season"];
    if (direct) return direct;

    const candidates = Object.values(peaks);
    return candidates.find(p =>
      String(p?.Season_Type ?? p?.season_type ?? "").toLowerCase() === seasonType.toLowerCase()
    ) ?? candidates.find(p => String(p?.profile_scope ?? "").toLowerCase().includes("5-year")) ?? null;
  }
  return null;
}

export function peakDisplayValues(peak) {
  if (!peak) return null;
  return {
    start: peak.peak_start_year ?? peak.start_year ?? peak.startYear ?? null,
    end: peak.peak_end_year ?? peak.end_year ?? peak.endYear ?? null,
    sdi: peak.peak_sdi ?? peak.SDI ?? peak.sdi ?? null,
    percentile: peak.sdi_percentile ?? peak.SDI_Percentile ?? peak.percentile ?? null,
    seasons: peak.peak_seasons ?? peak.seasons ?? null,
    skipped: peak.skipped_seasons ?? peak.skipped ?? null,
    statistics: peak.peak_statistics_json ?? peak.statistics ?? null,
  };
}
