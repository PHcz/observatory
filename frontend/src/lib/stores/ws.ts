import { writable, type Writable } from 'svelte/store';
import type { SnapshotData, WeatherData, MuonEvent, EarthquakeItem, SpaceWeatherData, LightningSummary, AuroraData } from '$lib/types';
import { nextBackoffMs, type BackoffConfig } from '$lib/api/reconnect';
import { setWeather } from '$lib/stores/weather';
import { bufferMuonEvent, setMuonSnapshot } from '$lib/stores/muon';
import { setSpaceWeather } from '$lib/stores/spaceWeather';
import { setLightning } from '$lib/stores/lightning';
import { setAurora } from '$lib/stores/aurora';
import { prependEarthquake, setEarthquakes } from '$lib/stores/earthquakes';
import { setAstronomy } from '$lib/stores/astronomy';
import { refetchAlerts } from '$lib/stores/alerts';
import type { AstronomyData } from '$lib/types';

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

export const wsStatus: Writable<WsStatus> = writable('connecting');

const WS_BACKOFF: BackoffConfig = { baseMs: 1000, capMs: 30000 };

let ws: WebSocket | null = null;
let attempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let manualClose = false;
let offlineListener: (() => void) | null = null;
let onlineListener: (() => void) | null = null;

// WATCHDOG: Inter-message silence detection. The TCP onclose event can take
// minutes to fire when the network is severed (only fires on next send-attempt
// timeout). The server emits a {type:'ping'} every api_ws_ping_interval_sec
// (default 30s); 60s = 2× that interval per UAT-gap-9 formula
// max(api_ws_ping_interval_sec × 2, ~60s). On timeout, force-close the socket
// so the existing onclose → scheduleReconnect() flow runs.
const WATCHDOG_MS = 60_000;
let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

function clearWatchdog(): void {
  if (watchdogTimer != null) {
    clearTimeout(watchdogTimer);
    watchdogTimer = null;
  }
}

function resetWatchdog(): void {
  clearWatchdog();
  if (manualClose) return;
  watchdogTimer = setTimeout(() => {
    watchdogTimer = null;
    wsStatus.set('disconnected');
    if (ws) {
      try { ws.close(); } catch { /* swallow */ }
    }
    scheduleReconnect();
  }, WATCHDOG_MS);
}

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
      if (snap.astronomy) setAstronomy(snap.astronomy as AstronomyData);
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
    case 'alert':
      // Trigger immediate re-fetch of the alerts store so the panel and badge
      // update within seconds of a new alert or resolution (30s poll + WS push).
      refetchAlerts();
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
    resetWatchdog();
  };

  ws.onmessage = (evt: MessageEvent<string>) => {
    resetWatchdog();
    routeMessage(evt.data);
  };

  ws.onclose = () => {
    clearWatchdog();
    wsStatus.set('disconnected');
    scheduleReconnect();
  };

  ws.onerror = () => {
    clearWatchdog();
    wsStatus.set('disconnected');
    scheduleReconnect();
  };
}

export function initWs(): () => void {
  manualClose = false;
  attempt = 0;
  connect();

  // Browser network-state listeners: react to wifi toggles within ~1s
  // instead of waiting for the 60s watchdog. SSR-safe via window guard.
  if (typeof window !== 'undefined') {
    offlineListener = () => {
      clearWatchdog();
      wsStatus.set('disconnected');
      if (ws) {
        try { ws.close(); } catch { /* swallow */ }
      }
    };
    onlineListener = () => {
      // Immediate reconnect, bypass exponential backoff.
      if (reconnectTimer != null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      attempt = 0;
      connect();
    };
    window.addEventListener('offline', offlineListener);
    window.addEventListener('online', onlineListener);
  }

  return () => {
    manualClose = true;
    clearWatchdog();
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (typeof window !== 'undefined') {
      if (offlineListener) {
        window.removeEventListener('offline', offlineListener);
        offlineListener = null;
      }
      if (onlineListener) {
        window.removeEventListener('online', onlineListener);
        onlineListener = null;
      }
    }
    if (ws) {
      ws.onclose = null;
      ws.onerror = null;
      ws.close();
      ws = null;
    }
  };
}
