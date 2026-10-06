// 차트 공통 스타일. 모든 화면이 같은 눈금 글자·격자·툴팁을 쓴다.
export const TICK = { fontSize: 11.5, fill: "var(--muted)" };
export const TICK_SMALL = { fontSize: 10.5, fill: "var(--muted)" };
export const AXIS_LINE = { stroke: "var(--line)" };
export const GRID = "var(--line)";
export const LABEL = { fontSize: 11.5, fill: "var(--ink-2)" };
export const LEGEND_STYLE = { fontSize: 12, paddingBottom: 6 };

// 가로 한계선의 글자는 선 바로 위 오른쪽에 둔다. 바깥(right)에 두면 여백이 좁을 때 잘리고,
// insideTopRight는 높이 0인 선 기준이라 글자가 선과 겹친다 — insideBottomRight가 선 위로 올라간다.
export function limitLabel(value) {
  return { value, position: "insideBottomRight", offset: 6, ...LABEL };
}

export function ChartTip({ active, payload, label, render }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tip">{render(payload, label)}</div>;
}

// 기본 Recharts Tooltip의 모양만 바꾼다 (formatter·labelFormatter는 그대로 쓸 수 있게).
export const TIP_STYLE = {
  contentStyle: { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 10, boxShadow: "0 6px 20px rgba(20,20,19,0.08)", fontSize: 12, padding: "8px 11px" },
  labelStyle: { color: "var(--ink)", fontWeight: 650, marginBottom: 4 },
  itemStyle: { color: "var(--ink-2)", padding: 0 },
};
