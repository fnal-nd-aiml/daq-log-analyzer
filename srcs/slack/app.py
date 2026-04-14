"""
File: app.py
Purpose: Slack Bolt application for the log analyzer bot.
Category: Utility
Author: artdaq team
Depends: srcs, client, models, callbacks, investigation, ...
Exports: _RecentMessageCache, _ActiveInvestigations, create_slack_app, run_slack_bot, DEFAULT_API_URL, ...
Complexity: High | Lines: 1129
"""

import asyncio
import hashlib
import logging
import os
import time as _time
from pathlib import Path
from typing import Any, Callable, Coroutine
import yaml
from pydantic import ValidationError
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from srcs import __version__
from srcs.api.client import AgentClient
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent
from srcs.output import MarkdownFormatter
from .binder_handler import handle_workbinder_command
from .commands import (
    ParsedCommand,
    get_help_text,
    parse_ask_command,
    parse_command,
    parse_config_command,
    parse_feedback_command,
    parse_init_command,
    parse_investigate_command,
    parse_investigate_content,
    parse_list_command,
    parse_message_command,
    parse_sync_source_command,
    parse_workbinder_command,
)
from .config_store import ChannelConfig, ConfigStore
from .file_handler import InvalidFileContentError, create_log_from_message
from .formatter import (
    format_correction_modal,
    format_error,
    format_feedback_details_modal,
    format_final_result_blocks,
    format_investigation_list,
    format_investigation_result,
    format_panel_response,
    format_reviewer_feedback_blocks,
    format_success,
)
from .progress import ProgressReporter
from .queue import QueuedTask, TaskQueue
from .settings import SlackSettings

logger = logging.getLogger(__name__)
DEFAULT_API_URL = "http://localhost:8000"


def _get_api_url() -> str:
    return os.environ.get("ARTDAQ_API_URL", DEFAULT_API_URL)


class _RecentMessageCache:

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._cache: dict[str, float] = {}
        self._ttl = ttl_seconds

    def is_duplicate(self, channel: str, text: str) -> bool:
        self._evict_expired()
        key = f"{channel}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        if key in self._cache:
            return True
        self._cache[key] = _time.monotonic()
        return False

    def _evict_expired(self) -> None:
        now = _time.monotonic()
        self._cache = {k: ts for k, ts in self._cache.items() if now - ts <= self._ttl}


class _ActiveInvestigations:

    def __init__(self) -> None:
        self._active: set[str] = set()

    def start(self, content_hash: str) -> bool:
        if content_hash in self._active:
            return False
        self._active.add(content_hash)
        return True

    def finish(self, content_hash: str) -> None:
        self._active.discard(content_hash)

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.strip().encode()).hexdigest()[:24]


def create_slack_app(settings: SlackSettings) -> AsyncApp:
    app = AsyncApp(token=settings.bot_token, signing_secret=settings.signing_secret)
    data_dir = Path(os.environ.get("ARTDAQ_DATA_DIR", "./data"))
    api_url = settings.api_url or _get_api_url()
    app._settings = settings
    app._api_url = api_url
    app._config_store = ConfigStore(data_dir, output_defaults=None)
    app._task_queue = TaskQueue(max_depth=settings.max_queue_depth)
    app._dedup_cache = _RecentMessageCache()
    app._active_investigations = _ActiveInvestigations()
    _register_handlers(app)
    return app


QUEUED_COMMANDS = {"investigate", "message", "ask", "sync-source", "init", "feedback"}
ACK_MESSAGES = {
    "investigate": ":mag: Investigating... This may take a moment.",
    "message": ":mag: Investigating error message...",
    "ask": ":thinking_face: Consulting the panel of experts...",
    "sync-source": ":arrows_counterclockwise: Syncing source repositories...",
    "init": ":gear: Initializing knowledge base...",
    "feedback": ":memo: Processing feedback...",
}


async def _handle_queued_command(
    task_queue: TaskQueue,
    say: Callable[..., Any],
    channel: str,
    user: str,
    command: str,
    handler_coro: Coroutine[Any, Any, None],
) -> None:
    if task_queue.is_full():
        queue_size = task_queue.queue_size()
        await say(text=f":hourglass: The bot is busy processing {queue_size} requests. Please try again in a moment.")
        return
    ack_text = ACK_MESSAGES.get(command, ":hourglass: Processing...")
    ack_msg = await say(text=ack_text)
    ack_ts = ack_msg.get("ts") if isinstance(ack_msg, dict) else None
    task = QueuedTask(channel=channel, user=user, command=command, coro=handler_coro, ack_message_ts=ack_ts)
    if not await task_queue.submit(task):
        await say(text=":x: Failed to queue request. Please try again.")


