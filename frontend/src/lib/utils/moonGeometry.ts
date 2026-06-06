/**
 * Moon-phase geometry for the photoreal disc widget.
 *
 * Given a normalised lunar phase (0 = new, 0.25 = first quarter, 0.5 = full,
 * 0.75 = last quarter — matching the backend `astral` convention), produce the
 * SVG path for the UNLIT region of the disc. That path is painted dark over a
 * fully-lit lunar photograph, so the visible bright area is the real phase.
 *
 * The terminator (day/night boundary) projects to a half-ellipse joining the
 * lunar poles, with horizontal semi-axis rx = R·|1 − 2k| where k is the
 * illuminated fraction; the lit/dark limb is a semicircle. Orientation is
 * Northern-hemisphere: waxing moons are lit on the right, waning on the left.
 *
 * SVG uses a y-down coordinate system, so a sweep-flag of 1 draws clockwise
 * *as seen on screen*. Going from the bottom pole to the top pole, sweep 1
 * passes through the left of the disc and sweep 0 through the right — the basis
 * for the limb/terminator flags below (verified against new/quarter/full).
 */

/** Normalise any phase into [0, 1). */
function norm(phase: number): number {
  return ((phase % 1) + 1) % 1;
}

/** Illuminated fraction (0–1) from normalised lunar phase. */
export function illuminatedFraction(phase: number): number {
  return (1 - Math.cos(2 * Math.PI * norm(phase))) / 2;
}

/** True on the waxing half of the cycle (lit limb on the right, N. hemisphere). */
export function isWaxing(phase: number): boolean {
  return norm(phase) < 0.5;
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * SVG path `d` for the unlit (shadow) region of a moon disc of radius `R`
 * centred at (`cx`, `cy`). Paint it dark over a full-brightness lunar photo.
 *
 * Degenerate cases fall out naturally: at the quarters rx = 0, so the
 * terminator arc collapses to the straight pole-to-pole diameter (SVG treats an
 * arc with a zero radius as a line); at new/full the shadow covers the whole /
 * none of the disc.
 */
export function moonShadowPath(phase: number, R: number, cx: number = R, cy: number = R): string {
  const p = norm(phase);
  const k = illuminatedFraction(p);
  const rx = R * Math.abs(1 - 2 * k);
  const waxing = p < 0.5;

  const topX = round(cx);
  const topY = round(cy - R);
  const botX = round(cx);
  const botY = round(cy + R);

  // Dark limb: waxing → dark on the left (sweep 0); waning → dark on the right (sweep 1).
  const limbSweep = waxing ? 0 : 1;
  // Terminator: bulges toward the lit side for a crescent (k<0.5) and toward the
  // dark side for a gibbous (k>0.5); the sweep flag flips at the quarter.
  const termSweep = waxing ? (k < 0.5 ? 0 : 1) : k < 0.5 ? 1 : 0;

  return [
    `M ${topX} ${topY}`,
    `A ${round(R)} ${round(R)} 0 0 ${limbSweep} ${botX} ${botY}`,
    `A ${round(rx)} ${round(R)} 0 0 ${termSweep} ${topX} ${topY}`,
    'Z',
  ].join(' ');
}
