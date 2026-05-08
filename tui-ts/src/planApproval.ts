export const APPROVAL_PROMPT =
  "[사용자 승인됨] 위 계획을 승인합니다. exit_strategy_mode를 호출한 뒤 plan에 따라 작업을 실행하세요.";

export const APPROVAL_OPTIONS = [
  { key: "approve", label: "Approve" },
  { key: "reject", label: "Reject" },
  { key: "change", label: "Type here to tell Ailex what to change" },
] as const;

export type ApprovalAction = (typeof APPROVAL_OPTIONS)[number]["key"];
