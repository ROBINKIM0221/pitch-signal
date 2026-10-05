"""Statcast 원데이터를 주 단위로 내려받아 저장할 때 쓰는 보조 함수."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger("pitchsignal.download")


def season_window(cfg: dict, season: int) -> tuple[date, date]:
    """설정의 download_window('MM-DD')를 그 시즌의 시작·끝 날짜로 바꾼다."""
    w = cfg["data"]["download_window"]
    return date.fromisoformat(f"{season}-{w['start']}"), date.fromisoformat(f"{season}-{w['end']}")


def week_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """start~end를 7일 단위 (시작, 끝) 목록으로 나눈다. 마지막 주는 end에서 자른다."""
    out = []
    while start <= end:
        out.append((start, min(start + timedelta(days=6), end)))
        start += timedelta(days=7)
    return out


def week_path(root: Path, start: date) -> Path:
    """주 파일 경로: <root>/<시즌>/<MMDD>.parquet (MMDD는 그 주의 시작일)."""
    return Path(root) / str(start.year) / f"{start:%m%d}.parquet"


def keep_game_type(df: pd.DataFrame, game_type: str) -> pd.DataFrame:
    return df[df["game_type"] == game_type]


def download_weeks(weeks, out_root: Path, fetch, game_type: str) -> dict[str, list[date]]:
    """주마다 fetch(start, end)로 받아 game_type 행만 <out_root>/<시즌>/<MMDD>.parquet로 저장한다.

    이미 있는 파일은 건너뛴다(끊겨도 이어받기). 응답이 비었거나 받다가 오류가 난 주는
    파일을 만들지 않고 failed에 담아 돌려준다.
    """
    result = {"saved": [], "skipped": [], "failed": []}
    for start, end in weeks:
        path = week_path(out_root, start)
        if path.exists():
            result["skipped"].append(start)
            continue
        try:
            df = fetch(start, end)
        except Exception as e:
            log.warning("%s~%s 실패: %s", start, end, e)
            result["failed"].append(start)
            continue
        if df.empty:
            log.warning("%s~%s 빈 응답", start, end)
            result["failed"].append(start)
            continue
        kept = keep_game_type(df, game_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        kept.to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(path)
        log.info("%s~%s 저장 %d행 (받은 행 %d)", start, end, len(kept), len(df))
        result["saved"].append(start)
    return result


def season_rows(out_root: Path, season: int) -> int:
    """그 시즌 폴더에 저장된 주 파일들의 행 수 합."""
    return sum(pq.read_metadata(f).num_rows for f in (Path(out_root) / str(season)).glob("*.parquet"))


def download_seasons(cfg: dict, seasons: list[int], out_root: Path, fetch) -> dict:
    """시즌을 차례로 받고, 실패한 주는 모아서 마지막에 한 번 더 시도한다.

    반환: {"seasons": [{season, weeks, rows, seconds}], "failed": [끝까지 실패한 주의 시작일]}
    seasons의 숫자는 그 시즌을 처음 돈 직후 기준이다(마지막 재시도 전).
    """
    game_type = cfg["data"]["game_type"]
    summary, failed = [], []
    for season in seasons:
        t0 = time.monotonic()
        weeks = week_ranges(*season_window(cfg, season))
        result = download_weeks(weeks, out_root, fetch, game_type)
        failed += [w for w in weeks if w[0] in result["failed"]]
        row = {"season": season, "weeks": len(result["saved"]) + len(result["skipped"]),
               "rows": season_rows(out_root, season), "seconds": round(time.monotonic() - t0)}
        log.info("%d 시즌: 받은 주 %d, 행 %d, %d초, 실패 %d주", season, row["weeks"], row["rows"],
                 row["seconds"], len(result["failed"]))
        summary.append(row)
    if failed:
        log.info("실패한 %d주를 다시 시도", len(failed))
        failed = download_weeks(failed, out_root, fetch, game_type)["failed"]
    return {"seasons": summary, "failed": failed}


def missing_rates(df: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    """열별 결측 비율. 열 자체가 없으면 NaN."""
    return {c: float(df[c].isna().mean()) if c in df.columns else np.nan for c in columns}