def _register_handlers(app: AsyncApp) -> None:

    @app.event("app_mention")
    async def handle_mention(event: dict, client: AsyncWebClient, say: Callable) -> None:
        await _handle_message(app, event, client, say)

    @app.event("message")
    async def handle_dm(event: dict, client: AsyncWebClient, say: Callable) -> None:
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id"):
            return
        await _handle_message(app, event, client, say)

    @app.action("reviewer_correct")
    async def handle_reviewer_correct(ack: Callable, body: dict, client: AsyncWebClient) -> None:
        await ack()
        await _handle_reviewer_action(app, body, client, was_correct=True)

    @app.action("reviewer_incorrect")
    async def handle_reviewer_incorrect(ack: Callable, body: dict, client: AsyncWebClient) -> None:
        await ack()
        investigation_id = body["actions"][0]["value"]
        modal = format_correction_modal(investigation_id)
        await client.views_open(trigger_id=body["trigger_id"], view=modal)

    @app.action("reviewer_skip")
    async def handle_reviewer_skip(ack: Callable, body: dict, client: AsyncWebClient) -> None:
        await ack()
        await _update_feedback_message(client, body, ":fast_forward: Feedback skipped")

    @app.view("reviewer_correction_modal")
    async def handle_correction_modal(ack: Callable, body: dict, client: AsyncWebClient, view: dict) -> None:
        await ack()
        await _handle_correction_submission(app, body, client, view)

    @app.action("feedback_add_details")
    async def handle_feedback_add_details(ack: Callable, body: dict, client: AsyncWebClient) -> None:
        await ack()
        value = body["actions"][0]["value"]
        parts = value.rsplit(":", 1)
        investigation_id = parts[0]
        was_correct = parts[1] == "correct" if len(parts) > 1 else True
        modal = format_feedback_details_modal(investigation_id, was_correct)
        await client.views_open(trigger_id=body["trigger_id"], view=modal)

    @app.view("feedback_details_modal")
    async def handle_feedback_details_modal(ack: Callable, body: dict, client: AsyncWebClient, view: dict) -> None:
        await ack()
        await _handle_feedback_details_submission(app, body, client, view)


async def _handle_message(app: AsyncApp, event: dict, client: AsyncWebClient, say: Callable[..., Any]) -> None:
    settings: SlackSettings = app._settings
    api_url: str = app._api_url
    config_store: ConfigStore = app._config_store
    task_queue: TaskQueue = app._task_queue
    dedup_cache: _RecentMessageCache = app._dedup_cache
    active_investigations: _ActiveInvestigations = app._active_investigations
    text = event.get("text", "")
    channel = event.get("channel", "")
    user = event.get("user", "")
    if dedup_cache.is_duplicate(channel, text):
        logger.info("Duplicate message from %s in %s, skipping", user, channel)
        return
    bot_user_id = (await client.auth_test()).get("user_id")
    cmd = parse_command(text, bot_user_id)
    if not cmd:
        await say(text="I didn't understand that command. Try `help` for available commands.")
        return
    logger.info("Command: %s from user %s in %s", cmd.command, user, channel)
    channel_config = config_store.get_config(channel)
    try:
        if cmd.command == "investigate":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_investigate(
                    api_url, settings, event, client, say, cmd, channel_config, active_investigations
                ),
            )
        elif cmd.command == "message":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_message_command(
                    api_url, settings, event, client, say, cmd, channel_config, active_investigations
                ),
            )
        elif cmd.command == "feedback":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_feedback(api_url, say, cmd),
            )
        elif cmd.command == "ask":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_ask(say, cmd, api_url=api_url),
            )
        elif cmd.command == "sync-source":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_sync_source(api_url, say, cmd),
            )
        elif cmd.command == "init":
            await _handle_queued_command(
                task_queue=task_queue,
                say=say,
                channel=channel,
                user=user,
                command=cmd.command,
                handler_coro=_handle_init(api_url, say, cmd),
            )
        elif cmd.command == "list":
            await _handle_list(api_url, say, cmd)
        elif cmd.command == "config":
            await _handle_config(config_store, channel, say, cmd, api_url)
        elif cmd.command == "workbinder":
            await _handle_workbinder(api_url, say, cmd, client, channel)
        elif cmd.command == "version":
            await say(text=f"Log Analyzer version {__version__}")
        elif cmd.command == "help":
            help_cmd = cmd.args[0] if cmd.args else None
            await say(text=get_help_text(help_cmd))
        else:
            await say(text=f"Unknown command: `{cmd.command}`. Try `help` for available commands.")
    except Exception as e:
        logger.exception("Error handling command %s: %s", cmd.command, e)
        await say(text=f"Error: {e}", blocks=format_error(f"An error occurred: {e}"))


