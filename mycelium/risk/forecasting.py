"""Observational measurements only - no scoring, no aggregation.

Per PROJECT_IDEA, this system does not compute scalar risk scores. The functions
here produce raw counts and structural facts that the analyst agent reasons over
(alongside investigator findings) to produce qualitative Findings.

The file name is kept as forecasting.py for import stability, but the content
is now strictly measurement.
"""


def compute_bus_factor(contributions: list[dict]) -> int:
    """Number of contributors whose combined expertise covers >= 80% of a module.

    This is a count, not a risk score. The analyst interprets the count in
    context (with investigator findings, documentation state, etc.) when it
    decides whether a low bus factor matters for a given module.
    """
    if not contributions:
        return 0
    scores = sorted([c["expertise_score"] for c in contributions], reverse=True)
    total = sum(scores)
    if total == 0:
        return 0
    cumulative = 0.0
    for i, s in enumerate(scores):
        cumulative += s
        if cumulative / total >= 0.8:
            return i + 1
    return len(scores)
