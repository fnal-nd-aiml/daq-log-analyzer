"""
File: merged_timeline.py
Purpose: Merged timeline parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: artifacts_types, pydantic
Exports: TimelineResponse, MergedTimelineParser, _EXPECTED_FIELDS
Complexity: Medium | Lines: 115
"""

from __future__ import annotations
import json
import logging
from typing import Any
from pydantic import BaseModel, Field
from srcs.workbinder.artifacts_types import MergedTimelineArtifact, MergedTimelineEntry
from .base import BaseParser
from .json_utils import extract_json, fix_json
logger = logging.getLogger(__name__)
_FIELD_ALIASES: dict[str, str] = {'type': 'level', 'severity': 'level', 'msg': 'message', 'summary': 'message', 'details': 'message', 'body': 'message', 'file': 'source_file', 'filename': 'source_file', 'board': 'board_name', 'name': 'component', 'source': 'component', 'category': 'component', 'time': 'timestamp', 'ts': 'timestamp', 'src_location': 'source_location', 'location': 'source_location'}
_EXPECTED_FIELDS = {'timestamp', 'source_file', 'board_name', 'level', 'component', 'message', 'source_location'}

class TimelineResponse(BaseModel):
    entries: list[dict[str, Any]] = Field(default_factory=list, description='Parsed log entries sorted chronologically')
    total_entries: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    total_info: int = 0
    file_count: int = 0
    earliest_timestamp: str = ''
    latest_timestamp: str = ''

class MergedTimelineParser(BaseParser[TimelineResponse, MergedTimelineEntry, MergedTimelineArtifact]):

    def parse_llm_response(self, raw_json: str) -> TimelineResponse:
        try:
            json_str = extract_json(raw_json)
            fixed = fix_json(json_str)
            data = json.loads(fixed)
        except Exception:
            return TimelineResponse()
        entries: list[dict[str, Any]] = []
        if isinstance(data, list):
            entries = [self.normalize_entry(e) for e in data if isinstance(e, dict)]
        elif isinstance(data, dict):
            if 'entries' in data and isinstance(data['entries'], list):
                entries = [self.normalize_entry(e) for e in data['entries'] if isinstance(e, dict)]
            else:
                for val in data.values():
                    if isinstance(val, list) and len(val) > 0:
                        if isinstance(val[0], dict):
                            entries = [self.normalize_entry(e) for e in val if isinstance(e, dict)]
                            break
        else:
            return TimelineResponse()
        if not entries:
            return TimelineResponse()
        total_errors = sum((1 for e in entries if e.get('level', '').lower() in ('error', 'fatal', 'e', 's')))
        total_warnings = sum((1 for e in entries if e.get('level', '').lower() in ('warning', 'w')))
        total_info = sum((1 for e in entries if e.get('level', '').lower() in ('info', 'i')))
        timestamps = [e.get('timestamp', '') for e in entries if e.get('timestamp')]
        earliest = timestamps[0] if timestamps else ''
        latest = timestamps[-1] if timestamps else ''
        files = {e.get('source_file', '') for e in entries if e.get('source_file')}
        return TimelineResponse(entries=entries, total_entries=len(entries), total_errors=total_errors, total_warnings=total_warnings, total_info=total_info, file_count=len(files), earliest_timestamp=earliest, latest_timestamp=latest)

    def to_domain_model(self, item: dict[str, Any], **context: Any) -> MergedTimelineEntry:
        return MergedTimelineEntry(timestamp=item.get('timestamp', ''), source_file=item.get('source_file', ''), board_name=item.get('board_name', ''), level=item.get('level', 'info'), component=item.get('component', ''), message=item.get('message', ''), source_location=item.get('source_location', ''))

    def to_artifact(self, domain_model: list[MergedTimelineEntry], created_by: str, phase: int, **kwargs: Any) -> MergedTimelineArtifact:
        total_errors = sum((1 for e in domain_model if e.level.lower() in ('error', 'fatal', 'e', 's')))
        total_warnings = sum((1 for e in domain_model if e.level.lower() in ('warning', 'w')))
        total_info = sum((1 for e in domain_model if e.level.lower() in ('info', 'i')))
        timestamps = [e.timestamp for e in domain_model if e.timestamp]
        files = {e.source_file for e in domain_model if e.source_file}
        return MergedTimelineArtifact(entries=domain_model, total_entries=len(domain_model), total_errors=total_errors, total_warnings=total_warnings, total_info=total_info, file_count=len(files), earliest_timestamp=timestamps[0] if timestamps else '', latest_timestamp=timestamps[-1] if timestamps else '', created_by=created_by, phase=phase)

    @staticmethod
    def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in entry.items():
            if key in _EXPECTED_FIELDS:
                normalized[key] = value
            elif key in _FIELD_ALIASES:
                target = _FIELD_ALIASES[key]
                if target not in normalized:
                    normalized[target] = value
            else:
                normalized[key] = value
        if 'message' not in normalized:
            header = normalized.pop('message_header', '')
            body = normalized.pop('message_body', '')
            parts = [p for p in (header, body) if p]
            normalized['message'] = '\n'.join(parts) if parts else ''
        else:
            normalized.pop('message_header', None)
            normalized.pop('message_body', None)
        return normalized

    @staticmethod
    def format_timeline(entries: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for entry in entries:
            board = entry.get('board_name', '')
            ts = entry.get('timestamp', '')
            level = entry.get('level', 'info').upper()
            component = entry.get('component', '')
            message = entry.get('message', '')
            src_loc = entry.get('source_location', '')
            board_tag = f'[{board}] ' if board else ''
            comp_tag = f'{component}: ' if component else ''
            loc_tag = f' ({src_loc})' if src_loc else ''
            msg_lines = message.split('\n') if message else ['']
            lines.append(f'{board_tag}{ts} {level} {comp_tag}{msg_lines[0]}{loc_tag}')
            for cont in msg_lines[1:]:
                if cont.strip():
                    lines.append(f'  {cont}')
        return '\n'.join(lines)

    def parse_and_store(self, raw_json: str, created_by: str='Chronicler', phase: int=-1) -> tuple[TimelineResponse | None, list[MergedTimelineEntry]]:
        response = self.parse_llm_response(raw_json)
        if not response.entries:
            return (None, [])
        entries = [self.to_domain_model(e) for e in response.entries]
        return (response, entries)