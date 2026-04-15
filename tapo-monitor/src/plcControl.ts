import ModbusRTU from "modbus-serial";
import type { Thresholds } from "./config";
import type { SensorReading } from "./automation";

export interface PlcConfig {
  ip: string;
  port: number;
  unitId: number;
  coilFcu: number;
  coilHumidifier: number;
  coilVentilation: number;
}

/**
 * Modbus TCP controller for the climate-control PLC.
 *
 * Coil mapping (configured via .env):
 *   coilFcu          : FCU (heating/cooling fan-coil unit)
 *   coilHumidifier   : 가습기
 *   coilVentilation  : 환풍기
 *
 * Threshold logic:
 *   temp > TEMP_MAX  → FCU ON, ventilation ON
 *   temp < TEMP_MIN  → FCU ON
 *   hum  > HUMID_MAX → ventilation ON
 *   hum  < HUMID_MIN → humidifier ON
 *   값이 정상 범위로 복귀하면 해당 코일은 OFF.
 */
export class PlcController {
  private client = new ModbusRTU();
  private connected = false;
  private lastKnown = new Map<number, boolean>();

  constructor(private readonly cfg: PlcConfig) {}

  private async ensureConnected(): Promise<void> {
    if (this.connected) return;
    await this.client.connectTCP(this.cfg.ip, { port: this.cfg.port });
    this.client.setID(this.cfg.unitId);
    this.connected = true;
  }

  async setCoil(address: number, value: boolean, reason: string): Promise<void> {
    if (this.lastKnown.get(address) === value) return;
    try {
      await this.ensureConnected();
      await this.client.writeCoil(address, value);
      this.lastKnown.set(address, value);
      console.log(
        `[plc coil ${address}] -> ${value ? "ON" : "OFF"} reason="${reason}"`,
      );
    } catch (err) {
      this.connected = false;
      try {
        this.client.close(() => {});
      } catch {
        /* ignore */
      }
      console.error(`[plc coil ${address}] write failed:`, err);
      throw err;
    }
  }

  /**
   * Compute the desired state of every coil from a single reading and apply
   * it. Multiple conditions can drive the same coil — e.g. ventilation is ON
   * if either temperature OR humidity exceeds its max.
   */
  async applyThresholds(reading: SensorReading, t: Thresholds): Promise<void> {
    const tempOver = reading.temperatureC > t.tempMax;
    const tempUnder = reading.temperatureC < t.tempMin;
    const humOver = reading.humidity > t.humidMax;
    const humUnder = reading.humidity < t.humidMin;

    const fcuOn = tempOver || tempUnder;
    const ventOn = tempOver || humOver;
    const humdOn = humUnder;

    const reasonFor = (flags: Array<[boolean, string]>) =>
      flags
        .filter(([cond]) => cond)
        .map(([, msg]) => msg)
        .join(", ") || "in range";

    const fcuReason = reasonFor([
      [tempOver, `temp ${reading.temperatureC}>${t.tempMax}`],
      [tempUnder, `temp ${reading.temperatureC}<${t.tempMin}`],
    ]);
    const ventReason = reasonFor([
      [tempOver, `temp ${reading.temperatureC}>${t.tempMax}`],
      [humOver, `hum ${reading.humidity}>${t.humidMax}`],
    ]);
    const humdReason = reasonFor([
      [humUnder, `hum ${reading.humidity}<${t.humidMin}`],
    ]);

    await Promise.allSettled([
      this.setCoil(this.cfg.coilFcu, fcuOn, `FCU: ${fcuReason}`),
      this.setCoil(
        this.cfg.coilVentilation,
        ventOn,
        `vent: ${ventReason}`,
      ),
      this.setCoil(
        this.cfg.coilHumidifier,
        humdOn,
        `humidifier: ${humdReason}`,
      ),
    ]);
  }

  async close(): Promise<void> {
    if (!this.connected) return;
    await new Promise<void>((resolve) => {
      this.client.close(() => {
        this.connected = false;
        resolve();
      });
    });
  }
}
