import { writable, type Writable } from 'svelte/store';
import type { MuonData, MuonPoint, MuonEvent } from '$lib/types';

export interface MuonState {
  current: MuonData | null;
  history: MuonPoint[];
  rate: number | null;
  lastUpdateTs: number | null;
}

export const muonStore: Writable<MuonState> = writable({
  current: null,
  history: [],
  rate: null,
  lastUpdateTs: null,
});

export function bufferMuonEvent(_evt: MuonEvent): void { throw new Error('NOT_IMPLEMENTED'); }
export function flushMuonBuffer(): void { throw new Error('NOT_IMPLEMENTED'); }
export function setMuonSnapshot(_data: MuonData | null): void { throw new Error('NOT_IMPLEMENTED'); }
