/**
 * Locally-weighted linear regression (LOESS / LOWESS) over an evenly-spaced series.
 * Single-pass (no robustness iterations — Poisson muon noise + temp noise are
 * Gaussian-enough for our purposes, and we want stable visual smoothing).
 *
 * @param ys     The y-values to smooth.
 * @param span   Bandwidth as fraction of N (default 0.15 → window = max(2, round(0.15·N))).
 * @returns      Smoothed y-values (same length as input).
 *
 * Exported for unit testing.
 */
export function loess(ys: number[], span: number = 0.15): number[] {
  const n = ys.length;
  if (n === 0) return [];
  if (n < 3) return ys.slice();
  const half = Math.max(1, Math.round((span * n) / 2));
  const out = new Array<number>(n);
  for (let i = 0; i < n; i++) {
    const lo = Math.max(0, i - half);
    const hi = Math.min(n - 1, i + half);
    const maxDist = Math.max(i - lo, hi - i) || 1;
    let swx = 0, swy = 0, swxx = 0, swxy = 0, sw = 0;
    for (let j = lo; j <= hi; j++) {
      const u = Math.abs(j - i) / maxDist;
      const w = u >= 1 ? 0 : (1 - u * u * u) ** 3; // tricube
      const x = j;
      const y = ys[j];
      sw   += w;
      swx  += w * x;
      swy  += w * y;
      swxx += w * x * x;
      swxy += w * x * y;
    }
    const denom = sw * swxx - swx * swx;
    if (denom === 0) {
      out[i] = sw > 0 ? swy / sw : ys[i];
    } else {
      const slope = (sw * swxy - swx * swy) / denom;
      const intercept = (swy - slope * swx) / sw;
      out[i] = intercept + slope * i;
    }
  }
  return out;
}
