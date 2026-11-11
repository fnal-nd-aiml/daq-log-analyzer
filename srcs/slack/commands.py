"""
File: commands.py
Purpose: Command parsing for Slack messages.
Category: Utility
Author: artdaq team
Depends: None
Exports: ParsedCommand, parse_command, parse_investigate_command, parse_investigate_content, parse_feedback_command, ...
Complexity: Medium | Lines: 126
"""

import re
import shlex
from dataclasses import dataclass, field

@dataclass
class ParsedCommand:
    command: str
    args: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    raw_text: str = ''

def parse_command(text: str, bot_user_id: str | None=None) -> ParsedCommand | None:
    if bot_user_id:
        text = re.sub(f'<@{bot_user_id}>', '', text)
    text = re.sub('<@U[A-Z0-9]+>', '', text).strip()
    if not text:
        return None
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    if not tokens:
        return None
    command = tokens[0].lower()
    args: list[str] = []
    options: dict[str, str] = {}
    for token in tokens[1:]:
        if '=' in token and (not token.startswith('=')) and (not token.endswith('=')):
            key, value = token.split('=', 1)
            options[key.lower()] = value
        else:
            args.append(token)
    return ParsedCommand(command=command, args=args, options=options, raw_text=text)

def parse_investigate_command(cmd: ParsedCommand) -> dict:
    return {'error_line': int(cmd.options['error']) if 'error' in cmd.options else None, 'context_lines': int(cmd.options.get('context', '60'))}

def parse_investigate_content(cmd: ParsedCommand) -> str | None:
    text = cmd.raw_text
    parts = text.split(None, 1)
    if len(parts) < 2:
        return None
    remainder = parts[1]
    tokens = remainder.split()
    content_tokens = [t for t in tokens if not ('=' in t and (not t.startswith('=')) and (not t.endswith('=')))]
    content = ' '.join(content_tokens).strip()
    return content if content else None

def parse_feedback_command(cmd: ParsedCommand) -> dict | None:
    if len(cmd.args) < 2:
        return None
    investigation_id = cmd.args[0]
    feedback_type = cmd.args[1].lower()
    if feedback_type not in ('correct', 'incorrect'):
        return None
    correct = feedback_type == 'correct'
    actual_cause = cmd.args[2] if len(cmd.args) > 2 else None
    return {'investigation_id': investigation_id, 'correct': correct, 'actual_cause': actual_cause}

def parse_list_command(cmd: ParsedCommand) -> dict:
    return {'limit': int(cmd.options.get('limit', '10'))}

def parse_ask_command(cmd: ParsedCommand) -> dict | None:
    if not cmd.args:
        return None
    question = ' '.join(cmd.args)
    return {'question': question}

def parse_config_command(cmd: ParsedCommand) -> dict:
    if not cmd.args:
        return {'setting': None, 'value': None}
    setting = cmd.args[0].lower()
    value = cmd.args[1].lower() if len(cmd.args) > 1 else None
    return {'setting': setting, 'value': value}

def parse_config_llm_provider_command(cmd: ParsedCommand) -> dict:
    if not cmd.args:
        return {'action': 'show'}
    action = cmd.args[0].lower() if cmd.args else 'show'
    return {'action': action}

def parse_workbinder_command(cmd: ParsedCommand) -> dict | None:
    subcommand = cmd.args[0].lower() if cmd.args else 'help'
    result = {'subcommand': subcommand, 'binder_id': None, 'investigation_id': None, 'artifact_type': cmd.options.get('type'), 'phase': int(cmd.options['phase']) if 'phase' in cmd.options else None, 'persona': cmd.options.get('persona'), 'limit': int(cmd.options.get('limit', '50')), 'query': None}
    if not cmd.args:
        return result
    if 'inv' in cmd.options:
        result['investigation_id'] = cmd.options['inv']
    elif len(cmd.args) > 1 and cmd.args[1].startswith('inv='):
        result['investigation_id'] = cmd.args[1].split('=', 1)[1]
    if len(cmd.args) > 1 and (not cmd.args[1].startswith('inv=')):
        if subcommand == 'search':
            result['binder_id'] = cmd.args[1]
            if len(cmd.args) > 2:
                result['query'] = ' '.join(cmd.args[2:])
        else:
            result['binder_id'] = cmd.args[1]
    return result

