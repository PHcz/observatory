import type { Component } from 'svelte';
import type { PanelKey } from '$lib/utils/settingsSchema';
import HeaderPanel from './HeaderPanel.svelte';
import StatsRow from './StatsRow.svelte';
import TodayStrip from './TodayStrip.svelte';
import ZambrettiCard from './ZambrettiCard.svelte';
import WeatherAlertsPanel from './WeatherAlertsPanel.svelte';
import ForecastPanel from './ForecastPanel.svelte';
import AirQualityPanel from './AirQualityPanel.svelte';
import MuonChart from './MuonChart.svelte';
import MuonDiagnosticsPanel from './MuonDiagnosticsPanel.svelte';
import MuonGainDriftPanel from './MuonGainDriftPanel.svelte';
import AdcSpectrumPanel from './AdcSpectrumPanel.svelte';
import BarometricPanel from './BarometricPanel.svelte';
import NmdbOverlayPanel from './NmdbOverlayPanel.svelte';
import ForbushPanel from './ForbushPanel.svelte';
import SpaceWeatherPanel from './SpaceWeatherPanel.svelte';
import EarthquakeList from './EarthquakeList.svelte';
import LightningPanel from './LightningPanel.svelte';
import AuroraPanel from './AuroraPanel.svelte';
import TemperatureChart from './TemperatureChart.svelte';
import PressureChart from './PressureChart.svelte';
import HumidityChart from './HumidityChart.svelte';
import LightChart from './LightChart.svelte';
import HealthRow from './HealthRow.svelte';

// One entry per 1:1 panel. `indoorAir` is intentionally absent — the dashboard
// renders IndoorStatsRow + IndoorCharts together for that key (see renderPlan
// 'indoor' item). earthquakes/lightning ARE here (their side-by-side grouping is
// the plan's job, but each is a normal component).
export const PANEL_COMPONENTS: Partial<Record<PanelKey, Component<Record<string, never>>>> = {
  headerPanel: HeaderPanel,
  statsRow: StatsRow,
  todayStrip: TodayStrip,
  zambrettiCard: ZambrettiCard,
  weatherAlerts: WeatherAlertsPanel,
  forecast: ForecastPanel,
  airQuality: AirQualityPanel,
  muonChart: MuonChart,
  muonDiagnostics: MuonDiagnosticsPanel,
  muonGainDrift: MuonGainDriftPanel,
  adcSpectrum: AdcSpectrumPanel,
  barometric: BarometricPanel,
  nmdbOverlay: NmdbOverlayPanel,
  forbush: ForbushPanel,
  spaceWeather: SpaceWeatherPanel,
  earthquakes: EarthquakeList,
  lightning: LightningPanel,
  aurora: AuroraPanel,
  temperatureChart: TemperatureChart,
  pressureChart: PressureChart,
  humidityChart: HumidityChart,
  lightChart: LightChart,
  healthRow: HealthRow,
};
