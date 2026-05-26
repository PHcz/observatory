import { writable, type Writable } from 'svelte/store';
import type { SnapshotData, WeatherData, MuonEvent, EarthquakeItem, SpaceWeatherData, LightningSummary, AuroraData } from '$lib/types';
import { nextBackoffMs, type BackoffConfig } from '$lib/api/reconnect';
import { setWeather } from '$lib/stores/weather';
import { bufferMuonEvent, setMuonSnapshot } from '$lib/stores/muon';
import { setSpaceWeather } from '$lib/stores/spaceWeather';
import { setLightning } from '$lib/stores/lightning';
import { setAurora } from '$lib/stores/aurora';
import { prependEarthquake, setEarthquakes } from '$lib/stores/earthquakes';

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

export const wsStatus: Writable<WsStatus> = writable('connecting');

const WS_BACKOFF: BackoffConfig = { baseMs: 1000, capMs: 30000 };

let ws: WebSocket | null = null;
let attempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let manualClose = false;

function buildWsUrl(): string {
  if (typeof window === 'undefined') return '';
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

function scheduleReconnect(): void {
  if (reconnectTimer != null || manualClose) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, nextBackoffMs(attempt, WS_BACKOFF));
  attempt += 1;
}

export function routeMessage(raw: string): void {
  let msg: { type: string; data?: unknown; ts?: number };
  try {
    msg = JSON.parse(raw) as { type: string; data?: unknown; ts?: number };
  } catch {
    return;
  }

  switch (msg.type) {
    case 'snapshot': {
      const snap = msg.data as SnapshotData;
      if (snap.weather?.data) setWeather(snap.weather.data as WeatherData);
      setMuonSnapshot(snap.muon?.data ?? null);
      if (snap.space_weather?.data) setSpaceWeather(snap.space_weather.data as SpaceWeatherData);
      if (snap.lightning_summary?.data) setLightning(snap.lightning_summary.data as LightningSummary);
      if (snap.aurora?.data) setAurora(snap.aurora.data as AuroraData);
      if (snap.earthquakes_recent) setEarthquakes(snap.earthquakes_recent as EarthquakeItem[]);
      break;
    }
    case 'weather':
      setWeather(msg.data as WeatherData);
      break;
    case 'muon':
      bufferMuonEvent(msg.data as MuonEvent);
      break;
    case 'earthquake':
      prependEarthquake(msg.data as EarthquakeItem);
      break;
    case 'space_weather':
      setSpaceWeather(msg.data as SpaceWeatherData);
      break;
    case 'lightning':
      setLightning(msg.data as LightningSummary);
      break;
    case 'aurora':
      setAurora(msg.data as AuroraData);
      break;
    case 'ping':
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'pong' }));
      }
      break;
    default:
      break;
  }
}

function connect(): void {
  wsStatus.set('connecting');
  const url = buildWsUrl();
  if (!url) return;
  ws = new WebSocket(url);

  ws.onopen = () => {
    attempt = 0;
    wsStatus.set('connected');
  };

  ws.onmessage = (evt: MessageEvent<string>) => {
    routeMessage(evt.data);
  };

  ws.onclose = () => {
    wsStatus.set('disconnected');
    scheduleReconnect();
  };

  ws.onerror = () => {
    wsStatus.set('disconnected');
    scheduleReconnect();
  };
}

export function initWs(): () => void {
  manualClose = false;
  attempt = 0;
  connect();
  return () => {
    manualClose = true;
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.onclose = null;
      ws.onerror = null;
      ws.close();
      ws = null;
    }
  };
}
