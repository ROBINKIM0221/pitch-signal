// 불펜 부하 채널을 날짜 기준으로 다시 계산한다. 정의는 src/common/load.py(파이프라인)와 같다:
//   3일 등판 수 = 오늘 포함 3일의 등판 횟수, 7일 투구 = 오늘 포함 7일 합,
//   ACWR = 최근 7일 합 ÷ (그 앞 21일 합 ÷ 3) — 시즌 첫 등판일부터 28일이 쌓인 뒤에만,
//   연투 = 어제도 오늘도 등판, 연속 등판일 = 오늘로 끝나는 연속 등판 일수(오늘 안 던졌으면 0),
//   표시(flag): 3일 연속 ≥ 3일, 3일 등판 ≥ 3회, 7일 투구 > 투수별 기준선 95백분위, ACWR > 기준, 긴 등판(≥30구) 뒤 쉰 날 ≤ 1일에 등판.
// 날짜 계산은 UTC 날짜 수(일)로 한다.

const DAY = 86400000;
const num = (date) => Math.round(Date.parse(date + "T00:00:00Z") / DAY);
const str = (n) => new Date(n * DAY).toISOString().slice(0, 10);

/** 날짜별 투구 수(같은 날 두 번이면 합)와 등판 횟수. */
function daily(outings) {
  const pitches = new Map(), apps = new Map();
  for (const o of outings) {
    const d = num(o.date);
    pitches.set(d, (pitches.get(d) || 0) + o.pitches);
    apps.set(d, (apps.get(d) || 0) + 1);
  }
  return { pitches, apps };
}

function sum(map, from, to) {
  let s = 0;
  for (let d = from; d <= to; d++) s += map.get(d) || 0;
  return s;
}

/**
 * date 기준 한 투수의 부하 상태.
 * outings: [{date, pitches}] (그 시즌 전부, 소속과 무관), rules: config load 블록, p7dLimit: 투수별 7일 투구 한계(없으면 null).
 */
export function dayState(outings, date, rules, p7dLimit) {
  const { pitches, apps } = daily(outings);
  const today = num(date);
  const days = [...pitches.keys()].sort((a, b) => a - b);
  const first = days.length ? days[0] : null;
  const pitchedToday = (apps.get(today) || 0) > 0;
  let consecutive = 0;
  for (let d = today; (apps.get(d) || 0) > 0; d--) consecutive++;
  let last = null;
  for (const d of days) { if (d <= today) last = d; else break; }
  let prev = null;                                              // 오늘보다 앞선 마지막 등판일 (쉰 날·직전 투구 수 계산용)
  for (const d of days) { if (d < today) prev = d; else break; }
  const apps3d = sum(apps, today - 2, today);
  const p7d = sum(pitches, today - 6, today);
  let acwr = null;
  if (first != null && today - first + 1 >= rules.acute_days + rules.chronic_days) {
    const chronic = sum(pitches, today - rules.acute_days - rules.chronic_days + 1, today - rules.acute_days) / (rules.chronic_days / 7);
    acwr = chronic > 0 ? p7d / chronic : null;
  }
  const restDays = prev == null ? null : today - prev - 1;
  const prevPitches = prev == null ? null : pitches.get(prev);
  const flags = [];
  if (pitchedToday && consecutive >= rules.consecutive_days_flag) flags.push("consecutive");
  if (apps3d >= rules.apps_3d_flag) flags.push("apps_3d");
  if (p7dLimit != null && p7d > p7dLimit) flags.push("p7d");
  if (acwr != null && acwr > rules.acwr_flag) flags.push("acwr");
  if (pitchedToday && prevPitches != null && prevPitches >= rules.long_outing_pitches && restDays <= rules.short_rest_days) flags.push("long_short");
  return {
    date, pitchedToday, todayPitches: pitches.get(today) || 0, consecutive, backToBack: pitchedToday && (apps.get(today - 1) || 0) > 0,
    lastDate: last == null ? null : str(last), daysSince: last == null ? null : today - last, lastPitches: last == null ? null : pitches.get(last),
    restDays, prevPitches, apps3d, p7d, acwr, flags,
  };
}

/** 신호등 한 단계: 표시가 하나라도 켜지면 '표시', 연투(어제도 오늘도 등판)이거나 ACWR이 1.5를 넘으면(1.8이 표시 기준) '주의', 아니면 '평소'.
 *  '주의'는 평가 계획에 없는 현황판용 중간 단계다 (2026-10-07, 3일 2등판은 불펜의 흔한 패턴이라 뺌). */
export function loadStatus(st) {
  if (st.flags.length) return "표시";
  if ((st.pitchedToday && st.backToBack) || (st.acwr != null && st.acwr > 1.5)) return "주의";
  return "평소";
}

/** 날짜 문자열에 며칠을 더한다 (UTC). */
export function addDays(date, n) {
  return str(num(date) + n);
}

/** 시작~끝 사이의 모든 날짜. */
export function dateRange(from, to) {
  const out = [];
  for (let d = num(from); d <= num(to); d++) out.push(str(d));
  return out;
}

/**
 * 고교 현황판(시즌 모드)의 날짜별 값. 정의는 src/common/highschool.daily_table과 같다:
 *   start~end(그 학교의 첫 경기일~마지막 경기일) 모든 날에 대해 pitches(등판 없는 날 0, 투구 수 모르는 등판은 null),
 *   sum_7d = 오늘 포함 7일 합(창 안에 모르는 날이 있으면 null),
 *   acwr = 7일 합 ÷ (그 앞 21일 합 ÷ 3) — start부터 28일이 쌓인 뒤부터, 두 창에 모르는 날이 없고 앞 21일 합이 0보다 클 때만,
 *   rules.min_chronic이 있으면 앞 3주 주평균이 그 값 이상일 때만(아니면 null = 판정 보류).
 * outings: [{date, pitches}] (pitches null = 모름).
 */
export function dailySeries(outings, start, end, rules) {
  const pitches = new Map(), unknown = new Set();
  for (const o of outings) {
    const d = num(o.date);
    if (o.pitches == null) unknown.add(d);
    else pitches.set(d, (pitches.get(d) || 0) + o.pitches);
  }
  const a = rules.acute_days, c = rules.chronic_days;
  const first = num(start), last = num(end);
  const windowSum = (from, to) => {
    let s = 0;
    for (let d = from; d <= to; d++) { if (unknown.has(d)) return null; s += pitches.get(d) || 0; }
    return s;
  };
  const out = [];
  for (let d = first; d <= last; d++) {
    const today = unknown.has(d) ? null : pitches.get(d) || 0;
    const acute = windowSum(Math.max(first, d - a + 1), d);                 // 시작 직후는 짧은 창 (파이프라인 min_periods=1과 같음)
    let acwr = null;
    if (d - first + 1 >= a + c && acute != null) {
      const prior = windowSum(d - a - c + 1, d - a);
      const chronic = prior == null ? null : prior / (c / 7);
      acwr = chronic != null && chronic > 0 && chronic >= (rules.min_chronic || 0) ? acute / chronic : null;
    }
    out.push({ date: str(d), pitches: today, sum_7d: acute, acwr });
  }
  return out;
}