async def _run_and_report_investigation(
    api_url: str,
    event: dict,
    client: AsyncWebClient,
    say: Callable[..., Any],
    error: Any,
    context: list[Any],
    channel_config: ChannelConfig,
    active_investigations: _ActiveInvestigations | None = None,
    source_files: list | None = None,
) -> None:
    channel = event.get("channel", "")
    content_hash = ""
    if active_investigations is not None:
        content_hash = _ActiveInvestigations.hash_content(getattr(error, "message", str(error)))
        if not active_investigations.start(content_hash):
            logger.info("Duplicate investigation for same content in %s, skipping", channel)
            return
    reporter = ProgressReporter(
        say=say,
        verbose=channel_config.verbose,
        client=client if channel_config.verbose else None,
        channel=channel if channel_config.verbose else None,
    )
    md_formatter = MarkdownFormatter(full_output=channel_config.full_output) if channel_config.llm_logging else None
    collected_events: list[LLMEvent | DataRetrievalEvent] = []
    reporter.start()
    if channel_config.verbose and channel:
        error_location = getattr(error, "component", None)
        if error_location and error_location.lower() == "unknown":
            error_location = None
        error_function = getattr(error, "function", None)
        await reporter.post_investigation_header(
            error_message=getattr(error, "message", str(error)),
            error_location=error_location,
            error_function=error_function,
        )
    error_message = getattr(error, "message", str(error))
    try:
        async with AgentClient(api_url) as agent:
            session = await agent.create_session()
            sid = session["session_id"]
            try:
                files_data = None
                if source_files:
                    files_data = [
                        {
                            "filename": getattr(sf, "filename", "unknown.log"),
                            "content": getattr(sf, "content", ""),
                            "error_line": getattr(sf, "error_line", None),
                        }
                        for sf in source_files
                    ]
                if channel_config.verbose or channel_config.llm_logging:
                    result_data = None
                    async for event in agent.investigate_stream(
                        sid, error_message=error_message, verbose=True, source_files=files_data
                    ):
                        if event.event.startswith("phase_"):
                            sse_fields = {"phase", "phase_name", "message", "event_type"}
                            phase_data = {k: v for k, v in event.data.items() if k not in sse_fields}
                            phase_event = PhaseEvent(
                                phase=event.data.get("phase", 0),
                                phase_name=event.data.get("phase_name", ""),
                                event_type=event.data.get("event_type", event.event.replace("phase_", "")),
                                data=phase_data,
                                message=event.data.get("message"),
                            )
                            reporter.on_phase_event(phase_event)
                        elif event.event.startswith("llm_"):
                            d = event.data
                            llm_event = LLMEvent(
                                phase=d.get("phase", 0),
                                event_type=event.event.removeprefix("llm_"),
                                system_prompt=d.get("system_prompt"),
                                user_prompt=d.get("user_prompt"),
                                response=d.get("response"),
                                response_model=d.get("response_model"),
                                model_name=d.get("model_name", ""),
                                parse_failed=d.get("parse_failed", False),
                                parse_error=d.get("parse_error"),
                                expected_schema=d.get("expected_schema"),
                            )
                            if channel_config.verbose:
                                reporter.on_llm_event(llm_event)
                            if channel_config.llm_logging:
                                collected_events.append(llm_event)
                        elif event.event.startswith("data_"):
                            d = event.data
                            data_event = DataRetrievalEvent(
                                phase=d.get("phase", 0),
                                event_type=event.event.removeprefix("data_"),
                                source=d.get("source", ""),
                                operation=d.get("operation", ""),
                                query_params=d.get("query_params", {}),
                                result_summary=d.get("result_summary"),
                                result_count=d.get("result_count"),
                            )
                            if channel_config.verbose:
                                reporter.on_data_event(data_event)
                            if channel_config.llm_logging:
                                collected_events.append(data_event)
                        elif event.event == "investigation_complete":
                            result_data = event.data
                        elif event.event == "error":
                            await reporter.stop()
                            if active_investigations and content_hash:
                                active_investigations.finish(content_hash)
                            await say(text=f":x: Investigation failed: {event.data.get('message')}")
                            return
                    if result_data is None:
                        await reporter.stop()
                        if active_investigations and content_hash:
                            active_investigations.finish(content_hash)
                        await say(text=":x: No investigation result received")
                        return
                else:
                    result_data = await agent.investigate(sid, error_message=error_message, source_files=files_data)
            finally:
                try:
                    await agent.delete_session(sid)
                except Exception:
                    logger.debug("Failed to delete session %s", sid, exc_info=True)
    except Exception as e:
        await reporter.stop()
        if active_investigations and content_hash:
            active_investigations.finish(content_hash)
        await say(text=f":x: Investigation failed: {e}")
        return
    await reporter.stop()
    if active_investigations and content_hash:
        active_investigations.finish(content_hash)
    if channel_config.llm_logging and md_formatter and collected_events:
        if not channel_config.verbose:
            await _send_collected_events(say, md_formatter, collected_events)
    from srcs.models import InvestigationResult

    try:
        investigation_result = InvestigationResult.model_validate(result_data)
    except (ValueError, ValidationError):
        from srcs.models.investigation import InvestigationOutcome
        from srcs.models.results import CalibratedConfidence, InvestigationConclusion

        outcome_str = result_data.get("outcome", "INSUFFICIENT") if isinstance(result_data, dict) else "INSUFFICIENT"
        try:
            outcome = InvestigationOutcome(outcome_str)
        except ValueError:
            outcome = InvestigationOutcome.INSUFFICIENT
        rd = result_data if isinstance(result_data, dict) else {}
        raw_root_cause = rd.get("root_cause")
        if isinstance(raw_root_cause, str):
            conf = rd.get("confidence", 0.0)
            root_cause = InvestigationConclusion(
                root_cause=raw_root_cause, confidence=CalibratedConfidence(raw=conf, calibrated=conf)
            )
        elif isinstance(raw_root_cause, dict):
            root_cause = InvestigationConclusion.model_validate(raw_root_cause)
        else:
            root_cause = None
        investigation_result = InvestigationResult(
            investigation_id=rd.get("investigation_id", ""),
            outcome=outcome,
            confidence=rd.get("confidence", 0.0),
            root_cause=root_cause,
            executive_summary=rd.get("executive_summary", ""),
            explanation=rd.get("explanation", ""),
            recommendations=rd.get("recommendations", []),
        )
    if channel_config.verbose:
        blocks = format_final_result_blocks(
            investigation_result,
            investigation_id=investigation_result.investigation_id,
            duration_seconds=investigation_result.duration_seconds,
        )
    else:
        blocks = format_investigation_result(investigation_result, verbose=False)
    text_fallback = f"Investigation complete: {investigation_result.outcome.value}"
    await say(text=text_fallback, blocks=blocks)
    if investigation_result.investigation_id:
        reviewer_blocks = format_reviewer_feedback_blocks(investigation_result.investigation_id)
        await say(text="Was this diagnosis helpful?", blocks=reviewer_blocks)


