"""
File: config.py
Purpose: Re-export of the investigation config models.
Category: Utility
Author: artdaq team
Depends: investigation_config
Exports: None
Complexity: Low | Lines: 2
"""

from srcs.models.investigation_config import CausalChainConfig, EvidenceConfig, HypothesisConfig, InvestigationConfig, OutcomeConfig
__all__ = ['CausalChainConfig', 'EvidenceConfig', 'HypothesisConfig', 'InvestigationConfig', 'OutcomeConfig']