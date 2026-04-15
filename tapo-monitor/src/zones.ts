import { config, type ZoneConfig } from "./config";

export type Zone = ZoneConfig;

/** .env 의 SENSOR_<id>_NAME / SENSOR_<id>_{TEMP,HUMID}_{MAX,MIN} 에서 파생. */
export const ZONES: readonly Zone[] = config.zones;
