"""
File: renderer.py
Purpose: Output renderers for different targets.
Category: Utility
Author: artdaq team
Depends: rich
Exports: ConsoleRenderer, SlackRenderer
Complexity: Medium | Lines: 134
"""

import re
from typing import Any
from rich.console import Console
from rich.markdown import Markdown

class ConsoleRenderer:

    def __init__(self, console: Console | None=None):
        self.console = console or Console()

    def render(self, markdown: str) -> None:
        if not markdown:
            return
        md = Markdown(markdown)
        self.console.print(md)

    def render_lines(self, lines: list[str]) -> None:
        for line in lines:
            if line:
                self.render(line)

class SlackRenderer:
    MAX_BLOCK_TEXT = 3000
    MAX_HEADER_TEXT = 150

    def render(self, markdown: str) -> list[dict[str, Any]]:
        if not markdown:
            return []
        blocks: list[dict[str, Any]] = []
        lines = markdown.split('\n')
        current_section: list[str] = []
        in_code_block = False
        code_lines: list[str] = []
        for line in lines:
            if line.startswith('```'):
                if in_code_block:
                    if current_section:
                        blocks.extend(self._create_text_blocks(current_section))
                        current_section = []
                    blocks.append(self._create_code_block(code_lines))
                    code_lines = []
                    in_code_block = False
                else:
                    if current_section:
                        blocks.extend(self._create_text_blocks(current_section))
                        current_section = []
                    in_code_block = True
                continue
            if in_code_block:
                code_lines.append(line)
                continue
            if line.startswith('# '):
                if current_section:
                    blocks.extend(self._create_text_blocks(current_section))
                    current_section = []
                blocks.append(self._create_header_block(line[2:].strip()))
                continue
            if line.startswith('## '):
                if current_section:
                    blocks.extend(self._create_text_blocks(current_section))
                    current_section = []
                blocks.append(self._create_section_block(f'*{line[3:].strip()}*'))
                continue
            if line.startswith('### '):
                if current_section:
                    blocks.extend(self._create_text_blocks(current_section))
                    current_section = []
                blocks.append(self._create_section_block(f'*{line[4:].strip()}*'))
                continue
            if line.strip() in ('---', '==='):
                if current_section:
                    blocks.extend(self._create_text_blocks(current_section))
                    current_section = []
                blocks.append({'type': 'divider'})
                continue
            current_section.append(self._convert_line_to_mrkdwn(line))
        if in_code_block and code_lines:
            blocks.append(self._create_code_block(code_lines))
        elif current_section:
            blocks.extend(self._create_text_blocks(current_section))
        return blocks

    def _convert_line_to_mrkdwn(self, line: str) -> str:
        line = re.sub('\\*\\*(.+?)\\*\\*', '*\\1*', line)
        line = re.sub('\\[([^\\]]+)\\]\\(([^)]+)\\)', '<\\2|\\1>', line)
        if line.startswith('> '):
            line = line
        return line

    def _create_header_block(self, text: str) -> dict[str, Any]:
        if len(text) > self.MAX_HEADER_TEXT:
            text = text[:self.MAX_HEADER_TEXT - 3] + '...'
        return {'type': 'header', 'text': {'type': 'plain_text', 'text': text}}

    def _create_section_block(self, text: str) -> dict[str, Any]:
        if len(text) > self.MAX_BLOCK_TEXT:
            text = text[:self.MAX_BLOCK_TEXT - 3] + '...'
        return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}

    def _create_code_block(self, lines: list[str]) -> dict[str, Any]:
        code = '\n'.join(lines)
        max_code = self.MAX_BLOCK_TEXT - 10
        if len(code) > max_code:
            code = code[:max_code] + '\n... (truncated)'
        return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'```{code}```'}}

    def _create_text_blocks(self, lines: list[str]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        current_text: list[str] = []
        current_length = 0
        for line in lines:
            line_length = len(line) + 1
            if current_length + line_length > self.MAX_BLOCK_TEXT:
                if current_text:
                    blocks.append(self._create_section_block('\n'.join(current_text)))
                current_text = [line]
                current_length = line_length
            else:
                current_text.append(line)
                current_length += line_length
        if current_text:
            blocks.append(self._create_section_block('\n'.join(current_text)))
        return blocks

    def render_as_text(self, markdown: str) -> str:
        text = markdown
        text = re.sub('```\\w*\\n?', '', text)
        text = re.sub('^#+\\s*', '', text, flags=re.MULTILINE)
        text = re.sub('\\*\\*(.+?)\\*\\*', '\\1', text)
        text = re.sub('\\*(.+?)\\*', '\\1', text)
        text = re.sub('`(.+?)`', '\\1', text)
        text = re.sub('^---$', '', text, flags=re.MULTILINE)
        text = re.sub('\\n{3,}', '\n\n', text)
        return text.strip()