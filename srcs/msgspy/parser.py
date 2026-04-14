"""
File: parser.py
Purpose: Parser for MessageFacility UDP wire-format messages.
Category: Utility
Author: artdaq team
Depends: None
Exports: validate_raw, parse, _PREFIX_RE
Complexity: Low | Lines: 48
"""

import re
from .errors import ParseError
from .models import MFMessage

_PREFIX_RE = re.compile(b"^UDPMFMESSAGE(\\d+)\\|")


def validate_raw(data: bytes) -> bool:
    return b"MF" in data and b"|" in data


def parse(data: bytes) -> MFMessage:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as e:
        raise ParseError(f"Failed to decode datagram: {e}") from e
    prefix_match = _PREFIX_RE.match(data)
    if not prefix_match:
        raise ParseError(f"Missing UDPMFMESSAGE prefix: {text[:60]!r}")
    prefix_pid = int(prefix_match.group(1))
    after_prefix = text[prefix_match.end() - 1 :]
    fields = after_prefix.split("|")
    if len(fields) < 11:
        raise ParseError(f"Expected at least 11 pipe-delimited fields, got {len(fields)}: {text[:80]!r}")
    line_str = fields[9].strip()
    try:
        line_number = int(line_str) if line_str else 0
    except ValueError:
        line_number = 0
    pid_str = fields[5].strip()
    try:
        pid = int(pid_str) if pid_str else prefix_pid
    except ValueError:
        pid = prefix_pid
    message_body = "|".join(fields[10:]) if len(fields) > 10 else ""
    return MFMessage(
        raw=data,
        severity=fields[1].strip(),
        category=fields[2].strip(),
        hostname=fields[3].strip(),
        application=fields[4].strip(),
        pid=pid,
        timestamp=fields[6].strip(),
        module=fields[7].strip(),
        filename=fields[8].strip(),
        line_number=line_number,
        message=message_body.strip(),
    )
