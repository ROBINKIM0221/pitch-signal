// 구속 하나로 돌리는 간이 감시 엔진 (브라우저용). src/common/monitoring.follow와 calibration.velo_signal을 구속 한 특징(p = 1)에 대해 그대로 옮겼다.
// 입력은 경기별 '직구 평균 구속'과 '직구 투구 수'뿐이므로, 투구별 흔들림(σ_w)과 평소가 움직이는 크기(Q)·등판 흔들림(Σ_e)·한계 k는
// MLB 개발셋에서 추정한 값을 빌려 쓴다. 따라서 오경보율 보장은 MLB에서만 검증된 것이다 (화면에 그렇게 적는다).

export const KMH_PER_MPH = 1.609344;
export const CHI2_1_99 = 6.634897;          // 시작 구간 정제 한계 χ²_{1, 0.99}

// 날짜·구속·투구 수를 적은 글을 표로 바꾼다. 쉼표·탭·공백 구분, 머리글 줄은 건너뛴다.
// 열 순서: 날짜, 직구 평균 구속, 직구 투구 수[, 전체 투구 수]. 날짜는 2026-04-03 / 2026.04.03 / 4/3 (연도 없으면 season) 를 받는다.
export function parseInput(text, season = new Date().getFullYear()) {
  const rows = [], problems = [];
  for (const [k, raw] of text.split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line) continue;
    const cells = line.split(/[,\t]+|\s{2,}|\s+(?=\d)/).map((c) => c.trim()).filter(Boolean);
    if (cells.length < 3) { if (!/[가-힣a-zA-Z]/.test(line)) problems.push(`${k + 1}번째 줄: 값이 3개 미만`); continue; }
    if (!/\d/.test(cells[1]) || !/\d/.test(cells[2])) continue;          // 머리글
    const date = parseDate(cells[0], season);
    const velo = Number(cells[1]), n_fb = Math.round(Number(cells[2])), n_all = cells[3] ? Math.round(Number(cells[3])) : null;
    if (!date) { problems.push(`${k + 1}번째 줄: 날짜를 읽을 수 없음 (${cells[0]})`); continue; }
    if (!(velo > 0) || !(n_fb > 0)) { problems.push(`${k + 1}번째 줄: 구속·투구 수는 0보다 커야 함`); continue; }
    rows.push({ date, velo, n_fb, n_all });
  }
  rows.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  return { rows, problems };
}

export function parseDate(s, season) {
  const m = s.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/) || s.match(/^(\d{1,2})[-./](\d{1,2})$/);
  if (!m) return null;
  const [y, mo, d] = m.length === 4 ? [Number(m[1]), Number(m[2]), Number(m[3])] : [season, Number(m[1]), Number(m[2])];
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

// 시작 구간 길이: 선발은 첫 N등판, 불펜은 N등판과 누적 직구 M구 중 늦은 시점 (SPEC 3.7 표 4)
export function startUpLength(rows, role, rules) {
  if (role === "SP") return Math.min(rules.starter_outings, rows.length);
  let cum = 0, need = rules.reliever_outings;
  for (let i = 0; i < rows.length; i++) {
    cum += rows[i].n_fb;
    if (i + 1 >= rules.reliever_outings && cum >= rules.reliever_min_fastballs) { need = i + 1; break; }
    need = i + 1;
  }
  return need;
}

/**
 * 구속(mph) 경기 평균과 직구 수로 움직이는 기준선을 따라가며 구속 하락 지수를 계산한다.
 * params: { sigma_w (mph), q, se (단위 없앤 값), lam, k }  — 역할별로 MLB 개발셋에서 추정한 값
 * 돌려주는 값: 등판마다 { phase, expected (mph), sd (mph), u, index, alarm } (시작 구간은 expected 등이 null)
 */
export function run(rows, nStart, params) {
  const { sigma_w, q, se, lam, k } = params;
  const x = rows.map((r) => r.velo / sigma_w), n = rows.map((r) => r.n_fb);
  const out = rows.map(() => ({ phase: "baseline", expected: null, sd: null, u: null, index: null, alarm: false }));
  if (rows.length === 0) return out;
  let level = x[0], spread = se + 1 / n[0];
  let z = 0;
  const ewmaScale = Math.sqrt((2 - lam) / lam);
  for (let t = 1; t < rows.length; t++) {
    const ahead = spread + q;
    const total = ahead + se + 1 / n[t];
    const u = (x[t] - level) / Math.sqrt(total);
    if (t >= nStart) {
      z = lam * u + (1 - lam) * z;
      const index = -ewmaScale * z / k;
      const alarm = index > 1;
      if (alarm) z = 0;
      out[t] = { phase: "monitor", expected: level * sigma_w, sd: Math.sqrt(total) * sigma_w, u, index, alarm };
    } else if (u * u > CHI2_1_99) {
      spread = ahead;                      // 시작 구간에서 크게 벗어난 등판은 평소 갱신에 쓰지 않는다
      continue;
    }
    const gain = ahead / total;
    level = level + gain * (x[t] - level);
    spread = (1 - gain) * ahead;
  }
  return out;
}

// 화면(리플레이 카드)이 읽는 모양으로 묶는다. 구속은 입력 단위(km/h)로 되돌려 보여 준다.
export function analyze(rows, role, params, rules, unit = "km/h", multiplier = 1) {
  const toMph = unit === "km/h" ? 1 / KMH_PER_MPH : 1, fromMph = 1 / toMph;
  const mphRows = rows.map((r) => ({ ...r, velo: r.velo * toMph }));
  const nStart = startUpLength(mphRows, role, rules);
  const res = run(mphRows, nStart, { ...params[role], k: params[role].k * multiplier });
  const outings = rows.map((r, i) => ({
    date: r.date, game_pk: i + 1, n_fb: r.n_fb, n_all: r.n_all ?? null, fb: "직구", phase: res[i].phase, velo: round(r.velo, 1),
    ...(res[i].phase === "monitor" ? {
      exp: { velo: round(res[i].expected * fromMph, 2) }, sd: { velo: round(res[i].sd * fromMph, 3) },
      velo_index: round(res[i].index, 3), change_index: null, velo_alarm: res[i].alarm, change_alarm: false,
    } : {}),
  }));
  const alerts = outings.filter((o) => o.velo_alarm).map((o) => ({
    date: o.date, signal: "velo_drop", index: o.velo_index, velo: o.velo - o.exp.velo,
    card: `구속 하락 지수 ${o.velo_index.toFixed(1)}, 이 등판 구속 예상보다 ${(o.velo - o.exp.velo).toFixed(1)} ${unit}`,
  }));
  return { nStart, monitored: outings.length - nStart, outings, alerts, unit };
}

function round(v, d) {
  return v == null ? null : Math.round(v * 10 ** d) / 10 ** d;
}
