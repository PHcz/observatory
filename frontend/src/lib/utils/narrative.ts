// Narrative subtitle composition for HeaderPanel

const WORDS = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen',
  'eighteen', 'nineteen', 'twenty'];

export function numberToWord(n: number): string {
  if (!isFinite(n) || n <= 0) return '';
  const rounded = Math.round(n);
  if (rounded >= 1 && rounded <= 20) return WORDS[rounded];
  return String(rounded);
}

export interface SubtitleParams {
  hourLocal: number;
  pressureTrendHpaPerHr: number | null;
  muonRate: number | null;
  ukSmallQuakeCount: number;
  ukMaxMag: number;
}

function timeDescriptor(hourLocal: number): string {
  if (hourLocal >= 5 && hourLocal <= 11) return 'morning';
  if (hourLocal >= 12 && hourLocal <= 17) return 'afternoon';
  if (hourLocal >= 18 && hourLocal <= 21) return 'evening';
  return 'night';
}

// Adjective for the leading sentence "A {adjective} {descriptor}." — eliminates
// the ungrammatical "A evening" / "A afternoon" article+vowel fragment (UAT
// gap 1, plan 07-09) and gives a coherent fallback tone when all data phrases
// are null.
function timeAdjective(hourLocal: number): string {
  if (hourLocal >= 5 && hourLocal <= 11) return 'quiet';
  if (hourLocal >= 12 && hourLocal <= 17) return 'calm';
  if (hourLocal >= 18 && hourLocal <= 21) return 'calm';
  return 'still';
}

export function composeSubtitle(params: SubtitleParams): string {
  const { hourLocal, pressureTrendHpaPerHr, muonRate, ukSmallQuakeCount, ukMaxMag } = params;
  const descriptor = timeDescriptor(hourLocal);
  const adjective = timeAdjective(hourLocal);

  const phrases: string[] = [];

  // Pressure phrase
  if (pressureTrendHpaPerHr !== null && isFinite(pressureTrendHpaPerHr)) {
    if (pressureTrendHpaPerHr > 0.3) {
      phrases.push('Pressure rising');
    } else if (pressureTrendHpaPerHr < -0.3) {
      phrases.push('Pressure falling');
    } else {
      phrases.push('Pressure steady');
    }
  }

  // Muon phrase — numberToWord('') for non-positive/non-finite values, in
  // which case we suppress the phrase entirely to avoid "  muons per minute".
  if (muonRate !== null && isFinite(muonRate)) {
    const count = numberToWord(Math.round(muonRate));
    if (count !== '') {
      phrases.push(`${count} muons per minute`);
    }
  }

  // Quake phrase
  if (ukSmallQuakeCount > 0) {
    const countWord = numberToWord(ukSmallQuakeCount);
    const size = ukMaxMag < 3.0 ? 'small' : 'moderate';
    phrases.push(`${countWord} ${size} earthquakes in Britain this week`);
  }

  const body = phrases.length > 0 ? ` ${phrases.join(', ')}.` : '';
  return `A ${adjective} ${descriptor}.${body}`;
}
