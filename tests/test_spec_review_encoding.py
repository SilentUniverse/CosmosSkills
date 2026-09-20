import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "spec_review_encoding_fixtures", ROOT / "tests/test_spec_review.py"
)
assert FIXTURE_SPEC and FIXTURE_SPEC.loader
fixtures = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(fixtures)
review = fixtures.spec_review
SCRIPT = ROOT / "workflow/spec/scripts/spec-review.py"
NODE = shutil.which("node")


class EncodingTests(unittest.TestCase):
    def test_cli_preserves_unicode_with_legacy_stream_encodings(self):
        for encoding in ("cp1252", "gbk"):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "中文 路径 🧪"
                feature = root / ".scratch/import"
                feature.mkdir(parents=True)
                text = fixtures.PRD.replace("导入取消后仍可能显示成功。", "中文输入 🧪：取消后仍可能显示成功。")
                (feature / "PRD.md").write_bytes(
                    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
                )
                env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0")
                for command in ("render", "accept", "validate"):
                    args = [sys.executable, "-B", str(SCRIPT), command, str(root), "import"]
                    if command == "validate":
                        args.append("--require-accepted")
                    result = subprocess.run(args, env=env, capture_output=True, timeout=20)
                    output = result.stdout.decode("utf-8", errors="strict")
                    errors = result.stderr.decode("utf-8", errors="strict")
                    self.assertEqual(0, result.returncode, errors)
                    if command == "render":
                        self.assertEqual(str(feature / "spec-review.html"), json.loads(output)["html"])
                self.assertEqual(text.encode("utf-8"), (feature / "spec-accepted.md").read_bytes())
                html = (feature / "spec-review.html").read_bytes().decode("utf-8", errors="strict")
                self.assertIn("中文输入 🧪", html)
                self.assertIn('<meta charset="utf-8">', html)
                state = json.loads((feature / "spec-review.json").read_bytes().decode("utf-8"))
                self.assertEqual(review.prd_digest(feature / "PRD.md"), state["accepted_digest"])
                missing = root / "不存在 🧪"
                result = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "render", str(missing), "中文功能"],
                    env=env, capture_output=True, timeout=20,
                )
                self.assertEqual(1, result.returncode)
                self.assertIn(str(missing), result.stderr.decode("utf-8", errors="strict"))
                self.assertIn("中文功能", result.stderr.decode("utf-8", errors="strict"))

    def test_http_unicode_feedback_survives_approve_and_feedback_actions(self):
        comment = "中文反馈 🧪\r\n第二行保留"
        global_feedback = "整体意见：不能批准 🚫\r\n请保留取消行为"
        for action, has_item, has_global in (
            ("feedback", True, True), ("approve", True, False), ("approve", False, True)
        ):
            with self.subTest(action=action, item=has_item, global_=has_global):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "中文 HTTP 🧪"
                    fixtures.plant_feature(root)
                    prepared, holder, thread, outcomes = fixtures.BridgeTests().bridge(root)
                    payload = {
                        "token": holder["token"], "spec_digest": prepared["digest"],
                        "action": action, "items": [],
                    }
                    if has_item:
                        payload["items"].append({"id": "D1", "action": "change", "comment": comment})
                    if has_global:
                        payload["global_feedback"] = global_feedback
                    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.assertIn(("🧪" if has_item else "🚫").encode("utf-8"), raw)
                    request = Request(holder["url"] + "submit", data=raw,
                                      headers={"Content-Type": "application/json; charset=utf-8"})
                    try:
                        with urlopen(request, timeout=5) as response:
                            body = response.read()
                            self.assertEqual("utf-8", response.headers.get_content_charset())
                            self.assertEqual(len(body), int(response.headers["Content-Length"]))
                            result = json.loads(body.decode("utf-8", errors="strict"))
                    finally:
                        thread.join(5)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual("feedback", result["status"])
                    if has_item:
                        self.assertEqual(comment, result["items"][0]["comment"])
                    if has_global:
                        self.assertEqual(global_feedback, result["global_feedback"])
                    self.assertEqual(result, outcomes[0])
                    state = review.load_state(root / ".scratch/import")
                    self.assertIsNone(state["accepted_digest"])
                    self.assertFalse((root / ".scratch/import/spec-accepted.md").exists())


