import type { Thresholds } from "./config";
import type { TapoPlug } from "./tapoPlug";

export interface SensorReading {
  humidity: number; // %RH
  temperatureC: number; // °C
  timestamp: number;
}

export interface Plugs {
  fan: TapoPlug; // 환풍기 (plugIp1)
  humidifier: TapoPlug; // 가습기 (plugIp2)
}

/**
 * Threshold-driven control.
 *
 * Each condition maps to exactly one plug action:
 *
 *   temperature > TEMP_MAX  -> fan ON        (환기로 온도 낮춤)
 *   temperature < TEMP_MIN  -> fan OFF       (너무 추우면 환기 중단)
 *   humidity    < HUMID_MIN -> humidifier ON (건조하면 가습 시작)
 *   humidity    > HUMID_MAX -> humidifier OFF(너무 습하면 가습 중단)
 *
 * When a reading sits between its min/max, the corresponding plug's state
 * is preserved — this is the hysteresis that prevents on/off flapping
 * around a single setpoint.
 */
export async function evaluateAndApply(
  reading: SensorReading,
  plugs: Plugs,
  t: Thresholds,
): Promise<void> {
  const tasks: Promise<void>[] = [];

  // Fan (환풍기) — driven by temperature.
  if (reading.temperatureC > t.tempMax) {
    tasks.push(
      plugs.fan.turnOn(`temp ${reading.temperatureC}>${t.tempMax}`),
    );
  } else if (reading.temperatureC < t.tempMin) {
    tasks.push(
      plugs.fan.turnOff(`temp ${reading.temperatureC}<${t.tempMin}`),
    );
  }

  // Humidifier (가습기) — driven by humidity.
  if (reading.humidity < t.humidMin) {
    tasks.push(
      plugs.humidifier.turnOn(`hum ${reading.humidity}<${t.humidMin}`),
    );
  } else if (reading.humidity > t.humidMax) {
    tasks.push(
      plugs.humidifier.turnOff(`hum ${reading.humidity}>${t.humidMax}`),
    );
  }

  await Promise.allSettled(tasks);
}
