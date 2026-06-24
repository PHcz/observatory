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

/**
 * Y-axis domain + explicit tick values that GUARANTEE the lowest tick is
 * strictly below the data minimum, so a chart line/dot never dips below the
 * lowest labelled gridline.
 *
 * `paddedYDomain` only pads the domain floor 5%; Plot's "nice tick" algorithm
 * then places the lowest tick at the smallest round value ≥ domain.min, which
 * can land ABOVE the data minimum (e.g. data min 13 → lowest tick 15; dewpoint
 * min 12 → lowest tick 20). By snapping the floor to a nice step strictly below
 * the min (and the ceiling strictly above the max) and returning the ticks
 * ourselves, the axis always brackets the data: a labelled gridline sits both
 * under the lowest point and over the highest, so a line/dot/spike never reaches
 * the top or bottom edge unlabelled. Returns null on empty input (caller falls
 * back to auto-domain).
 */
export function niceFloorDomain(
  values: number[],
  approxTicks = 4,
): { domain: [number, number]; ticks: number[] } | null {
  if (values.length === 0) return null;
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const span = dataMax - dataMin || 1; // guard flat series

  // Nice step ≈ span/approxTicks, snapped to a 1/2/5/10 × 10^k value.
  const rawStep = span / Math.max(1, approxTicks);
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const niceUnit = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  const step = niceUnit * mag;

  // Floor strictly below the min (drop a step if the min sits on a boundary);
  // ceil at/above the max.
  let lo = Math.floor(dataMin / step) * step;
  if (lo >= dataMin) lo -= step;
  let hi = Math.ceil(dataMax / step) * step;
  if (hi <= dataMax) hi += step;

  // Round to the step's natural precision to strip floating-point noise.
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  const round = (v: number) => Number(v.toFixed(decimals));
  lo = round(lo);
  hi = round(hi);

  const n = Math.round((hi - lo) / step);
  const ticks: number[] = [];
  for (let i = 0; i <= n; i++) ticks.push(round(lo + i * step));

  return { domain: [lo, hi], ticks };
}