async def _handle_investigate(
    api_url: str,
    settings: SlackSettings,
    event: dict,
    client: AsyncWebClient,
    say: Callable[..., Any],
    cmd: ParsedCommand,
    channel_config: ChannelConfig,
    active_investigations: _ActiveInvestigations | None = None,
) -> None:
    files = event.get("files", [])
    if not files:
        inline_content = parse_investigate_content(cmd)
        if not inline_content:
            await say(
                text="Please attach a log file or include log content inline.\nExample: `investigate 2024-01-15 10:30:45 ERROR [BR] readData: timeout`"
            )
            return
        from srcs.models.log_parser import parse_log_content

        logs = parse_log_content(inline_content)
        if not logs:
            error = create_log_from_message(inline_content)
            context: list[Any] = []
        else:
            options = parse_investigate_command(cmd)
            from srcs.models.log_parser import extract_error_and_context

            error, context = extract_error_and_context(logs, options["error_line"], options["context_lines"])
        await _run_and_report_investigation(
            api_url, event, client, say, error, context, channel_config, active_investigations=active_investigations
        )
        return
    options = parse_investigate_command(cmd)
    if len(files) > 1:
        from srcs.models.logs import SourceFile
        from srcs.slack.file_handler import download_slack_file

        source_files_list: list[SourceFile] = []
        for file_info in files:
            file_url = file_info.get("url_private_download") or file_info.get("url_private")
            file_name = file_info.get("name", "unknown.log")
            if not file_url:
                await say(text=f":x: Could not get URL for file: {file_name}")
                continue
            try:
                raw_bytes = await download_slack_file(file_url, settings.bot_token)
                content = raw_bytes.decode("utf-8", errors="replace")
                source_files_list.append(
                    SourceFile(filename=file_name, content=content, error_line=options["error_line"])
                )
            except InvalidFileContentError as e:
                await say(
                    text=f":warning: `{file_name}`: Slack returned an HTML page instead of the file content. Please re-upload the file."
                )
                logger.warning("HTML content detected for %s: %s", file_name, e)
                continue
            except Exception as e:
                await say(text=f":x: Failed to download file {file_name}: {e}")
                continue
        if not source_files_list:
            await say(text=":x: No files could be processed")
            return
        from srcs.models.log_parser import extract_error_and_context, parse_log_content

        best_error = None
        best_context: list[Any] = []
        best_score = -1
        for sf in source_files_list:
            sf_logs = parse_log_content(sf.content)
            if not sf_logs:
                continue
            for i, log_entry in enumerate(sf_logs):
                if log_entry.level not in ("ERROR", "FATAL"):
                    continue
                severity_score = 2 if log_entry.level == "FATAL" else 1
                if severity_score > best_score or (
                    severity_score == best_score
                    and best_error is not None
                    and (log_entry.timestamp is not None)
                    and (best_error.timestamp is not None)
                    and (log_entry.timestamp < best_error.timestamp)
                ):
                    candidate, ctx = extract_error_and_context(sf_logs, i + 1, options["context_lines"])
                    best_error = candidate
                    best_context = ctx
                    best_score = severity_score
        if best_error is not None:
            error = best_error
            context = best_context
        else:
            error = create_log_from_message("Multi-file investigation")
            context = []
        await say(text=f":mag: Analyzing {len(source_files_list)} files as a single investigation...")
        await _run_and_report_investigation(
            api_url,
            event,
            client,
            say,
            error,
            context,
            channel_config,
            active_investigations=active_investigations,
            source_files=source_files_list,
        )
    else:
        from srcs.models.logs import SourceFile
        from srcs.slack.file_handler import download_slack_file

        for file_info in files:
            file_url = file_info.get("url_private_download") or file_info.get("url_private")
            file_name = file_info.get("name", "unknown.log")
            if not file_url:
                await say(text=f":x: Could not get URL for file: {file_name}")
                continue
            try:
                raw_bytes = await download_slack_file(file_url, settings.bot_token)
                content = raw_bytes.decode("utf-8", errors="replace")
            except InvalidFileContentError:
                await say(
                    text=f":warning: `{file_name}`: Slack returned an HTML page instead of the file content. Please re-upload the file."
                )
                continue
            except Exception as e:
                await say(text=f":x: Failed to download file {file_name}: {e}")
                continue
            from srcs.models.log_parser import extract_error_and_context, parse_log_content

            logs = parse_log_content(content)
            if not logs:
                await say(text=f":x: Failed to parse log file: {file_name}")
                continue
            error, context = extract_error_and_context(logs, options["error_line"], options["context_lines"])
            source_file = SourceFile(filename=file_name, content=content, error_line=options["error_line"])
            await _run_and_report_investigation(
                api_url,
                event,
                client,
                say,
                error,
                context,
                channel_config,
                active_investigations=active_investigations,
                source_files=[source_file],
            )


