/**
 * STP (standard temperature & pressure) correction for muon flux — TS mirror of
 * observatory/muon/pressure.py, matching UKRAA_PicoMuon's STP method:
 *
 *   corrected = raw / ( ((T_degC + 273.15) / 293.15) * (1013.25 / P_hPa) )
 *
 * Normalizes the rate to 20 degC / 1013.25 hPa. Returns the raw rate unchanged
 * when temperature or pressure is missing/invalid (can't correct without both).
 */
export const REFERENCE_TEMP_K = 293.15; // 20 degC
export const REFERENCE_PRESSURE_HPA = 1013.25;

export function stpFactor(tempC: number, pressureHpa: number): number {
  return ((tempC + 273.15) / REFERENCE_TEMP_K) * (REFERENCE_PRESSURE_HPA / pressureHpa);
}

export function stpCorrectedRate(
  rate: number | null,
  tempC: number | null | undefined,
  pressureHpa: number | null | undefined,
): number | null {
  if (rate == null) return rate;
  if (tempC == null || pressureHpa == null || pressureHpa <= 0) return rate;
  const factor = stpFactor(tempC, pressureHpa);
  if (factor <= 0) return rate;
  return rate / factor;
}
