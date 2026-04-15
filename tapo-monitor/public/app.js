// Simple dashboard client: loads zones/thresholds, renders 9 cards,
// subscribes to SSE for live updates, and draws time-series charts.

const state = {
  zones: [],
  zoneById: new Map(), // zoneId -> Zone (with thresholds)
  defaultThresholds: null,
  latest: new Map(), // zoneId -> { ts, temperature, humidity }
  selectedZone: 1,
  hours: 6,
  tempChart: null,
  humChart: null,
};

function thresholdsFor(zoneId) {
  return state.zoneById.get(zoneId)?.thresholds ?? state.defaultThresholds;
}

function fmt(n, d = 1) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(d);
}

function timeAgo(tsMs) {
  if (!tsMs) return "—";
  const s = Math.floor((Date.now() - tsMs) / 1000);
  if (s < 60) return `${s}초 전`;
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  return `${Math.floor(s / 3600)}시간 전`;
}

function classifyTemp(t, zoneId) {
  const { tempMax, tempMin } = thresholdsFor(zoneId);
  if (t > tempMax) return "over";
  if (t < tempMin) return "under";
  return "ok";
}
function classifyHum(h, zoneId) {
  const { humidMax, humidMin } = thresholdsFor(zoneId);
  if (h > humidMax) return "over";
  if (h < humidMin) return "under";
  return "ok";
}

function renderGrid() {
  const grid = document.getElementById("zone-grid");
  grid.innerHTML = "";
  for (const z of state.zones) {
    const r = state.latest.get(z.id);
    const t = r?.temperature;
    const h = r?.humidity;
    const tClass = t != null ? classifyTemp(t, z.id) : "ok";
    const hClass = h != null ? classifyHum(h, z.id) : "ok";
    const alertLevel = tClass !== "ok" || hClass !== "ok" ? "alert" : "";
    const th = thresholdsFor(z.id);

    const card = document.createElement("div");
    card.className = `card ${alertLevel}`;
    card.innerHTML = `
      <div class="card-head">
        <h3>${z.name}</h3>
        <span class="pill ${alertLevel ? "err" : "ok"}">${alertLevel ? "경보" : "정상"}</span>
      </div>
      <div class="metrics">
        <div class="metric ${tClass}">
          <span class="label">온도</span>
          <div><span class="value">${fmt(t, 1)}</span><span class="unit">°C</span></div>
        </div>
        <div class="metric ${hClass}">
          <span class="label">습도</span>
          <div><span class="value">${fmt(h, 1)}</span><span class="unit">%</span></div>
        </div>
      </div>
      <div class="card-foot">
        <span>임계값 ${th.tempMin}~${th.tempMax}°C / ${th.humidMin}~${th.humidMax}%</span>
        <span>${timeAgo(r?.ts)}</span>
      </div>`;
    grid.appendChild(card);
  }
  renderAlertSummary();
}

function renderAlertSummary() {
  const pill = document.getElementById("alert-summary");
  let count = 0;
  for (const z of state.zones) {
    const r = state.latest.get(z.id);
    if (!r) continue;
    if (
      classifyTemp(r.temperature, z.id) !== "ok" ||
      classifyHum(r.humidity, z.id) !== "ok"
    )
      count++;
  }
  if (count === 0) {
    pill.textContent = `정상 (${state.zones.length}/${state.zones.length})`;
    pill.className = "pill ok";
  } else {
    pill.textContent = `임계값 초과: ${count}개 구역`;
    pill.className = "pill err";
  }
  document.getElementById("last-updated").textContent = `업데이트 ${new Date().toLocaleTimeString()}`;
}

async function loadMeta() {
  const res = await fetch("/api/zones");
  const data = await res.json();
  state.zones = data.zones;
  state.zoneById = new Map(data.zones.map((z) => [z.id, z]));
  state.defaultThresholds = data.defaultThresholds;

  const zoneSelect = document.getElementById("zone-select");
  zoneSelect.innerHTML = "";
  for (const z of state.zones) {
    const opt = document.createElement("option");
    opt.value = z.id;
    opt.textContent = z.name;
    zoneSelect.appendChild(opt);
  }
  zoneSelect.value = state.selectedZone;
  zoneSelect.addEventListener("change", () => {
    state.selectedZone = Number(zoneSelect.value);
    refreshCharts();
  });

  const hoursSelect = document.getElementById("hours-select");
  hoursSelect.addEventListener("change", () => {
    state.hours = Number(hoursSelect.value);
    refreshCharts();
  });
}

