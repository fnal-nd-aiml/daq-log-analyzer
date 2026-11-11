import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
BASE_TS = '2025-01-15T10:00:00'
TS_01 = '2025-01-15T10:05:00'
TS_02 = '2025-01-15T10:10:00'
TS_03 = '2025-01-15T10:15:00'
TS_04 = '2025-01-15T10:20:00'
TS_05 = '2025-01-15T10:25:00'
TS_06 = '2025-01-15T10:30:00'
TS_07 = '2025-01-15T10:35:00'
TS_08 = '2025-01-15T10:40:00'
TS_09 = '2025-01-15T10:45:00'
TS_10 = '2025-01-15T10:50:00'
TS_11 = '2025-01-15T10:55:00'
TS_12 = '2025-01-15T11:00:00'
TS_13 = '2025-01-15T11:05:00'
TS_14 = '2025-01-15T11:10:00'
TS_15 = '2025-01-15T11:15:00'
TS_16 = '2025-01-15T11:30:00'
TS_17 = '2025-01-15T12:00:00'
TS_18 = '2025-01-15T12:30:00'
TS_19 = '2025-01-16T09:00:00'
TS_20 = '2025-01-16T10:00:00'
TS_21 = '2025-01-16T11:00:00'
TS_22 = '2025-01-17T08:00:00'
TS_23 = '2025-01-17T08:30:00'
BINDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_binders (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS binder_artifacts (
    id TEXT PRIMARY KEY,
    binder_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    phase INTEGER,
    function_name TEXT,
    priority TEXT DEFAULT 'normal',
    tags_json TEXT,
    content_json TEXT NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by TEXT,
    deleted_reason TEXT,
    FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifact_history (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    modified_by TEXT NOT NULL,
    modified_at TIMESTAMP NOT NULL,
    action TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifact_tags (
    artifact_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (artifact_id, tag),
    FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifact_annotations (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    target_artifact_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    annotation_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS binder_audit_log (
    id TEXT PRIMARY KEY,
    binder_id TEXT NOT NULL,
    persona_name TEXT NOT NULL,
    phase_number INTEGER,
    timestamp TIMESTAMP NOT NULL,
    access_sequence INTEGER NOT NULL,
    operation_type TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    artifact_id TEXT,
    method_name TEXT NOT NULL,
    result_count INTEGER DEFAULT 1,
    success BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_binder_artifacts_binder
    ON binder_artifacts(binder_id);
CREATE INDEX IF NOT EXISTS idx_binder_artifacts_type
    ON binder_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_binder_artifacts_phase
    ON binder_artifacts(phase);
CREATE INDEX IF NOT EXISTS idx_binder_artifacts_function
    ON binder_artifacts(function_name);
CREATE INDEX IF NOT EXISTS idx_artifact_tags_tag
    ON artifact_tags(tag);
CREATE INDEX IF NOT EXISTS idx_binders_investigation
    ON work_binders(investigation_id);
CREATE INDEX IF NOT EXISTS idx_binders_status
    ON work_binders(status);
CREATE INDEX IF NOT EXISTS idx_annotations_target
    ON artifact_annotations(target_artifact_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_binder
    ON binder_audit_log(binder_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_persona
    ON binder_audit_log(persona_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_phase
    ON binder_audit_log(phase_number);
CREATE INDEX IF NOT EXISTS idx_audit_log_sequence
    ON binder_audit_log(binder_id, access_sequence);
"""
KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    trigger_error_json TEXT NOT NULL,
    context_logs_json TEXT,
    outcome TEXT,
    hypotheses_json TEXT,
    evidence_json TEXT,
    causal_chains_json TEXT,
    challenges_json TEXT,
    matched_pattern_id TEXT,
    similar_investigation_ids_json TEXT,
    duration_seconds REAL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    processing_tier INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    description TEXT NOT NULL,
    source TEXT,
    prior_probability REAL DEFAULT 0.5,
    score REAL DEFAULT 0.0,
    rank INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_queries (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    hypothesis_id TEXT REFERENCES hypotheses(id),
    query_type TEXT NOT NULL,
    query_text TEXT NOT NULL,
    iteration INTEGER DEFAULT 1,
    result_count INTEGER DEFAULT 0,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_items (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    evidence_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    strength TEXT DEFAULT 'WEAK',
    query_id TEXT REFERENCES evidence_queries(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS causal_chains (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    hypothesis_id TEXT REFERENCES hypotheses(id),
    root_cause TEXT,
    final_effect TEXT,
    chain_strength REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS causal_steps (
    id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL REFERENCES causal_chains(id),
    step_number INTEGER NOT NULL,
    cause TEXT NOT NULL,
    effect TEXT NOT NULL,
    mechanism TEXT,
    evidence_item_id TEXT REFERENCES evidence_items(id),
    confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    hypothesis_id TEXT REFERENCES hypotheses(id),
    challenge_type TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT DEFAULT 'MEDIUM',
    requires_response BOOLEAN DEFAULT TRUE,
    resolved BOOLEAN DEFAULT FALSE,
    resolution TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_records (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    was_correct BOOLEAN NOT NULL,
    actual_cause TEXT,
    feedback_notes TEXT,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    patterns_updated_json TEXT,
    patterns_created_json TEXT,
    feedback_source TEXT DEFAULT 'cli'
);

CREATE TABLE IF NOT EXISTS hypothesis_strategy_performance (
    id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    error_type TEXT,
    times_used INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    avg_confidence REAL DEFAULT 0.0,
    avg_rank REAL DEFAULT 0.0,
    last_used TIMESTAMP,
    UNIQUE(strategy_name, error_type)
);

CREATE TABLE IF NOT EXISTS query_type_effectiveness (
    id TEXT PRIMARY KEY,
    query_type TEXT NOT NULL,
    error_type TEXT,
    times_used INTEGER DEFAULT 0,
    times_useful INTEGER DEFAULT 0,
    avg_evidence_strength REAL DEFAULT 0.0,
    avg_result_count REAL DEFAULT 0.0,
    last_used TIMESTAMP,
    UNIQUE(query_type, error_type)
);

CREATE TABLE IF NOT EXISTS error_patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    signature_function TEXT,
    signature_message_pattern TEXT,
    signature_level TEXT DEFAULT 'ERROR',
    times_seen INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    times_incorrect INTEGER DEFAULT 0,
    pattern_confidence REAL DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    user_verified BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP
);

CREATE TABLE IF NOT EXISTS root_cause_patterns (
    id TEXT PRIMARY KEY,
    error_pattern_id TEXT REFERENCES error_patterns(id),
    description TEXT NOT NULL,
    frequency REAL DEFAULT 0.0,
    confirming_evidence TEXT,
    refuting_evidence TEXT,
    typical_fix TEXT
);

CREATE TABLE IF NOT EXISTS model_calibration (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    error_type TEXT,
    buckets_json TEXT NOT NULL,
    overall_bias REAL DEFAULT 0.0,
    sample_size INTEGER DEFAULT 0,
    last_updated TIMESTAMP,
    UNIQUE(model_name, error_type)
);

CREATE TABLE IF NOT EXISTS calibration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    error_type TEXT,
    recorded_at TIMESTAMP NOT NULL,
    overall_bias REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    overall_accuracy REAL NOT NULL,
    buckets_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_investigations_timestamp
    ON investigations(timestamp);
CREATE INDEX IF NOT EXISTS idx_investigations_outcome
    ON investigations(outcome);
CREATE INDEX IF NOT EXISTS idx_patterns_signature
    ON error_patterns(signature_function, signature_message_pattern);
CREATE INDEX IF NOT EXISTS idx_patterns_active
    ON error_patterns(is_active);
CREATE INDEX IF NOT EXISTS idx_hypotheses_investigation
    ON hypotheses(investigation_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_score
    ON hypotheses(score DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_items_investigation
    ON evidence_items(investigation_id);
CREATE INDEX IF NOT EXISTS idx_evidence_items_type
    ON evidence_items(evidence_type);
CREATE INDEX IF NOT EXISTS idx_causal_chains_investigation
    ON causal_chains(investigation_id);
CREATE INDEX IF NOT EXISTS idx_challenges_investigation
    ON challenges(investigation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_investigation
    ON feedback_records(investigation_id);
CREATE INDEX IF NOT EXISTS idx_cal_history_model
    ON calibration_history(model_name, recorded_at);
"""

def _j(obj: object) -> str:
    return json.dumps(obj)

def create_fixture_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(BINDER_SCHEMA)
        conn.executescript(KNOWLEDGE_SCHEMA)
        _seed_binders(conn)
        _seed_artifacts(conn)
        _seed_artifact_history(conn)
        _seed_artifact_tags(conn)
        _seed_artifact_annotations(conn)
        _seed_audit_log(conn)
        _seed_patterns(conn)
        _seed_root_causes(conn)
        _seed_calibrations(conn)
        _seed_calibration_history(conn)
        _seed_investigations(conn)
        conn.commit()
    finally:
        conn.close()

def _seed_binders(conn: sqlite3.Connection) -> None:
    rows = [('binder_001', 'inv_001', BASE_TS, TS_18, 'active'), ('binder_002', 'inv_002', TS_19, TS_21, 'completed'), ('binder_003', 'inv_003', TS_22, TS_23, 'archived')]
    conn.executemany('INSERT INTO work_binders (id, investigation_id, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?)', rows)

def _seed_artifacts(conn: sqlite3.Connection) -> None:
    artifacts = [('hyp_001', 'binder_001', 'hypothesis_artifact', 'Theorist', TS_06, TS_06, 1, 'BoardReader::processData', 'high', _j(['timeout', 'network']), _j({'description': 'Network latency causing timeout in BoardReader', 'source': 'code_hint', 'prior_probability': 0.75, 'score': 0.82, 'supporting_evidence_ids': ['ev_001', 'ev_002'], 'contradicting_evidence_ids': []}), False, None, None), ('hyp_002', 'binder_001', 'hypothesis_artifact', 'Theorist', TS_06, TS_07, 1, 'DataTransfer::send', 'normal', _j(['buffer', 'memory']), _j({'description': 'Buffer overflow in DataTransfer send path', 'source': 'pattern', 'prior_probability': 0.6, 'score': 0.55, 'supporting_evidence_ids': ['ev_003'], 'contradicting_evidence_ids': ['ev_001']}), False, None, None), ('hyp_003', 'binder_001', 'hypothesis_artifact', 'Theorist', TS_07, TS_07, 1, None, 'low', _j(['speculative']), _j({'description': 'Hardware fault in DAQ board', 'source': 'fresh', 'prior_probability': 0.2, 'score': 0.15, 'supporting_evidence_ids': [], 'contradicting_evidence_ids': ['ev_002']}), False, None, None), ('ev_001', 'binder_001', 'evidence_artifact', 'Detective', TS_08, TS_08, 2, 'BoardReader::processData', 'high', _j(['log_evidence', 'timeout']), _j({'evidence_type': 'log', 'content': 'Timeout at 10:25:00 in BoardReader::processData after 30s wait', 'source': 'log_search', 'strength': 'STRONG', 'supports_hypothesis_ids': ['hyp_001'], 'contradicts_hypothesis_ids': ['hyp_002']}), False, None, None), ('ev_002', 'binder_001', 'evidence_artifact', 'Detective', TS_09, TS_09, 2, 'NetworkManager::connect', 'high', _j(['network', 'connection']), _j({'evidence_type': 'code', 'content': 'NetworkManager::connect shows no retry logic for dropped packets', 'source': 'code_analysis', 'strength': 'STRONG', 'supports_hypothesis_ids': ['hyp_001'], 'contradicts_hypothesis_ids': ['hyp_003']}), False, None, None), ('ev_003', 'binder_001', 'evidence_artifact', 'Detective', TS_10, TS_10, 2, 'DataTransfer::send', 'normal', _j(['buffer']), _j({'evidence_type': 'log', 'content': 'Buffer allocation succeeded with 512MB available', 'source': 'log_search', 'strength': 'MODERATE', 'supports_hypothesis_ids': ['hyp_002'], 'contradicts_hypothesis_ids': []}), False, None, None), ('ev_004', 'binder_001', 'evidence_artifact', 'Detective', TS_11, TS_11, 2, None, 'low', _j(['timing']), _j({'evidence_type': 'timing', 'content': 'System clock drift detected: 2ms over 1 hour', 'source': 'system_check', 'strength': 'WEAK', 'supports_hypothesis_ids': [], 'contradicts_hypothesis_ids': []}), False, None, None), ('chain_001', 'binder_001', 'causal_chain', 'Logician', TS_12, TS_12, 3, 'BoardReader::processData', 'high', _j(['primary_chain']), _j({'hypothesis_id': 'hyp_001', 'steps': [{'cause': 'Network packet loss', 'effect': 'Delayed response'}, {'cause': 'Delayed response', 'effect': 'Timeout threshold exceeded'}, {'cause': 'Timeout threshold exceeded', 'effect': 'BoardReader exception'}], 'completeness_score': 0.9}), False, None, None), ('chain_002', 'binder_001', 'causal_chain', 'Logician', TS_13, TS_13, 3, 'DataTransfer::send', 'normal', _j(['secondary_chain']), _j({'hypothesis_id': 'hyp_002', 'steps': [{'cause': 'Large fragment size', 'effect': 'Buffer pressure'}, {'cause': 'Buffer pressure', 'effect': 'Slow send operation'}], 'completeness_score': 0.6}), False, None, None), ('chal_001', 'binder_001', 'challenge', 'Critic', TS_14, TS_15, 4, None, 'high', _j(['adversarial']), _j({'target_hypothesis_id': 'hyp_001', 'content': 'Network latency should affect all components, not just BoardReader', 'severity': 'HIGH', 'resolved': True, 'resolution': 'BoardReader has stricter timeout than other components (30s vs 120s)'}), False, None, None), ('chal_002', 'binder_001', 'challenge', 'Critic', TS_15, TS_15, 4, None, 'normal', _j(['adversarial']), _j({'target_hypothesis_id': 'hyp_001', 'content': 'No direct evidence of packet loss in network logs', 'severity': 'MEDIUM', 'resolved': False, 'resolution': None}), False, None, None), ('llmreq_001', 'binder_001', 'llm_request', 'Theorist', TS_06, TS_06, 1, None, 'normal', _j(['llm']), _j({'persona': 'Theorist', 'prompt_key': 'hypothesis_generation', 'system_prompt': 'You are an expert at generating hypotheses.', 'user_prompt': 'Analyze this error: Timeout in BoardReader::processData', 'model': 'claude-3-sonnet', 'temperature': 0.1}), False, None, None), ('llmreq_002', 'binder_001', 'llm_request', 'Detective', TS_08, TS_08, 2, None, 'normal', _j(['llm']), _j({'persona': 'Detective', 'prompt_key': 'evidence_seeking', 'system_prompt': 'You are an evidence-seeking detective.', 'user_prompt': 'Find evidence for: Network latency causing timeout', 'model': 'claude-3-sonnet', 'temperature': 0.0}), False, None, None), ('llmresp_001', 'binder_001', 'llm_response', 'Theorist', TS_06, TS_06, 1, None, 'normal', _j(['llm']), _j({'linked_request_id': 'llmreq_001', 'raw_response': 'Based on analysis, the most likely cause is network latency.', 'parsed_content': {'hypotheses': ['Network latency', 'Buffer overflow']}, 'tokens_used': 1500, 'latency_ms': 2300.5, 'parse_success': True}), False, None, None), ('llmresp_002', 'binder_001', 'llm_response', 'Detective', TS_09, TS_09, 2, None, 'normal', _j(['llm']), _j({'linked_request_id': 'llmreq_002', 'raw_response': 'Found timeout log entries and missing retry logic.', 'parsed_content': {'evidence': ['timeout_log', 'no_retry']}, 'tokens_used': 800, 'latency_ms': 1100.0, 'parse_success': True}), False, None, None), ('ps_000', 'binder_001', 'phase_state', 'Archivist', BASE_TS, TS_05, 0, None, 'normal', _j(['phase']), _j({'phase_number': 0, 'persona_name': 'Archivist', 'status': 'completed', 'started_at': BASE_TS, 'completed_at': TS_05}), False, None, None), ('ps_001', 'binder_001', 'phase_state', 'Theorist', TS_06, TS_07, 1, None, 'normal', _j(['phase']), _j({'phase_number': 1, 'persona_name': 'Theorist', 'status': 'completed', 'started_at': TS_06, 'completed_at': TS_07}), False, None, None), ('ps_002', 'binder_001', 'phase_state', 'Detective', TS_08, TS_11, 2, None, 'normal', _j(['phase']), _j({'phase_number': 2, 'persona_name': 'Detective', 'status': 'completed', 'started_at': TS_08, 'completed_at': TS_11}), False, None, None), ('ps_003', 'binder_001', 'phase_state', 'Logician', TS_12, TS_13, 3, None, 'normal', _j(['phase']), _j({'phase_number': 3, 'persona_name': 'Logician', 'status': 'completed', 'started_at': TS_12, 'completed_at': TS_13}), False, None, None), ('ps_004', 'binder_001', 'phase_state', 'Critic', TS_14, TS_15, 4, None, 'normal', _j(['phase']), _j({'phase_number': 4, 'persona_name': 'Critic', 'status': 'completed', 'started_at': TS_14, 'completed_at': TS_15}), False, None, None), ('ps_005', 'binder_001', 'phase_state', 'Coordinator', TS_16, TS_16, 5, None, 'normal', _j(['phase']), _j({'phase_number': 5, 'persona_name': 'Coordinator', 'status': 'completed', 'started_at': TS_16, 'completed_at': TS_16}), False, None, None), ('ps_006', 'binder_001', 'phase_state', 'Synthesizer', TS_17, TS_18, 6, None, 'normal', _j(['phase']), _j({'phase_number': 6, 'persona_name': 'Synthesizer', 'status': 'completed', 'started_at': TS_17, 'completed_at': TS_18}), False, None, None), ('is_001', 'binder_001', 'investigation_state', 'Coordinator', BASE_TS, TS_18, None, None, 'high', _j(['state']), _j({'investigation_id': 'inv_001', 'current_phase': 6, 'status': 'completed', 'outcome': 'CONFIDENT', 'started_at': BASE_TS, 'completed_at': TS_18, 'error_message': 'Timeout waiting for data from BoardReader', 'error_function': 'BoardReader::processData'}), False, None, None), ('hyp_201', 'binder_002', 'hypothesis_artifact', 'Theorist', TS_19, TS_19, 1, 'FragmentGenerator::generate', 'normal', _j(['timeout', 'fragment']), _j({'description': 'Fragment generation timeout due to slow disk I/O', 'source': 'pattern', 'prior_probability': 0.5, 'score': 0.45, 'supporting_evidence_ids': ['ev_201'], 'contradicting_evidence_ids': []}), False, None, None), ('hyp_202', 'binder_002', 'hypothesis_artifact', 'Theorist', TS_19, TS_20, 1, 'SharedMemoryManager::allocate', 'normal', _j(['memory']), _j({'description': 'Shared memory exhaustion', 'source': 'fresh', 'prior_probability': 0.3, 'score': 0.25, 'supporting_evidence_ids': ['ev_202'], 'contradicting_evidence_ids': []}), False, None, None), ('ev_201', 'binder_002', 'evidence_artifact', 'Detective', TS_20, TS_20, 2, 'FragmentGenerator::generate', 'normal', _j(['disk', 'io']), _j({'evidence_type': 'log', 'content': 'Disk I/O latency spike to 500ms at 09:30', 'source': 'log_search', 'strength': 'MODERATE', 'supports_hypothesis_ids': ['hyp_201'], 'contradicts_hypothesis_ids': []}), False, None, None), ('ev_202', 'binder_002', 'evidence_artifact', 'Detective', TS_20, TS_20, 2, 'SharedMemoryManager::allocate', 'normal', _j(['memory']), _j({'evidence_type': 'code', 'content': 'SharedMemoryManager has 4GB limit, allocation requested 3.8GB', 'source': 'code_analysis', 'strength': 'MODERATE', 'supports_hypothesis_ids': ['hyp_202'], 'contradicts_hypothesis_ids': []}), False, None, None), ('chain_201', 'binder_002', 'causal_chain', 'Logician', TS_21, TS_21, 3, 'FragmentGenerator::generate', 'normal', _j(['primary_chain']), _j({'hypothesis_id': 'hyp_201', 'steps': [{'cause': 'Disk I/O spike', 'effect': 'Slow fragment write'}, {'cause': 'Slow fragment write', 'effect': 'Generation timeout'}], 'completeness_score': 0.5}), False, None, None), ('chal_201', 'binder_002', 'challenge', 'Critic', TS_21, TS_21, 4, None, 'normal', _j(['adversarial']), _j({'target_hypothesis_id': 'hyp_201', 'content': 'Disk I/O spike was brief and may not have lasted long enough', 'severity': 'MEDIUM', 'resolved': False, 'resolution': None}), False, None, None), ('llmreq_201', 'binder_002', 'llm_request', 'Theorist', TS_19, TS_19, 1, None, 'normal', _j(['llm']), _j({'persona': 'Theorist', 'prompt_key': 'hypothesis_generation', 'system_prompt': 'You are an expert at generating hypotheses.', 'user_prompt': 'Analyze: Fragment generation timeout', 'model': 'claude-3-sonnet', 'temperature': 0.1}), False, None, None), ('llmresp_201', 'binder_002', 'llm_response', 'Theorist', TS_20, TS_20, 1, None, 'normal', _j(['llm']), _j({'linked_request_id': 'llmreq_201', 'raw_response': 'Disk I/O and memory exhaustion are candidate causes.', 'parsed_content': {'hypotheses': ['Disk I/O', 'Memory exhaustion']}, 'tokens_used': 900, 'latency_ms': 1800.0, 'parse_success': True}), False, None, None), ('is_002', 'binder_002', 'investigation_state', 'Coordinator', TS_19, TS_21, None, None, 'normal', _j(['state']), _j({'investigation_id': 'inv_002', 'current_phase': 6, 'status': 'completed', 'outcome': 'UNCERTAIN', 'started_at': TS_19, 'completed_at': TS_21, 'error_message': 'Fragment generation timeout in FragmentGenerator', 'error_function': 'FragmentGenerator::generate'}), False, None, None), ('hyp_301', 'binder_003', 'hypothesis_artifact', 'Theorist', TS_22, TS_22, 1, None, 'low', _j(['unknown']), _j({'description': 'Insufficient data to determine cause', 'source': 'fresh', 'prior_probability': 0.1, 'score': 0.05, 'supporting_evidence_ids': [], 'contradicting_evidence_ids': []}), False, None, None), ('is_003', 'binder_003', 'investigation_state', 'Coordinator', TS_22, TS_23, None, None, 'normal', _j(['state']), _j({'investigation_id': 'inv_003', 'current_phase': 5, 'status': 'completed', 'outcome': 'INSUFFICIENT', 'started_at': TS_22, 'completed_at': TS_23, 'error_message': 'Unknown error', 'error_function': None}), False, None, None)]
    conn.executemany('INSERT INTO binder_artifacts (id, binder_id, artifact_type, created_by, created_at, updated_at, phase, function_name, priority, tags_json, content_json, is_deleted, deleted_by, deleted_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', artifacts)

def _seed_artifact_history(conn: sqlite3.Connection) -> None:
    rows = [('hist_001', 'hyp_001', 'Theorist', TS_06, 'created', _j({'description': 'Initial hypothesis creation'})), ('hist_002', 'hyp_001', 'Detective', TS_08, 'updated', _j({'score': {'old': 0.75, 'new': 0.82}})), ('hist_003', 'ev_001', 'Detective', TS_08, 'created', _j({'content': 'Log evidence found'})), ('hist_004', 'chal_001', 'Critic', TS_14, 'created', _j({'content': 'Challenge raised'})), ('hist_005', 'chal_001', 'Theorist', TS_15, 'updated', _j({'resolved': {'old': False, 'new': True}})), ('hist_006', 'hyp_002', 'Theorist', TS_06, 'created', _j({'description': 'Buffer overflow hypothesis'})), ('hist_007', 'hyp_002', 'Detective', TS_10, 'updated', _j({'score': {'old': 0.6, 'new': 0.55}}))]
    conn.executemany('INSERT INTO artifact_history (id, artifact_id, modified_by, modified_at, action, changes_json) VALUES (?, ?, ?, ?, ?, ?)', rows)

def _seed_artifact_tags(conn: sqlite3.Connection) -> None:
    tags = [('hyp_001', 'timeout'), ('hyp_001', 'network'), ('hyp_002', 'buffer'), ('hyp_002', 'memory'), ('hyp_003', 'speculative'), ('ev_001', 'log_evidence'), ('ev_001', 'timeout'), ('ev_002', 'network'), ('ev_002', 'connection'), ('ev_003', 'buffer'), ('ev_004', 'timing'), ('chain_001', 'primary_chain'), ('chain_002', 'secondary_chain'), ('chal_001', 'adversarial'), ('chal_002', 'adversarial')]
    conn.executemany('INSERT INTO artifact_tags (artifact_id, tag) VALUES (?, ?)', tags)

def _seed_artifact_annotations(conn: sqlite3.Connection) -> None:
    rows = [('ann_001', 'ev_001', 'hyp_001', 'Detective', 'comment', 'Strong evidence supporting network latency hypothesis', TS_09), ('ann_002', 'ev_002', 'hyp_001', 'Detective', 'highlight', 'Key finding: no retry logic in NetworkManager', TS_09), ('ann_003', 'chal_001', 'hyp_001', 'Critic', 'question', 'Why only BoardReader affected?', TS_14), ('ann_004', 'ev_003', 'hyp_002', 'Detective', 'comment', 'Buffer allocation succeeded, weakens overflow hypothesis', TS_10)]
    conn.executemany('INSERT INTO artifact_annotations (id, artifact_id, target_artifact_id, created_by, annotation_type, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_audit_log(conn: sqlite3.Connection) -> None:
    rows = [('aud_001', 'binder_001', 'Archivist', 0, BASE_TS, 1, 'store', 'error_context', None, 'add_error_context', 1, True), ('aud_002', 'binder_001', 'Archivist', 0, TS_01, 2, 'store', 'source_location', None, 'add_source_location', 1, True), ('aud_003', 'binder_001', 'Archivist', 0, TS_02, 3, 'store', 'call_graph', None, 'add_call_graph', 1, True), ('aud_004', 'binder_001', 'Theorist', 1, TS_06, 4, 'store', 'hypothesis_artifact', 'hyp_001', 'add_hypothesis', 1, True), ('aud_005', 'binder_001', 'Theorist', 1, TS_06, 5, 'store', 'hypothesis_artifact', 'hyp_002', 'add_hypothesis', 1, True), ('aud_006', 'binder_001', 'Theorist', 1, TS_07, 6, 'store', 'hypothesis_artifact', 'hyp_003', 'add_hypothesis', 1, True), ('aud_007', 'binder_001', 'Detective', 2, TS_08, 7, 'store', 'evidence_artifact', 'ev_001', 'add_evidence', 1, True), ('aud_008', 'binder_001', 'Detective', 2, TS_09, 8, 'store', 'evidence_artifact', 'ev_002', 'add_evidence', 1, True), ('aud_009', 'binder_001', 'Detective', 2, TS_10, 9, 'store', 'evidence_artifact', 'ev_003', 'add_evidence', 1, True), ('aud_010', 'binder_001', 'Detective', 2, TS_11, 10, 'store', 'evidence_artifact', 'ev_004', 'add_evidence', 1, True), ('aud_011', 'binder_001', 'Detective', 2, TS_08, 11, 'retrieve', 'hypothesis_artifact', 'hyp_001', 'get_hypotheses', 3, True), ('aud_012', 'binder_001', 'Logician', 3, TS_12, 12, 'store', 'causal_chain', 'chain_001', 'add_causal_chain', 1, True), ('aud_013', 'binder_001', 'Logician', 3, TS_13, 13, 'store', 'causal_chain', 'chain_002', 'add_causal_chain', 1, True), ('aud_014', 'binder_001', 'Critic', 4, TS_14, 14, 'store', 'challenge', 'chal_001', 'add_challenge', 1, True), ('aud_015', 'binder_001', 'Critic', 4, TS_15, 15, 'store', 'challenge', 'chal_002', 'add_challenge', 1, True), ('aud_016', 'binder_001', 'Synthesizer', 6, TS_17, 16, 'retrieve', 'hypothesis_artifact', None, 'get_hypotheses', 3, True), ('aud_017', 'binder_001', 'Synthesizer', 6, TS_17, 17, 'retrieve', 'evidence_artifact', None, 'get_evidence', 4, True), ('aud_201', 'binder_002', 'Theorist', 1, TS_19, 1, 'store', 'hypothesis_artifact', 'hyp_201', 'add_hypothesis', 1, True), ('aud_202', 'binder_002', 'Detective', 2, TS_20, 2, 'store', 'evidence_artifact', 'ev_201', 'add_evidence', 1, True), ('aud_203', 'binder_002', 'Detective', 2, TS_20, 3, 'store', 'evidence_artifact', 'ev_202', 'add_evidence', 1, True)]
    conn.executemany('INSERT INTO binder_audit_log (id, binder_id, persona_name, phase_number, timestamp, access_sequence, operation_type, artifact_type, artifact_id, method_name, result_count, success) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_patterns(conn: sqlite3.Connection) -> None:
    rows = [('pat_001', 'Timeout in BoardReader', 'BoardReader timeout due to network latency or hardware issues', 'BoardReader::processData', 'Timeout waiting for data', 'ERROR', 25, 21, 4, 0.84, True, True, '2024-06-15T10:00:00', '2025-01-15T10:00:00'), ('pat_002', 'Connection Refused', 'Connection refused errors typically from service not running', None, 'Connection refused', 'ERROR', 45, 40, 5, 0.92, True, False, '2024-03-10T08:00:00', '2025-01-10T08:00:00'), ('pat_003', 'Fragment Timeout', 'Fragment generation timeout from disk I/O or memory issues', 'FragmentGenerator::generate', 'Fragment.*timeout', 'ERROR', 8, 5, 3, 0.55, True, False, '2024-10-01T09:00:00', '2025-01-05T09:00:00')]
    conn.executemany('INSERT INTO error_patterns (id, name, description, signature_function, signature_message_pattern, signature_level, times_seen, times_correct, times_incorrect, pattern_confidence, is_active, user_verified, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_root_causes(conn: sqlite3.Connection) -> None:
    rows = [('rc_001', 'pat_001', 'Network congestion causing packet loss', 0.65, _j(['Log entries showing retransmissions']), _j([]), 'Check network switches and increase timeout thresholds'), ('rc_002', 'pat_001', 'Hardware board malfunction', 0.25, _j(['Board diagnostic logs']), _j(['Software restart resolved issue']), 'Replace board or update firmware'), ('rc_003', 'pat_002', 'Target service not running', 0.7, _j(['Process listing shows service absent']), _j([]), 'Restart the target service'), ('rc_004', 'pat_002', 'Firewall blocking port', 0.2, _j(['Firewall rule audit']), _j([]), 'Update firewall rules to allow traffic')]
    conn.executemany('INSERT INTO root_cause_patterns (id, error_pattern_id, description, frequency, confirming_evidence, refuting_evidence, typical_fix) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_calibrations(conn: sqlite3.Connection) -> None:
    buckets = {'0.3': {'correct': 3, 'total': 10}, '0.5': {'correct': 8, 'total': 15}, '0.7': {'correct': 14, 'total': 18}, '0.9': {'correct': 9, 'total': 10}}
    rows = [('cal_001', 'default', None, _j(buckets), 0.03, 53, '2025-01-15T12:00:00'), ('cal_002', 'default', 'timeout', _j({'0.5': {'correct': 5, 'total': 8}, '0.7': {'correct': 7, 'total': 9}}), 0.05, 17, '2025-01-15T12:00:00')]
    conn.executemany('INSERT INTO model_calibration (id, model_name, error_type, buckets_json, overall_bias, sample_size, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_calibration_history(conn: sqlite3.Connection) -> None:
    rows = [('default', None, '2025-01-01T00:00:00', 0.08, 30, 0.72, _j({})), ('default', None, '2025-01-05T00:00:00', 0.06, 38, 0.76, _j({})), ('default', None, '2025-01-10T00:00:00', 0.04, 45, 0.8, _j({})), ('default', None, '2025-01-15T00:00:00', 0.03, 53, 0.82, _j({})), ('default', 'timeout', '2025-01-15T00:00:00', 0.05, 17, 0.78, _j({}))]
    conn.executemany('INSERT INTO calibration_history (model_name, error_type, recorded_at, overall_bias, sample_size, overall_accuracy, buckets_json) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)

def _seed_investigations(conn: sqlite3.Connection) -> None:
    trigger_error_1 = {'message': 'Timeout waiting for data from BoardReader', 'level': 'ERROR', 'component': 'DataTransfer', 'function': 'BoardReader::processData', 'timestamp': BASE_TS}
    trigger_error_2 = {'message': 'Fragment generation timeout in FragmentGenerator', 'level': 'ERROR', 'component': 'FragmentSystem', 'function': 'FragmentGenerator::generate', 'timestamp': TS_19}
    rows = [('inv_001', BASE_TS, _j(trigger_error_1), _j([]), 'CONFIDENT', _j([]), _j({}), _j([]), _j([]), 'pat_001', _j([]), 9000.0, BASE_TS, TS_18, 2), ('inv_002', TS_19, _j(trigger_error_2), _j([]), 'UNCERTAIN', _j([]), _j({}), _j([]), _j([]), None, _j([]), 7200.0, TS_19, TS_21, 3)]
    conn.executemany('INSERT INTO investigations (id, timestamp, trigger_error_json, context_logs_json, outcome, hypotheses_json, evidence_json, causal_chains_json, challenges_json, matched_pattern_id, similar_investigation_ids_json, duration_seconds, started_at, completed_at, processing_tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)

@contextmanager
def fixture_environment() -> Generator[Path, None, None]:
    original_data_dir = os.environ.get('ARTDAQ_DATA_DIR')
    tmp_dir = tempfile.mkdtemp(prefix='mcptester_fixture_')
    tmp_path = Path(tmp_dir)
    try:
        db_path = tmp_path / 'knowledge.db'
        create_fixture_db(db_path)
        os.environ['ARTDAQ_DATA_DIR'] = str(tmp_path)
        yield tmp_path
    finally:
        if original_data_dir is not None:
            os.environ['ARTDAQ_DATA_DIR'] = original_data_dir
        else:
            os.environ.pop('ARTDAQ_DATA_DIR', None)
        shutil.rmtree(tmp_dir, ignore_errors=True)