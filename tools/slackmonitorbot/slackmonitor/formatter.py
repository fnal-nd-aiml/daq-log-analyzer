from datetime import datetime

def format_message(event: dict) -> str:
    ts = event.get('ts', '0')
    try:
        timestamp = datetime.fromtimestamp(float(ts))
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError):
        time_str = 'unknown'
    channel = event.get('channel', 'unknown')
    user = event.get('user', '')
    bot_id = event.get('bot_id', '')
    text = event.get('text', '')
    files = event.get('files', [])
    thread_ts = event.get('thread_ts', '')
    subtype = event.get('subtype', '')
    if bot_id:
        sender = 'BOT'
    elif subtype == 'bot_message':
        sender = 'BOT'
    elif user:
        sender = f'MESSAGE from user:{user}'
    else:
        sender = 'MESSAGE'
    ts_line = f'ts: {ts}'
    if thread_ts and thread_ts != ts:
        ts_line += f' | thread: {thread_ts}'
    lines = ['=' * 80, f'[{time_str}] {sender} in #{channel}', ts_line, '-' * 80]
    if text:
        lines.append(text)
    else:
        lines.append('(no text)')
    if files:
        file_parts = []
        for f in files:
            name = f.get('name', 'unnamed')
            size = f.get('size', 0)
            size_kb = size // 1024 if size else 0
            file_parts.append(f'{name} ({size_kb}KB)')
        file_info = ', '.join(file_parts)
        lines.append('')
        lines.append(f'Files: {file_info}')
    lines.append('=' * 80)
    lines.append('')
    return '\n'.join(lines)