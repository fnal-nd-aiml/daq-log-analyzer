from typing import Any

def validate_blocks(blocks: list[dict[str, Any]] | None) -> tuple[bool, str]:
    if blocks is None:
        return (True, 'No blocks to validate')
    if not isinstance(blocks, list):
        return (False, f'Blocks must be a list, got {type(blocks).__name__}')
    valid_block_types = {'section', 'divider', 'header', 'context', 'actions', 'image', 'input', 'file', 'rich_text'}
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            return (False, f'Block {i} must be a dict, got {type(block).__name__}')
        if 'type' not in block:
            return (False, f"Block {i} missing 'type' field")
        block_type = block['type']
        if block_type not in valid_block_types:
            return (False, f'Block {i} has invalid type: {block_type}')
        if block_type == 'section':
            if 'text' not in block and 'fields' not in block:
                return (False, f"Section block {i} must have 'text' or 'fields'")
    return (True, 'Blocks are valid')

def validate_has_text(text: str | None, expected_contains: str) -> tuple[bool, str]:
    if text is None:
        return (False, 'Text is None')
    if expected_contains.lower() in text.lower():
        return (True, f"Text contains '{expected_contains}'")
    return (False, f"Text does not contain '{expected_contains}'")

def validate_has_emoji(text: str | None, emoji: str) -> tuple[bool, str]:
    if text is None:
        return (False, 'Text is None')
    if emoji in text:
        return (True, f'Text contains emoji {emoji}')
    return (False, f'Text does not contain emoji {emoji}')

def validate_error_response(text: str | None, blocks: list[dict[str, Any]] | None) -> tuple[bool, str]:
    if text and ':x:' in text:
        return (True, 'Response is error format (has :x: emoji)')
    if blocks:
        for block in blocks:
            if block.get('type') == 'section':
                block_text = block.get('text', {})
                if isinstance(block_text, dict):
                    text_content = block_text.get('text', '')
                    if ':x:' in text_content:
                        return (True, 'Response block contains :x: emoji')
    return (False, 'Response does not appear to be an error format')

def validate_success_response(text: str | None, blocks: list[dict[str, Any]] | None) -> tuple[bool, str]:
    success_indicators = [':white_check_mark:', ':heavy_check_mark:']
    if text:
        for indicator in success_indicators:
            if indicator in text:
                return (True, f'Response is success format (has {indicator})')
    if blocks:
        for block in blocks:
            if block.get('type') == 'section':
                block_text = block.get('text', {})
                if isinstance(block_text, dict):
                    text_content = block_text.get('text', '')
                    for indicator in success_indicators:
                        if indicator in text_content:
                            return (True, f'Response block contains {indicator}')
    return (False, 'Response does not appear to be a success format')

def validate_parsed_command(result: dict[str, Any] | None, expected_fields: dict[str, Any]) -> tuple[bool, str]:
    if result is None:
        return (False, 'Parse result is None')
    for field, expected in expected_fields.items():
        if field not in result:
            return (False, f'Missing expected field: {field}')
        actual = result[field]
        if actual != expected:
            return (False, f"Field '{field}': expected {expected!r}, got {actual!r}")
    return (True, 'All expected fields present and correct')

def validate_help_response(text: str | None) -> tuple[bool, str]:
    if text is None:
        return (False, 'Text is None')
    help_indicators = ['Usage:', 'Commands:', 'help', 'Available']
    for indicator in help_indicators:
        if indicator.lower() in text.lower():
            return (True, f"Response appears to be help text (contains '{indicator}')")
    return (False, 'Response does not appear to be help text')