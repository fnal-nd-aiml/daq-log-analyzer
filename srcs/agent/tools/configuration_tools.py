"""
File: configuration_tools.py
Purpose: Configuration file analysis tools.
Category: Utility
Author: artdaq team
Depends: models
Exports: ConfigurationTools
Complexity: Low | Lines: 83
"""

import asyncio
import re
from pathlib import Path
from srcs.models import EvidenceItem
from .base import logger, make_evidence, validate_path

class ConfigurationTools:

    def __init__(self, config_paths: list[Path] | None=None):
        self.config_paths = config_paths or []
        self._config_cache: dict[str, dict] = {}

    async def get_configuration(self, param_name: str, config_file: str | None=None) -> list[EvidenceItem]:
        results = []
        files_to_search = []
        if config_file:
            files_to_search.append(Path(config_file))
        else:
            for config_path in self.config_paths:
                if config_path.is_dir():
                    files_to_search.extend(config_path.glob('**/*.fcl'))
                    files_to_search.extend(config_path.glob('**/*.fhicl'))
                elif config_path.exists():
                    files_to_search.append(config_path)
        pattern = param_name.replace('*', '.*').replace('?', '.')
        for file_path in files_to_search[:50]:
            try:
                if self.config_paths:
                    validate_path(file_path, self.config_paths)
                content = await asyncio.to_thread(file_path.read_text)
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if re.search(f'\\b{pattern}\\s*:', line, re.IGNORECASE):
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context = '\n'.join(lines[start:end])
                        results.append(make_evidence(evidence_type='configuration', content=f'Configuration found in {file_path.name}:{i + 1}\nContext:\n{context}', source=f'config:{file_path}:{i + 1}', strength='STRONG'))
            except ValueError:
                logger.debug('Path validation failed for %s', file_path)
            except Exception as e:
                logger.debug('Failed to read config file %s: %s', file_path, e)
        if not results:
            results.append(make_evidence(evidence_type='configuration', content=f"No configuration found for parameter '{param_name}'", source='config:not_found', strength='WEAK'))
        return results[:10]

    async def parse_fcl_block(self, block_name: str, config_file: Path) -> dict | None:
        if not config_file.exists():
            return None
        try:
            if self.config_paths:
                validate_path(config_file, self.config_paths)
        except ValueError:
            logger.warning('Path validation failed for %s', config_file)
            return None
        try:
            content = await asyncio.to_thread(config_file.read_text)
            block_pattern = f'{block_name}\\s*:\\s*\\{{'
            match = re.search(block_pattern, content)
            if not match:
                return None
            start = match.end()
            depth = 1
            end = start
            while depth > 0 and end < len(content):
                if content[end] == '{':
                    depth += 1
                elif content[end] == '}':
                    depth -= 1
                end += 1
            block_content = content[start:end - 1]
            result = {}
            for line in block_content.split('\n'):
                line = line.strip()
                if ':' in line and (not line.startswith('#')):
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip().rstrip(',')
                    if key:
                        result[key] = value
            return result
        except Exception as e:
            logger.warning('Failed to parse FCL block %s in %s: %s', block_name, config_file, e)
            return None