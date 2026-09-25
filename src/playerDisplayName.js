// Public-facing player-name normalization.
// Historical source data can contain asterisks; the website hides them
// while preserving canonical source data.
export function playerDisplayName(name) {
  return String(name ?? "").replace(/\*/g, "").replace(/\s{2,}/g, " ").trim();
}
