"""
File: calibration.py
Purpose: Calibration endpoints.
Category: Utility
Author: artdaq team
Depends: knowledge, reporting, pydantic
Exports: BucketInfo, CalibrationReportResponse, CalibrationTrendResponse, CalibrationSummaryResponse, ExportFormat, ...
Complexity: High | Lines: 203
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from srcs.knowledge import (
    CalibrationHistoryTracker,
    CalibrationReporter,
    format_calibration_report,
    generate_calibration_chart,
)
from ..dependencies import StorageConfig, get_calibration_reporter, get_storage_config

router = APIRouter()


class BucketInfo(BaseModel):
    range_label: str
    stated_confidence: float
    actual_accuracy: float
    sample_count: int
    bias: float
    status: str


class CalibrationReportResponse(BaseModel):
    model_name: str
    total_samples: int
    overall_bias: float
    overall_accuracy: float
    buckets: list[BucketInfo]
    recommendations: list[str]
    report_text: str
    chart_text: str


class CalibrationTrendResponse(BaseModel):
    model_name: str
    data_points: int
    recent_biases: list[float]
    recent_accuracies: list[float]
    recent_sample_counts: list[int]
    trend_text: str


class CalibrationSummaryResponse(BaseModel):
    models: list[str]
    total_samples: int
    average_bias: float
    average_accuracy: float


@router.get("/calibration", response_model=CalibrationReportResponse)
async def get_calibration_report(
    model: str = "default",
    error_type: str | None = None,
    reporter: CalibrationReporter = Depends(get_calibration_reporter),
) -> CalibrationReportResponse:
    try:
        report = await reporter.generate_report(model, error_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
    buckets = [
        BucketInfo(
            range_label=b.range_label,
            stated_confidence=b.stated_confidence,
            actual_accuracy=b.actual_accuracy,
            sample_count=b.sample_count,
            bias=b.bias,
            status=b.calibration_status,
        )
        for b in report.buckets
    ]
    report_text = format_calibration_report(report)
    chart_text = generate_calibration_chart(report)
    return CalibrationReportResponse(
        model_name=report.model_name,
        total_samples=report.total_samples,
        overall_bias=report.overall_bias,
        overall_accuracy=report.overall_accuracy,
        buckets=buckets,
        recommendations=report.recommendations,
        report_text=report_text,
        chart_text=chart_text,
    )


@router.get("/calibration/trend", response_model=CalibrationTrendResponse)
async def get_calibration_trend(
    model: str = "default",
    error_type: str | None = None,
    limit: int = 30,
    storage_config: StorageConfig = Depends(get_storage_config),
) -> CalibrationTrendResponse:
    from srcs.knowledge.reporting import format_trend_chart

    try:
        tracker = CalibrationHistoryTracker(storage_config.sqlite_path)
        trend = await tracker.get_trend(model, error_type, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trend: {str(e)}")
    trend_text = format_trend_chart(trend)
    return CalibrationTrendResponse(
        model_name=trend.model_name,
        data_points=len(trend.timestamps),
        recent_biases=trend.biases[-10:] if trend.biases else [],
        recent_accuracies=trend.accuracies[-10:] if trend.accuracies else [],
        recent_sample_counts=trend.sample_counts[-10:] if trend.sample_counts else [],
        trend_text=trend_text,
    )


@router.post("/calibration/snapshot")
async def record_calibration_snapshot(
    model: str = "default", error_type: str | None = None, storage_config: StorageConfig = Depends(get_storage_config)
) -> dict:
    try:
        tracker = CalibrationHistoryTracker(storage_config.sqlite_path)
        await tracker.record_snapshot(model, error_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record snapshot: {str(e)}")
    return {"message": f"Snapshot recorded for model {model}"}


@router.get("/calibration/summary", response_model=CalibrationSummaryResponse)
async def get_calibration_summary(
    reporter: CalibrationReporter = Depends(get_calibration_reporter),
) -> CalibrationSummaryResponse:
    try:
        calibrations = await reporter.get_all_calibrations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")
    models = list(set((c.model_name for c in calibrations)))
    total_samples = sum((c.sample_size for c in calibrations))
    if calibrations:
        avg_bias = sum((c.overall_bias for c in calibrations)) / len(calibrations)
        total_correct = 0
        total = 0
        for c in calibrations:
            for bucket in c.buckets.values():
                total_correct += bucket.actual_accuracy * bucket.sample_count
                total += bucket.sample_count
        avg_accuracy = total_correct / total if total > 0 else 0.0
    else:
        avg_bias = 0.0
        avg_accuracy = 0.0
    return CalibrationSummaryResponse(
        models=models, total_samples=total_samples, average_bias=avg_bias, average_accuracy=avg_accuracy
    )


class ExportFormat(str):
    JSON = "json"
    CSV = "csv"


@router.get("/calibration/export")
async def export_calibration(
    format: str = "json",
    model: str = "default",
    error_type: str | None = None,
    reporter: CalibrationReporter = Depends(get_calibration_reporter),
    storage_config: StorageConfig = Depends(get_storage_config),
):
    from fastapi.responses import PlainTextResponse
    from srcs.knowledge import export_calibration_json, export_trend_csv

    if format.lower() == "json":
        try:
            report = await reporter.generate_report(model, error_type)
            return export_calibration_json(report)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to export JSON: {str(e)}")
    elif format.lower() == "csv":
        try:
            tracker = CalibrationHistoryTracker(storage_config.sqlite_path)
            trend = await tracker.get_trend(model, error_type, limit=1000)
            csv_content = export_trend_csv(trend)
            return PlainTextResponse(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=calibration_{model}.csv"},
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to export CSV: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use 'json' or 'csv'.")


@router.delete("/calibration/history")
async def clear_calibration_history(
    model: str | None = None, storage_config: StorageConfig = Depends(get_storage_config)
) -> dict:
    import aiosqlite

    try:
        async with aiosqlite.connect(storage_config.sqlite_path) as conn:
            if model:
                await conn.execute("DELETE FROM calibration_history WHERE model_name = ?", (model,))
            else:
                await conn.execute("DELETE FROM calibration_history")
            await conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")
    msg = f"Cleared history for model {model}" if model else "Cleared all history"
    return {"message": msg}
