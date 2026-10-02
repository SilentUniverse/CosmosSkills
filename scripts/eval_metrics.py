"""Shared verdict metric sets so one verdict name means one computation everywhere.

Same-harness sessions may compare wall time, token, and tool-call counters when the telemetry scope
is paired; provider accounting differences keep raw counters diagnostic otherwise.
"""

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
    names = {
        SESSION_FULL: "session-full",
    }
    name = names.get(tuple(fields), "custom")
    return "Verdict metric basis: %s (%s)" % (name, ", ".join(fields))
