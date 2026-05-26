export function tsToLocalTime(epochSec: number): string {
  return new Date(epochSec * 1000).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function ageSeconds(epochSec: number): number {
  return Math.max(0, Math.floor(Date.now() / 1000) - epochSec);
}

export function ageMinutes(epochSec: number): number {
  return Math.floor(ageSeconds(epochSec) / 60);
}

export function formatAgeCaption(epochSec: number): string {
  const s = ageSeconds(epochSec);
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return `${h}h ${rem}m ago`;
}
