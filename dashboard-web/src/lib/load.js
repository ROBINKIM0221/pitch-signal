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

/** 신호등 한 단계: 표시가 하나라도 켜지면 '표시', 연투·3일 2등판·ACWR 1.5 초과면 '주의', 아니면 '평소'. */
export function loadStatus(st) {
  if (st.flags.length) return "표시";
  if ((st.pitchedToday && st.backToBack) || st.apps3d === 2 || (st.acwr != null && st.acwr > 1.5)) return "주의";
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
