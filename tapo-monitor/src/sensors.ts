import { ZONES } from "./zones";

export interface ZoneReading {
  zoneId: number;
  timestamp: number;
  temperatureC: number;
  humidity: number;
}

/**
 * 실제 센서(H100 허브의 T310/T315 등)를 붙이기 전까지 사용할 스텁.
 * 각 구역마다 초기값에서 완만하게 random-walk 하는 값을 반환한다.
 * 실제 센서 연동 시 이 함수만 교체하면 된다.
 */
const state = new Map<number, { t: number; h: number }>();
for (const z of ZONES) {
  // 구역별로 약간씩 다른 시작점을 주어 대시보드에서 구분이 보이도록.
  state.set(z.id, {
    t: 22 + ((z.id * 0.7) % 4),
    h: 65 + ((z.id * 3) % 15),
  });
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

export async function readAllZones(): Promise<ZoneReading[]> {
  const now = Date.now();
  return ZONES.map((z) => {
    const s = state.get(z.id)!;
    s.t = clamp(s.t + (Math.random() - 0.5) * 0.4, 10, 35);
    s.h = clamp(s.h + (Math.random() - 0.5) * 1.0, 30, 100);
    return {
      zoneId: z.id,
      timestamp: now,
      temperatureC: Number(s.t.toFixed(2)),
      humidity: Number(s.h.toFixed(1)),
    };
  });
}
