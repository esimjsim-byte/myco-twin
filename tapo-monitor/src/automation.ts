import type { Thresholds } from "./config";
import type { TapoPlug } from "./tapoPlug";

export interface SensorReading {
  humidity: number; // %RH
  temperatureC: number; // °C
  co2Ppm?: number; // ppm (optional)
  timestamp: number;
}

export interface Plugs {
  fan: TapoPlug; // 환풍기 (plugIp1)
  humidifier: TapoPlug; // 가습기 (plugIp2)
}

/**
 * Threshold-driven control for the grow chamber.
 *
 * Fan (환풍기):
 *   - ON  when CO2 exceeds co2High, or temperature exceeds tempHigh,
 *         or humidity exceeds humidityHigh.
 *   - OFF when all three are back within range.
 *
 * Humidifier (가습기):
 *   - ON  when humidity drops below humidityLow.
 *   - OFF when humidity rises to or above humidityHigh.
 *   (Between low and high: keep current state to provide hysteresis.)
 */
export async function evaluateAndApply(
  reading: SensorReading,
  plugs: Plugs,
  t: Thresholds,
): Promise<void> {
  const reasons: string[] = [];

  const tempOver = reading.temperatureC > t.tempHigh;
  const humOver = reading.humidity > t.humidityHigh;
  const co2Over = reading.co2Ppm !== undefined && reading.co2Ppm > t.co2High;

  if (tempOver) reasons.push(`temp ${reading.temperatureC}>${t.tempHigh}`);
  if (humOver) reasons.push(`hum ${reading.humidity}>${t.humidityHigh}`);
  if (co2Over) reasons.push(`co2 ${reading.co2Ppm}>${t.co2High}`);

  const fanShouldBeOn = tempOver || humOver || co2Over;

  const tasks: Promise<void>[] = [];

  if (fanShouldBeOn) {
    tasks.push(plugs.fan.turnOn(`over: ${reasons.join(", ")}`));
  } else {
    tasks.push(plugs.fan.turnOff("within range"));
  }

  if (reading.humidity < t.humidityLow) {
    tasks.push(
      plugs.humidifier.turnOn(`hum ${reading.humidity}<${t.humidityLow}`),
    );
  } else if (reading.humidity >= t.humidityHigh) {
    tasks.push(
      plugs.humidifier.turnOff(`hum ${reading.humidity}>=${t.humidityHigh}`),
    );
  }

  await Promise.allSettled(tasks);
}
