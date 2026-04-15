import "dotenv/config";

export interface Thresholds {
  tempMax: number;
  tempMin: number;
  humidMax: number;
  humidMin: number;
}

export interface ZoneConfig {
  id: number;
  name: string;
  thresholds: Thresholds;
}

export interface PlcSettings {
  ip: string;
  port: number;
  unitId: number;
  coilFcu: number;
  coilHumidifier: number;
  coilVentilation: number;
}

export interface AppConfig {
  tapoEmail: string;
  tapoPassword: string;
  hubIp: string; // H100 hub (온습도 센서 등 연결)
  plugIp1: string; // 환풍기 (fan)
  plugIp2: string; // 가습기 (humidifier)
  /** 전역 기본 임계값. 구역별 값이 없을 때 fallback. */
  thresholds: Thresholds;
  /** 구역 정의 (이름 + 구역별 임계값). */
  zones: ZoneConfig[];
  minToggleIntervalMs: number;
  plc: PlcSettings;
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

function str(name: string, fallback: string): string {
  const v = process.env[name];
  return v && v.trim() ? v.trim() : fallback;
}

const ZONE_COUNT = num("ZONE_COUNT", 9);

const defaultThresholds: Thresholds = {
  tempMax: num("TEMP_MAX", 28),
  tempMin: num("TEMP_MIN", 10),
  humidMax: num("HUMID_MAX", 100),
  humidMin: num("HUMID_MIN", 60),
};

function buildZone(id: number): ZoneConfig {
  return {
    id,
    name: str(`SENSOR_${id}_NAME`, `구역 ${id}`),
    thresholds: {
      tempMax: num(`SENSOR_${id}_TEMP_MAX`, defaultThresholds.tempMax),
      tempMin: num(`SENSOR_${id}_TEMP_MIN`, defaultThresholds.tempMin),
      humidMax: num(`SENSOR_${id}_HUMID_MAX`, defaultThresholds.humidMax),
      humidMin: num(`SENSOR_${id}_HUMID_MIN`, defaultThresholds.humidMin),
    },
  };
}

const zones: ZoneConfig[] = [];
for (let id = 1; id <= ZONE_COUNT; id++) zones.push(buildZone(id));

export const config: AppConfig = {
  tapoEmail: required("TAPO_EMAIL"),
  tapoPassword: required("TAPO_PASSWORD"),
  hubIp: required("HUB_IP"),
  plugIp1: required("PLUG_IP_1"),
  plugIp2: required("PLUG_IP_2"),
  thresholds: defaultThresholds,
  zones,
  minToggleIntervalMs: num("MIN_TOGGLE_INTERVAL_MS", 30_000),
  plc: {
    ip: required("PLC_IP"),
    port: num("PLC_PORT", 502),
    unitId: num("PLC_UNIT_ID", 1),
    coilFcu: num("PLC_COIL_FCU", 1),
    coilHumidifier: num("PLC_COIL_HUMIDIFIER", 2),
    coilVentilation: num("PLC_COIL_VENTILATION", 3),
  },
};
