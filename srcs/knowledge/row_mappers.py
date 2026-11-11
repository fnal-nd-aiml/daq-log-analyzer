"""
File: row_mappers.py
Purpose: Database row -> Pydantic model conversion.
Category: Utility
Author: artdaq team
Depends: models
Exports: scalar_column, scalar, row_to_investigation, row_to_pattern, row_to_root_cause, ...
Complexity: Low | Lines: 37
"""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from srcs.models import CalibrationBucket, CalibrationData, CausalChain, Challenge, ErrorPattern, Evidence, Hypothesis, Investigation, InvestigationOutcome, Log, RootCausePattern

def scalar_column(row: Any, column: str, default: Any=0) -> Any:
    if row is None:
        return default
    value = row[column]
    return default if value is None else value

def scalar(row: Sequence[Any] | None, index: int=0, default: Any=0) -> Any:
    if row is None:
        return default
    value = row[index]
    return default if value is None else value

def row_to_investigation(row: dict[str, Any]) -> Investigation:
    trigger_error = Log.model_validate_json(row['trigger_error_json'])
    context_logs = [Log.model_validate(log) for log in json.loads(row['context_logs_json'] or '[]')]
    hypotheses = [Hypothesis.model_validate(h) for h in json.loads(row['hypotheses_json'] or '[]')]
    evidence = Evidence.model_validate_json(row['evidence_json']) if row['evidence_json'] else Evidence()
    causal_chains = [CausalChain.model_validate(c) for c in json.loads(row['causal_chains_json'] or '[]')]
    challenges = [Challenge.model_validate(ch) for ch in json.loads(row['challenges_json'] or '[]')]
    return Investigation(id=row['id'], trigger_error=trigger_error, context_logs=context_logs, started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else datetime.now(), completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None, outcome=InvestigationOutcome(row['outcome']) if row['outcome'] else None, hypotheses=hypotheses, evidence=evidence, causal_chains=causal_chains, challenges=challenges, matched_pattern_id=row['matched_pattern_id'], similar_investigation_ids=json.loads(row['similar_investigation_ids_json'] or '[]'), confidence=row['confidence'] if 'confidence' in row.keys() else None)

def row_to_pattern(row: dict[str, Any]) -> ErrorPattern:
    return ErrorPattern(id=row['id'], name=row['name'], description=row.get('description'), signature_function=row.get('signature_function'), signature_message_pattern=row.get('signature_message_pattern'), signature_level=row.get('signature_level', 'ERROR'), times_seen=row.get('times_seen', 0), times_correct=row.get('times_correct', 0), times_incorrect=row.get('times_incorrect', 0), pattern_confidence=row.get('pattern_confidence', 0.0), is_active=row.get('is_active', True), user_verified=row.get('user_verified', False), first_seen=datetime.fromisoformat(row['first_seen']) if row.get('first_seen') else None, last_seen=datetime.fromisoformat(row['last_seen']) if row.get('last_seen') else None)

def row_to_root_cause(row: dict[str, Any]) -> RootCausePattern:
    return RootCausePattern(id=row['id'], error_pattern_id=row['error_pattern_id'], description=row['description'], frequency=row.get('frequency', 0.0), confirming_evidence_patterns=json.loads(row.get('confirming_evidence') or '[]'), refuting_evidence_patterns=json.loads(row.get('refuting_evidence') or '[]'))

def row_to_calibration(row: dict[str, Any]) -> CalibrationData:
    buckets_raw = json.loads(row['buckets_json'] or '{}')
    buckets = {k: CalibrationBucket.model_validate(v) for k, v in buckets_raw.items()}
    return CalibrationData(model_name=row['model_name'], error_type=row.get('error_type'), buckets=buckets, overall_bias=row.get('overall_bias', 0.0), sample_size=row.get('sample_size', 0))