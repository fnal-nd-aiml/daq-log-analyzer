"""
File: result_builders.py
Purpose: Result builders for fast path early returns.
Category: Utility
Author: artdaq team
Depends: knowledge, models, results
Exports: ResultBuilderRegistry
Complexity: Medium | Lines: 153
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from srcs.knowledge import KnowledgeBase
    from srcs.models import Investigation, InvestigationResult
logger = logging.getLogger(__name__)
ResultBuilderFunction = Callable[[dict[str, Any], "Investigation"], Coroutine[Any, Any, "InvestigationResult"]]


class ResultBuilderRegistry:

    def __init__(self, kb: "KnowledgeBase | None" = None) -> None:
        self._builders: dict[str, ResultBuilderFunction] = {}
        self._kb = kb
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register("pattern_fast_path", self._pattern_fast_path_builder)
        self.register("code_hint_fast_path", self._code_hint_fast_path_builder)

    def register(self, name: str, builder_fn: ResultBuilderFunction) -> None:
        self._builders[name] = builder_fn
        logger.debug(f"Registered result builder: {name}")

    def get(self, name: str) -> ResultBuilderFunction | None:
        return self._builders.get(name)

    def list_builders(self) -> list[str]:
        return list(self._builders.keys())

    async def build(
        self, name: str, context: dict[str, Any], investigation: "Investigation"
    ) -> "InvestigationResult | None":
        builder_fn = self.get(name)
        if builder_fn is None:
            logger.warning(f"Unknown result builder: {name}")
            return None
        try:
            return await builder_fn(context, investigation)
        except Exception as e:
            logger.error(f"Result builder '{name}' failed: {e}")
            return None

    async def _pattern_fast_path_builder(
        self, context: dict[str, Any], investigation: "Investigation"
    ) -> "InvestigationResult":
        from srcs.models import Hypothesis, InvestigationOutcome, InvestigationResult
        from srcs.models.results import CalibratedConfidence, InvestigationConclusion

        prior = context.get("prior_knowledge")
        if prior is None or not prior.matched_patterns:
            raise ValueError("Pattern fast path requires matched patterns")
        match = prior.matched_patterns[0]
        pattern = match.pattern
        root_causes = []
        if self._kb:
            try:
                root_causes = await self._kb.get_pattern_root_causes(pattern.id)
            except Exception as e:
                logger.debug(f"Failed to get root causes: {e}")
        primary_cause = root_causes[0] if root_causes else None
        hypothesis = Hypothesis(
            description=pattern.description or pattern.name,
            source="pattern_match",
            prior=pattern.pattern_confidence,
            score=pattern.pattern_confidence,
        )
        investigation.hypotheses = [hypothesis]
        from srcs.models import Evidence, EvidenceItem

        evidence = Evidence()
        context_logs = context.get("context_logs", [])
        for log in context_logs:
            strength = "STRONG" if log.level == "ERROR" else "MODERATE" if log.level == "WARNING" else "WEAK"
            item = EvidenceItem(
                evidence_type="log",
                content=f"[{log.timestamp}] {log.level} {log.component}: {log.message}",
                source=f"context_log:{log.timestamp.isoformat()}",
                strength=strength,
            )
            evidence.add(item)
        investigation.evidence = evidence
        investigation.outcome = InvestigationOutcome.CONFIDENT
        investigation.completed_at = datetime.now()
        calibrated_conf = CalibratedConfidence(
            raw=pattern.pattern_confidence,
            calibrated=pattern.pattern_confidence,
            derivation={"source": "pattern_match", "pattern_id": pattern.id},
            calibration_notes=["Fast path - using pattern confidence directly"],
        )
        conclusion = InvestigationConclusion(
            root_cause=primary_cause.description if primary_cause else pattern.description or pattern.name,
            confidence=calibrated_conf,
            caveats=["Result based on pattern matching, not full investigation"],
        )
        return InvestigationResult(
            investigation_id=investigation.id,
            outcome=InvestigationOutcome.CONFIDENT,
            root_cause=conclusion,
            confidence=pattern.pattern_confidence,
            explanation=f"Fast path match: {pattern.name}",
            primary_hypothesis=hypothesis,
            duration_seconds=(investigation.completed_at - investigation.started_at).total_seconds(),
            processing_tier=1,
            pattern_match_used=True,
        )

    async def _code_hint_fast_path_builder(
        self, context: dict[str, Any], investigation: "Investigation"
    ) -> "InvestigationResult":
        from srcs.models import Hypothesis, InvestigationOutcome, InvestigationResult
        from srcs.models.results import CalibratedConfidence, InvestigationConclusion

        prior = context.get("prior_knowledge")
        if prior is None:
            raise ValueError("Code hint fast path requires prior knowledge")
        auth_hint = None
        for rh in prior.recommended_hypotheses:
            if rh.is_authoritative and rh.source.startswith("code_hint:explicit_cause"):
                auth_hint = rh
                break
        if auth_hint is None:
            raise ValueError("Code hint fast path requires authoritative hint")
        hypothesis = Hypothesis(
            description=auth_hint.description, source=auth_hint.source, prior=auth_hint.prior, score=auth_hint.prior
        )
        investigation.hypotheses = [hypothesis]
        investigation.outcome = InvestigationOutcome.PROBABLE
        investigation.completed_at = datetime.now()
        calibrated_conf = CalibratedConfidence(
            raw=auth_hint.prior,
            calibrated=auth_hint.prior * 0.95,
            derivation={"source": "code_hint", "hint_source": auth_hint.source},
            calibration_notes=["Code hint fast path - developer explanation"],
        )
        conclusion = InvestigationConclusion(
            root_cause=auth_hint.description,
            confidence=calibrated_conf,
            caveats=["Based on developer comment, limited evidence gathering"],
        )
        return InvestigationResult(
            investigation_id=investigation.id,
            outcome=InvestigationOutcome.PROBABLE,
            root_cause=conclusion,
            confidence=auth_hint.prior * 0.95,
            explanation=f"Code hint: {auth_hint.description}",
            primary_hypothesis=hypothesis,
            duration_seconds=(investigation.completed_at - investigation.started_at).total_seconds(),
            processing_tier=2,
            pattern_match_used=False,
        )
