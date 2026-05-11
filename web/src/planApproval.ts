export const STRATEGY_APPROVAL_PROMPT =
  "[사용자 승인됨] 위 계획을 승인합니다. exit_strategy_mode를 호출한 뒤 plan에 따라 작업을 실행하세요.";

export const BRIEF_APPROVAL_PROMPT =
  "[사용자 승인됨] 위 목차를 승인합니다. approve_brief_outline()을 호출한 뒤 각 섹션을 brief_<kind> 서브에이전트에 순서대로 위임하여 작성하세요.";

export const MODE_APPROVAL_PROMPT = {
  strategy: STRATEGY_APPROVAL_PROMPT,
  brief: BRIEF_APPROVAL_PROMPT,
} as const;

export const APPROVAL_OPTIONS = [
  { key: "approve", label: "Approve" },
  { key: "reject", label: "Reject" },
  { key: "change", label: "Type here to tell Ailex what to change" },
] as const;

export type ApprovalAction = (typeof APPROVAL_OPTIONS)[number]["key"];
