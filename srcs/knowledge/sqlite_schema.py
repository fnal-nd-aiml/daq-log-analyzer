"""
File: sqlite_schema.py
Purpose: SQLite database schema for knowledge store.
Category: Utility
Author: artdaq team
Depends: None
Exports: SCHEMA
Complexity: Medium | Lines: 212
"""

SCHEMA = """
-- Core investigations table (normalized - JSON blobs for backward compatibility)
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
    processing_tier INTEGER DEFAULT 3,
    confidence REAL
);

-- Normalized hypotheses table for cross-investigation queries
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

-- Evidence queries table for tracking what queries were executed
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

-- Normalized evidence items table
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

-- Normalized causal chains table
CREATE TABLE IF NOT EXISTS causal_chains (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    hypothesis_id TEXT REFERENCES hypotheses(id),
    root_cause TEXT,
    final_effect TEXT,
    chain_strength REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Causal steps within chains
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

-- Normalized challenges table
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

-- Feedback records table for audit trail
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

-- Strategy performance tracking for meta-learning
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

-- Query type effectiveness tracking for meta-learning
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
    refuting_evidence TEXT
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

-- Indexes for efficient queries
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
CREATE INDEX IF NOT EXISTS idx_strategy_performance
    ON hypothesis_strategy_performance(strategy_name, error_type);
CREATE INDEX IF NOT EXISTS idx_query_effectiveness
    ON query_type_effectiveness(query_type, error_type);

-- Additional indexes for performance optimization (Phase 5)
CREATE INDEX IF NOT EXISTS idx_evidence_items_strength
    ON evidence_items(strength);
CREATE INDEX IF NOT EXISTS idx_feedback_was_correct
    ON feedback_records(was_correct);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence
    ON error_patterns(pattern_confidence DESC);
-- Serves find_pattern: WHERE is_active ... ORDER BY times_seen DESC LIMIT N
CREATE INDEX IF NOT EXISTS idx_patterns_active_seen
    ON error_patterns(is_active, times_seen DESC);
CREATE INDEX IF NOT EXISTS idx_investigations_matched_pattern
    ON investigations(matched_pattern_id);
"""