/**
 * Compute a y-domain with 5% padding on each side of the visible data.
 * Preserves negative range when present; never clamps to zero.
 * Returns null when data is empty (caller falls back to Plot's auto-domain).
 */
export function paddedYDomain(values: number[]): [number, number] | null {
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1; // guard flat series
  return [Math.floor(min - 0.05 * range), Math.ceil(max + 0.05 * range)];
}