async def _handle_message_command(
    api_url: str,
    settings: SlackSettings,
    event: dict,
    client: AsyncWebClient,
    say: Callable[..., Any],
    cmd: ParsedCommand,
    channel_config: ChannelConfig,
    active_investigations: _ActiveInvestigations | None = None,
) -> None:
    options = parse_message_command(cmd)
    if not options:
        await say(text='Usage: `message "error text"`')
        return
    error = create_log_from_message(options["message"])
    context: list[Any] = []
    await _run_and_report_investigation(
        api_url, event, client, say, error, context, channel_config, active_investigations=active_investigations
    )


async def _handle_feedback(api_url: str, say: Callable[..., Any], cmd: ParsedCommand) -> None:
    options = parse_feedback_command(cmd)
    if not options:
        await say(text='Usage: `feedback <id> correct` or `feedback <id> incorrect "actual cause"`')
        return
    try:
        async with AgentClient(api_url) as client:
            await client.submit_feedback(
                options["investigation_id"],
                options["correct"],
                actual_cause=options.get("actual_cause"),
                feedback_source="slack",
            )
        if options["correct"]:
            msg = "Feedback recorded: Diagnosis was correct"
            await say(text=msg, blocks=format_success(msg))
        else:
            msg = "Feedback recorded: Diagnosis was incorrect"
            if options.get("actual_cause"):
                msg += f"\nActual cause: {options['actual_cause']}"
            await say(text=msg, blocks=format_success(msg))
    except Exception as e:
        err_msg = f"Failed to submit feedback: {e}"
        await say(text=err_msg, blocks=format_error(err_msg))


async def _handle_reviewer_action(app: AsyncApp, body: dict, client: AsyncWebClient, was_correct: bool) -> None:
    api_url: str = app._api_url
    investigation_id = body["actions"][0]["value"]
    try:
        async with AgentClient(api_url) as agent:
            await agent.submit_feedback(investigation_id, was_correct, feedback_source="slack_interactive")
        verdict = "correct" if was_correct else "incorrect"
        if was_correct:
            status = ":white_check_mark: Feedback recorded: Diagnosis was correct"
        else:
            status = ":x: Feedback recorded: Diagnosis was incorrect"
        await _update_feedback_with_details_option(client, body, status, investigation_id, verdict)
    except Exception as e:
        logger.exception("Failed to process reviewer feedback: %s", e)
        await _update_feedback_message(client, body, f":x: Failed to record feedback: {e}")


async def _handle_correction_submission(app: AsyncApp, body: dict, client: AsyncWebClient, view: dict) -> None:
    api_url: str = app._api_url
    investigation_id = view.get("private_metadata", "")
    values = view.get("state", {}).get("values", {})
    actual_cause = values.get("corrected_root_cause", {}).get("root_cause_input", {}).get("value", "")
    try:
        async with AgentClient(api_url) as agent:
            await agent.submit_feedback(
                investigation_id, False, actual_cause=actual_cause or None, feedback_source="slack_interactive"
            )
        user_id = body.get("user", {}).get("id", "")
        msg = f":white_check_mark: Correction recorded for `{investigation_id}`"
        if actual_cause:
            msg += f"\n*Actual cause:* {actual_cause[:200]}"
        msg += """
_Use the Add Details button to provide more feedback._"""
        if user_id:
            try:
                await client.chat_postMessage(channel=user_id, text=msg)
            except Exception:
                logger.debug("Failed to send correction DM to %s", user_id, exc_info=True)
    except Exception as e:
        logger.exception("Failed to process correction: %s", e)


