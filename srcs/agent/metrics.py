"""
File: metrics.py
Purpose: Investigation quality metrics and scoring.
Category: Utility
Author: artdaq team
Depends: models
Exports: QualityLevel, EvidenceMetrics, HypothesisMetrics, ChainMetrics, InvestigationQualityReport, ...
Complexity: Medium | Lines: 212
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from srcs.models import CausalChain, Evidence, Hypothesis, Investigation, InvestigationOutcome
logger = logging.getLogger(__name__)

class QualityLevel(str, Enum):
    EXCELLENT = 'EXCELLENT'
    GOOD = 'GOOD'
    ADEQUATE = 'ADEQUATE'
    POOR = 'POOR'
    INSUFFICIENT = 'INSUFFICIENT'

@dataclass
class EvidenceMetrics:
    total_items: int = 0
    strong_items: int = 0
    moderate_items: int = 0
    weak_items: int = 0
    supporting_items: int = 0
    contradicting_items: int = 0
    code_evidence: int = 0
    log_evidence: int = 0
    coverage_score: float = 0.0

@dataclass
class HypothesisMetrics:
    total_hypotheses: int = 0
    active_hypotheses: int = 0
    rejected_hypotheses: int = 0
    top_score: float = 0.0
    second_score: float = 0.0
    discrimination_ratio: float = 0.0
    convergence_score: float = 0.0

@dataclass
class ChainMetrics:
    total_steps: int = 0
    evidenced_steps: int = 0
    assumption_steps: int = 0
    logical_validity: float = 0.0
    evidence_coverage: float = 0.0
    gap_count: int = 0

@dataclass
class InvestigationQualityReport:
    investigation_id: str
    outcome: InvestigationOutcome | None
    quality_level: QualityLevel
    overall_score: float
    evidence_metrics: EvidenceMetrics
    hypothesis_metrics: HypothesisMetrics
    chain_metrics: ChainMetrics | None
    unresolved_challenges: int = 0
    total_challenges: int = 0
    quality_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

class QualityAnalyzer:
    THRESHOLDS = {QualityLevel.EXCELLENT: 0.85, QualityLevel.GOOD: 0.7, QualityLevel.ADEQUATE: 0.5, QualityLevel.POOR: 0.3}
    WEIGHTS = {'evidence_coverage': 0.25, 'evidence_strength': 0.15, 'hypothesis_discrimination': 0.2, 'chain_quality': 0.2, 'challenge_resolution': 0.1, 'outcome_confidence': 0.1}

    def analyze(self, investigation: Investigation) -> InvestigationQualityReport:
        evidence_metrics = self._analyze_evidence(investigation.evidence)
        hypothesis_metrics = self._analyze_hypotheses(investigation.hypotheses)
        chain_metrics = self._analyze_chain(investigation.causal_chains[0]) if investigation.causal_chains else None
        total_challenges = len(investigation.challenges)
        unresolved = sum((1 for c in investigation.challenges if c.requires_response and (not c.resolved)))
        overall_score = self._calculate_overall_score(evidence_metrics, hypothesis_metrics, chain_metrics, investigation)
        quality_level = self._determine_quality_level(overall_score)
        issues, recommendations = self._generate_recommendations(evidence_metrics, hypothesis_metrics, chain_metrics, investigation)
        return InvestigationQualityReport(investigation_id=investigation.id, outcome=investigation.outcome, quality_level=quality_level, overall_score=overall_score, evidence_metrics=evidence_metrics, hypothesis_metrics=hypothesis_metrics, chain_metrics=chain_metrics, unresolved_challenges=unresolved, total_challenges=total_challenges, quality_issues=issues, recommendations=recommendations)

    def _analyze_evidence(self, evidence: Evidence) -> EvidenceMetrics:
        metrics = EvidenceMetrics()
        metrics.total_items = len(evidence.items)
        for item in evidence.items.values():
            if item.strength == 'STRONG':
                metrics.strong_items += 1
            elif item.strength == 'MODERATE':
                metrics.moderate_items += 1
            else:
                metrics.weak_items += 1
            if item.evidence_type == 'code':
                metrics.code_evidence += 1
            elif item.evidence_type == 'log':
                metrics.log_evidence += 1
        if metrics.total_items > 0:
            strength_score = (metrics.strong_items * 1.0 + metrics.moderate_items * 0.6 + metrics.weak_items * 0.3) / metrics.total_items
            diversity_bonus = 0.0
            if metrics.code_evidence > 0 and metrics.log_evidence > 0:
                diversity_bonus = 0.1
            metrics.coverage_score = min(1.0, strength_score + diversity_bonus)
        return metrics

    def _analyze_hypotheses(self, hypotheses: list[Hypothesis]) -> HypothesisMetrics:
        metrics = HypothesisMetrics()
        metrics.total_hypotheses = len(hypotheses)
        if not hypotheses:
            return metrics
        for h in hypotheses:
            if h.status == 'active':
                metrics.active_hypotheses += 1
            elif h.status == 'rejected':
                metrics.rejected_hypotheses += 1
        sorted_hyps = sorted(hypotheses, key=lambda h: h.score, reverse=True)
        metrics.top_score = sorted_hyps[0].score
        if len(sorted_hyps) > 1:
            metrics.second_score = sorted_hyps[1].score
            if metrics.second_score > 0:
                metrics.discrimination_ratio = (metrics.top_score - metrics.second_score) / metrics.second_score
            elif metrics.top_score > 0:
                metrics.discrimination_ratio = 1.0
        if metrics.total_hypotheses > 0:
            reject_ratio = metrics.rejected_hypotheses / metrics.total_hypotheses
            metrics.convergence_score = min(1.0, reject_ratio + (0.3 if metrics.top_score > 0.6 else 0))
        return metrics

    def _analyze_chain(self, chain: CausalChain) -> ChainMetrics:
        metrics = ChainMetrics()
        metrics.total_steps = len(chain.steps)
        for step in chain.steps:
            if step.is_assumption:
                metrics.assumption_steps += 1
            if step.evidence_ids:
                metrics.evidenced_steps += 1
        metrics.logical_validity = chain.logical_validity
        metrics.evidence_coverage = chain.evidence_coverage
        metrics.gap_count = len(chain.gaps)
        return metrics

    def _calculate_overall_score(self, evidence: EvidenceMetrics, hypotheses: HypothesisMetrics, chain: ChainMetrics | None, investigation: Investigation) -> float:
        scores = {}
        scores['evidence_coverage'] = evidence.coverage_score
        if evidence.total_items > 0:
            scores['evidence_strength'] = (evidence.strong_items * 1.0 + evidence.moderate_items * 0.5) / evidence.total_items
        else:
            scores['evidence_strength'] = 0.0
        scores['hypothesis_discrimination'] = min(1.0, hypotheses.discrimination_ratio / 2.0 + (0.3 if hypotheses.top_score > 0.5 else 0))
        if chain:
            scores['chain_quality'] = chain.logical_validity * 0.5 + chain.evidence_coverage * 0.5
        else:
            scores['chain_quality'] = 0.0
        if investigation.challenges:
            resolved = sum((1 for c in investigation.challenges if c.resolved))
            scores['challenge_resolution'] = resolved / len(investigation.challenges)
        else:
            scores['challenge_resolution'] = 1.0
        if investigation.outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
            scores['outcome_confidence'] = hypotheses.top_score
        else:
            scores['outcome_confidence'] = 0.3
        total_score = sum((scores[key] * weight for key, weight in self.WEIGHTS.items()))
        return min(1.0, total_score)

    def _determine_quality_level(self, score: float) -> QualityLevel:
        if score >= self.THRESHOLDS[QualityLevel.EXCELLENT]:
            return QualityLevel.EXCELLENT
        elif score >= self.THRESHOLDS[QualityLevel.GOOD]:
            return QualityLevel.GOOD
        elif score >= self.THRESHOLDS[QualityLevel.ADEQUATE]:
            return QualityLevel.ADEQUATE
        elif score >= self.THRESHOLDS[QualityLevel.POOR]:
            return QualityLevel.POOR
        else:
            return QualityLevel.INSUFFICIENT

    def _generate_recommendations(self, evidence: EvidenceMetrics, hypotheses: HypothesisMetrics, chain: ChainMetrics | None, investigation: Investigation) -> tuple[list[str], list[str]]:
        issues = []
        recommendations = []
        if evidence.total_items == 0:
            issues.append('No evidence collected')
            recommendations.append('Add evidence seeking phase or expand log context')
        elif evidence.strong_items == 0:
            issues.append('No strong evidence found')
            recommendations.append('Look for more definitive evidence sources')
        if evidence.code_evidence == 0 and evidence.log_evidence > 0:
            recommendations.append('Consider adding code analysis for deeper insight')
        if hypotheses.total_hypotheses == 0:
            issues.append('No hypotheses generated')
        elif hypotheses.discrimination_ratio < 0.3:
            issues.append('Poor hypothesis discrimination')
            recommendations.append('Seek evidence that distinguishes between top hypotheses')
        if hypotheses.top_score < 0.5:
            issues.append('Low confidence in top hypothesis')
        if chain:
            if chain.assumption_steps > chain.total_steps / 2:
                issues.append('Causal chain has too many assumptions')
                recommendations.append('Find evidence to support assumed steps')
            if chain.gap_count > 2:
                issues.append(f'Causal chain has {chain.gap_count} gaps')
        unresolved = sum((1 for c in investigation.challenges if c.requires_response and (not c.resolved)))
        if unresolved > 0:
            issues.append(f'{unresolved} unresolved challenges')
            recommendations.append('Address challenges before finalizing conclusion')
        return (issues, recommendations)

def format_quality_report(report: InvestigationQualityReport) -> str:
    lines = [f'Investigation Quality Report: {report.investigation_id}', '=' * 50, '', f"Outcome: {(report.outcome.value if report.outcome else 'N/A')}", f'Quality Level: {report.quality_level.value}', f'Overall Score: {report.overall_score:.0%}', '', 'Evidence Metrics:', f'  - Total items: {report.evidence_metrics.total_items}', f'  - Strong: {report.evidence_metrics.strong_items}', f'  - Moderate: {report.evidence_metrics.moderate_items}', f'  - Weak: {report.evidence_metrics.weak_items}', f'  - Coverage score: {report.evidence_metrics.coverage_score:.0%}', '', 'Hypothesis Metrics:', f'  - Total: {report.hypothesis_metrics.total_hypotheses}', f'  - Top score: {report.hypothesis_metrics.top_score:.0%}', f'  - Discrimination: {report.hypothesis_metrics.discrimination_ratio:.2f}', '']
    if report.chain_metrics:
        lines.extend(['Causal Chain:', f'  - Steps: {report.chain_metrics.total_steps}', f'  - Evidenced: {report.chain_metrics.evidenced_steps}', f'  - Assumptions: {report.chain_metrics.assumption_steps}', f'  - Validity: {report.chain_metrics.logical_validity:.0%}', ''])
    lines.append(f'Challenges: {report.unresolved_challenges}/{report.total_challenges} unresolved')
    if report.quality_issues:
        lines.extend(['', 'Issues:'])
        for issue in report.quality_issues:
            lines.append(f'  - {issue}')
    if report.recommendations:
        lines.extend(['', 'Recommendations:'])
        for rec in report.recommendations:
            lines.append(f'  - {rec}')
    return '\n'.join(lines)