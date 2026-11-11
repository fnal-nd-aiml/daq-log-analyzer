"""
File: formatter.py
Purpose: Slack mrkdwn formatting for investigation results.
Category: Utility
Author: artdaq team
Depends: models, callbacks, question, phase_formatter
Exports: PhaseMetrics, RichPhaseOutput, ThreadState, truncate, format_code_block, ...
Complexity: Medium | Lines: 724
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from srcs.models import InvestigationOutcome, InvestigationResult
from srcs.models.callbacks import PhaseEvent
from srcs.models.question import PanelResponse
from srcs.output.phase_formatter import PhaseFormatter
_phase_formatter = PhaseFormatter()
OUTCOME_EMOJI: dict[InvestigationOutcome | str, str] = {InvestigationOutcome.CONFIDENT: ':white_check_mark:', InvestigationOutcome.PROBABLE: ':large_yellow_circle:', InvestigationOutcome.UNCERTAIN: ':warning:', InvestigationOutcome.INSUFFICIENT: ':x:', InvestigationOutcome.CONTRADICTORY: ':no_entry:'}
STATUS_EMOJI = {'pending': ':white_circle:', 'in_progress': ':large_blue_circle:', 'complete': ':white_check_mark:', 'warning': ':warning:', 'error': ':x:'}
PERSONA_CONFIG: dict[str, dict[str, Any]] = {'Chronicler': {'emoji': ':scroll:', 'label': 'Multi-File Log Triage', 'metrics': ['file_count', 'merged_events']}, 'Archivist': {'emoji': ':books:', 'label': 'Prior Knowledge', 'metrics': ['similar_cases', 'source_locations', 'code_hints']}, 'Theorist': {'emoji': ':bulb:', 'label': 'Hypothesis Generation', 'metrics': ['hypothesis_count', 'top_confidence']}, 'Detective': {'emoji': ':mag_right:', 'label': 'Evidence Seeking', 'metrics': ['evidence_strong', 'evidence_moderate', 'rounds']}, 'Logician': {'emoji': ':link:', 'label': 'Causal Chain', 'metrics': ['chain_steps', 'evidence_cited']}, 'Skeptic': {'emoji': ':smiling_imp:', 'label': 'Adversarial Review', 'metrics': ['challenges_high', 'challenges_medium']}, 'Judge': {'emoji': ':scales:', 'label': 'Assessment', 'metrics': ['outcome']}, 'Synthesizer': {'emoji': ':clipboard:', 'label': 'Final Report', 'metrics': ['confidence', 'steps_count']}, 'Learner': {'emoji': ':brain:', 'label': 'Pattern Learning', 'metrics': ['patterns_learned']}, 'Reviewer': {'emoji': ':clipboard:', 'label': 'User Feedback', 'metrics': ['feedback_status']}}
PHASE_REFERENCES: dict[int, list[int]] = {1: [0], 2: [1], 3: [2], 4: [3, 1], 5: [4, 2], 6: [5, 1]}
PHASE_TO_PERSONA: dict[int, str] = {-1: 'Chronicler', 0: 'Archivist', 1: 'Theorist', 2: 'Detective', 3: 'Logician', 4: 'Skeptic', 5: 'Judge', 6: 'Synthesizer', 7: 'Learner', 8: 'Reviewer'}

@dataclass
class PhaseMetrics:
    count: int = 0
    strong: int = 0
    moderate: int = 0
    weak: int = 0
    top_score: float = 0.0
    rounds: int = 0
    current_round: int = 0
    duration_ms: int = 0
    challenges_high: int = 0
    challenges_medium: int = 0
    challenges_low: int = 0

@dataclass
class RichPhaseOutput:
    phase: int
    persona: str
    status: str
    main_blocks: list[dict[str, Any]]
    thread_blocks: list[dict[str, Any]] | None = None
    mentions: list[str] = field(default_factory=list)
    metrics: PhaseMetrics = field(default_factory=PhaseMetrics)
    summary_text: str = ''

@dataclass
class ThreadState:
    root_ts: str | None = None
    phase_ts: dict[int, str] = field(default_factory=dict)
    evidence_counts: dict[str, int] = field(default_factory=dict)
    hypothesis_scores: dict[str, float] = field(default_factory=dict)
    start_time_ms: int = 0
OUTCOME_DESCRIPTIONS = {InvestigationOutcome.CONFIDENT: 'High confidence in root cause', InvestigationOutcome.PROBABLE: 'Likely root cause identified', InvestigationOutcome.UNCERTAIN: 'Multiple hypotheses remain viable', InvestigationOutcome.INSUFFICIENT: 'Insufficient evidence for conclusion', InvestigationOutcome.CONTRADICTORY: 'Evidence contradicts itself'}

def truncate(text: str, max_len: int=200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'

def format_code_block(code: str, max_lines: int=15) -> str:
    lines = code.split('\n')
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'... ({len(lines) - max_lines} more lines)']
    return '```\n' + '\n'.join(lines) + '\n```'

def _text_to_blocks(text: str, prefix: str='', max_len: int=2900) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    full_text = f'{prefix}\n\n{text}' if prefix else text
    while full_text:
        if len(full_text) <= max_len:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': full_text}})
            break
        split_at = full_text.rfind('\n', 0, max_len)
        if split_at < max_len // 2:
            split_at = full_text.rfind(' ', 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': full_text[:split_at]}})
        full_text = full_text[split_at:].lstrip()
    return blocks

def format_investigation_result(result: InvestigationResult, verbose: bool=False) -> list[dict]:
    blocks: list[dict] = []
    emoji = OUTCOME_EMOJI.get(result.outcome, ':question:')
    description = OUTCOME_DESCRIPTIONS.get(result.outcome, '')
    blocks.append({'type': 'header', 'text': {'type': 'plain_text', 'text': f'{emoji} {result.outcome.value}'}})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_{description}_'}})
    blocks.append({'type': 'divider'})
    if result.outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
        blocks.extend(_format_confident_result(result, verbose))
    elif result.outcome == InvestigationOutcome.UNCERTAIN:
        blocks.extend(_format_uncertain_result(result))
    elif result.outcome == InvestigationOutcome.INSUFFICIENT:
        blocks.extend(_format_insufficient_result(result))
    elif result.outcome == InvestigationOutcome.CONTRADICTORY:
        blocks.extend(_format_contradictory_result(result))
    blocks.append({'type': 'divider'})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'Completed in {result.duration_seconds:.1f}s | Investigation ID: `{result.investigation_id}`'}]})
    return blocks

def _format_confident_result(result: InvestigationResult, verbose: bool) -> list[dict]:
    blocks: list[dict] = []
    if result.executive_summary:
        blocks.extend(_text_to_blocks(result.executive_summary, prefix=':memo: *Executive Summary*'))
        blocks.append({'type': 'divider'})
    if result.root_cause:
        rc = result.root_cause
        confidence = rc.confidence
        blocks.extend(_text_to_blocks(rc.root_cause, prefix='*Root Cause:*'))
        conf_bar = _confidence_bar(confidence.calibrated)
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*Confidence:* {confidence.calibrated:.0%} {conf_bar}\n_(raw: {confidence.raw:.0%})_'}})
        if rc.code_location:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*Error Location:* `{rc.code_location}`'}})
        if rc.code_snippet:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Code Context:*\n' + format_code_block(rc.code_snippet)}})
        if rc.sub_causes:
            sub_cause_text = '*Ranked Causes:*\n'
            for i, sc in enumerate(rc.sub_causes[:5], 1):
                sub_cause_text += f'{i}. {sc.description} ({sc.probability:.0%})\n'
            blocks.extend(_text_to_blocks(sub_cause_text))
        if rc.debugging_steps:
            steps_text = '*Debugging Steps:*\n'
            for i, step in enumerate(rc.debugging_steps, 1):
                steps_text += f'{i}. {step}\n'
            blocks.extend(_text_to_blocks(steps_text))
        if verbose and rc.key_files:
            files_text = '*Key Files:*\n'
            for kf in rc.key_files[:5]:
                files_text += f'• `{kf.file_path}` - {kf.purpose}\n'
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': files_text}})
        if rc.caveats:
            caveats_text = '*Caveats:*\n'
            for caveat in rc.caveats:
                caveats_text += f':warning: {caveat}\n'
            blocks.extend(_text_to_blocks(caveats_text))
    if result.recommendations:
        rec_text = '*Recommendations:*\n'
        for rec in result.recommendations:
            rec_text += f'• {rec}\n'
        blocks.extend(_text_to_blocks(rec_text))
    if verbose and result.alternatives:
        alt_text = '*Alternative Hypotheses:*\n'
        for alt in result.alternatives[:3]:
            alt_text += f'• {alt.description} ({alt.score:.0%})\n'
        blocks.extend(_text_to_blocks(alt_text))
    return blocks

def _format_uncertain_result(result: InvestigationResult) -> list[dict]:
    blocks: list[dict] = []
    if result.executive_summary:
        blocks.extend(_text_to_blocks(result.executive_summary, prefix=':memo: *Executive Summary*'))
        blocks.append({'type': 'divider'})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_Multiple hypotheses remain viable. More evidence is needed._'}})
    if result.viable_hypotheses:
        hyp_text = '*Viable Hypotheses:*\n'
        for h in result.viable_hypotheses:
            hyp_text += f'• {h.description} ({h.score:.0%})\n'
        blocks.extend(_text_to_blocks(hyp_text))
    if result.discrimination_needed:
        disc_text = '*To Discriminate:*\n'
        for d in result.discrimination_needed:
            disc_text += f'• {d}\n'
        blocks.extend(_text_to_blocks(disc_text))
    return blocks

def _format_insufficient_result(result: InvestigationResult) -> list[dict]:
    blocks: list[dict] = []
    if result.executive_summary:
        blocks.extend(_text_to_blocks(result.executive_summary, prefix=':memo: *Executive Summary*'))
        blocks.append({'type': 'divider'})
    reason = result.insufficient_reason or 'Insufficient evidence to reach conclusion'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_{reason}_'}})
    if result.missing_evidence:
        missing_text = '*Missing Evidence:*\n'
        for m in result.missing_evidence:
            missing_text += f'• {m}\n'
        blocks.extend(_text_to_blocks(missing_text))
    if result.viable_hypotheses:
        guess_text = '*Best Guesses (unconfirmed):*\n'
        for h in result.viable_hypotheses[:3]:
            guess_text += f'• {h.description} ({h.score:.0%})\n'
        blocks.extend(_text_to_blocks(guess_text))
    return blocks

def _format_contradictory_result(result: InvestigationResult) -> list[dict]:
    blocks: list[dict] = []
    if result.executive_summary:
        blocks.extend(_text_to_blocks(result.executive_summary, prefix=':memo: *Executive Summary*'))
        blocks.append({'type': 'divider'})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_Evidence contradicts itself - multiple incompatible explanations found._'}})
    if result.insufficient_reason:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_{result.insufficient_reason}_'}})
    if result.viable_hypotheses:
        conflict_text = '*Conflicting Hypotheses:*\n'
        for h in result.viable_hypotheses:
            conflict_text += f'• {h.description} ({h.score:.0%})\n'
        blocks.extend(_text_to_blocks(conflict_text))
    return blocks

def _confidence_bar(confidence: float, width: int=10) -> str:
    filled = int(confidence * width)
    empty = width - filled
    return '[' + '=' * filled + '-' * empty + ']'

def format_investigation_list(investigations: list, limit: int=10) -> list[dict]:
    blocks: list[dict] = []
    blocks.append({'type': 'header', 'text': {'type': 'plain_text', 'text': f'Recent Investigations ({len(investigations)})'}})
    if not investigations:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_No investigations found_'}})
        return blocks
    text_lines = []
    for inv in investigations[:limit]:
        outcome = inv.get('outcome', None) if isinstance(inv, dict) else inv.outcome
        inv_id = inv.get('investigation_id', inv.get('id', '?')) if isinstance(inv, dict) else inv.id
        emoji = OUTCOME_EMOJI.get(outcome, ':question:') if outcome else ':question:'
        if isinstance(inv, dict):
            msg = truncate(str(inv.get('root_cause') or inv.get('message') or '?'), 50)
        else:
            msg = truncate(inv.trigger_error.message, 50)
        text_lines.append(f'{emoji} `{inv_id}` - {msg}')
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(text_lines)}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': 'Use `@bot feedback <ID> correct/incorrect` to provide feedback'}]})
    return blocks

def format_phase_event(event: PhaseEvent) -> str | None:
    return _phase_formatter.format_event(event)

def format_panel_response(response: PanelResponse) -> list[dict]:
    blocks: list[dict] = []
    if response.confidence >= 0.7:
        conf_emoji = ':white_check_mark:'
        conf_text = 'High confidence'
    elif response.confidence >= 0.5:
        conf_emoji = ':large_yellow_circle:'
        conf_text = 'Moderate confidence'
    else:
        conf_emoji = ':warning:'
        conf_text = 'Low confidence'
    blocks.append({'type': 'header', 'text': {'type': 'plain_text', 'text': f'{conf_emoji} Answer ({conf_text}: {response.confidence:.0%})'}})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': truncate(response.answer, 2900)}})
    if response.key_points:
        points_text = '*Key Points:*\n'
        for point in response.key_points:
            points_text += f'• {truncate(point, 100)}\n'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': points_text}})
    if response.caveats:
        caveats_text = '*Caveats:*\n'
        for caveat in response.caveats:
            caveats_text += f':warning: {truncate(caveat, 100)}\n'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': caveats_text}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'Question ID: `{response.question_id}`'}]})
    return blocks

def format_error(error_message: str) -> list[dict]:
    return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':x: *Error:* {error_message}'}}]

def format_success(message: str) -> list[dict]:
    return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':white_check_mark: {message}'}}]

def format_reviewer_feedback_blocks(investigation_id: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': ':clipboard: *REVIEWER* • Was this diagnosis correct?\n_Your feedback helps improve future investigations._'}})
    blocks.append({'type': 'actions', 'block_id': f'reviewer_feedback_{investigation_id}', 'elements': [{'type': 'button', 'text': {'type': 'plain_text', 'text': 'Correct', 'emoji': True}, 'action_id': 'reviewer_correct', 'style': 'primary', 'value': investigation_id}, {'type': 'button', 'text': {'type': 'plain_text', 'text': 'Incorrect', 'emoji': True}, 'action_id': 'reviewer_incorrect', 'style': 'danger', 'value': investigation_id}, {'type': 'button', 'text': {'type': 'plain_text', 'text': 'Skip', 'emoji': True}, 'action_id': 'reviewer_skip', 'value': investigation_id}]})
    return blocks

def format_correction_modal(investigation_id: str) -> dict[str, Any]:
    return {'type': 'modal', 'callback_id': 'reviewer_correction_modal', 'private_metadata': investigation_id, 'title': {'type': 'plain_text', 'text': 'Correction Details'}, 'submit': {'type': 'plain_text', 'text': 'Submit'}, 'close': {'type': 'plain_text', 'text': 'Cancel'}, 'blocks': [{'type': 'input', 'block_id': 'corrected_root_cause', 'label': {'type': 'plain_text', 'text': 'Corrected Root Cause'}, 'element': {'type': 'plain_text_input', 'action_id': 'root_cause_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'What was the actual root cause?'}}}, {'type': 'input', 'block_id': 'corrected_summary', 'optional': True, 'label': {'type': 'plain_text', 'text': 'Corrected Executive Summary'}, 'element': {'type': 'plain_text_input', 'action_id': 'summary_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'Optional: corrected summary'}}}]}

def format_feedback_details_modal(investigation_id: str, was_correct: bool) -> dict[str, Any]:
    verdict = 'correct' if was_correct else 'incorrect'
    return {'type': 'modal', 'callback_id': 'feedback_details_modal', 'private_metadata': f'{investigation_id}:{verdict}', 'title': {'type': 'plain_text', 'text': 'Feedback Details'}, 'submit': {'type': 'plain_text', 'text': 'Submit'}, 'close': {'type': 'plain_text', 'text': 'Cancel'}, 'blocks': [{'type': 'input', 'block_id': 'what_was_helpful', 'optional': True, 'label': {'type': 'plain_text', 'text': 'What was helpful?'}, 'element': {'type': 'plain_text_input', 'action_id': 'helpful_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'What parts of the diagnosis were useful?'}}}, {'type': 'input', 'block_id': 'what_was_wrong', 'optional': True, 'label': {'type': 'plain_text', 'text': 'What was wrong?'}, 'element': {'type': 'plain_text_input', 'action_id': 'wrong_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'What was inaccurate or misleading?'}}}, {'type': 'input', 'block_id': 'suggestions', 'optional': True, 'label': {'type': 'plain_text', 'text': 'Suggestions'}, 'element': {'type': 'plain_text_input', 'action_id': 'suggestions_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'How could the investigation be improved?'}}}, {'type': 'input', 'block_id': 'additional_notes', 'optional': True, 'label': {'type': 'plain_text', 'text': 'Additional Notes'}, 'element': {'type': 'plain_text_input', 'action_id': 'notes_input', 'multiline': True, 'placeholder': {'type': 'plain_text', 'text': 'Any other context or observations'}}}]}

def format_investigation_header(error_message: str, error_location: str | None=None, error_function: str | None=None, start_time: str | None=None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'header', 'text': {'type': 'plain_text', 'text': ':microscope: INVESTIGATION STARTED', 'emoji': True}})
    error_text = f':rotating_light: *{truncate(error_message, 200)}*'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': error_text}})
    if error_location or error_function:
        location_parts = []
        if error_location:
            location_parts.append(f'`{error_location}`')
        if error_function:
            location_parts.append(f'`{error_function}()`')
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(location_parts)}})
    context_parts = []
    if start_time:
        context_parts.append(f':clock1: Started {start_time}')
    context_parts.append(':brain: 7-phase analysis')
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': ' • '.join(context_parts)}]})
    return blocks

def format_phase_card(phase: int, status: str, summary_text: str, metrics: PhaseMetrics | None=None, mentions: list[str] | None=None, thread_reply_count: int=0, investigation_id: str | None=None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    persona_name = PHASE_TO_PERSONA.get(phase, 'Unknown')
    config = PERSONA_CONFIG.get(persona_name, {'emoji': ':question:', 'label': 'Unknown'})
    status_emoji = STATUS_EMOJI.get(status, ':white_circle:')
    mention_text = ''
    if mentions:
        mention_refs = [f'`{m}`' for m in mentions]
        mention_text = f"   {' '.join(mention_refs)}"
    header_text = f"{config['emoji']} *{persona_name.upper()}* • {config['label']}{mention_text} {status_emoji}"
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': header_text}})
    if summary_text:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'"{truncate(summary_text, 500)}"'}})
    if metrics:
        metrics_blocks = _format_phase_metrics(phase, metrics, status)
        blocks.extend(metrics_blocks)
    context_parts = []
    if investigation_id:
        context_parts.append(f':id: `{investigation_id}`')
    if thread_reply_count > 0:
        context_parts.append(f':thread: _{thread_reply_count} replies_')
    if metrics and metrics.duration_ms > 0:
        duration_s = metrics.duration_ms / 1000
        context_parts.append(f':stopwatch: {duration_s:.1f}s')
    if context_parts:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': ' • '.join(context_parts)}]})
    return blocks

def _format_phase_metrics(phase: int, metrics: PhaseMetrics, status: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if phase == 0:
        fields = []
        if metrics.count > 0:
            fields.append({'type': 'mrkdwn', 'text': f':card_file_box: *{metrics.count}* similar cases'})
        if metrics.strong > 0:
            fields.append({'type': 'mrkdwn', 'text': f':mag: *{metrics.strong}* source locations'})
        if metrics.moderate > 0:
            fields.append({'type': 'mrkdwn', 'text': f':link: *{metrics.moderate}* patterns'})
        if fields:
            blocks.append({'type': 'section', 'fields': fields[:3]})
    elif phase == 1:
        if metrics.count > 0:
            text = f':bar_chart: Generated *{metrics.count}* hypotheses'
            if metrics.top_score > 0:
                text += f' • Top confidence: `{metrics.top_score:.0%}`'
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    elif phase == 2:
        if status == 'in_progress' and metrics.rounds > 0:
            progress = metrics.current_round / metrics.rounds if metrics.rounds > 0 else 0
            filled = int(progress * 10)
            bar = '█' * filled + '░' * (10 - filled)
            text = f':arrows_counterclockwise: *Round {metrics.current_round} of {metrics.rounds}*\n{bar} {progress:.0%}'
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
        elif status == 'complete':
            lines = [':bar_chart: *Evidence Summary*']
            if metrics.strong > 0:
                lines.append(f":large_green_circle: Strong: {'█' * min(metrics.strong, 12)} {metrics.strong}")
            if metrics.moderate > 0:
                lines.append(f":large_yellow_circle: Moderate: {'█' * min(metrics.moderate, 12)} {metrics.moderate}")
            if metrics.weak > 0:
                lines.append(f":red_circle: Weak: {'█' * min(metrics.weak, 12)} {metrics.weak}")
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(lines)}})
    elif phase == 3:
        if metrics.count > 0:
            text = f':chains: Built *{metrics.count}* causal chains'
            if metrics.strong > 0:
                text += f' with *{metrics.strong}* evidence citations'
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    elif phase == 4:
        challenges = []
        if metrics.challenges_high > 0:
            challenges.append(f':red_circle: {metrics.challenges_high} high')
        if metrics.challenges_medium > 0:
            challenges.append(f':large_yellow_circle: {metrics.challenges_medium} medium')
        if metrics.challenges_low > 0:
            challenges.append(f':large_green_circle: {metrics.challenges_low} low')
        if challenges:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f":point_right: Challenges: {' • '.join(challenges)}"}})
    elif phase == 5:
        if metrics.top_score > 0:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':gavel: Verdict confidence: `{metrics.top_score:.0%}`'}})
    return blocks

def format_hypothesis_list(hypotheses: list[dict[str, Any]], max_display: int=3) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    medals = [':first_place_medal:', ':second_place_medal:', ':third_place_medal:']
    for i, hyp in enumerate(hypotheses[:max_display]):
        medal = medals[i] if i < len(medals) else f':keycap_{i + 1}:'
        desc = truncate(hyp.get('description', 'Unknown'), 80)
        score = hyp.get('score', hyp.get('prior', 0))
        text = f'{medal} *{desc}* `{score:.0%}`'
        if hyp.get('source'):
            text += f"\n> Source: {hyp['source']}"
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if len(hypotheses) > max_display:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_+{len(hypotheses) - max_display} more hypotheses in thread_'}]})
    return blocks

def format_evidence_summary(strong: int, moderate: int, weak: int, top_hypothesis: str | None=None, old_score: float | None=None, new_score: float | None=None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = [':bar_chart: *Evidence Summary*']
    if strong > 0:
        lines.append(f":large_green_circle: Strong    {'█' * min(strong, 12):12} {strong}")
    if moderate > 0:
        lines.append(f":large_yellow_circle: Moderate {'█' * min(moderate, 12):12} {moderate}")
    if weak > 0:
        lines.append(f":red_circle: Weak      {'█' * min(weak, 12):12} {weak}")
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(lines)}})
    if top_hypothesis and old_score is not None and (new_score is not None):
        direction = ':arrow_upper_right:' if new_score > old_score else ':arrow_lower_right:'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':bulb: *Top Hypothesis Update*\n"{truncate(top_hypothesis, 60)}" `{old_score:.0%}` → `{new_score:.0%}` {direction}'}})
    return blocks

def format_final_result_blocks(result: InvestigationResult, investigation_id: str | None=None, duration_seconds: float | None=None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    emoji = OUTCOME_EMOJI.get(result.outcome, ':question:')
    description = OUTCOME_DESCRIPTIONS.get(result.outcome, '')
    blocks.append({'type': 'header', 'text': {'type': 'plain_text', 'text': f'{emoji} INVESTIGATION COMPLETE', 'emoji': True}})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{result.outcome.value}*\n_{description}_'}})
    blocks.append({'type': 'divider'})
    if result.outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
        blocks.extend(_format_confident_result_rich(result))
    elif result.outcome == InvestigationOutcome.UNCERTAIN:
        blocks.extend(_format_uncertain_result(result))
    elif result.outcome == InvestigationOutcome.INSUFFICIENT:
        blocks.extend(_format_insufficient_result(result))
    elif result.outcome == InvestigationOutcome.CONTRADICTORY:
        blocks.extend(_format_contradictory_result(result))
    blocks.append({'type': 'divider'})
    footer_parts = []
    if duration_seconds is not None:
        footer_parts.append(f':stopwatch: {duration_seconds:.1f}s')
    if investigation_id:
        footer_parts.append(f':id: `{investigation_id}`')
    footer_parts.append(':brain: 7 phases')
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': ' • '.join(footer_parts)}]})
    return blocks

def _format_confident_result_rich(result: InvestigationResult) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if result.executive_summary:
        blocks.extend(_text_to_blocks(result.executive_summary, prefix=':memo: *EXECUTIVE SUMMARY*\n'))
        blocks.append({'type': 'divider'})
    if result.root_cause:
        rc = result.root_cause
        confidence = rc.confidence
        blocks.extend(_text_to_blocks(rc.root_cause, prefix=':dart: *ROOT CAUSE*\n\n'))
        if rc.code_location:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':round_pushpin: *Error Location:* `{rc.code_location}`'}})
        if rc.code_snippet:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': ':page_facing_up: *Code Context:*\n' + format_code_block(rc.code_snippet, max_lines=25)}})
        conf_pct = int(confidence.calibrated * 100)
        filled = int(confidence.calibrated * 20)
        bar = '█' * filled + '░' * (20 - filled)
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':chart_with_upwards_trend: *CONFIDENCE*\n\nCalibrated: *{conf_pct}%*  {bar}\nRaw: {confidence.raw:.0%} _(calibration applied)_'}})
        if rc.sub_causes:
            sub_cause_text = ':bar_chart: *RANKED CAUSES*\n\n'
            for i, sc in enumerate(rc.sub_causes[:5], 1):
                sub_cause_text += f' {i}. {sc.description} ({sc.probability:.0%})\n'
            blocks.extend(_text_to_blocks(sub_cause_text))
        if rc.debugging_steps:
            steps_text = ':clipboard: *DEBUGGING STEPS*\n\n'
            for i, step in enumerate(rc.debugging_steps, 1):
                steps_text += f' {i}. {step}\n'
            blocks.extend(_text_to_blocks(steps_text))
        if rc.key_files:
            files_text = ':file_folder: *KEY FILES*\n\n'
            for kf in rc.key_files[:5]:
                files_text += f' • `{kf.file_path}` - {kf.purpose}\n'
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': files_text}})
        if rc.caveats:
            caveats_text = ':warning: *CAVEATS*\n\n'
            for caveat in rc.caveats:
                caveats_text += f' • {caveat}\n'
            blocks.extend(_text_to_blocks(caveats_text))
    if result.recommendations:
        rec_text = ':bulb: *RECOMMENDATIONS*\n\n'
        for rec in result.recommendations:
            rec_text += f' • {rec}\n'
        blocks.extend(_text_to_blocks(rec_text))
    return blocks

def format_thread_evidence(evidence_rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': ':mag_right: *DETECTIVE* • Evidence Details'}})
    blocks.append({'type': 'divider'})
    for i, round_data in enumerate(evidence_rounds, 1):
        round_text = f":keycap_{i}: *Round {i} - {round_data.get('title', 'Analysis')}*\n"
        round_text += '''ââââââââââââââââââââââââââââââââââââââââââââââââ
'''
        round_text += f"│ :dart: Target: `{round_data.get('target', 'Unknown')}`\n"
        round_text += f"│ :mag: Query: {round_data.get('query', 'Unknown')}\n"
        round_text += '''ââââââââââââââââââââââââââââââââââââââââââââââââ
'''
        round_text += '│ :bulb: *Finding*\n'
        round_text += f"│ {truncate(round_data.get('finding', ''), 200)}\n"
        supports = round_data.get('supports', [])
        refutes = round_data.get('refutes', [])
        if supports:
            round_text += f"│\n│ :link: *Supports*: {', '.join(supports)} :arrow_upper_right:\n"
        if refutes:
            round_text += f"│ :x: *Refutes*: {', '.join(refutes)}\n"
        round_text += '└───────────────────────────────────────────────'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': round_text}})
    return blocks

def format_thread_hypotheses(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': ':bulb: *THEORIST* • All Hypotheses'}})
    blocks.append({'type': 'divider'})
    medals = [':first_place_medal:', ':second_place_medal:', ':third_place_medal:']
    for i, hyp in enumerate(hypotheses):
        medal = medals[i] if i < len(medals) else f':keycap_{i + 1}:'
        desc = hyp.get('description', 'Unknown')
        score = hyp.get('score', hyp.get('prior', 0))
        label = hyp.get('label', '')
        text = f'{medal} *#{i + 1} {truncate(desc, 60)}* — `{score:.0%}`'
        if label:
            text += f' :label: {label}'
        text += f'\n> {truncate(desc, 150)}\n'
        text += '''ââââââââââââââââââââââââââââââââââââââââââââââââ
'''
        confirm = hyp.get('confirm_if', '')
        refute = hyp.get('refute_if', '')
        if confirm:
            text += f'│ :white_check_mark: *Confirm if:* {truncate(confirm, 80)}\n'
        if refute:
            text += f'│ :x: *Refute if:* {truncate(refute, 80)}\n'
        text += '└───────────────────────────────────────────────'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    return blocks

def format_challenge_card(challenges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for challenge in challenges:
        severity = challenge.get('severity', 'MEDIUM')
        desc = challenge.get('description', '')
        severity_indicator = {'HIGH': ':red_circle:', 'MEDIUM': ':large_yellow_circle:', 'LOW': ':large_green_circle:'}.get(severity, ':white_circle:')
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':point_right: *Challenge* ({severity} severity) {severity_indicator}\n> {truncate(desc, 300)}'}})
    return blocks

def get_persona_references(phase: int) -> list[str]:
    ref_phases = PHASE_REFERENCES.get(phase, [])
    return [PHASE_TO_PERSONA[p] for p in ref_phases if p in PHASE_TO_PERSONA]

def format_similar_case_thread(case: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    case_id = case.get('investigation_id') or case.get('id') or 'unknown'
    error_msg = truncate(case.get('error_message') or case.get('root_cause') or 'No details', 200)
    outcome = case.get('outcome') or 'unknown'
    similarity = case.get('similarity_score') or case.get('similarity') or 0
    outcome_emoji = OUTCOME_EMOJI.get(outcome, ':question:')
    text = f':card_file_box: *Similar Case* `{case_id}`\n'
    text += f'{outcome_emoji} Outcome: {outcome} • Similarity: `{similarity:.0%}`\n'
    text += f'> {error_msg}'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    root_cause = case.get('root_cause')
    if root_cause:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':dart: *Root Cause:* {truncate(root_cause, 300)}'}})
    return blocks

def format_source_location_thread(loc: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    file_path = loc.get('file_path') or loc.get('file', 'unknown')
    line = loc.get('line_number') or loc.get('line')
    function = loc.get('function_name') or loc.get('function', '')
    snippet = loc.get('snippet', '')
    location_str = f'`{file_path}'
    if line:
        location_str += f':{line}'
    location_str += '`'
    text = f':mag: *Source Location*\n{location_str}'
    if function:
        text += f'\n:memo: Function: `{function}()`'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if snippet:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': format_code_block(snippet, max_lines=10)}})
    return blocks

def format_pattern_thread(pattern: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    name = pattern.get('name', 'Unknown Pattern')
    description = truncate(pattern.get('description', ''), 300)
    confidence = pattern.get('confidence', 0)
    accuracy = pattern.get('accuracy', 0)
    seen_count = pattern.get('seen_count', 0)
    text = f':link: *Pattern:* {name}\n'
    if description:
        text += f'> {description}\n'
    text += f':bar_chart: Confidence: `{confidence:.0%}` • '
    text += f'Accuracy: `{accuracy:.0%}` • Seen: {seen_count} times'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    root_cause = pattern.get('root_cause')
    if root_cause:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':bulb: *Suggested Cause:* {truncate(root_cause, 200)}'}})
    return blocks

def format_hypothesis_thread(hyp: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    description = hyp.get('description', 'Unknown hypothesis')
    prior = hyp.get('prior', hyp.get('score', 0))
    source = hyp.get('source', '')
    tier = hyp.get('tier', '')
    text = f':bulb: *Hypothesis* — `{prior:.0%}`'
    if tier:
        text += f' :label: {tier}'
    text += f'\n> {truncate(description, 400)}'
    if source:
        text += f'\n:card_index: Source: _{source}_'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    confirm_if = hyp.get('confirm_if', '')
    refute_if = hyp.get('refute_if', '')
    if confirm_if or refute_if:
        criteria_text = ''
        if confirm_if:
            criteria_text += f':white_check_mark: *Confirm if:* {truncate(confirm_if, 150)}\n'
        if refute_if:
            criteria_text += f':x: *Refute if:* {truncate(refute_if, 150)}'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': criteria_text}})
    return blocks

def format_evidence_round_thread(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    description = truncate(evidence.get('description', 'Unknown evidence'), 400)
    strength = evidence.get('strength', 'WEAK')
    source = evidence.get('source', '')
    hypothesis = evidence.get('hypothesis', '')
    strength_emoji = {'STRONG': ':large_green_circle:', 'MODERATE': ':large_yellow_circle:', 'WEAK': ':red_circle:'}.get(strength, ':white_circle:')
    text = f':mag_right: *Evidence* {strength_emoji} {strength}\n'
    text += f'> {description}'
    if source:
        text += f'\n:file_folder: Source: `{source}`'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    supports = evidence.get('supports', [])
    refutes = evidence.get('refutes', [])
    if hypothesis or supports or refutes:
        impact_text = ''
        if hypothesis:
            impact_text += f':dart: Testing: _{hypothesis}_\n'
        if supports:
            supports_str = ', '.join(supports) if isinstance(supports, list) else str(supports)
            impact_text += f':arrow_upper_right: *Supports:* {truncate(supports_str, 100)}\n'
        if refutes:
            refutes_str = ', '.join(refutes) if isinstance(refutes, list) else str(refutes)
            impact_text += f':arrow_lower_right: *Refutes:* {truncate(refutes_str, 100)}'
        if impact_text:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': impact_text}})
    return blocks

def format_causal_chain_thread(chain: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    hypothesis = truncate(chain.get('hypothesis_id', 'Unknown'), 100)
    steps = chain.get('steps', [])
    evidence_cited = chain.get('evidence_cited', 0)
    text = f':link: *Causal Chain*\n:dart: Hypothesis: _{hypothesis}_'
    if evidence_cited:
        text += f'\n:clipboard: Evidence citations: {evidence_cited}'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if steps:
        steps_text = '*Reasoning Chain:*\n'
        for i, step in enumerate(steps[:10], 1):
            step_desc = step.get('description', str(step)) if isinstance(step, dict) else str(step)
            steps_text += f' {i}. {truncate(step_desc, 100)}\n'
        if len(steps) > 10:
            steps_text += f'_...and {len(steps) - 10} more steps_'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': steps_text}})
    return blocks

def format_similar_cases_consolidated(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':card_file_box: *Similar Cases* ({len(cases)} found)'}})
    blocks.append({'type': 'divider'})
    for case in cases[:5]:
        case_id = case.get('investigation_id') or case.get('id') or 'unknown'
        outcome = case.get('outcome') or 'unknown'
        similarity = case.get('similarity_score') or case.get('similarity') or 0
        root_cause = truncate(case.get('root_cause', ''), 150)
        outcome_emoji = OUTCOME_EMOJI.get(outcome, ':question:')
        text = f'{outcome_emoji} `{case_id}` • Similarity: `{similarity:.0%}`\n> :dart: {root_cause}'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if len(cases) > 5:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_+{len(cases) - 5} more similar cases_'}]})
    return blocks

def format_hypotheses_consolidated(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':bulb: *Hypotheses* ({len(hypotheses)} generated)'}})
    blocks.append({'type': 'divider'})
    medals = [':first_place_medal:', ':second_place_medal:', ':third_place_medal:']
    for i, hyp in enumerate(hypotheses[:8]):
        medal = medals[i] if i < len(medals) else f'#{i + 1}'
        description = hyp.get('description', 'Unknown hypothesis')
        prior = hyp.get('prior', hyp.get('score', 0))
        source = hyp.get('source', '')
        tier = hyp.get('tier', '')
        text = f'{medal} *{truncate(description, 80)}* — `{prior:.0%}`'
        if tier:
            text += f' :label: {tier}'
        if source:
            text += f'\n> Source: _{source}_'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if len(hypotheses) > 8:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_+{len(hypotheses) - 8} more hypotheses_'}]})
    return blocks

def format_challenges_consolidated(challenges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':smiling_imp: *Challenges* ({len(challenges)} raised)'}})
    blocks.append({'type': 'divider'})
    severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    sorted_challenges = sorted(challenges, key=lambda c: severity_order.get(c.get('severity', 'MEDIUM'), 1))
    for challenge in sorted_challenges[:6]:
        description = truncate(challenge.get('content', 'Unknown'), 200)
        severity = challenge.get('severity', 'MEDIUM')
        target = challenge.get('target', '')
        severity_emoji = {'HIGH': ':red_circle:', 'MEDIUM': ':large_yellow_circle:', 'LOW': ':large_green_circle:'}.get(severity, ':white_circle:')
        text = f'{severity_emoji} *{severity}*: {description}'
        if target:
            text += f'\n> :dart: Target: _{target}_'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if len(challenges) > 6:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_+{len(challenges) - 6} more challenges_'}]})
    return blocks

def format_challenge_thread(challenge: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    description = truncate(challenge.get('content', 'Unknown challenge'), 400)
    severity = challenge.get('severity', 'MEDIUM')
    target = challenge.get('target', '')
    suggestion = challenge.get('suggestion', '')
    severity_emoji = {'HIGH': ':red_circle:', 'MEDIUM': ':large_yellow_circle:', 'LOW': ':large_green_circle:'}.get(severity, ':white_circle:')
    text = f':smiling_imp: *Challenge* {severity_emoji} {severity} severity\n'
    text += f'> {description}'
    if target:
        text += f'\n:dart: Target: _{target}_'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    if suggestion:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':bulb: *Suggestion:* {truncate(suggestion, 200)}'}})
    return blocks