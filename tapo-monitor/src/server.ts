import http from "http";
import fs from "fs";
import path from "path";
import { config } from "./config";
import { ZONES } from "./zones";
import { getLatestPerZone, getZoneHistory } from "./db";
import type { ZoneReading } from "./sensors";

const PUBLIC_DIR = path.resolve(__dirname, "..", "public");

const sseClients = new Set<http.ServerResponse>();

export function broadcastReadings(readings: ZoneReading[]): void {
  if (sseClients.size === 0) return;
  const payload = `data: ${JSON.stringify({ type: "readings", readings })}\n\n`;
  for (const res of sseClients) {
    try {
      res.write(payload);
    } catch {
      sseClients.delete(res);
    }
  }
}

function sendJson(res: http.ServerResponse, body: unknown, status = 200): void {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
}

function serveStatic(req: http.IncomingMessage, res: http.ServerResponse, urlPath: string): void {
  const relative = urlPath === "/" ? "/index.html" : urlPath;
  const abs = path.normalize(path.join(PUBLIC_DIR, relative));
  if (!abs.startsWith(PUBLIC_DIR)) {
    res.writeHead(403).end();
    return;
  }
  fs.readFile(abs, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not Found");
      return;
    }
    const ext = path.extname(abs).toLowerCase();
    const contentType =
      ext === ".html" ? "text/html; charset=utf-8"
      : ext === ".js" ? "application/javascript; charset=utf-8"
      : ext === ".css" ? "text/css; charset=utf-8"
      : ext === ".svg" ? "image/svg+xml"
      : "application/octet-stream";
    res.writeHead(200, { "Content-Type": contentType });
    res.end(data);
  });
}

export function startServer(port: number): http.Server {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

    if (url.pathname === "/api/zones") {
      sendJson(res, {
        zones: ZONES,
        defaultThresholds: config.thresholds,
      });
      return;
    }

    if (url.pathname === "/api/current") {
      sendJson(res, { readings: getLatestPerZone() });
      return;
    }

    if (url.pathname === "/api/history") {
      const zoneId = Number(url.searchParams.get("zone") ?? "1");
      const hours = Number(url.searchParams.get("hours") ?? "6");
      const since = Date.now() - Math.max(0.1, hours) * 3600_000;
      sendJson(res, { zoneId, rows: getZoneHistory(zoneId, since) });
      return;
    }

    if (url.pathname === "/events") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      });
      res.write(": connected\n\n");
      sseClients.add(res);
      req.on("close", () => sseClients.delete(res));
      return;
    }

    serveStatic(req, res, url.pathname);
  });

  server.listen(port, () => {
    console.log(`Dashboard: http://localhost:${port}`);
  });
  return server;
}