async function loadCurrent() {
  const res = await fetch("/api/current");
  const data = await res.json();
  for (const row of data.readings ?? []) {
    state.latest.set(row.zone_id, {
      ts: row.ts,
      temperature: row.temperature,
      humidity: row.humidity,
    });
  }
  renderGrid();
}

function handleLiveReadings(readings) {
  for (const r of readings) {
    state.latest.set(r.zoneId, {
      ts: r.timestamp,
      temperature: r.temperatureC,
      humidity: r.humidity,
    });
  }
  renderGrid();
  // 선택된 구역의 차트에 실시간 포인트 추가
  const live = readings.find((r) => r.zoneId === state.selectedZone);
  if (live && state.tempChart) {
    const th = thresholdsFor(state.selectedZone);
    appendPoint(state.tempChart, live.timestamp, live.temperatureC, th.tempMax, th.tempMin);
    appendPoint(state.humChart, live.timestamp, live.humidity, th.humidMax, th.humidMin);
  }
}

function appendPoint(chart, ts, value, max, min) {
  const ds = chart.data.datasets[0];
  ds.data.push({ x: ts, y: value });
  const cutoff = Date.now() - state.hours * 3600_000;
  while (ds.data.length && ds.data[0].x < cutoff) ds.data.shift();
  const xFrom = ds.data.length ? ds.data[0].x : cutoff;
  setThresholdLines(chart, max, min, xFrom, ts);
  chart.update("none");
}

function buildChart(canvasId, label, color) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [
        {
          label,
          data: [],
          borderColor: color,
          backgroundColor: color + "22",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
        },
        {
          label: "상한",
          data: [],
          borderColor: "#f85149",
          borderDash: [5, 5],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
        {
          label: "하한",
          data: [],
          borderColor: "#58a6ff",
          borderDash: [5, 5],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          type: "time",
          time: { unit: "minute", displayFormats: { minute: "HH:mm", hour: "HH:mm" } },
          ticks: { color: "#8b99a8", maxRotation: 0 },
          grid: { color: "#2a333f55" },
        },
        y: {
          ticks: { color: "#8b99a8" },
          grid: { color: "#2a333f55" },
        },
      },
      plugins: {
        legend: { labels: { color: "#e6edf3" } },
        tooltip: { mode: "nearest", intersect: false },
      },
    },
  });
}

function setThresholdLines(chart, max, min, xFrom, xTo) {
  chart.data.datasets[1].data = [
    { x: xFrom, y: max },
    { x: xTo, y: max },
  ];
  chart.data.datasets[2].data = [
    { x: xFrom, y: min },
    { x: xTo, y: min },
  ];
}

async function refreshCharts() {
  const res = await fetch(`/api/history?zone=${state.selectedZone}&hours=${state.hours}`);
  const data = await res.json();
  const points = (data.rows ?? []).map((r) => ({
    ts: r.ts,
    t: r.temperature,
    h: r.humidity,
  }));

  if (!state.tempChart) {
    state.tempChart = buildChart("temp-chart", "온도 (°C)", "#f85149");
    state.humChart = buildChart("hum-chart", "습도 (%)", "#58a6ff");
  }

  state.tempChart.data.datasets[0].data = points.map((p) => ({ x: p.ts, y: p.t }));
  state.humChart.data.datasets[0].data = points.map((p) => ({ x: p.ts, y: p.h }));

  const th = thresholdsFor(state.selectedZone);
  const xFrom = points.length ? points[0].ts : Date.now() - state.hours * 3600_000;
  const xTo = points.length ? points[points.length - 1].ts : Date.now();
  setThresholdLines(state.tempChart, th.tempMax, th.tempMin, xFrom, xTo);
  setThresholdLines(state.humChart, th.humidMax, th.humidMin, xFrom, xTo);

  state.tempChart.update("none");
  state.humChart.update("none");
}

function connectSse() {
  const es = new EventSource("/events");
  const conn = document.getElementById("conn");
  es.onopen = () => {
    conn.textContent = "● live";
    conn.className = "pill ok";
  };
  es.onerror = () => {
    conn.textContent = "● 재연결 중";
    conn.className = "pill warn";
  };
  es.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "readings") handleLiveReadings(msg.readings);
    } catch (err) {
      console.error("bad SSE payload", err);
    }
  };
}

(async function init() {
  await loadMeta();
  await loadCurrent();
  await refreshCharts();
  connectSse();
  // 카드의 "xx초 전" 상대 시각을 주기적으로 리프레시
  setInterval(renderGrid, 30_000);
})();
