// 내보낸 표준화 오차(uv, u)로 두 신호를 다시 계산한다 — 한계 배수를 바꿀 때 쓴다 (운영 곡선과 같은 방식: k·T² 한계·h에 모두 배수를 곱함).
// 배수 1이면 파이프라인(calibration.velo_signal, stats_core.monitor)이 내보낸 값과 같아야 한다.

export function recompute(outings, limits, multiplier = 1) {
  const lam = limits.lam ?? 0.2;
  const k = limits.velo_k * multiplier, t2lim = limits.change_t2 * multiplier, h = limits.change_h * multiplier;
  const c = Math.sqrt((2 - lam) / lam);
  let zv = 0;
  let z = null;
  return outings.map((o) => {
    if (o.phase !== "monitor" || o.uv == null) return o;
    zv = lam * o.uv + (1 - lam) * zv;
    const velo_index = -c * zv / k;
    const velo_alarm = velo_index > 1;
    if (velo_alarm) zv = 0;
    let change_index = o.change_index, change_alarm = o.change_alarm;
    if (o.u) {
      const u = Object.values(o.u);
      z = z ? u.map((v, i) => lam * v + (1 - lam) * z[i]) : u.map((v) => lam * v);
      const q = ((2 - lam) / lam) * z.reduce((s, v) => s + v * v, 0);
      const t2 = u.reduce((s, v) => s + v * v, 0);
      change_index = Math.max(t2 / t2lim, q / h);
      change_alarm = q > h || t2 > t2lim;
      if (change_alarm) z = z.map(() => 0);
    }
    return { ...o, velo_index: round3(velo_index), velo_alarm, change_index: round3(change_index), change_alarm };
  });
}

// 배수를 바꿔 새로 생긴 경보의 카드. 설계점(배수 1)의 경보는 내보낸 카드(원인 분해 포함)를 그대로 쓴다.
export function syntheticAlert(o, data, signal) {
  const velo = signal === "velo";
  const unit = data.unit ?? "mph";
  const delta = o.exp ? o.velo - o.exp.velo : null;
  return {
    id: data.id, who: data.name, date: o.date, synthetic: true,
    signal: velo ? "velo_drop" : "change", rule: velo ? "EWMA" : "T²/MEWMA", index: velo ? o.velo_index : o.change_index,
    velo_delta: delta, unit,
    z: o.u ? Object.fromEntries(Object.entries(o.u).map(([f, v]) => [f, v])) : null,
    card: velo
      ? `구속 하락 지수 ${o.velo_index.toFixed(1)}${delta != null ? `, 이 등판 구속 예상보다 ${delta.toFixed(1)} ${unit}` : ""}`
      : `폼 변화 지수 ${o.change_index.toFixed(1)} — 표준화 이탈 ${o.u ? Object.entries(o.u).map(([f, v]) => `${f} ${v > 0 ? "+" : ""}${v.toFixed(1)}σ`).join(", ") : ""}`,
  };
}

function round3(v) {
  return Math.round(v * 1000) / 1000;
}
