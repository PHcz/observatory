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
