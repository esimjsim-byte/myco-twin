import { config } from "./config";
import { TapoPlug } from "./tapoPlug";
import { evaluateAndApply, type Plugs, type SensorReading } from "./automation";
import { PlcController } from "./plcControl";
import { readAllZones } from "./sensors";
import { insertReading, pruneOld } from "./db";
import { startServer, broadcastReadings } from "./server";

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

const plc = new PlcController(config.plc);

/** 제어 판단 기준용 대표 reading. 현재는 구역 1의 값을 사용한다. */
function pickControlReading(
  readings: Awaited<ReturnType<typeof readAllZones>>,
): SensorReading {
  const primary = readings.find((r) => r.zoneId === 1) ?? readings[0];
  if (!primary) {
    return { humidity: 70, temperatureC: 22, timestamp: Date.now() };
  }
  return {
    humidity: primary.humidity,
    temperatureC: primary.temperatureC,
    timestamp: primary.timestamp,
  };
}

async function tick(): Promise<void> {
  try {
    const readings = await readAllZones();

    for (const r of readings) {
      insertReading(r.zoneId, r.timestamp, r.temperatureC, r.humidity);
    }
    broadcastReadings(readings);

    const control = pickControlReading(readings);
    await Promise.allSettled([
      evaluateAndApply(control, plugs, config.thresholds),
      plc.applyThresholds(control, config.thresholds),
    ]);
  } catch (err) {
    console.error("tick failed:", err);
  }
}

async function main(): Promise<void> {
  // Prime plug state so the first decision has an accurate cache.
  await Promise.allSettled([fan.refreshState(), humidifier.refreshState()]);

  const port = Number(process.env.DASHBOARD_PORT ?? 3000);
  startServer(port);

  const intervalMs = Number(process.env.POLL_INTERVAL_MS ?? 10_000);
  console.log(`tapo-monitor started (poll=${intervalMs}ms)`);
  await tick();
  setInterval(tick, intervalMs);

  // 매 시각 오래된 데이터 정리
  setInterval(() => pruneOld(), 3600_000);
}

main().catch((err) => {
  console.error("fatal:", err);
  process.exit(1);
});
