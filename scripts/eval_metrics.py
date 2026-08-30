"""Shared verdict metric sets so one verdict name means one computation everywhere.

CAMPAIGN_CORE composes cross-harness campaign verdicts: whole-system arms differ in
harness and provider, and process counters (alignment rounds, repairs, retries) are not
comparable across that boundary, so only resource metrics decide campaign verdicts.
SESSION_FULL composes same-harness session reports, where every lower-is-better metric
was measured under one telemetry scope and may take part.
"""

CAMPAIGN_CORE = ("wall_time_ms", "total_tokens", "tool_calls")

SESSION_FULL = (
    "wall_time_ms",
    "total_tokens",
    "tool_calls",
    "alignment_round_count",
    "clarification_count",
    "ac_repair_count",
    "dependency_repair_count",
    "replan_count",
    "executor_discovered_invariant_count",
    "scope_leakage_count",
    "retry_count",
)


def metrics_basis(fields):
    """One-line provenance for reports: which set decided the verdict."""
    name = "campaign-core" if tuple(fields) == CAMPAIGN_CORE else "session-full"
    return "Verdict metric basis: %s (%s)" % (name, ", ".join(fields))
