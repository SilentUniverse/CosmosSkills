"""Shared verdict metric sets so one verdict name means one computation everywhere.

Whole-system campaigns can compare elapsed time from the controlled runner. Raw token and tool-call
counters remain diagnostic because providers and harnesses account for them differently.
Policy-only campaigns and same-harness sessions may use those counters when telemetry scope is
paired.
"""

CAMPAIGN_WHOLE_SYSTEM = ("wall_time_ms",)
CAMPAIGN_POLICY = ("wall_time_ms", "total_tokens", "tool_calls")

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
        CAMPAIGN_WHOLE_SYSTEM: "campaign-whole-system-speed",
        CAMPAIGN_POLICY: "campaign-policy-efficiency",
        SESSION_FULL: "session-full",
    }
    name = names.get(tuple(fields), "custom")
    return "Verdict metric basis: %s (%s)" % (name, ", ".join(fields))
