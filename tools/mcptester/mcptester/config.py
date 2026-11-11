from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field

class ScenariosConfig(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: ['binders', 'artifacts', 'audit', 'patterns', 'calibrations', 'specialized', 'llm_tracing', 'investigation', 'commands'])

class MockConfig(BaseModel):
    simulate_delays: bool = False
    mock_llm_responses: bool = True
    investigation_timeout: int = 5

class OutputConfig(BaseModel):
    format: Literal['terminal', 'json'] = 'terminal'
    verbose: bool = True

class LiveConfig(BaseModel):
    server_url: str = 'http://localhost:8001'
    transport: Literal['stdio', 'sse', 'streamable-http'] = 'sse'
    timeout: int = 30

class FixtureConfig(BaseModel):
    enabled: bool = True

class TesterConfig(BaseModel):
    scenarios: ScenariosConfig = Field(default_factory=ScenariosConfig)
    mock: MockConfig = Field(default_factory=MockConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    fixture: FixtureConfig = Field(default_factory=FixtureConfig)

def load_config(config_path: Path | None=None) -> TesterConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return TesterConfig.model_validate(data)
    return TesterConfig()