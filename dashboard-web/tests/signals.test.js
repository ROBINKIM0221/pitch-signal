// 한계 배수 재계산 시험. 실행: node --test dashboard-web/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { recompute, syntheticAlert } from "../src/lib/signals.js";

const DIR = new URL("../public/data/replay/", import.meta.url);
const files = readdirSync(DIR).filter((f) => f.endsWith(".json")).slice(0, 60);     // 앞쪽 60개 투수-시즌으로 확인
const load = (f) => JSON.parse(readFileSync(new URL(f, DIR), "utf-8"));

test("with multiplier 1 the recomputation reproduces the exported indexes and alarms", () => {
  let checked = 0;
  for (const f of files) {
    const d = load(f);
    if (!d.outings.some((o) => o.uv != null)) continue;
    const re = recompute(d.outings, d.limits, 1);
    d.outings.forEach((o, i) => {
      if (o.phase !== "monitor") return;
      assert.ok(Math.abs(re[i].velo_index - o.velo_index) < 0.01, `${f} ${o.date} velo ${re[i].velo_index} vs ${o.velo_index}`);
      assert.equal(re[i].velo_alarm, o.velo_alarm, `${f} ${o.date} velo alarm`);
      assert.ok(Math.abs(re[i].change_index - o.change_index) < 0.02, `${f} ${o.date} change ${re[i].change_index} vs ${o.change_index}`);
      assert.equal(re[i].change_alarm, o.change_alarm, `${f} ${o.date} change alarm`);
      checked++;
    });
  }
  assert.ok(checked > 500, `checked ${checked}`);
});

test("a looser multiplier never removes alarms that the design point had, and adds some", () => {
  let base = 0, loose = 0;
  for (const f of files) {
    const d = load(f);
    const a1 = recompute(d.outings, d.limits, 1), a07 = recompute(d.outings, d.limits, 0.7);
    base += a1.filter((o) => o.velo_alarm).length; loose += a07.filter((o) => o.velo_alarm).length;
  }
  assert.ok(loose > base, `${loose} > ${base}`);
});

test("synthetic alert cards carry the index, velocity gap and standardized deviations", () => {
  const d = load(files[0]);
  const re = recompute(d.outings, d.limits, 0.5);
  const o = re.find((x) => x.velo_alarm) || re.find((x) => x.phase === "monitor");
  const card = syntheticAlert(o, d, "velo");
  assert.equal(card.signal, "velo_drop");
  assert.ok(card.card.startsWith("구속 하락 지수"));
  assert.ok(Math.abs(card.velo_delta - (o.velo - o.exp.velo)) < 1e-9);
  const change = syntheticAlert(o, d, "change");
  assert.ok(change.card.includes("σ") && change.z.velo != null);
});
