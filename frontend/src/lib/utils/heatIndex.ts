/**
 * Rothfusz heat index approximation (NWS / RESEARCH Pattern 7).
 *
 * Returns apparent temperature in °C. The formula is only valid when
 * temp_c ≥ 26.7°C AND humidity_pct ≥ 40%. Outside that regime the raw
 * temperature is returned unchanged (heat index is undefined below freezing;
 * callers must additionally guard temp_c > 0 before displaying).
 */
export function feelsLikeC(tempC: number, humidityPct: number): number {
  if (tempC < 26.7 || humidityPct < 40) return tempC;
  const T = tempC, R = humidityPct;
  return (
    -8.78469475556 +
    1.61139411 * T +
    2.33854883889 * R -
    0.14611605 * T * R -
    0.012308094 * T * T -
    0.0164248277778 * R * R +
    0.002211732 * T * T * R +
    0.00072546 * T * R * R -
    0.000003582 * T * T * R * R
  );
}
