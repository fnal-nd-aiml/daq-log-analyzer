"""
File: code_artifacts.py
Purpose: Typed builders for code-analysis artifacts.
Category: Utility
Author: artdaq team
Depends: models
Exports: CodeArtifactsMixin
Complexity: Medium | Lines: 58
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from ..artifacts import Annotation, AnnotationType, CalleeInfo, CallerInfo, CallGraphNode, CodeSnippet, ErrorContextArtifact, Finding, FindingType, FunctionSummaryArtifact, Priority, SourceLocationArtifact
from ._state import BinderState
if TYPE_CHECKING:
    from srcs.models import Log
logger = logging.getLogger(__name__)

class CodeArtifactsMixin(BinderState):

    def add_call_graph(self, center_function: str, callers: list[dict[str, Any]], callees: list[dict[str, Any]], created_by: str, phase: int | None=None, diagram: str | None=None, depth: int=1) -> str:
        caller_infos = [CallerInfo(**c) for c in callers]
        callee_infos = [CalleeInfo(**c) for c in callees]
        artifact = CallGraphNode(center_function=center_function, callers=caller_infos, callees=callee_infos, created_by=created_by, phase=phase, function_name=center_function, diagram=diagram, depth_explored=depth)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='call_graph', method_name='add_call_graph', artifact_id=artifact_id)
        logger.info(f'Stored call graph: {center_function} ({len(callers)} callers, {len(callees)} callees)')
        return artifact_id

    def add_function_summary(self, function_name: str, purpose: str, mechanism: str, data_flow: str, error_paths: str, error_line_relevance: str, center_function: str, role: str, created_by: str, phase: int | None=None, file_path: str | None=None) -> str:
        artifact = FunctionSummaryArtifact(function_name=function_name, file_path=file_path, purpose=purpose, mechanism=mechanism, data_flow=data_flow, error_paths=error_paths, error_line_relevance=error_line_relevance, center_function=center_function, role=role, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='function_summary', method_name='add_function_summary', artifact_id=artifact_id)
        logger.info(f'Stored function summary: {function_name} ({role} of {center_function})')
        return artifact_id

    def add_code_snippet(self, file_path: str, start_line: int, end_line: int, content: str, created_by: str, language: str='cpp', function_name: str | None=None, summary: str | None=None, phase: int | None=None, match_score: float | None=None) -> str:
        artifact = CodeSnippet(file_path=file_path, start_line=start_line, end_line=end_line, content=content, created_by=created_by, language=language, snippet_function_name=function_name, function_name=function_name, summary=summary, phase=phase, match_score=match_score)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='code_snippet', method_name='add_code_snippet', artifact_id=artifact_id)
        func_info = f' ({function_name})' if function_name else ''
        logger.info(f'Stored code snippet: {file_path}:{start_line}-{end_line}{func_info} ({len(content)} chars)')
        return artifact_id

    def add_finding(self, persona: str, finding_type: FindingType | str, content: str, confidence: float=0.5, related_artifacts: list[str] | None=None, phase: int | None=None, tags: list[str] | None=None) -> str:
        if isinstance(finding_type, str):
            finding_type = FindingType(finding_type)
        artifact = Finding(persona=persona, finding_type=finding_type, content=content, confidence=confidence, related_artifacts=related_artifacts or [], created_by=persona, phase=phase, tags=tags or [])
        return self.add_artifact(artifact)

    def add_annotation(self, target_artifact_id: str, annotation_type: AnnotationType | str, content: str, created_by: str) -> str:
        if isinstance(annotation_type, str):
            annotation_type = AnnotationType(annotation_type)
        artifact = Annotation(target_artifact_id=target_artifact_id, annotation_type=annotation_type, annotation_content=content, created_by=created_by)
        return self.add_artifact(artifact)

    def add_source_location(self, file_path: str, line_number: int, created_by: str, matched_line: str | None=None, match_score: float=0.0, is_log_statement: bool=False, function_name: str | None=None, function_signature: str | None=None, function_body: str | None=None, context_before: list[str] | None=None, context_after: list[str] | None=None, phase: int | None=None) -> str:
        artifact = SourceLocationArtifact(file_path=file_path, line_number=line_number, matched_line=matched_line, match_score=match_score, is_log_statement=is_log_statement, function_name=function_name, function_signature=function_signature, function_body=function_body, context_before=context_before or [], context_after=context_after or [], created_by=created_by, phase=phase, priority=Priority.HIGH if match_score > 0.8 else Priority.NORMAL)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='source_location', method_name='add_source_location', artifact_id=artifact_id)
        func_info = f', function={function_name}' if function_name else ''
        logger.info(f'Stored source location: {file_path}:{line_number} (score={match_score:.2f}{func_info})')
        return artifact_id

    def add_error_context(self, error: 'Log', context_logs: list['Log'], created_by: str) -> str:
        artifact = ErrorContextArtifact(error_message=error.message, error_level=error.level, error_component=error.component, error_function=error.function, error_timestamp=error.timestamp, context_logs=[log.model_dump() for log in context_logs], created_by=created_by, phase=0, priority=Priority.CRITICAL)
        return self.add_artifact(artifact)