async def _handle_feedback_details_submission(app: AsyncApp, body: dict, client: AsyncWebClient, view: dict) -> None:
    api_url: str = app._api_url
    private_metadata = view.get("private_metadata", "")
    parts = private_metadata.rsplit(":", 1)
    investigation_id = parts[0]
    was_correct = parts[1] == "correct" if len(parts) > 1 else True
    values = view.get("state", {}).get("values", {})
    what_was_helpful = values.get("what_was_helpful", {}).get("helpful_input", {}).get("value")
    what_was_wrong = values.get("what_was_wrong", {}).get("wrong_input", {}).get("value")
    suggestions = values.get("suggestions", {}).get("suggestions_input", {}).get("value")
    additional_notes = values.get("additional_notes", {}).get("notes_input", {}).get("value")
    user_id = body.get("user", {}).get("id", "")
    try:
        async with AgentClient(api_url) as agent:
            await agent.submit_feedback(
                investigation_id,
                was_correct,
                feedback_source="slack_interactive",
                user_id=user_id or None,
                what_was_helpful=what_was_helpful,
                what_was_wrong=what_was_wrong,
                suggestions=suggestions,
                additional_notes=additional_notes,
            )
        msg = f":memo: Detailed feedback recorded for `{investigation_id}`"
        if user_id:
            try:
                await client.chat_postMessage(channel=user_id, text=msg)
            except Exception:
                logger.debug("Failed to send feedback DM to %s", user_id, exc_info=True)
    except Exception as e:
        logger.exception("Failed to submit feedback details: %s", e)


async def _update_feedback_with_details_option(
    client: AsyncWebClient, body: dict, status_text: str, investigation_id: str, verdict: str
) -> None:
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")
    if not channel or not message_ts:
        return
    try:
        await client.chat_update(
            channel=channel,
            ts=message_ts,
            text=status_text,
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": status_text}},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Add Details", "emoji": True},
                            "action_id": "feedback_add_details",
                            "value": f"{investigation_id}:{verdict}",
                        }
                    ],
                },
            ],
        )
    except Exception as e:
        logger.warning("Failed to update feedback message: %s", e)


async def _update_feedback_message(client: AsyncWebClient, body: dict, status_text: str) -> None:
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")
    if not channel or not message_ts:
        return
    try:
        await client.chat_update(
            channel=channel,
            ts=message_ts,
            text=status_text,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": status_text}}],
        )
    except Exception as e:
        logger.warning("Failed to update feedback message: %s", e)


async def _handle_list(api_url: str, say: Callable[..., Any], cmd: ParsedCommand) -> None:
    options = parse_list_command(cmd)
    try:
        async with AgentClient(api_url) as client:
            data = await client.list_investigations(limit=options["limit"])
        investigations = data.get("investigations", [])
        blocks = format_investigation_list(investigations, options["limit"])
        await say(text=f"Found {len(investigations)} investigation(s)", blocks=blocks)
    except Exception as e:
        err_msg = f"Failed to list investigations: {e}"
        await say(text=err_msg, blocks=format_error(err_msg))


async def _handle_ask(say: Callable[..., Any], cmd: ParsedCommand, api_url: str | None = None) -> None:
    options = parse_ask_command(cmd)
    if not options:
        await say(text='Usage: `ask "your question"`')
        return
    if api_url is None:
        api_url = _get_api_url()
    try:
        async with AgentClient(api_url) as agent:
            session = await agent.create_session()
            sid = session["session_id"]
            try:
                result = await agent.ask_experts(sid, options["question"])
                response_data = result.get("result", result)
                try:
                    from srcs.models.question import PanelResponse

                    response = PanelResponse(
                        question_id=response_data.get("question_id", "?"),
                        question_type=response_data.get("question_type", "how_to"),
                        answer=response_data.get("answer", "No answer available."),
                        confidence=response_data.get("confidence", 0.0),
                        key_points=response_data.get("key_points", []),
                        caveats=response_data.get("caveats", []),
                        contributions_summary=response_data.get("contributions_summary", {}),
                        dissenting_views=response_data.get("dissenting_views", []),
                        sources=response_data.get("sources", []),
                        citations=response_data.get("citations", []),
                    )
                    blocks = format_panel_response(response)
                    await say(text="Panel response", blocks=blocks)
                except (ValueError, ValidationError):
                    answer = response_data.get("answer", "No answer available.")
                    await say(text=answer)
            finally:
                try:
                    await agent.delete_session(sid)
                except Exception:
                    logger.debug("Failed to delete session %s", sid, exc_info=True)
    except Exception as e:
        err_msg = f"Failed to get answer: {e}"
        await say(text=err_msg, blocks=format_error(err_msg))


