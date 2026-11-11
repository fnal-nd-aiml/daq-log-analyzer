## Evidence Strength Scale

**STRONG** (weight 1.0):
- Direct observation in logs/code showing the claimed behavior
- Multiple independent sources corroborate the same finding
- Code explicitly demonstrates the mechanism
- Example: `if (ptr == nullptr) { LOG("bad pointer") }` directly shows null causes error

**MODERATE** (weight 0.6):
- Circumstantial but consistent with the claim
- Single source with clear relevance
- Code patterns suggest but don't prove mechanism
- Example: Function handles configuration but we don't see the specific parameter

**WEAK** (weight 0.3):
- Tangentially related to the claim
- Requires interpretation or inference
- Code is in the area but doesn't directly show mechanism
- Example: Component is mentioned in logs but not the specific function

**NOT_EVIDENCE** (weight 0.0):
- Absence of something (unless expected to be present)
- Generic patterns that match many causes
- Speculation without supporting data
