from typing import Any
from uuid import uuid4

def generate_uuid() -> str:
    return str(uuid4())

def generate_short_id() -> str:
    return uuid4().hex[:8]
SAMPLE_BINDERS = [{'id': 'binder001', 'investigation_id': 'inv001', 'status': 'active', 'created_at': '2024-01-15T10:00:00', 'updated_at': '2024-01-15T12:30:00'}, {'id': 'binder002', 'investigation_id': 'inv002', 'status': 'archived', 'created_at': '2024-01-10T08:00:00', 'updated_at': '2024-01-10T16:00:00'}]
SAMPLE_ARTIFACTS = [{'id': 'artifact001', 'artifact_type': 'hypothesis_artifact', 'phase': 1, 'function_name': 'BoardReader::processData', 'tags': ['timeout', 'network'], 'content': {'description': 'Timeout during data processing'}, 'created_at': '2024-01-15T10:30:00'}, {'id': 'artifact002', 'artifact_type': 'evidence', 'phase': 2, 'function_name': None, 'tags': ['log_evidence'], 'content': {'text': 'Connection refused at 10:25:00'}, 'created_at': '2024-01-15T10:35:00'}, {'id': 'artifact003', 'artifact_type': 'call_graph', 'phase': 0, 'function_name': 'FragmentGenerator::generate', 'tags': ['code_analysis'], 'content': {'calls': ['DataStore::write', 'Logger::log']}, 'created_at': '2024-01-15T10:20:00'}]
SAMPLE_AUDIT_ENTRIES = [{'id': 'audit001', 'binder_id': 'binder001', 'artifact_id': 'artifact001', 'persona_name': 'Theorist', 'phase_number': 1, 'operation_type': 'store', 'timestamp': '2024-01-15T10:30:00'}, {'id': 'audit002', 'binder_id': 'binder001', 'artifact_id': 'artifact001', 'persona_name': 'Detective', 'phase_number': 2, 'operation_type': 'retrieve', 'timestamp': '2024-01-15T10:35:00'}]
SAMPLE_PATTERNS = [{'id': 'pattern001', 'error_signature': 'Timeout waiting for data', 'root_causes': ['Network congestion', 'Buffer overflow'], 'confidence': 0.85, 'times_seen': 25, 'accuracy': 0.82, 'active': True}, {'id': 'pattern002', 'error_signature': 'Connection refused', 'root_causes': ['Service not running', 'Port blocked'], 'confidence': 0.92, 'times_seen': 45, 'accuracy': 0.88, 'active': True}]
SAMPLE_CALIBRATIONS = [{'model': 'default', 'error_type': None, 'buckets': {'0.5': {'correct': 8, 'total': 10}}, 'bias': 0.02, 'sample_size': 50}]
SAMPLE_LLM_REQUEST = {'id': 'llm_req001', 'binder_id': 'binder001', 'persona': 'Theorist', 'phase': 1, 'prompt_key': 'hypothesis_generation', 'prompt_text': 'Analyze this error...', 'model': 'claude-3', 'timestamp': '2024-01-15T10:30:00'}
SAMPLE_LLM_RESPONSE = {'id': 'llm_resp001', 'request_id': 'llm_req001', 'binder_id': 'binder001', 'phase': 1, 'response_text': 'Based on the evidence...', 'parse_success': True, 'latency_ms': 1500, 'tokens_in': 500, 'tokens_out': 200, 'timestamp': '2024-01-15T10:30:02'}
SAMPLE_INVESTIGATION_STATE = {'binder_id': 'binder001', 'investigation_id': 'inv001', 'current_phase': 6, 'outcome': 'PROBABLE', 'started_at': '2024-01-15T10:00:00', 'completed_at': '2024-01-15T12:30:00'}
SAMPLE_INVESTIGATION_RESULT = {'investigation_id': 'inv_test001', 'outcome': 'PROBABLE', 'root_cause': 'Timeout in BoardReader due to network latency', 'confidence': 0.75, 'trigger_error': {'message': 'Timeout waiting for data from BoardReader', 'component': 'DataTransfer', 'function': 'processData', 'timestamp': '2024-01-15T10:25:00'}, 'hypotheses': [{'id': 'hyp001', 'description': 'Network latency causing timeout', 'score': 0.75, 'source': 'pattern', 'supporting_evidence': ['ev001'], 'contradicting_evidence': []}], 'causal_chains': [{'hypothesis_id': 'hyp001', 'chain': ['Network packet loss detected', 'Retry mechanism triggered', 'Timeout threshold exceeded']}]}
SAMPLE_PANEL_RESPONSE = {'question_id': 'q_test001', 'answer': 'A BoardReader is a component in the artdaq framework responsible for reading data from hardware boards.', 'confidence': 0.85, 'key_points': ['BoardReader reads raw data from DAQ hardware', 'It implements the artdaq fragment interface', 'Multiple BoardReaders can run in parallel'], 'caveats': ['Implementation details may vary by experiment'], 'contributions_summary': {'Archivist': 'Provided historical context', 'Synthesizer': 'Combined perspectives into answer'}, 'dissenting_views': [], 'sources': ['artdaq documentation', 'FNAL wiki'], 'citations': []}

class MockLLMProvider:

    async def generate(self, prompt: str) -> str:
        return 'Mock LLM response for testing'

    async def generate_structured(self, prompt: str, model: type) -> Any:
        return {'response': 'structured mock response'}

class MockKnowledgeBase:

    def __init__(self) -> None:
        self.patterns = SAMPLE_PATTERNS.copy()
        self.calibrations = SAMPLE_CALIBRATIONS.copy()

    async def get_investigation(self, investigation_id: str) -> dict[str, Any] | None:
        if investigation_id == 'inv_test001':
            return SAMPLE_INVESTIGATION_RESULT
        return None

    async def update_calibration(self, model: str, stated_confidence: float, correct: bool) -> None:
        pass

class MockPanelOrchestrator:

    async def answer(self, question: str, related_logs: list | None=None, callback: Any=None) -> dict[str, Any]:
        if callback:
            await callback({'event': 'classification', 'question_type': 'WHAT_IS'})
            await callback({'event': 'panel_selected', 'personas': ['Archivist', 'Synthesizer']})
            await callback({'event': 'synthesis_complete', 'confidence': 0.85})
        return type('PanelResponse', (), SAMPLE_PANEL_RESPONSE)()