// Health-band → Hyborg-token collapses for the Air Quality panel.
// Every band table here is the LOCKED contract from 11-UI-SPEC §Color.
// Tokens only (--accent / --warn / --alert) → light + dark for free.

export type BandToken = '--accent' | '--warn' | '--alert';
export interface Band {
  label: string;
  token: BandToken;
}
export interface UvBand extends Band {
  advice: string;
}

export type PollenType = 'alder' | 'birch' | 'grass' | 'mugwort' | 'olive' | 'ragweed';

/**
 * European AQI: 6 official bands collapsed onto 3 Hyborg tokens.
 * Boundaries inclusive-low / exclusive-high (>= 80 → Very poor).
 */
export function aqiBand(aqi: number): Band {
  if (aqi < 20) return { label: 'Good', token: '--accent' };
  if (aqi < 40) return { label: 'Fair', token: '--accent' };
  if (aqi < 60) return { label: 'Moderate', token: '--warn' };
  if (aqi < 80) return { label: 'Poor', token: '--warn' };
  if (aqi < 100) return { label: 'Very poor', token: '--alert' };
  return { label: 'Extremely poor', token: '--alert' };
}

/**
 * WHO UV index: 5 bands + one-line advice collapsed onto 3 tokens.
 * Advice strings use commas / `·` only (no em dashes — ForecastPanel convention).
 */
export function uvBand(uv: number): UvBand {
  if (uv < 3) return { label: 'Low', token: '--accent', advice: 'No protection needed' };
  if (uv < 6)
    return { label: 'Moderate', token: '--warn', advice: 'Seek shade midday; sunscreen advised' };
  if (uv < 8) return { label: 'High', token: '--warn', advice: 'Sun protection advised' };
  if (uv < 11)
    return { label: 'Very high', token: '--alert', advice: 'Extra protection, avoid midday sun' };
  return { label: 'Extreme', token: '--alert', advice: 'Avoid sun 11:00-15:00; full protection' };
}

// Per-type CAMS thresholds (RESEARCH §Band-mapping, MEDIUM confidence — Open Q3).
// High-threshold types (tree / mugwort pollen): Low 1-9 / Moderate 10-99 / High 100-299 / Very high >=300.
// Low-threshold types (grass / ragweed):        Low 1-2 / Moderate 3-49 / High 50-149 / Very high >=150.
const HIGH_THRESHOLD: ReadonlySet<PollenType> = new Set(['alder', 'birch', 'olive', 'mugwort']);

/**
 * Map a per-type pollen concentration to a 3-token band.
 * Returns null for value <= 0 (off-season / absent) so the caller drops the row.
 */
export function pollenBand(type: PollenType, value: number): Band | null {
  if (value <= 0) return null;
  if (HIGH_THRESHOLD.has(type)) {
    if (value < 10) return { label: 'Low', token: '--accent' };
    if (value < 100) return { label: 'Moderate', token: '--warn' };
    if (value < 300) return { label: 'High', token: '--alert' };
    return { label: 'Very high', token: '--alert' };
  }
  // grass / ragweed
  if (value < 3) return { label: 'Low', token: '--accent' };
  if (value < 50) return { label: 'Moderate', token: '--warn' };
  if (value < 150) return { label: 'High', token: '--alert' };
  return { label: 'Very high', token: '--alert' };
}
