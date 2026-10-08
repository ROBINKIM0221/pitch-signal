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

// 경보 카드의 특징 이름(src/common/myt.py LABELS와 같게)과 방향 글. 폼 변화 지수는 평소보다 높아져도 낮아져도 커지므로(방향을 가리지 않음)
// 어느 쪽으로 달라졌는지는 카드에 글로 따로 적는다 (2026-10-08 사용자 결정: 계산은 그대로, 방향만 글로).
const LABEL = { velo: "구속", rel_z: "수직 릴리스", arm_angle: "팔 각도" };
const DIRECTION = { velo: ["평소보다 빠름", "평소보다 느림"], rel_z: ["평소보다 높음", "평소보다 낮음"], arm_angle: ["팔이 평소보다 올라감", "팔이 평소보다 내려감"] };

/** 표준화 이탈 z(σ)의 방향 글. |z| < near 이면 '평소 수준'. */
export function direction(f, z, near = 0.5) {
  if (z == null || !Number.isFinite(z)) return "";
  if (Math.abs(z) < near) return "평소 수준";
  const [up, down] = DIRECTION[f] ?? ["평소보다 높음", "평소보다 낮음"];
  return z > 0 ? up : down;
}

function signed(z) {
  return `${z > 0 ? "+" : z < 0 ? "−" : ""}${Math.abs(z).toFixed(1)}σ`;
}

/** 폼 변화 경보 카드 머리글: T² 기여 몫(step)이 큰 특징 top개(몫이 없으면 |z| 큰 순)의 부호 있는 표준화 이탈과 방향.
 *  고르는 법은 myt.card와 같다. 예: '수직 릴리스 −1.8σ(평소보다 낮음), 구속 −1.2σ(평소보다 느림)' */
export function changeHeadline(alert, top = 2) {
  const z = alert.z ?? {};
  const feats = Object.keys(z).filter((f) => z[f] != null);
  const key = alert.step ? (f) => alert.step[f] ?? 0 : (f) => Math.abs(z[f]);
  return feats.slice().sort((a, b) => key(b) - key(a)).slice(0, top).map((f) => `${LABEL[f] ?? f} ${signed(z[f])}(${direction(f, z[f])})`).join(", ");
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
      : `폼 변화 지수 ${o.change_index.toFixed(1)} — ${o.u ? changeHeadline({ z: o.u }, 3) : ""}`,
  };
}

function round3(v) {
  return Math.round(v * 1000) / 1000;
}
