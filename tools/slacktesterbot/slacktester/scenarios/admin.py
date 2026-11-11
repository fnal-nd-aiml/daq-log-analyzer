from tools.slacktesterbot.slacktester.scenarios.base import BaseScenario, TestCase

class AdminScenario(BaseScenario):
    name = 'admin'
    description = 'Admin commands (init, sync-source) parsing'

    def get_test_cases(self) -> list[TestCase]:
        return [TestCase(name='init_basic', command='init', expected={'error': False, 'parse_result': {'skip_source': False}}, description='Init command without options'), TestCase(name='init_skip_source', command='init skip-source', expected={'error': False, 'parse_result': {'skip_source': True}}, description='Init command with skip-source flag'), TestCase(name='sync_source_basic', command='sync-source', expected={'error': False, 'parse_result': {'status_only': False}}, description='Sync-source command without options'), TestCase(name='sync_source_status', command='sync-source status', expected={'error': False, 'parse_result': {'status_only': True}}, description='Sync-source command with status flag')]