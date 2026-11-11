"""
File: calibration.py
Purpose: Confidence calibration reporting and history.
Category: Utility
Author: artdaq team
Depends: knowledge, reporting, workbinder
Exports: register
Complexity: Medium | Lines: 109
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING
from mcp.server.fastmcp import FastMCP
from srcs.workbinder import BinderStore
from ..context import _json_default, get_db_path
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_calibrations(limit: int=50) -> str:
        store = BinderStore(get_db_path())
        calibrations = await store.list_calibrations(limit=limit)
        return json.dumps(calibrations, default=_json_default, indent=2)

    @mcp.tool()
    async def get_calibration(model: str, error_type: str | None=None) -> str:
        store = BinderStore(get_db_path())
        calibration = await store.get_calibration(model, error_type)
        if not calibration:
            return json.dumps({'error': f'No calibration found for model: {model}'})
        return json.dumps(calibration, default=_json_default, indent=2)

    @mcp.tool()
    async def get_calibration_trend(model: str='default', error_type: str | None=None, limit: int=30) -> str:
        from srcs.knowledge import CalibrationHistoryTracker, StorageConfig
        from srcs.knowledge.reporting import format_trend_chart
        try:
            config = StorageConfig()
            tracker = CalibrationHistoryTracker(config.sqlite_path)
            trend = await tracker.get_trend(model, error_type, limit)
            trend_text = format_trend_chart(trend)
            return json.dumps({'model_name': trend.model_name, 'data_points': len(trend.timestamps), 'recent_biases': trend.biases[-10:] if trend.biases else [], 'recent_accuracies': trend.accuracies[-10:] if trend.accuracies else [], 'recent_sample_counts': trend.sample_counts[-10:] if trend.sample_counts else [], 'trend_text': trend_text}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get calibration trend')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def record_calibration_snapshot(model: str='default', error_type: str | None=None) -> str:
        from srcs.knowledge import CalibrationHistoryTracker, StorageConfig
        try:
            config = StorageConfig()
            tracker = CalibrationHistoryTracker(config.sqlite_path)
            await tracker.record_snapshot(model, error_type)
            return json.dumps({'message': f'Snapshot recorded for model {model}'}, indent=2)
        except Exception as e:
            logger.exception('Failed to record calibration snapshot')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_calibration_summary() -> str:
        from srcs.knowledge import CalibrationReporter, StorageConfig
        try:
            config = StorageConfig()
            reporter = CalibrationReporter(config.sqlite_path)
            calibrations = await reporter.get_all_calibrations()
            models = list(set((c.model_name for c in calibrations)))
            total_samples = sum((c.sample_size for c in calibrations))
            if calibrations:
                avg_bias = sum((c.overall_bias for c in calibrations)) / len(calibrations)
                total_correct: float = 0.0
                total = 0
                for c in calibrations:
                    for bucket in c.buckets.values():
                        total_correct += bucket.actual_accuracy * bucket.sample_count
                        total += bucket.sample_count
                avg_accuracy = total_correct / total if total > 0 else 0.0
            else:
                avg_bias = 0.0
                avg_accuracy = 0.0
            return json.dumps({'models': models, 'total_samples': total_samples, 'average_bias': avg_bias, 'average_accuracy': avg_accuracy}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get calibration summary')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def export_calibration(model: str='default', error_type: str | None=None) -> str:
        from srcs.knowledge import CalibrationReporter, StorageConfig, export_calibration_json
        try:
            config = StorageConfig()
            reporter = CalibrationReporter(config.sqlite_path)
            report = await reporter.generate_report(model, error_type)
            data = export_calibration_json(report)
            return json.dumps(data, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to export calibration')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def clear_calibration_history(model: str | None=None) -> str:
        import aiosqlite
        from srcs.knowledge import StorageConfig
        try:
            config = StorageConfig()
            async with aiosqlite.connect(config.sqlite_path) as conn:
                if model:
                    await conn.execute('DELETE FROM calibration_history WHERE model_name = ?', (model,))
                else:
                    await conn.execute('DELETE FROM calibration_history')
                await conn.commit()
            msg = f'Cleared history for model {model}' if model else 'Cleared all history'
            return json.dumps({'message': msg})
        except Exception as e:
            logger.exception('Failed to clear calibration history')
            return json.dumps({'error': str(e)}, indent=2)