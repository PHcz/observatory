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
};

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
    return { theme, panels };
  } catch {
    return structuredClone(DEFAULTS);
  }
}
