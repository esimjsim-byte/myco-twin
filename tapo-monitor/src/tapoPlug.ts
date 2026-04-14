import { loginDeviceByIp } from "tp-link-tapo-connect";

type TapoSession = Awaited<ReturnType<typeof loginDeviceByIp>>;

/**
 * Thin wrapper around a single Tapo P100/P110 plug with:
 * - lazy (re-)login on first use or after errors
 * - local state cache to avoid redundant API calls
 * - a minimum interval between toggles to prevent rapid flapping
 */
export class TapoPlug {
  private session: TapoSession | null = null;
  private lastKnownOn: boolean | null = null;
  private lastToggleAt = 0;

  constructor(
    public readonly name: string,
    private readonly ip: string,
    private readonly email: string,
    private readonly password: string,
    private readonly minToggleIntervalMs: number,
  ) {}

  private async getSession(): Promise<TapoSession> {
    if (this.session) return this.session;
    this.session = await loginDeviceByIp(this.email, this.password, this.ip);
    return this.session;
  }

  async refreshState(): Promise<boolean> {
    try {
      const s = await this.getSession();
      const info = await s.getDeviceInfo();
      this.lastKnownOn = Boolean((info as unknown as { device_on?: boolean }).device_on);
      return this.lastKnownOn;
    } catch (err) {
      this.session = null;
      throw err;
    }
  }

  async setState(desiredOn: boolean, reason: string): Promise<void> {
    if (this.lastKnownOn === desiredOn) return;

    const now = Date.now();
    if (now - this.lastToggleAt < this.minToggleIntervalMs) {
      console.log(
        `[${this.name}] skip toggle (cooldown): want=${desiredOn} reason="${reason}"`,
      );
      return;
    }

    try {
      const s = await this.getSession();
      if (desiredOn) await s.turnOn();
      else await s.turnOff();
      this.lastKnownOn = desiredOn;
      this.lastToggleAt = now;
      console.log(
        `[${this.name}] -> ${desiredOn ? "ON" : "OFF"} reason="${reason}"`,
      );
    } catch (err) {
      this.session = null;
      console.error(`[${this.name}] toggle failed:`, err);
      throw err;
    }
  }

  async turnOn(reason: string): Promise<void> {
    await this.setState(true, reason);
  }

  async turnOff(reason: string): Promise<void> {
    await this.setState(false, reason);
  }
}
