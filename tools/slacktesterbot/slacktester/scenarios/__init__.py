from tools.slacktesterbot.slacktester.scenarios.admin import AdminScenario
from tools.slacktesterbot.slacktester.scenarios.ask import AskScenario
from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, ScenarioResult
from tools.slacktesterbot.slacktester.scenarios.config_cmd import ConfigScenario
from tools.slacktesterbot.slacktester.scenarios.feedback import FeedbackScenario
from tools.slacktesterbot.slacktester.scenarios.help import HelpScenario, VersionScenario
from tools.slacktesterbot.slacktester.scenarios.investigate import InvestigateScenario
from tools.slacktesterbot.slacktester.scenarios.list_cmd import ListScenario
from tools.slacktesterbot.slacktester.scenarios.message import MessageScenario
from tools.slacktesterbot.slacktester.scenarios.workbinder import WorkbinderScenario

def get_all_scenarios() -> dict[str, BaseScenario]:
    return {'investigate': InvestigateScenario(), 'message': MessageScenario(), 'feedback': FeedbackScenario(), 'ask': AskScenario(), 'list': ListScenario(), 'config': ConfigScenario(), 'workbinder': WorkbinderScenario(), 'admin': AdminScenario(), 'help': HelpScenario(), 'version': VersionScenario()}
__all__ = ['BaseScenario', 'ScenarioResult', 'get_all_scenarios', 'InvestigateScenario', 'MessageScenario', 'FeedbackScenario', 'AskScenario', 'ListScenario', 'ConfigScenario', 'WorkbinderScenario', 'AdminScenario', 'HelpScenario', 'VersionScenario']