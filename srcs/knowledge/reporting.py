"""
File: reporting.py
Purpose: Calibration reporting and visualization.
Category: Utility
Author: artdaq team
Depends: models
Exports: CalibrationReport, BucketSummary, CalibrationTrend, CalibrationReporter, CalibrationHistoryTracker, ...
Complexity: High | Lines: 281
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
import aiosqlite
from srcs.models import CalibrationBucket, CalibrationData
if TYPE_CHECKING:
    from .store_interface import StructuredStore
logger = logging.getLogger(__name__)

@dataclass
class CalibrationReport:
    model_name: str
    generated_at: datetime
    total_samples: int
    overall_bias: float
    overall_accuracy: float
    buckets: list[BucketSummary] = field(default_factory=list)
    overconfident_ranges: list[str] = field(default_factory=list)
    underconfident_ranges: list[str] = field(default_factory=list)
    well_calibrated_ranges: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

@dataclass
class BucketSummary:
    range_label: str
    stated_confidence: float
    actual_accuracy: float
    sample_count: int
    bias: float
    calibration_status: str

@dataclass
class CalibrationTrend:
    model_name: str
    timestamps: list[datetime]
    biases: list[float]
    sample_counts: list[int]
    accuracies: list[float]

class CalibrationReporter:
    OVERCONFIDENT_THRESHOLD = 0.1
    UNDERCONFIDENT_THRESHOLD = -0.1

    def __init__(self, db_path: str | None=None, store: 'StructuredStore | None'=None):
        self._store = store
        self.db_path = db_path or './data/knowledge.db'

    @classmethod
    def from_store(cls, store: 'StructuredStore') -> 'CalibrationReporter':
        return cls(db_path=None, store=store)

    async def generate_report(self, model: str='default', error_type: str | None=None) -> CalibrationReport:
        calibration = await self._get_calibration(model, error_type)
        report = CalibrationReport(model_name=model, generated_at=datetime.now(), total_samples=calibration.sample_size if calibration else 0, overall_bias=calibration.overall_bias if calibration else 0.0, overall_accuracy=0.0)
        if not calibration or not calibration.buckets:
            report.recommendations.append('No calibration data available. Run more investigations.')
            return report
        total_correct = 0.0
        total_samples = 0
        for key, bucket in sorted(calibration.buckets.items()):
            bias = bucket.stated_confidence - bucket.actual_accuracy
            if bias > self.OVERCONFIDENT_THRESHOLD:
                status = 'overconfident'
                report.overconfident_ranges.append(key)
            elif bias < self.UNDERCONFIDENT_THRESHOLD:
                status = 'underconfident'
                report.underconfident_ranges.append(key)
            else:
                status = 'well_calibrated'
                report.well_calibrated_ranges.append(key)
            report.buckets.append(BucketSummary(range_label=key, stated_confidence=bucket.stated_confidence, actual_accuracy=bucket.actual_accuracy, sample_count=bucket.sample_count, bias=bias, calibration_status=status))
            total_correct += bucket.actual_accuracy * bucket.sample_count
            total_samples += bucket.sample_count
        if total_samples > 0:
            report.overall_accuracy = total_correct / total_samples
        report.recommendations = self._generate_recommendations(report)
        return report

    def _generate_recommendations(self, report: CalibrationReport) -> list[str]:
        recommendations = []
        if report.total_samples < 10:
            recommendations.append('Insufficient samples for reliable calibration. Need at least 10.')
        if report.overconfident_ranges:
            ranges = ', '.join(report.overconfident_ranges)
            recommendations.append(f'Model is overconfident in ranges: {ranges}. Consider more conservative confidence estimates.')
        if report.underconfident_ranges:
            ranges = ', '.join(report.underconfident_ranges)
            recommendations.append(f'Model is underconfident in ranges: {ranges}. Confidence could be increased.')
        if abs(report.overall_bias) > 0.15:
            direction = 'overconfident' if report.overall_bias > 0 else 'underconfident'
            recommendations.append(f'Overall {direction} bias of {abs(report.overall_bias):.0%}. Apply global correction factor.')
        if report.overall_accuracy < 0.5:
            recommendations.append('Overall accuracy below 50%. Review hypothesis generation strategy.')
        return recommendations

    async def _get_calibration(self, model: str, error_type: str | None) -> CalibrationData | None:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            params: tuple[Any, ...]
            if error_type:
                query = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type = ?'
                params = (model, error_type)
            else:
                query = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type IS NULL'
                params = (model,)
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            buckets_raw = json.loads(row['buckets_json'] or '{}')
            buckets = {k: CalibrationBucket.model_validate(v) for k, v in buckets_raw.items()}
            return CalibrationData(model_name=row['model_name'], error_type=row['error_type'] if 'error_type' in row.keys() else None, buckets=buckets, overall_bias=row['overall_bias'], sample_size=row['sample_size'])

    async def get_all_calibrations(self) -> list[CalibrationData]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM model_calibration') as cursor:
                rows = await cursor.fetchall()
            results = []
            for row in rows:
                buckets_raw = json.loads(row['buckets_json'] or '{}')
                buckets = {k: CalibrationBucket.model_validate(v) for k, v in buckets_raw.items()}
                results.append(CalibrationData(model_name=row['model_name'], error_type=row['error_type'] if 'error_type' in row.keys() else None, buckets=buckets, overall_bias=row['overall_bias'], sample_size=row['sample_size']))
            return results

def format_calibration_report(report: CalibrationReport) -> str:
    lines = [f'Calibration Report: {report.model_name}', '=' * 50, f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}", '', 'Summary:', f'  Total samples: {report.total_samples}', f'  Overall bias: {report.overall_bias:+.1%}', f'  Overall accuracy: {report.overall_accuracy:.1%}', '']
    if report.buckets:
        lines.append('Calibration Buckets:')
        lines.append('-' * 50)
        lines.append(f"{'Range':12} {'Stated':>8} {'Actual':>8} {'Bias':>8} {'N':>5} {'Status':15}")
        lines.append('-' * 50)
        for bucket in report.buckets:
            status_marker = {'overconfident': '↑', 'underconfident': '↓', 'well_calibrated': '✓'}.get(bucket.calibration_status, ' ')
            lines.append(f'{bucket.range_label:12} {bucket.stated_confidence:>7.0%} {bucket.actual_accuracy:>7.0%} {bucket.bias:>+7.0%} {bucket.sample_count:>5} {status_marker} {bucket.calibration_status}')
        lines.append('-' * 50)
    if report.recommendations:
        lines.extend(['', 'Recommendations:'])
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f'  {i}. {rec}')
    return '\n'.join(lines)

def generate_calibration_chart(report: CalibrationReport) -> str:
    if not report.buckets:
        return 'No data to chart'
    lines = ['Calibration Chart (Stated vs Actual)', '', '100% |']
    for bucket in sorted(report.buckets, key=lambda b: b.stated_confidence, reverse=True):
        stated_bar = int(bucket.stated_confidence * 40)
        actual_bar = int(bucket.actual_accuracy * 40)
        stated_str = 'S' * stated_bar
        actual_str = 'A' * actual_bar
        lines.append(f'{bucket.range_label:>10} |{stated_str}')
        lines.append(f"{'':>10} |{actual_str}")
        lines.append(f"{'':>10} |")
    lines.append('  0% |' + '-' * 40)
    lines.append('     Legend: S=Stated, A=Actual')
    return '\n'.join(lines)

class CalibrationHistoryTracker:

    def __init__(self, db_path: str | None=None, store: 'StructuredStore | None'=None):
        self._store = store
        self.db_path = db_path or './data/knowledge.db'

    @classmethod
    def from_store(cls, store: 'StructuredStore') -> 'CalibrationHistoryTracker':
        return cls(db_path=None, store=store)

    async def ensure_history_table(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS calibration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    error_type TEXT,
                    recorded_at TIMESTAMP NOT NULL,
                    overall_bias REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    overall_accuracy REAL NOT NULL,
                    buckets_json TEXT
                )
            ''')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_cal_history_model ON calibration_history(model_name, recorded_at)')
            await conn.commit()

    async def record_snapshot(self, model: str='default', error_type: str | None=None) -> None:
        await self.ensure_history_table()
        reporter = CalibrationReporter(self.db_path)
        calibration = await reporter._get_calibration(model, error_type)
        if not calibration:
            return
        total_correct = 0.0
        total_samples = 0
        for bucket in calibration.buckets.values():
            total_correct += bucket.actual_accuracy * bucket.sample_count
            total_samples += bucket.sample_count
        accuracy = total_correct / total_samples if total_samples > 0 else 0.0
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''
                INSERT INTO calibration_history (
                    model_name, error_type, recorded_at,
                    overall_bias, sample_size, overall_accuracy, buckets_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (model, error_type, datetime.now().isoformat(), calibration.overall_bias, calibration.sample_size, accuracy, json.dumps({k: v.model_dump() for k, v in calibration.buckets.items()})))
            await conn.commit()

    async def get_trend(self, model: str='default', error_type: str | None=None, limit: int=30) -> CalibrationTrend:
        await self.ensure_history_table()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            params: tuple[Any, ...]
            if error_type:
                query = '''
                    SELECT * FROM calibration_history
                    WHERE model_name = ? AND error_type = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                '''
                params = (model, error_type, limit)
            else:
                query = '''
                    SELECT * FROM calibration_history
                    WHERE model_name = ? AND error_type IS NULL
                    ORDER BY recorded_at DESC
                    LIMIT ?
                '''
                params = (model, limit)
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
        rows = list(rows)[::-1]
        trend = CalibrationTrend(model_name=model, timestamps=[], biases=[], sample_counts=[], accuracies=[])
        for row in rows:
            trend.timestamps.append(datetime.fromisoformat(row['recorded_at']))
            trend.biases.append(row['overall_bias'])
            trend.sample_counts.append(row['sample_size'])
            trend.accuracies.append(row['overall_accuracy'])
        return trend

def format_trend_chart(trend: CalibrationTrend) -> str:
    if not trend.timestamps:
        return 'No trend data available'
    lines = [f'Calibration Trend: {trend.model_name}', '', 'Bias over time:']
    min_bias = min(trend.biases) if trend.biases else 0
    max_bias = max(trend.biases) if trend.biases else 0
    range_bias = max_bias - min_bias if max_bias != min_bias else 1.0
    sparkline = ''
    for bias in trend.biases:
        normalized = (bias - min_bias) / range_bias
        if normalized < 0.25:
            sparkline += '▁'
        elif normalized < 0.5:
            sparkline += '▃'
        elif normalized < 0.75:
            sparkline += '▅'
        else:
            sparkline += '▇'
    lines.append(f'  {sparkline}')
    lines.append(f'  Min: {min_bias:+.1%}, Max: {max_bias:+.1%}')
    lines.append('')
    if len(trend.timestamps) > 0:
        lines.append('Recent values:')
        for i in range(min(5, len(trend.timestamps))):
            idx = -(i + 1)
            ts = trend.timestamps[idx]
            lines.append(f"  {ts.strftime('%Y-%m-%d')}: bias={trend.biases[idx]:+.1%}, acc={trend.accuracies[idx]:.1%}, n={trend.sample_counts[idx]}")
    return '\n'.join(lines)

def export_calibration_json(report: CalibrationReport) -> dict:
    return {'model_name': report.model_name, 'generated_at': report.generated_at.isoformat(), 'total_samples': report.total_samples, 'overall_bias': report.overall_bias, 'overall_accuracy': report.overall_accuracy, 'buckets': [{'range_label': b.range_label, 'stated_confidence': b.stated_confidence, 'actual_accuracy': b.actual_accuracy, 'sample_count': b.sample_count, 'bias': b.bias, 'calibration_status': b.calibration_status} for b in report.buckets], 'overconfident_ranges': report.overconfident_ranges, 'underconfident_ranges': report.underconfident_ranges, 'well_calibrated_ranges': report.well_calibrated_ranges, 'recommendations': report.recommendations}

def export_trend_csv(trend: CalibrationTrend) -> str:
    lines = ['timestamp,bias,accuracy,sample_count']
    for i, ts in enumerate(trend.timestamps):
        bias = trend.biases[i] if i < len(trend.biases) else 0.0
        accuracy = trend.accuracies[i] if i < len(trend.accuracies) else 0.0
        sample_count = trend.sample_counts[i] if i < len(trend.sample_counts) else 0
        lines.append(f'{ts.isoformat()},{bias:.6f},{accuracy:.6f},{sample_count}')
    return '\n'.join(lines)