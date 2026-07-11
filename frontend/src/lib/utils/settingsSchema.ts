// Settings schema for Phase 8.5 UI-16 + UI-17; extended in Phase 16 (ENH-01/02/04/05).
// localStorage key: observatory.settings.v1
// Safe-merge: missing panel keys default to visible (true).

export type Theme = 'light' | 'dark' | 'auto';

export type PanelKey =
  | 'headerPanel'
  | 'statsRow'
  | 'todayStrip'
  | 'zambrettiCard'
  | 'weatherAlerts'
  | 'forecast'
  | 'airQuality'
  | 'indoorAir'
  | 'muonChart'
  | 'muonDiagnostics'
  | 'muonGainDrift'
  | 'adcSpectrum'
  | 'barometric'
  | 'nmdbOverlay'
  | 'forbush'
  | 'spaceWeather'
  | 'earthquakes'
  | 'lightning'
  | 'aurora'
  | 'temperatureChart'
  | 'pressureChart'
  | 'humidityChart'
  | 'lightChart'
  | 'healthRow';

export interface Settings {
  theme: Theme;
  panels: Record<PanelKey, boolean>;
  order: PanelKey[];
}

export const ALL_PANELS: PanelKey[] = [
  'headerPanel',
  'statsRow',
  'todayStrip',
  'zambrettiCard',
  'weatherAlerts',
  'forecast',
  'airQuality',
  'indoorAir',
  'muonChart',
  'muonDiagnostics',
  'muonGainDrift',
  'adcSpectrum',
  'barometric',
  'nmdbOverlay',
  'forbush',
  'spaceWeather',
  'earthquakes',
  'lightning',
  'aurora',
  'temperatureChart',
  'pressureChart',
  'humidityChart',
  'lightChart',
  'healthRow',
];

// Phase 16 (ENH-01/02/04/05): muon diagnostic panels default OFF (advanced/verbose);
// all other panels (including the three new weather panels) default ON.
// This replaces the prior uniform Object.fromEntries(ALL_PANELS.map(...true)) approach.
const PANEL_DEFAULTS_OFF: PanelKey[] = ['muonDiagnostics', 'muonGainDrift'];

export const DEFAULTS: Settings = {
  theme: 'auto',
  panels: Object.fromEntries(
    ALL_PANELS.map((k) => [k, !PANEL_DEFAULTS_OFF.includes(k)])
  ) as Record<PanelKey, boolean>,
  order: [...ALL_PANELS],
};

// Safe-merge a stored order into a full permutation of `canonical`:
// keep valid stored keys in their stored order (de-duped), drop unknown keys,
// then append any canonical keys the stored order was missing. Guarantees the
// result is always a complete permutation — the same missing-key philosophy as
// the panels safe-merge above.
export function mergeOrder(stored: unknown, canonical: PanelKey[]): PanelKey[] {
  const valid = new Set<string>(canonical);
  const seen = new Set<PanelKey>();
  const result: PanelKey[] = [];
  if (Array.isArray(stored)) {
    for (const k of stored) {
      if (typeof k === 'string' && valid.has(k) && !seen.has(k as PanelKey)) {
        result.push(k as PanelKey);
        seen.add(k as PanelKey);
      }
    }
  }
  for (const k of canonical) {
    if (!seen.has(k)) result.push(k);
  }
  return result;
}

export function parseSettings(raw: string | null): Settings {
  if (!raw) return structuredClone(DEFAULTS);
  try {
    const parsed = JSON.parse(raw) as Partial<Settings>;
    const theme: Theme =
      parsed?.theme === 'light' || parsed?.theme === 'dark' || parsed?.theme === 'auto'
        ? parsed.theme
        : DEFAULTS.theme;
    const panels = { ...DEFAULTS.panels } as Record<PanelKey, boolean>;
    if (parsed?.panels && typeof parsed.panels === 'object') {
      for (const k of ALL_PANELS) {
        const v = (parsed.panels as Record<string, unknown>)[k];
        if (typeof v === 'boolean') panels[k] = v;
        // Missing keys keep DEFAULTS (= visible) — safe-merge rule.
      }
    }
    const order = mergeOrder((parsed as { order?: unknown })?.order, ALL_PANELS);
    return { theme, panels, order };
  } catch {
    return structuredClone(DEFAULTS);
  }
}
