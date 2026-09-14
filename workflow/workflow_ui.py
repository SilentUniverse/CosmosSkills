"""Validate a real Playwright JSON report against the selected scenario contract."""

import re


def evaluate(report, contract):
    required = contract.get("required_cases", [])
    assertions = contract.get("assertions", {})
    if not required or len(set(required)) != len(required) or any(not assertions.get(case) for case in required):
        raise ValueError("UI checks require named scenarios and independently expected assertion steps")
    if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1 or report.get("kind") != "cosmos-playwright" or "suites" not in report):
        raise ValueError("missing browser report")
    cases, failures = {}, []
    if report.get("errors"):
        failures.append("runner_errors")
    if report.get("status") != "passed":
        failures.append("runner_did_not_pass")

    def steps(rows):
        result = set()
        for row in rows:
            if row.get("error"):
                failures.append("failed_step:" + row.get("title", ""))
            elif row.get("category") == "expect":
                result.add(row.get("title", ""))
            result.update(steps(row.get("steps", [])))
        return result

    def visit(suites):
        for suite in suites:
            visit(suite.get("suites", []))
            for spec in suite.get("specs", []):
                match = re.match(r"\[([A-Za-z0-9_.-]+)\]", spec.get("title", ""))
                case = match[1] if match else spec.get("title", "")
                if case in cases:
                    raise ValueError("duplicate UI scenario identity; select one project per job")
                tests = spec.get("tests", [])
                attempts = [result for test in tests for result in test.get("results", [])]
                observed = set()
                valid = (len(tests) == 1 and len(attempts) == 1 and
                         tests[0].get("expectedStatus") == "passed" and
                         attempts[0].get("status") == "passed" and not attempts[0].get("errors"))
                for attempt in attempts:
                    observed.update(steps(attempt.get("steps", [])))
                if not valid:
                    failures.append("not_single_clean_pass:" + case)
                if case in required and not set(assertions[case]) <= observed:
                    failures.append("missing_assertions:" + case)
                cases[case] = {"passed": valid, "assertions": sorted(observed), "attempts": len(attempts)}

    visit(report["suites"])
    failures.extend("not_collected:" + case for case in required if case not in cases)
    if not cases:
        failures.append("zero_scenarios")
    return {"passed": not failures, "cases": cases, "failures": failures,
            "evidence_kind": "cosmos_playwright_report", "native_exploration_equivalent": False}
