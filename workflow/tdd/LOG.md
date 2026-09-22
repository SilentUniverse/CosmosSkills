# Log-based verification

Load for `/tdd -log` or a device scenario judged by a log predicate. Keep scope, readiness, evidence
identity and completion rules. Replace test-writing with the control action and a predicate that
fails when behavior is absent; a launcher/capture exit alone is insufficient.

Use native tools and project runners. Retain action, exit, input/candidate identity, log digest and
decisive excerpt. Long streams require bounded capture and an explicit stop condition. For ADB,
read `~/.claude/references/android-adb.md` first. Shared devices need actual resource-owner exclusion
and recovery; agents do not provide it. Apply [TEST-POLICY.md](../TEST-POLICY.md) and
[COMPLETION-RECORD.md](COMPLETION-RECORD.md).
