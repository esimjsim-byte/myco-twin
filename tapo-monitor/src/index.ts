import { config } from "./config";
import { TapoPlug } from "./tapoPlug";
import { evaluateAndApply, type Plugs, type SensorReading } from "./automation";

const fan = new TapoPlug(
  "fan",
  config.plugIp1,
  config.tapoEmail,
  config.tapoPassword,
  config.minToggleIntervalMs,
);
const humidifier = new TapoPlug(
  "humidifier",
  config.plugIp2,
  config.tapoEmail,
  config.tapoPassword,
  config.minToggleIntervalMs,
);
const plugs: Plugs = { fan, humidifier };

/**
 * Replace this stub with a real sensor read (e.g. SCD41, SHT31, etc.).
 */
async function readSensor(): Promise<SensorReading> {
  return {
    humidity: Number(process.env.TEST_HUMIDITY ?? 90),
    temperatureC: Number(process.env.TEST_TEMP ?? 24),
    timestamp: Date.now(),
  };
}

async function tick(): Promise<void> {
  try {
    const reading = await readSensor();
    await evaluateAndApply(reading, plugs, config.thresholds);
  } catch (err) {
    console.error("tick failed:", err);
  }
}

async function main(): Promise<void> {
  // Prime plug state so the first decision has an accurate cache.
  await Promise.allSettled([fan.refreshState(), humidifier.refreshState()]);

  const intervalMs = Number(process.env.POLL_INTERVAL_MS ?? 10_000);
  console.log(`tapo-monitor started (poll=${intervalMs}ms)`);
  await tick();
  setInterval(tick, intervalMs);
}

main().catch((err) => {
  console.error("fatal:", err);
  process.exit(1);
});
