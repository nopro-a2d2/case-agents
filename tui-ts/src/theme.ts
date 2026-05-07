// Single source of truth for design tokens. Mirrors DESIGN.md front-matter.
// Values flow into Ink's <Text color={…}> / <Box paddingX={…}> directly.
//
// Note: the DESIGN.md `text-dim` role does not live here — components use
// Ink's `<Text dimColor>` prop instead of a color string. The `text` role is
// the terminal default foreground; passing it explicitly is unnecessary, so
// it's not exported either. Both are documented in DESIGN.md only.

export const colors = {
  brand:        "rgb(215,119,87)",   // assistant message text
  brandShimmer: "rgb(245,149,117)",  // reserved — future streaming shimmer
  userPrefix:   "greenBright",       // ANSI named — Ink accepts as <Text color="…">
  borderPrompt: "rgb(153,153,153)",  // reserved — future PromptInput border
  success:      "rgb(105,219,124)",  // done bullet, future diff-added
  error:        "rgb(255,168,180)",  // failed bullet, future diff-removed
  warning:      "rgb(150,108,30)",   // reserved
  permission:   "rgb(87,105,247)",   // reserved — future permission prompts
  planMode:     "rgb(0,102,102)",    // reserved — future plan mode
  userBubbleBg: "rgb(235,235,235)",  // soft light-gray bar behind UserBubble (truecolor; not ANSI "gray", which maps to a dark palette index on most terminals)
} as const;

export const glyphs = {
  spinnerFrames:     ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
  spinnerIntervalMs: 100,
  bulletDone:        "●",
  bulletFailed:      "●",
  assistantMarker:   "●",
  userPrefix:        ">",
  treeConnector:     "└",
  divider:           "│",
  ellipsis:          "…",
  thinkingDot:       "·",
  listBullet:        "•",
} as const;

export const spacing = {
  none: 0,
  xs:   1,
  sm:   2,
  md:   3,
  lg:   4,
} as const;

export const truncate = {
  toolArgs:          60,
  toolResult:        80,
  subagentTailLines: 2,
  subagentLineWidth: 80,
} as const;
