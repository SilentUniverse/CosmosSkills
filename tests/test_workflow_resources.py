import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / "workflow"
sys.path.insert(0, str(WORKFLOW))
from workflow_resources import inspect, operation


class ResourceTests(unittest.TestCase):
    def test_cross_workspace_contention_and_persistent_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry"
            code = """import sys
sys.path.insert(0, sys.argv[1])
from workflow_resources import operation
with operation(['DEVICE-A', 'device-b'], 'other-workspace') as grant:
 grant['recovered']=True
"""
            def contender():
                return subprocess.run([sys.executable, "-B", "-c", code, str(WORKFLOW)], cwd=root,
                                      env={**os.environ, "COSMOS_RESOURCE_ROOT": str(registry)},
                                      capture_output=True, text=True, timeout=10)
            with operation(["device-b", "Device-A"], "first-workspace", root=registry) as grant:
                blocked = contender()
                self.assertNotEqual(0, blocked.returncode)
                self.assertIn("lock", blocked.stderr.lower())
                self.assertEqual({"device-a": 1, "device-b": 1}, grant["resources"])
            self.assertEqual("recovery_required", inspect(["device-a"], registry)["device-a"]["state"])
            blocked = contender()
            self.assertNotEqual(0, blocked.returncode)
            self.assertIn("recovery required", blocked.stderr)
            with self.assertRaisesRegex(ValueError, "another unresolved run"):
                with operation(["device-a"], "wrong-owner", root=registry, recovery=True):
                    self.fail("wrong recovery owner admitted")
            with operation(["device-a", "device-b"], "repair", root=registry, recovery=True, expected_owner="first-workspace") as grant:
                grant["recovered"] = True
            self.assertEqual(0, contender().returncode)
            self.assertEqual(3, inspect(["device-a"], registry)["device-a"]["epoch"])


if __name__ == "__main__":
    unittest.main()
