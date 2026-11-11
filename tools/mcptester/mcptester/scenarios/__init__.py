from tools.mcptester.mcptester.scenarios.artifacts import ArtifactsScenario
from tools.mcptester.mcptester.scenarios.audit import AuditScenario
from tools.mcptester.mcptester.scenarios.base import BaseScenario, ScenarioResult, TestCase
from tools.mcptester.mcptester.scenarios.binders import BindersScenario
from tools.mcptester.mcptester.scenarios.calibrations import CalibrationsScenario
from tools.mcptester.mcptester.scenarios.commands import CommandsScenario
from tools.mcptester.mcptester.scenarios.investigation import InvestigationScenario
from tools.mcptester.mcptester.scenarios.llm_tracing import LLMTracingScenario
from tools.mcptester.mcptester.scenarios.patterns import PatternsScenario
from tools.mcptester.mcptester.scenarios.specialized import SpecializedScenario

def get_all_scenarios() -> dict[str, BaseScenario]:
    return {'binders': BindersScenario(), 'artifacts': ArtifactsScenario(), 'audit': AuditScenario(), 'patterns': PatternsScenario(), 'calibrations': CalibrationsScenario(), 'specialized': SpecializedScenario(), 'llm_tracing': LLMTracingScenario(), 'investigation': InvestigationScenario(), 'commands': CommandsScenario()}
__all__ = ['BaseScenario', 'TestCase', 'ScenarioResult', 'get_all_scenarios']