def parse_message_command(cmd: ParsedCommand) -> dict | None:
    if not cmd.args:
        return None
    message = ' '.join(cmd.args)
    return {'message': message}

def parse_init_command(cmd: ParsedCommand) -> dict:
    skip_source = 'skip-source' in cmd.args or 'skip_source' in cmd.args
    return {'skip_source': skip_source}

def parse_sync_source_command(cmd: ParsedCommand) -> dict:
    status_only = 'status' in cmd.args
    return {'status_only': status_only}
COMMAND_HELP = {'investigate': {'format': '@bot investigate [error=N] [context=N] [inline log content]', 'description': 'Investigate attached log file or inline pasted log content. Optionally specify error line and context.', 'examples': ['@bot investigate', '@bot investigate error=150', '@bot investigate error=150 context=100', '@bot investigate 2024-01-15 10:30:45 ERROR [BR] readData: timeout']}, 'message': {'format': '@bot message "error text"', 'description': 'Investigate an error message directly without a log file.', 'examples': ['@bot message "Connection timeout: no data received"', '@bot message Buffer overflow in processData']}, 'feedback': {'format': '@bot feedback <id> correct|incorrect ["actual cause"]', 'description': 'Submit feedback for a previous investigation.', 'examples': ['@bot feedback abc123 correct', '@bot feedback abc123 incorrect "Buffer overflow in handler"']}, 'list': {'format': '@bot list [limit=N]', 'description': 'List recent investigations.', 'examples': ['@bot list', '@bot list limit=20']}, 'ask': {'format': '@bot ask "question"', 'description': 'Ask the expert panel a question.', 'examples': ['@bot ask "What causes fragment timeouts?"', '@bot ask How do I configure BoardReaders']}, 'config': {'format': '@bot config [setting|llm-provider] [value|show]', 'description': 'View or change bot settings and LLM configuration.', 'examples': ['@bot config', '@bot config verbose on', '@bot config llm-logging off', '@bot config llm-provider']}, 'workbinder': {'format': '@bot workbinder <subcommand> [args]', 'description': 'Inspect workbinder artifacts. Subcommands: list, show, artifacts, artifact, search, history, audit.', 'examples': ['@bot workbinder list', '@bot workbinder show abc123', '@bot workbinder artifacts abc123 type=hypothesis', '@bot workbinder search abc123 "timeout"']}, 'sync-source': {'format': '@bot sync-source [status]', 'description': 'Sync source repositories or show status.', 'examples': ['@bot sync-source', '@bot sync-source status']}, 'init': {'format': '@bot init [skip-source]', 'description': 'Initialize the knowledge base.', 'examples': ['@bot init', '@bot init skip-source']}, 'version': {'format': '@bot version', 'description': 'Show version information.', 'examples': ['@bot version']}, 'help': {'format': '@bot help [command]', 'description': 'Show help information.', 'examples': ['@bot help', '@bot help investigate']}}

def get_help_text(command: str | None=None) -> str:
    if command and command in COMMAND_HELP:
        info = COMMAND_HELP[command]
        lines: list[str] = [f'*{command}*', f"Format: `{info['format']}`", str(info['description']), '', 'Examples:']
        for example in info['examples']:
            lines.append(f'  `{example}`')
        return '\n'.join(lines)
    all_lines: list[str] = ['*Available Commands:*', '']
    for cmd, info in COMMAND_HELP.items():
        all_lines.append(f"*{cmd}* - {info['description']}")
    all_lines.extend(['', 'Use `@bot help <command>` for detailed help on a specific command.'])
    return '\n'.join(all_lines)