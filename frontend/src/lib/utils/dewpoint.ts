// Magnus-formula approximation for dew point
// b = 17.625, c = 243.04 (August-Roche-Magnus constants)
const B = 17.625;
const C = 243.04;

export function dewPointC(tempC: number, humidityPct: number): number {
  if (!isFinite(tempC) || !isFinite(humidityPct) || humidityPct <= 0) return NaN;
  const gamma = Math.log(humidityPct / 100) + (B * tempC) / (C + tempC);
  const dp = (C * gamma) / (B - gamma);
  return Math.round(dp * 10) / 10;
}

// Single comfort descriptor for a dew-point value. Bands derived from the
// operator's guide (under ~10°C dry · 15–18°C sticky · 20°C+ muggy), made
// continuous: the dry/comfortable band runs up to the sticky threshold (15°C),
// sticky runs to the muggy threshold (20°C). Returns null for NaN/invalid.
export function dewComfort(dewpointC: number): string | null {
  if (!isFinite(dewpointC)) return null;
  if (dewpointC < 15) return 'dry, comfortable';
  if (dewpointC < 20) return 'starting to feel sticky';
  return 'muggy, oppressive';
}
