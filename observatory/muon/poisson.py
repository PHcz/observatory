"""Phase 16 ENH-02: Poisson statistics helpers for muon rate analysis.

Pure functions — stdlib math + statistics only, no third-party dependencies.

Functions provided:
  poisson_band      — +-1 sigma Poisson confidence interval for a bucketed count
  anomaly_z_score   — z-score vs rolling median baseline
  anomaly_severity  — "warn" (|z|>3) / "alert" (|z|>5) / None
  rolling_median_baseline — median of a rate list (robust to anomalies)
  dt_exponential_histogram — inter-arrival Δt histogram
  rate_pmf          — observed vs Poisson PMF for per-minute counts
"""

from __future__ import annotations

import math
import statistics


def poisson_band(n: int, delta_t_sec: float) -> dict[str, float]:
    """Return +-1 sigma Poisson confidence interval for a bucketed event count.

    For N events observed in a window of delta_t_sec seconds:
      rate_per_min = N / delta_t_sec * 60
      sigma_per_min = sqrt(N) / delta_t_sec * 60
      upper_1sigma = rate_per_min + sigma_per_min
      lower_1sigma = max(0, rate_per_min - sigma_per_min)

    Args:
        n:            Integer event count in the bucket.
        delta_t_sec:  Bucket duration in seconds (must be > 0).

    Returns:
        Dict with keys rate_per_min, lower_1sigma, upper_1sigma (all float).
        All values are 0.0 when delta_t_sec <= 0.
    """
    if delta_t_sec <= 0:
        return {"rate_per_min": 0.0, "lower_1sigma": 0.0, "upper_1sigma": 0.0}
    rate = n / delta_t_sec * 60.0
    sigma = math.sqrt(n) / delta_t_sec * 60.0
    upper = rate + sigma
    lower = max(0.0, rate - sigma)
    return {
        "rate_per_min": round(rate, 4),
        "lower_1sigma": round(lower, 4),
        "upper_1sigma": round(upper, 4),
    }


def anomaly_z_score(rate: float, baseline: float, delta_t_min: float) -> float | None:
    """Compute z-score of rate vs a Poisson baseline.

    z = (rate - baseline) / sqrt(baseline / delta_t_min)

    Guards:
      - baseline <= 0  → None
      - delta_t_min <= 0 → None
      - variance <= 0  → None (should not occur given guards above)

    Args:
        rate:         Observed rate in events/min.
        baseline:     Expected (baseline) rate in events/min (rolling median).
        delta_t_min:  Bucket duration in minutes.

    Returns:
        z-score float, or None when the computation cannot be performed.
    """
    if baseline <= 0 or delta_t_min <= 0:
        return None
    variance = baseline / delta_t_min
    if variance <= 0:
        return None
    return (rate - baseline) / math.sqrt(variance)


def anomaly_severity(z: float | None) -> str | None:
    """Map z-score to severity label.

    |z| > 5 → "alert"
    |z| > 3 → "warn"
    otherwise → None

    Args:
        z: z-score from anomaly_z_score, or None.

    Returns:
        "alert" | "warn" | None
    """
    if z is None:
        return None
    az = abs(z)
    if az > 5:
        return "alert"
    if az > 3:
        return "warn"
    return None


def rolling_median_baseline(rates: list[float | None]) -> float | None:
    """Compute rolling median baseline from a list of rates.

    Median is used (not mean) to be robust to anomalous spikes or dips
    that would bias the baseline — see RESEARCH Pitfall 6.

    Args:
        rates: List of per-minute rates (None values are filtered out).

    Returns:
        Median float, or None if no valid values.
    """
    vals = [r for r in rates if r is not None]
    return statistics.median(vals) if vals else None


def dt_exponential_histogram(
    event_ts: list[int], max_s: float = 5.0, bins: int = 25
) -> list[dict[str, float | int]]:
    """Compute inter-arrival (Δt) histogram for a list of event timestamps.

    Consecutive timestamps are differenced to get inter-arrival times.
    Times in the range [0, max_s) are binned into `bins` equal-width bins.
    Times >= max_s are discarded (they fall in a long-tail bucket that is
    not informative for the exponential fit diagnostic).

    Args:
        event_ts: Sorted list of event timestamps in integer seconds.
        max_s:    Upper bound for histogram (exclusive). Default 5 s.
        bins:     Number of equal-width bins. Default 25.

    Returns:
        List of {"bin_s": float, "count": int} dicts, ordered by bin_s.
        Returns [] if fewer than 2 events are provided.
    """
    if len(event_ts) < 2:
        return []

    sorted_ts = sorted(event_ts)
    deltas = [sorted_ts[i + 1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)]

    bin_width = max_s / bins
    counts = [0] * bins
    for dt in deltas:
        if 0 <= dt < max_s:
            idx = int(dt / bin_width)
            idx = min(idx, bins - 1)
            counts[idx] += 1

    return [{"bin_s": round(i * bin_width, 4), "count": counts[i]} for i in range(bins)]


def rate_pmf(per_minute_counts: list[int], baseline_rate: float | None) -> list[dict[str, float]]:
    """Compute observed probability and Poisson PMF for per-minute event counts.

    For each unique count value k in the observed data:
      observed_prob  = (number of minutes with k events) / total_minutes
      poisson_prob   = e^(-λ) * λ^k / k!   where λ = baseline_rate

    Args:
        per_minute_counts: List of integer event counts per minute.
        baseline_rate:     Expected rate λ (events/min). If None, poisson_prob
                           will be 0.0 for all bins.

    Returns:
        List of {"count_per_min": int, "observed_prob": float, "poisson_prob": float}
        sorted by count_per_min. Returns [] if per_minute_counts is empty.
    """
    if not per_minute_counts:
        return []

    total = len(per_minute_counts)
    freq: dict[int, int] = {}
    for c in per_minute_counts:
        freq[c] = freq.get(c, 0) + 1

    lam = baseline_rate if (baseline_rate is not None and baseline_rate > 0) else None

    result = []
    for k in sorted(freq.keys()):
        observed_prob = freq[k] / total
        if lam is not None:
            # Poisson PMF: e^(-λ) * λ^k / k!
            poisson_prob = math.exp(-lam) * (lam**k) / math.factorial(k)
        else:
            poisson_prob = 0.0
        result.append(
            {
                "count_per_min": k,
                "observed_prob": round(observed_prob, 6),
                "poisson_prob": round(poisson_prob, 6),
            }
        )

    return result