async def _handle_config(
    config_store: ConfigStore, channel: str, say: Callable[..., Any], cmd: ParsedCommand, api_url: str | None = None
) -> None:
    options = parse_config_command(cmd)
    if options["setting"] == "llm-provider":
        await _handle_config_llm_provider(say)
        return
    if not options["setting"]:
        await say(text=config_store.format_config(channel))
        return
    if options["value"] not in ("on", "off"):
        await say(text="Value must be `on` or `off`")
        return
    value = options["value"] == "on"
    success = config_store.set_setting(channel, options["setting"], value)
    if success:
        msg = f"Set `{options['setting']}` to `{options['value']}`"
        await say(text=msg, blocks=format_success(msg))
    else:
        await say(
            text=f"Unknown setting: `{options['setting']}`. Valid settings: verbose, llm-logging, full-output, llm-provider"
        )


async def _handle_config_llm_provider(say: Callable[..., Any]) -> None:
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f) or {}
        llm_config = config.get("llm", {})
    except (IOError, OSError, yaml.YAMLError):
        logger.debug("Failed to read config.yaml for LLM provider info", exc_info=True)
        llm_config = {}
    provider = llm_config.get("provider", "ollama")
    temperature = llm_config.get("temperature", 0.1)
    max_tokens = llm_config.get("max_tokens", 4096)
    lines = [
        "*LLM Provider Configuration:*",
        f"  `provider`: `{provider}`",
        f"  `temperature`: `{temperature}`",
        f"  `max_tokens`: `{max_tokens}`",
        "",
    ]
    providers = llm_config.get("providers", {})
    if provider == "ollama":
        cfg = providers.get("ollama", {})
        lines.extend(
            [
                "*Ollama Settings:*",
                f"  `host`: `{cfg.get('host', 'http://localhost:11434')}`",
                f"  `model`: `{cfg.get('model', 'unknown')}`",
            ]
        )
    elif provider == "anthropic":
        cfg = providers.get("anthropic", {})
        models = cfg.get("models", {})
        lines.extend(
            [
                "*Anthropic Settings:*",
                f"  `base_url`: `{cfg.get('base_url', 'default')}`",
                f"  `model (default)`: `{models.get('default', 'unknown')}`",
                f"  `model (small_fast)`: `{models.get('small_fast', 'not set')}`",
            ]
        )
    elif provider == "openrouter":
        cfg = providers.get("openrouter", {})
        models = cfg.get("models", {})
        lines.extend(
            [
                "*OpenRouter Settings:*",
                f"  `base_url`: `{cfg.get('base_url', 'unknown')}`",
                f"  `model (default)`: `{models.get('default', 'unknown')}`",
                f"  `model (small_fast)`: `{models.get('small_fast', 'not set')}`",
            ]
        )
    embedding = llm_config.get("embedding", {})
    lines.extend(
        [
            "",
            "*Embedding Settings:*",
            f"  `provider`: `{embedding.get('provider', 'ollama')}`",
            f"  `model`: `{embedding.get('model', 'unknown')}`",
            f"  `host`: `{embedding.get('host', 'http://localhost:11434')}`",
        ]
    )
    await say(text="\n".join(lines))


async def _handle_workbinder(
    api_url: str, say: Callable[..., Any], cmd: ParsedCommand, client: AsyncWebClient, channel: str
) -> None:
    options = parse_workbinder_command(cmd)
    if not options:
        await say(text="Usage: `workbinder <subcommand> [args]`. Use `workbinder help` for details.")
        return
    response = await handle_workbinder_command(
        subcommand=options["subcommand"],
        binder_id=options["binder_id"],
        investigation_id=options["investigation_id"],
        artifact_type=options["artifact_type"],
        phase=options["phase"],
        persona=options["persona"],
        limit=options["limit"],
        query=options["query"],
        api_url=api_url,
    )
    await say(text=f"Workbinder: {options['subcommand']}", blocks=response.blocks)
    if response.file_content and response.file_name:
        try:
            await client.files_upload_v2(
                channel=channel,
                content=response.file_content,
                filename=response.file_name,
                title=response.file_title or response.file_name,
            )
        except Exception as e:
            logger.warning("Failed to upload artifact file: %s", e)


async def _handle_sync_source(api_url: str, say: Callable[..., Any], cmd: ParsedCommand) -> None:
    options = parse_sync_source_command(cmd)
    try:
        async with AgentClient(api_url) as client:
            if options["status_only"]:
                data = await client.get_source_status()
                repos = data.get("repositories", [])
                if not repos:
                    await say(text="_No repositories configured_")
                    return
                lines = ["*Repository Status:*"]
                for repo in repos:
                    name = repo.get("name", "?")
                    status = repo.get("status", "unknown")
                    branch = repo.get("branch", "?")
                    commit = repo.get("commit", "?")
                    if status == "cloned":
                        lines.append(f":white_check_mark: `{name}` - {branch} @ `{commit[:8]}`")
                    elif status == "not_cloned":
                        lines.append(f":x: `{name}` - not cloned")
                    else:
                        lines.append(f":warning: `{name}` - {status}")
                await say(text="\n".join(lines))
            else:
                data = await client.sync_source_repos()
                results = data.get("results", [])
                success_count = data.get("success_count", 0)
                lines = ["*Sync Results:*"]
                for result in results:
                    repo_name = result.get("repo_name", "?")
                    success = result.get("success", False)
                    action = result.get("action", "unknown")
                    message = result.get("message", "")
                    if success:
                        if action == "cloned":
                            lines.append(f":white_check_mark: `{repo_name}` - cloned")
                        elif action == "updated":
                            lines.append(f":white_check_mark: `{repo_name}` - updated")
                        else:
                            lines.append(f":large_blue_circle: `{repo_name}` - skipped")
                    else:
                        lines.append(f":x: `{repo_name}` - {message}")
                lines.append(f"\n_Synced {success_count}/{len(results)} repositories_")
                await say(text="\n".join(lines))
    except Exception as e:
        err_msg = f"Failed to sync sources: {e}"
        await say(text=err_msg, blocks=format_error(err_msg))


