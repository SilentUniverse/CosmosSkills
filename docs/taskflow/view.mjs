const names = {
  request: "收到请求",
  confirming_intent: "已复述意图，等你确认",
  aligning: "调研与实质决策对齐",
  planned: "已给计划，等你说开始",
  asking: "等你做实质决定",
  coding: "实现中",
  verifying: "按范围验证中",
  verified: "已验证",
  blocked: "两次修复失败，停下换思路",
  stopped: "停在本地，已报告",
  landing: "PR 等必过检查",
  merged: "已合并并收尾",
};
const groups = {
  request: "规划", confirming_intent: "规划", aligning: "规划", planned: "规划", asking: "规划",
  coding: "实现", blocked: "实现",
  verifying: "验证", verified: "验证",
  landing: "提交", merged: "提交", stopped: "提交",
};
const steps = {
  RestateForPlan: "你要计划、/spec 或意图模糊，先复述意图",
  ReviseIntent: null,
  ConfirmIntent: "你确认意图（仅解锁规划）",
  PlanDecision: null,
  GivePlan: "完成调研与对齐，给出计划",
  UserSaysOk: null,
  UserRevisesPlan: "你要求修订计划",
  UserSaysStart: "你说「开始实现」或 /tdd",
  StartDirect: "清晰小改动，转述后直接实现",
  NeedDecision: "遇到实质选择",
  UserDecides: "你选定",
  ReadyCheck: "改完并按范围验证（后台/固定候选）",
  VerifyPass: "对应范围检查通过（交付门含全量）",
  StopLocal: "没要求提交",
  Land: "你要求提交，/pr 推送",
  CiPass: "必过检查通过并合并",
  Done: null,
  Rethink: "/diagnose 或新子代理复查后再改",
};
export const title = "任务流";
export const colors = { 规划: "blue", 实现: "orange", 验证: "purple", 提交: "teal" };
export const group = (v) => groups[v.phase];
export const state = (v) => names[v.phase];
export const step = (action, from, to) => {
  if (action === "Fail")
    return to.phase === "blocked" ? "修复后又失败" : from.phase === "verifying" ? "验证失败，修复" : "必过检查失败，修复";
  return steps[action];
};
