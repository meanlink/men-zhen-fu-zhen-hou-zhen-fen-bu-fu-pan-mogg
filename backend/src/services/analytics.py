from __future__ import annotations

import math
from statistics import median

from ..models import DepartmentSlot, WaitSample


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 1)


def wait_minutes(sample: WaitSample) -> float | None:
    if not sample.checkin_time or not sample.called_time:
        return None
    return round((sample.called_time - sample.checkin_time).total_seconds() / 60, 1)


def distribution_bucket(minutes: float) -> str:
    if minutes < 15:
        return "0-14 分钟"
    if minutes < 30:
        return "15-29 分钟"
    if minutes < 45:
        return "30-44 分钟"
    if minutes < 60:
        return "45-59 分钟"
    return "60 分钟以上"


def calculate_review(samples: list[WaitSample], slot: DepartmentSlot) -> dict:
    usable = []
    missing = []
    for sample in samples:
        duration = wait_minutes(sample)
        if duration is None:
            missing.append(sample.sample_code)
        else:
            usable.append((sample, duration))

    values = [duration for _, duration in usable]
    med = round(median(values), 1) if values else None
    mad = round(median([abs(value - med) for value in values]), 1) if values and med is not None else None
    anomaly_codes = []
    for sample, duration in usable:
        threshold_hit = duration > slot.threshold_minutes
        mad_hit = bool(mad and mad > 0 and abs(duration - med) > 3 * mad)
        if threshold_hit or mad_hit:
            anomaly_codes.append(sample.sample_code)

    counts = {"0-14 分钟": 0, "15-29 分钟": 0, "30-44 分钟": 0, "45-59 分钟": 0, "60 分钟以上": 0}
    for value in values:
        counts[distribution_bucket(value)] += 1
    distribution = [{"label": label, "count": count} for label, count in counts.items()]
    p50 = percentile(values, 0.5)
    p90 = percentile(values, 0.9)
    summary = (
        f"本时段共纳入 {len(values)} 条有效候诊样本，P50 为 {p50 or 0:.1f} 分钟，P90 为 {p90 or 0:.1f} 分钟。"
        f" 科室阈值为 {slot.threshold_minutes} 分钟，{len(anomaly_codes)} 条样本需要科室复核。"
    )
    return {
        "sample_count": len(values),
        "missing_checkin_count": len(missing),
        "missing_codes": missing,
        "p50_minutes": p50,
        "p90_minutes": p90,
        "median_minutes": med,
        "mad_minutes": mad,
        "anomaly_count": len(anomaly_codes),
        "anomaly_codes": anomaly_codes,
        "distribution": distribution,
        "summary": summary,
    }
