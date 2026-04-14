import "dotenv/config";

export interface Thresholds {
  humidityLow: number;
  humidityHigh: number;
  co2High: number;
  tempHigh: number;
}

export interface AppConfig {
  tapoEmail: string;
  tapoPassword: string;
  plugIp1: string; // 환풍기 (fan)
  plugIp2: string; // 가습기 (humidifier)
  thresholds: Thresholds;
  minToggleIntervalMs: number;
}

function required(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env var: ${name}`);
  return v;
}

function num(name: string, fallback: number): number {
  const v = process.env[name];
  if (v === undefined || v === "") return fallback;
  const n = Number(v);
  if (Number.isNaN(n)) throw new Error(`Invalid number for ${name}: ${v}`);
  return n;
}

export const config: AppConfig = {
  tapoEmail: required("TAPO_EMAIL"),
  tapoPassword: required("TAPO_PASSWORD"),
  plugIp1: required("PLUG_IP_1"),
  plugIp2: required("PLUG_IP_2"),
  thresholds: {
    humidityLow: num("HUMIDITY_LOW", 80),
    humidityHigh: num("HUMIDITY_HIGH", 95),
    co2High: num("CO2_HIGH", 1200),
    tempHigh: num("TEMP_HIGH", 26),
  },
  minToggleIntervalMs: num("MIN_TOGGLE_INTERVAL_MS", 30_000),
};
