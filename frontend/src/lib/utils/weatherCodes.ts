// WMO 4677 / Open-Meteo weather_code -> { glyph, label } map (10-RESEARCH table).
// The glyph string names a line-art family rendered by WeatherGlyph.svelte;
// the label is the short Hyborg condition text shown beside the glyph.
// Any unmapped (or null) code falls back to { glyph: 'cloud', label: '—' } per
// the UI-SPEC §Glyph contract — never render nothing.

export interface Condition {
  glyph: string;
  label: string;
}

const MAP: Record<number, Condition> = {
  0: { glyph: 'sun', label: 'Clear' },
  1: { glyph: 'sun-cloud', label: 'Mainly clear' },
  2: { glyph: 'sun-cloud', label: 'Partly cloudy' },
  3: { glyph: 'cloud', label: 'Overcast' },
  45: { glyph: 'fog', label: 'Fog' },
  48: { glyph: 'fog', label: 'Fog' },
  51: { glyph: 'drizzle', label: 'Drizzle' },
  53: { glyph: 'drizzle', label: 'Drizzle' },
  55: { glyph: 'drizzle', label: 'Drizzle' },
  56: { glyph: 'drizzle', label: 'Freezing drizzle' },
  57: { glyph: 'drizzle', label: 'Freezing drizzle' },
  61: { glyph: 'rain', label: 'Rain' },
  63: { glyph: 'rain', label: 'Rain' },
  65: { glyph: 'rain', label: 'Heavy rain' },
  66: { glyph: 'rain', label: 'Freezing rain' },
  67: { glyph: 'rain', label: 'Freezing rain' },
  71: { glyph: 'snow', label: 'Snow' },
  73: { glyph: 'snow', label: 'Snow' },
  75: { glyph: 'snow', label: 'Snow' },
  77: { glyph: 'snow', label: 'Snow grains' },
  80: { glyph: 'rain', label: 'Rain showers' },
  81: { glyph: 'rain', label: 'Rain showers' },
  82: { glyph: 'rain', label: 'Heavy rain' },
  85: { glyph: 'snow', label: 'Snow showers' },
  86: { glyph: 'snow', label: 'Snow showers' },
  95: { glyph: 'storm', label: 'Thunderstorm' },
  96: { glyph: 'storm', label: 'Thunderstorm' },
  99: { glyph: 'storm', label: 'Thunderstorm' },
};

export function condition(code: number | null): Condition {
  return (code != null && MAP[code]) || { glyph: 'cloud', label: '—' }; // fallback (UI-SPEC)
}
