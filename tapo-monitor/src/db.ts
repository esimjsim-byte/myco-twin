import Database from "better-sqlite3";
import path from "path";

const DB_PATH = process.env.DB_PATH ?? path.resolve(process.cwd(), "tapo-monitor.db");

const db = new Database(DB_PATH);
db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    temperature REAL NOT NULL,
    humidity REAL NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_readings_zone_ts ON readings(zone_id, ts);
`);

export interface StoredReading {
  zone_id: number;
  ts: number;
  temperature: number;
  humidity: number;
}

const insertStmt = db.prepare<[number, number, number, number]>(
  "INSERT INTO readings (zone_id, ts, temperature, humidity) VALUES (?, ?, ?, ?)",
);

const latestStmt = db.prepare<[], StoredReading>(`
  SELECT zone_id, ts, temperature, humidity
  FROM readings r
  WHERE ts = (SELECT MAX(ts) FROM readings WHERE zone_id = r.zone_id)
  ORDER BY zone_id ASC
`);

const historyStmt = db.prepare<[number, number], { ts: number; temperature: number; humidity: number }>(`
  SELECT ts, temperature, humidity
  FROM readings
  WHERE zone_id = ? AND ts >= ?
  ORDER BY ts ASC
`);

const pruneStmt = db.prepare<[number]>(
  "DELETE FROM readings WHERE ts < ?",
);

export function insertReading(zoneId: number, ts: number, temperatureC: number, humidity: number): void {
  insertStmt.run(zoneId, ts, temperatureC, humidity);
}

export function getLatestPerZone(): StoredReading[] {
  return latestStmt.all();
}

export function getZoneHistory(
  zoneId: number,
  sinceMs: number,
): Array<{ ts: number; temperature: number; humidity: number }> {
  return historyStmt.all(zoneId, sinceMs);
}

/** 기본 7일 이상 지난 데이터를 정리. */
export function pruneOld(olderThanMs: number = Date.now() - 7 * 24 * 3600_000): void {
  pruneStmt.run(olderThanMs);
}

export { DB_PATH };
