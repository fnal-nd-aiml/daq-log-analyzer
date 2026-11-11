import json
from typing import Any

def exact_value(obj: dict[str, Any], field: str, expected: Any) -> tuple[bool, str | None]:
    if field not in obj:
        return (False, f"Field '{field}' not found")
    actual = obj[field]
    if actual != expected:
        return (False, f"Field '{field}': expected {expected!r}, got {actual!r}")
    return (True, None)

def value_in(obj: dict[str, Any], field: str, allowed: list[Any]) -> tuple[bool, str | None]:
    if field not in obj:
        return (False, f"Field '{field}' not found")
    actual = obj[field]
    if actual not in allowed:
        return (False, f"Field '{field}': {actual!r} not in {allowed!r}")
    return (True, None)

def array_length_between(obj: list[Any], min_len: int, max_len: int) -> tuple[bool, str | None]:
    if not isinstance(obj, list):
        return (False, f'Expected array, got {type(obj).__name__}')
    length = len(obj)
    if length < min_len or length > max_len:
        return (False, f'Array length {length} not in [{min_len}, {max_len}]')
    return (True, None)

def all_items_have_keys(obj: list[Any], keys: list[str]) -> tuple[bool, str | None]:
    if not isinstance(obj, list):
        return (False, f'Expected array, got {type(obj).__name__}')
    for i, item in enumerate(obj):
        if not isinstance(item, dict):
            return (False, f'Item [{i}] is not a dict')
        missing = [k for k in keys if k not in item]
        if missing:
            return (False, f'Item [{i}] missing keys: {missing}')
    return (True, None)

def all_items_match(obj: list[Any], field: str, value: Any) -> tuple[bool, str | None]:
    if not isinstance(obj, list):
        return (False, f'Expected array, got {type(obj).__name__}')
    for i, item in enumerate(obj):
        if not isinstance(item, dict):
            return (False, f'Item [{i}] is not a dict')
        if field not in item:
            return (False, f"Item [{i}] missing field '{field}'")
        if item[field] != value:
            return (False, f"Item [{i}] field '{field}': expected {value!r}, got {item[field]!r}")
    return (True, None)

def nested_value(obj: dict[str, Any], path: str, expected: Any) -> tuple[bool, str | None]:
    parts = path.split('.')
    current: Any = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return (False, f"Path '{path}' not found (failed at '{part}')")
    if current != expected:
        return (False, f"Path '{path}': expected {expected!r}, got {current!r}")
    return (True, None)

def is_valid_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, TypeError):
        return False

def parse_json_safely(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

def has_keys(obj: dict[str, Any], keys: list[str]) -> tuple[bool, list[str]]:
    if not isinstance(obj, dict):
        return (False, keys)
    missing = [k for k in keys if k not in obj]
    return (len(missing) == 0, missing)

def is_array(obj: Any) -> bool:
    return isinstance(obj, list)

def has_min_length(obj: Any, min_len: int) -> bool:
    if hasattr(obj, '__len__'):
        return len(obj) >= min_len
    return False

def contains_text(text: str, search: str, case_sensitive: bool=False) -> bool:
    if not case_sensitive:
        return search.lower() in text.lower()
    return search in text

def validate_investigation_result(result: dict[str, Any]) -> tuple[bool, str | None]:
    required_keys = ['investigation_id', 'outcome']
    valid_outcomes = ['CONFIDENT', 'PROBABLE', 'UNCERTAIN', 'CONTRADICTORY', 'INSUFFICIENT']
    all_present, missing = has_keys(result, required_keys)
    if not all_present:
        return (False, f'Missing required keys: {missing}')
    outcome = result.get('outcome')
    if outcome not in valid_outcomes:
        return (False, f"Invalid outcome '{outcome}', expected one of {valid_outcomes}")
    return (True, None)

def validate_feedback_result(result: dict[str, Any]) -> tuple[bool, str | None]:
    if 'error' in result:
        return (True, None)
    required_keys = ['success']
    all_present, missing = has_keys(result, required_keys)
    if not all_present:
        return (False, f'Missing required keys: {missing}')
    return (True, None)

def validate_panel_response(result: dict[str, Any]) -> tuple[bool, str | None]:
    required_keys = ['answer', 'confidence']
    all_present, missing = has_keys(result, required_keys)
    if not all_present:
        return (False, f'Missing required keys: {missing}')
    confidence = result.get('confidence')
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return (False, f'Invalid confidence value: {confidence}')
    return (True, None)

def validate_binder_list(result: Any) -> tuple[bool, str | None]:
    if not is_array(result):
        return (False, 'Expected array of binders')
    if len(result) > 0:
        first = result[0]
        required_keys = ['id']
        all_present, missing = has_keys(first, required_keys)
        if not all_present:
            return (False, f'Binder missing keys: {missing}')
    return (True, None)

def validate_artifact_list(result: Any) -> tuple[bool, str | None]:
    if not is_array(result):
        return (False, 'Expected array of artifacts')
    if len(result) > 0:
        first = result[0]
        required_keys = ['id', 'artifact_type']
        all_present, missing = has_keys(first, required_keys)
        if not all_present:
            return (False, f'Artifact missing keys: {missing}')
    return (True, None)