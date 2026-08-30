import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("overnight", ROOT / "scripts" / "overnight.py")
assert SPEC and SPEC.loader
overnight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overnight)


class OvernightTests(unittest.TestCase):
    def test_dispatch_receipt_tokens_are_parsed_for_issue_briefs(self):
        key = "a" * 64
        output = "\n".join(
            [
                "drain-wave: wave 1 dispatched (01-one, 02-two)",
                f"brief: 01-one receipt-hit:{key}",
                f"brief: 02-two receipt-hit:{key}",
                "baseline recorded; subagents may start",
            ]
        )
        self.assertEqual(
            {
                "01-one": [f"receipt-hit:{key}"],
                "02-two": [f"receipt-hit:{key}"],
            },
            overnight.parse_receipt_hits(output),
        )


if __name__ == "__main__":
    unittest.main()