async def _handle_init(api_url: str, say: Callable[..., Any], cmd: ParsedCommand) -> None:
    options = parse_init_command(cmd)
    try:
        async with AgentClient(api_url) as client:
            result = await client.init_system(skip_source=options["skip_source"])
        status = result.get("status", "unknown")
        if status == "success":
            lines = []
            for step in result.get("steps", []):
                step_name = step.get("name", "")
                step_status = step.get("status", "")
                if step_status == "success":
                    lines.append(f":white_check_mark: {step_name}")
                elif step_status == "skipped":
                    lines.append(f":fast_forward: {step_name} (skipped)")
                else:
                    lines.append(f":warning: {step_name}: {step.get('message', '')}")
            lines.append("\n*Knowledge base initialized!*")
            await say(text="\n".join(lines))
        else:
            message = result.get("message", "Unknown error")
            await say(text=f":x: Initialization failed: {message}")
    except Exception as e:
        err_msg = f"Initialization failed: {e}"
        await say(text=err_msg, blocks=format_error(err_msg))


async def _send_collected_events(
    say: Callable[..., Any], formatter: MarkdownFormatter, events: list[LLMEvent | DataRetrievalEvent]
) -> None:
    current_chunk: list[str] = []
    chunk_length = 0
    max_chunk = 2500
    for event in events:
        if isinstance(event, LLMEvent):
            text = formatter.format_llm_event(event)
        else:
            text = formatter.format_data_event(event)
        if not text:
            continue
        text_length = len(text)
        if chunk_length + text_length > max_chunk and current_chunk:
            await say(text="\n".join(current_chunk))
            current_chunk = []
            chunk_length = 0
        current_chunk.append(text)
        chunk_length += text_length + 1
    if current_chunk:
        await say(text="\n".join(current_chunk))


async def _announce_connection(client: AsyncWebClient, channel: str, connected: bool) -> None:
    try:
        if connected:
            text = ":robot_face: *Log Analyzer Bot* connected!\nReady to investigate DAQ log files and answer questions.\n_Mention me with `help` to see available commands._"
        else:
            text = ":wave: *Log Analyzer Bot* disconnecting.\n_Goodbye for now!_"
        await client.chat_postMessage(channel=channel, text=text)
        status = "connection" if connected else "disconnection"
        logger.info("Announced %s to %s", status, channel)
    except Exception as e:
        logger.warning("Failed to announce to %s: %s", channel, e)


async def run_slack_bot(socket_mode: bool = True, port: int = 3000) -> None:
    import signal

    settings = SlackSettings()
    if socket_mode:
        if not settings.app_token:
            raise ValueError("LOGANALYZER_SLACK_BOT_APP_TOKEN required for Socket Mode")
        app = create_slack_app(settings)
        handler = AsyncSocketModeHandler(app, settings.app_token)
        client = AsyncWebClient(token=settings.bot_token)
        announce_channel = settings.announce_channel
        shutdown_event = asyncio.Event()

        def handle_shutdown(sig: int, frame: Any) -> None:
            sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
            print(f"\n\nReceived {sig_name}, shutting down gracefully...")
            logger.info("Received signal %s, shutting down...", sig)
            shutdown_event.set()

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        logger.info("Starting Slack bot in Socket Mode...")
        await handler.connect_async()
        if announce_channel:
            await _announce_connection(client, announce_channel, connected=True)
        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            if announce_channel:
                await _announce_connection(client, announce_channel, connected=False)
            await handler.close_async()
    else:
        if not settings.signing_secret:
            raise ValueError("LOGANALYZER_SLACK_BOT_SIGNING_SECRET required for HTTP mode")
        import uvicorn
        from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
        from starlette.applications import Starlette
        from starlette.routing import Route

        app = create_slack_app(settings)
        app_handler = AsyncSlackRequestHandler(app)

        async def endpoint(request):
            return await app_handler.handle(request)

        starlette_app = Starlette(routes=[Route("/slack/events", endpoint=endpoint, methods=["POST"])])
        logger.info("Starting Slack bot in HTTP mode on port %s...", port)
        config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port)
        server = uvicorn.Server(config)
        await server.serve()
