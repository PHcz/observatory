import { writable, type Writable } from 'svelte/store';

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

export const wsStatus: Writable<WsStatus> = writable('connecting');

export function initWs(): () => void { throw new Error('NOT_IMPLEMENTED'); }
