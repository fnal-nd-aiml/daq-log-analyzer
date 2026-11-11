"""
File: log_parser.py
Purpose: Log parsing utilities.
Category: Data
Author: artdaq team
Depends: None
Exports: create_log_from_message, parse_log_content, parse_log_lines, parse_log_file, extract_error_and_context, ...
Complexity: Medium | Lines: 144
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from .logs import Log
logger = logging.getLogger(__name__)
_FALLBACK_LEVEL_PATTERN = re.compile('(?:^|[\\s\\[\\]()/:|,;])(ERROR|WARNING|INFO|DEBUG)(?:[\\s\\[\\]()/:|,;]|$)', re.IGNORECASE)
_FALLBACK_MAX_LINE_LENGTH = 500
_HTML_JS_MARKERS = ('<script', '<div', '<span', '<meta', '<link', '<style', '<body', '<head', '<html', '<!doctype', '<table', '<form', '<input', '<img', 'function(', 'function (', 'window.', 'document.', 'var ', 'const ', 'let ', '=>', '});', 'createElement', 'addEventListener', 'innerHTML', 'querySelector', 'getElementById')
_ARTDAQ_PATTERN = re.compile('(\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{3})?)\\s+(\\w+)\\s+\\[(\\w+)\\]\\s*(?:(\\w+):)?\\s*(.*)')
_SIMPLE_PATTERN = re.compile('\\[?(\\d{4}-\\d{2}-\\d{2}[\\sT]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?)\\]?\\s+(\\w+)[:\\s]+(.+)')
_MSG_FACILITY_PATTERN = re.compile('%MSG-([ewids])\\s+(\\S+?)(?::)?\\s+.*?(\\d{1,2}-\\w{3}-\\d{4}\\s+\\d{2}:\\d{2}:\\d{2})\\s+(\\w+)')
_MSG_LEVEL_MAP = {'e': 'ERROR', 'w': 'WARNING', 'i': 'INFO', 'd': 'DEBUG', 's': 'INFO'}

def create_log_from_message(message: str) -> Log:
    return Log(timestamp=datetime.now(), level='ERROR', component='Unknown', message=message, raw_line=message)

def parse_log_content(content: str, max_lines: int | None=None) -> list[Log]:
    lines = content.splitlines()
    if max_lines is not None and len(lines) > max_lines:
        logger.warning('Log content has %d lines, exceeding max_lines=%d; parsing the first %d lines only', len(lines), max_lines, max_lines)
        lines = lines[:max_lines]
    return parse_log_lines(lines)

def parse_log_lines(lines: list[str]) -> list[Log]:
    logs: list[Log] = []
    i = 0
    while i < len(lines):
        line_num = i + 1
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        msg_log = _parse_msg_facility(line, line_num, lines, i)
        if msg_log is not None:
            log_entry, new_i = msg_log
            logs.append(log_entry)
            i = new_i
            continue
        log = _parse_line(line, line_num)
        if log is not None:
            logs.append(log)
        i += 1
    return logs

def _parse_msg_facility(line: str, line_num: int, lines: list[str], idx: int) -> tuple[Log, int] | None:
    match = _MSG_FACILITY_PATTERN.match(line)
    if not match:
        return None
    level_char, component, timestamp_str, _tz = match.groups()
    level = _MSG_LEVEL_MAP.get(level_char, 'INFO')
    try:
        timestamp = datetime.strptime(timestamp_str, '%d-%b-%Y %H:%M:%S')
    except ValueError:
        timestamp = datetime.now()
    body_lines: list[str] = []
    j = idx + 1
    while j < len(lines):
        body = lines[j].strip()
        if body == '%MSG':
            j += 1
            break
        if body.startswith('%MSG-'):
            break
        if body:
            body_lines.append(body)
        j += 1
    message = ' '.join(body_lines) if body_lines else line
    function = None
    func_match = re.search('(\\w+\\.\\w+:\\d+)', line)
    if func_match:
        function = func_match.group(1)
    return (Log(timestamp=timestamp, level=level, component=component, function=function, message=message, raw_line=line, line=line_num), j)

def parse_log_file(log_file: Path, max_lines: int | None=None) -> list[Log]:
    lines: list[str] = []
    truncated = False
    with open(log_file, encoding='utf-8', errors='replace') as f:
        for line in f:
            lines.append(line.rstrip('\r\n'))
            if max_lines is not None and len(lines) >= max_lines:
                truncated = True
                break
    if truncated:
        logger.warning('Log file %s exceeds max_lines=%d; parsing the first %d lines only', log_file, max_lines, max_lines)
    return parse_log_lines(lines)

def extract_error_and_context(logs: list[Log], error_line: int | None, context_lines: int) -> tuple[Log, list[Log]]:
    if error_line is not None:
        error_idx = None
        for i, log in enumerate(logs):
            if log.line == error_line:
                error_idx = i
                break
        if error_idx is None:
            error_idx = min(error_line - 1, len(logs) - 1)
    else:
        error_idx = next((i for i, log in enumerate(logs) if log.level == 'ERROR'), len(logs) - 1)
    error = logs[error_idx]
    start = max(0, error_idx - context_lines)
    context = logs[start:error_idx]
    return (error, context)

def parse_content_to_error_and_context(content: str, error_line: int | None=None, context_lines: int=60) -> tuple[Log, list[Log]] | None:
    logs = parse_log_content(content)
    if not logs:
        return None
    return extract_error_and_context(logs, error_line, context_lines)

def _parse_line(line: str, line_num: int) -> Log | None:
    match = _ARTDAQ_PATTERN.match(line)
    if match:
        timestamp_str, level, component, function, message = match.groups()
        try:
            if '.' in timestamp_str:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            else:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            timestamp = datetime.now()
        return Log(timestamp=timestamp, level=level.upper(), component=component, function=function, message=message, raw_line=line, line=line_num)
    match = _SIMPLE_PATTERN.match(line)
    if match:
        timestamp_str, level, message = match.groups()
        try:
            timestamp_str = timestamp_str.replace('T', ' ')
            if '.' in timestamp_str:
                timestamp = datetime.strptime(timestamp_str[:23], '%Y-%m-%d %H:%M:%S.%f')
            else:
                timestamp = datetime.strptime(timestamp_str[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            timestamp = datetime.now()
        return Log(timestamp=timestamp, level=level.upper(), component='Unknown', message=message, raw_line=line, line=line_num)
    if len(line) > _FALLBACK_MAX_LINE_LENGTH:
        return None
    line_lower = line.lower()
    for marker in _HTML_JS_MARKERS:
        if marker in line_lower:
            return None
    match = _FALLBACK_LEVEL_PATTERN.search(line)
    if match:
        level = match.group(1).upper()
        return Log(timestamp=datetime.now(), level=level, component='Unknown', message=line, raw_line=line, line=line_num)
    return None