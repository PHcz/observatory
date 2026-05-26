export interface BackoffConfig { baseMs: number; capMs: number; }
export function nextBackoffMs(_attempt: number, _cfg: BackoffConfig): number { throw new Error('NOT_IMPLEMENTED'); }
