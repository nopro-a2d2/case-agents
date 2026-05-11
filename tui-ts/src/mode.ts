// Three-state mode toggled via Shift+Tab. Keep in sync with web/src/mode.ts.
//
// normal   — no force flag; agent runs with the base system prompt.
// strategy — backend turns receive force_strategy=true (STRATEGY_FORCE_REMINDER).
// brief    — backend turns receive force_brief=true     (BRIEF_FORCE_REMINDER).
export type ModeState = "normal" | "strategy" | "brief";

export const cycleMode = (m: ModeState): ModeState =>
  m === "normal" ? "strategy" : m === "strategy" ? "brief" : "normal";
