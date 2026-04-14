"""
File: calibration.py
Purpose: Confidence calibration logic.
Category: Utility
Author: artdaq team
Depends: models
Exports: calculate_calibrated_confidence, wilson_score_interval, calculate_calibration_adjustment, estimate_true_confidence
Complexity: Low | Lines: 81
"""

import math
from srcs.models import CalibrationBucket, CalibrationData


def calculate_calibrated_confidence(
    raw_confidence: float, calibration: CalibrationData | None
) -> tuple[float, list[str]]:
    notes = []
    if calibration is None:
        notes.append("No calibration data available - using raw confidence")
        return (raw_confidence, notes)
    if calibration.sample_size < 5:
        notes.append(f"Limited calibration data ({calibration.sample_size} samples)")
        return (raw_confidence, notes)
    bucket_key = _get_bucket_key(raw_confidence)
    bucket = calibration.buckets.get(bucket_key)
    if bucket and bucket.sample_count >= 10:
        if bucket.stated_confidence > 0:
            ratio = bucket.actual_accuracy / bucket.stated_confidence
            calibrated = raw_confidence * ratio
            notes.append(
                f"Bucket {bucket_key} calibration: stated {bucket.stated_confidence:.0%} -> actual {bucket.actual_accuracy:.0%}"
            )
        else:
            calibrated = raw_confidence
    else:
        calibrated = raw_confidence - calibration.overall_bias
        notes.append(f"Overall bias correction: {calibration.overall_bias:+.2f}")
    calibrated = max(0.1, min(0.95, calibrated))
    return (calibrated, notes)


def _get_bucket_key(confidence: float) -> str:
    bucket_start = int(confidence * 10) / 10
    bucket_end = min(1.0, bucket_start + 0.1)
    return f"{bucket_start:.1f}-{bucket_end:.1f}"


def wilson_score_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p = min(successes / total, 1.0)
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    lower = (center - spread) / denominator
    upper = (center + spread) / denominator
    return (max(0.0, lower), min(1.0, upper))


def calculate_calibration_adjustment(buckets: dict[str, CalibrationBucket]) -> dict[str, float]:
    adjustments = {}
    for key, bucket in buckets.items():
        if bucket.sample_count < 5:
            adjustments[key] = 1.0
            continue
        if bucket.stated_confidence > 0:
            adjustments[key] = bucket.actual_accuracy / bucket.stated_confidence
        else:
            adjustments[key] = 1.0
    return adjustments


def estimate_true_confidence(
    stated_confidence: float, calibration: CalibrationData | None, uncertainty_factor: float = 0.1
) -> tuple[float, float, float]:
    if calibration is None:
        lower = max(0.0, stated_confidence - uncertainty_factor * 2)
        upper = min(1.0, stated_confidence + uncertainty_factor * 2)
        return (stated_confidence, lower, upper)
    bucket_key = _get_bucket_key(stated_confidence)
    bucket = calibration.buckets.get(bucket_key)
    if bucket and bucket.sample_count >= 5:
        lower, upper = wilson_score_interval(int(bucket.actual_accuracy * bucket.sample_count), bucket.sample_count)
        estimate = bucket.actual_accuracy
    else:
        estimate = stated_confidence - calibration.overall_bias
        bias_uncertainty = abs(calibration.overall_bias) + uncertainty_factor
        lower = max(0.0, estimate - bias_uncertainty)
        upper = min(1.0, estimate + bias_uncertainty)
    return (estimate, lower, upper)
