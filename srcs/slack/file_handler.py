"""
File: file_handler.py
Purpose: File handling for Slack attachments.
Category: Utility
Author: artdaq team
Depends: models, base, log_parser
Exports: InvalidFileContentError, validate_downloaded_content, download_slack_file, download_and_save_file, process_log_file, ...
Complexity: Medium | Lines: 84
"""

import logging
import re
import tempfile
from pathlib import Path
import httpx
from srcs.models import Log
from srcs.models.log_parser import extract_error_and_context, parse_log_file
logger = logging.getLogger(__name__)

class InvalidFileContentError(Exception):

    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f'Invalid content for {filename}: {reason}')
_HTML_SIGNATURES = [b'<!doctype html', b'<html', b'<head>', b'<head ', b'<script', b'<meta ', b'<link ', b'<style', b'<!doctype']
_HTML_PATTERN = re.compile(b'<(?:html|head|script|meta|link|style|body|div)\\b', re.IGNORECASE)

def validate_downloaded_content(content: bytes, filename: str) -> bytes:
    if not content:
        return content
    header = content[:1000].lower().lstrip()
    for sig in _HTML_SIGNATURES:
        if sig in header:
            raise InvalidFileContentError(filename, 'Slack returned an HTML page instead of the file content')
    if _HTML_PATTERN.search(content[:1000]):
        raise InvalidFileContentError(filename, 'Slack returned an HTML page instead of the file content')
    return content
_MAX_REDIRECTS = 5

async def download_slack_file(file_url: str, bot_token: str, timeout: float=60.0) -> bytes:
    headers = {'Authorization': f'Bearer {bot_token}'}
    url = file_url
    async with httpx.AsyncClient() as client:
        for _ in range(_MAX_REDIRECTS):
            response = await client.get(url, headers=headers, timeout=timeout, follow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('location')
                if not location:
                    break
                url = location
                logger.debug('Following redirect to %s', url)
                continue
            break
        response.raise_for_status()
        content = response.content
        validate_downloaded_content(content, file_url.rsplit('/', 1)[-1])
        return content

async def download_and_save_file(file_url: str, file_name: str, bot_token: str) -> Path:
    content = await download_slack_file(file_url, bot_token)
    temp_dir = Path(tempfile.gettempdir()) / 'loganalyzer_slack'
    temp_dir.mkdir(exist_ok=True)
    from srcs.models.base import generate_id
    unique_name = f'{generate_id()}_{file_name}'
    file_path = temp_dir / unique_name
    file_path.write_bytes(content)
    return file_path

async def process_log_file(file_url: str, file_name: str, bot_token: str, error_line: int | None=None, context_lines: int=60) -> tuple[Log, list[Log]] | None:
    try:
        file_path = await download_and_save_file(file_url, file_name, bot_token)
        logs = parse_log_file(file_path)
        if not logs:
            logger.warning('No logs found in file: %s', file_name)
            return None
        error, context = extract_error_and_context(logs, error_line, context_lines)
        try:
            file_path.unlink()
        except OSError:
            pass
        return (error, context)
    except InvalidFileContentError:
        raise
    except httpx.HTTPStatusError as e:
        logger.error('Failed to download file %s: %s', file_name, e)
        return None
    except Exception as e:
        logger.error('Failed to process file %s: %s', file_name, e)
        return None

def create_log_from_message(message: str) -> Log:
    from datetime import datetime
    return Log(timestamp=datetime.now(), level='ERROR', component='Unknown', message=message, raw_line=message)