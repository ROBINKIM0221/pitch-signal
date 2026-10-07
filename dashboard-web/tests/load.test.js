// 팀 불펜 현황판의 날짜별 부하 계산 시험: 파이프라인(src/common/load.py → load.parquet)이 등판일에 낸 값과 같아야 한다.
// 실행: node --test dashboard-web/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dayState, loadStatus } from "../src/lib/load.js";

const { rules, sample } = JSON.parse(readFileSync(new URL("./fixtures/load_sample.json", import.meta.url), "utf-8"));

test("on every outing date the browser reproduces the pipeline's load metrics and flags", () => {
  let checked = 0;
  for (const s of sample) {
    for (const e of s.expected) {
      const st = dayState(s.outings, e.date, rules, s.p7d_limit);
      assert.equal(st.apps3d, e.apps_3d, `${s.pitcher} ${e.date} apps_3d`);
      assert.ok(Math.abs(st.p7d - e.p7d) < 1e-9, `${s.pitcher} ${e.date} p7d ${st.p7d} vs ${e.p7d}`);
      if (e.acwr == null) assert.equal(st.acwr, null, `${s.pitcher} ${e.date} acwr should be null`);
      else assert.ok(Math.abs(st.acwr - e.acwr) < 1e-9, `${s.pitcher} ${e.date} acwr ${st.acwr} vs ${e.acwr}`);
      assert.equal(st.consecutive, e.consecutive, `${s.pitcher} ${e.date} consecutive`);
      assert.equal(st.backToBack, e.back_to_back, `${s.pitcher} ${e.date} back_to_back`);
      assert.equal(st.restDays, e.rest_days, `${s.pitcher} ${e.date} rest_days`);
      assert.deepEqual([...st.flags].sort(), e.flags, `${s.pitcher} ${e.date} flags`);
      checked++;
    }
  }
  assert.ok(checked > 150, `checked ${checked}`);
});

test("between outings the state describes the rest: nothing pitched today, rest days grow, streak resets", () => {
  const outings = [{ date: "2024-05-01", pitches: 20 }, { date: "2024-05-02", pitches: 15 }];
  const st = dayState(outings, "2024-05-05", rules, null);
  assert.equal(st.pitchedToday, false);
  assert.equal(st.lastDate, "2024-05-02");
  assert.equal(st.daysSince, 3);                 // 5/2 → 5/5
  assert.equal(st.restDays, 2);                  // 사이에 쉰 날 5/3, 5/4
  assert.equal(st.consecutive, 0);
  assert.equal(st.apps3d, 0);                    // 5/3~5/5 등판 없음
  assert.equal(st.p7d, 35);
  assert.equal(st.acwr, null);                   // 28일이 안 쌓임
  assert.deepEqual(st.flags, []);
});

test("before the first outing of the season there is no state", () => {
  const st = dayState([{ date: "2024-05-01", pitches: 20 }], "2024-04-30", rules, null);
  assert.equal(st.lastDate, null);
  assert.equal(st.p7d, 0);
  assert.deepEqual(st.flags, []);
});

test("status: any flag → 표시; back-to-back today or acwr above 1.5 → 주의; two appearances in three days alone is 평소", () => {
  assert.equal(loadStatus({ flags: ["acwr"], pitchedToday: true, backToBack: false, apps3d: 1, acwr: 2.1 }), "표시");
  assert.equal(loadStatus({ flags: [], pitchedToday: true, backToBack: true, apps3d: 2, acwr: null }), "주의");
  assert.equal(loadStatus({ flags: [], pitchedToday: false, backToBack: false, apps3d: 2, acwr: 1.1 }), "평소");
  assert.equal(loadStatus({ flags: [], pitchedToday: false, backToBack: false, apps3d: 1, acwr: 1.6 }), "주의");
  assert.equal(loadStatus({ flags: [], pitchedToday: false, backToBack: false, apps3d: 1, acwr: 1.2 }), "평소");
});
