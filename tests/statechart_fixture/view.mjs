const names = { cart: "购物车", paying: "付款中", charged: "已扣款", failed: "付款失败", paid: "已支付" };
const steps = {
  YouPay: "你点付款",
  BankCharges: "银行扣款",
  ReplyLost: "扣款回执丢失",
  Timeout: "付款超时",
  Retry: "你点重试",
  Reconcile: "对账发现已扣款",
  Confirm: "确认成功",
  Done: null,
};
export const title = "结账";
export const state = (v) => names[v.phase];
export const step = (action) => steps[action];