@unittest.skipUnless(NODE, "Node is required to execute review JavaScript")
class FeedbackJavaScriptTests(unittest.TestCase):
    def run_js(self, source, harness, inputs=None):
        script = "const source=" + json.dumps(source) + ";const inputs=" + json.dumps(inputs) + ";\n" + harness
        result = subprocess.run([NODE, "-e", script], capture_output=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", errors="replace"))
        return json.loads(result.stdout.decode("utf-8", errors="strict"))

    def test_static_copy_reports_actual_outcome_and_preserves_unicode(self):
        harness = r"""
const vm=require('vm'); const callbacks={}; let copiedText=null;
const out={value:'',focus(){},select(){},set textContent(value){this.value=value;}};
const button={textContent:'复制反馈',addEventListener(event,fn){callbacks[event]=fn;}};
const nodes={'feedback-data':{textContent:JSON.stringify({spec:'PRD.md',spec_digest:'abc',items:{}})},
 'feedback-text':out,'global-feedback':{value:'中文意见 🧪\n第二行'},'copy-feedback':button,
 'approve':{addEventListener(){}}};
const navigator={};
if(inputs!=='missing') navigator.clipboard={writeText(text){
 if(inputs==='reject') return Promise.reject(new Error('denied'));
 copiedText=text; return Promise.resolve();
}};
const context={document:{getElementById(id){return nodes[id];},querySelectorAll(){return [];},
 execCommand(){if(inputs==='legacy'){copiedText=out.value;return true;}return false;}},
 navigator,setTimeout(){}};
(async()=>{vm.runInNewContext(source,context);await callbacks.click.call(button);
 console.log(JSON.stringify({text:out.value,label:button.textContent,copiedText}));})()
 .catch(error=>{console.error(error);process.exitCode=1;});
"""
        for mode in ("legacy", "success", "reject", "missing"):
            with self.subTest(mode=mode):
                result = self.run_js(review.STATIC_JS, harness, mode)
                self.assertIn("中文意见 🧪\n第二行", result["text"])
                self.assertTrue(result["text"].endswith("END FEEDBACK"))
                if mode in ("legacy", "success"):
                    self.assertEqual("已复制", result["label"])
                    self.assertEqual(result["text"], result["copiedText"])
                else:
                    self.assertIn("手动复制", result["label"])
                    self.assertIsNone(result["copiedText"])

    def test_static_approve_copies_bound_confirmation_or_existing_feedback(self):
        harness = r"""
const vm=require('vm');const callbacks={};let copied;
const out={value:'',focus(){},select(){},set textContent(value){this.value=value;}};
const global={value:inputs==='global'?'整体意见 🧪':'',addEventListener(event,fn){callbacks.input=fn;}};
const text={value:inputs==='item'?'保留条目意见 🧪':''};
const boxes=[{querySelector(){return text;},getAttribute(){return 'D1';}}];
const nodes={'feedback-data':{textContent:JSON.stringify({spec:'PRD-v2.md',spec_digest:'abc',items:{}})},
 'feedback-text':out,'global-feedback':global,
 'approve':{addEventListener(event,fn){callbacks.approve=fn;}},
 'copy-feedback':{addEventListener(event,fn){callbacks.copy=fn;}}};
const document={getElementById(id){return nodes[id];},
 querySelectorAll(selector){return selector==='.comment'?boxes:[global];},
 execCommand(){copied=out.value;return true;}};
(async()=>{vm.runInNewContext(source,{document,navigator:{},setTimeout(){}});
 await callbacks.approve.call(nodes.approve);
 const approval=copied,label=nodes.approve.textContent;
 global.value='追加意见';callbacks.input({type:'input'});await callbacks.copy.call(nodes['copy-feedback']);
 console.log(JSON.stringify({approval,label,updated:copied}));})()
 .catch(error=>{console.error(error);process.exitCode=1;});
"""
        for mode in ("empty", "item", "global"):
            with self.subTest(mode=mode):
                result = self.run_js(review.STATIC_JS, harness, mode)
                self.assertIn("Spec: PRD-v2.md\nDigest: abc", result["approval"])
                if mode == "empty":
                    self.assertIn("我已审阅并批准", result["approval"])
                    self.assertIn("已复制确认", result["label"])
                else:
                    self.assertTrue(result["approval"].startswith("SPEC FEEDBACK"))
                    self.assertIn("意见 🧪", result["approval"])
                    self.assertNotIn("我已审阅并批准", result["approval"])
                self.assertIn("追加意见", result["updated"])
                self.assertNotIn("我已审阅并批准", result["updated"])

    def test_approve_preserves_typed_feedback(self):
        harness = r"""
const vm=require('vm'); const callbacks={}; let sent;
const data={token:'token',url:'http://127.0.0.1/',spec_digest:'abc',items:{D1:'hash'}};
const nodes={'bridge-data':{textContent:JSON.stringify(data)},
 'global-feedback':{value:inputs==='global'?'整体意见 🧪':''},'result':{},
 'approve':{addEventListener(event,fn){callbacks.approve=fn;}},
 'feedback':{addEventListener(event,fn){callbacks.feedback=fn;}}};
const boxes=inputs==='item'?[{querySelector(){return {value:'保留反馈 🧪'};},getAttribute(){return 'D1';}}]:[];
vm.runInNewContext(source,{document:{getElementById(id){return nodes[id];},querySelectorAll(){return boxes;}},
 fetch(url,options){sent=JSON.parse(options.body);return Promise.resolve({json(){return Promise.resolve({status:sent.action});}});}});
callbacks.approve.call(nodes.approve);console.log(JSON.stringify(sent));
"""
        for mode in ("item", "global", "empty"):
            with self.subTest(mode=mode):
                result = self.run_js(review.BRIDGE_JS, harness, mode)
                self.assertEqual("approve" if mode == "empty" else "feedback", result["action"])
                if mode == "item":
                    self.assertEqual("保留反馈 🧪", result["items"][0]["comment"])
                if mode == "global":
                    self.assertEqual("整体意见 🧪", result["global_feedback"])


if __name__ == "__main__":
    unittest.main()
