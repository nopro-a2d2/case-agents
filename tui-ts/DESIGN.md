---
version: alpha
name: case-agent TUI
description: Terminal UI design system for the case-agent tui-ts (Ink/React) frontend, styled after Claude Code.

colors:
  brand:           "rgb(215,119,87)"
  brand-shimmer:   "rgb(245,149,117)"
  user-prefix:     "ansi:greenBright"
  text:            "rgb(255,255,255)"
  text-dim:        "rgb(153,153,153)"
  border-prompt:   "rgb(153,153,153)"
  success:         "rgb(105,219,124)"
  error:           "rgb(255,168,180)"
  warning:         "rgb(150,108,30)"
  permission:      "rgb(87,105,247)"
  plan-mode:       "rgb(0,102,102)"
  user-bubble-bg:  "rgb(235,235,235)"

typography:
  prompt-prefix:     { weight: bold,   color: "{colors.user-prefix}" }
  header-label:      { weight: bold }
  header-meta:       { weight: dim }
  message-user:      { weight: normal }
  message-assistant: { weight: normal }
  tool-name-running: { weight: dim }
  tool-name-done:    { weight: normal, color: "{colors.success}" }
  tool-name-failed:  { weight: normal, color: "{colors.error}" }
  tool-args:         { weight: dim }
  tool-result:       { weight: dim }
  tree-connector:    { weight: dim }
  status-line:       { weight: dim }

spacing:
  none: 0
  xs:   1
  sm:   2
  md:   3
  lg:   4

rounded:
  none:   "none"
  single: "single"
  round:  "round"

glyphs:
  spinner-frames:      ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
  spinner-interval-ms: 100
  bullet-done:         "●"
  bullet-failed:       "●"
  assistant-marker:    "●"
  user-prefix:         ">"
  tree-connector:      "└"
  divider:             "│"
  ellipsis:            "…"
  thinking-dot:        "·"
  list-bullet:         "•"

components:

  Header:
    layout: two-column
    paddingX: "{spacing.sm}"
    paddingY: "{spacing.xs}"
    divider:  "{glyphs.divider}"
    divider-color: "{colors.text-dim}"
    left-typography:  "{typography.header-label}"
    left-meta-typography: "{typography.header-meta}"
    right-typography: "{typography.header-label}"
    right-meta-typography: "{typography.header-meta}"

  PromptInput:
    prefix:        "{glyphs.user-prefix}"
    prefix-typography: "{typography.prompt-prefix}"
    marginX:       "{spacing.sm}"
    marginTop:     "{spacing.xs}"
    paddingX:      "{spacing.xs}"
    cursor-style:  inverse
    placeholder-color: "{colors.text-dim}"
    border:        "{rounded.round}"
    border-color:  "{colors.border-prompt}"

  UserBubble:
    marginTop:    "{spacing.xs}"
    prefix:       "{glyphs.user-prefix}"
    prefix-typography: "{typography.prompt-prefix}"
    text-typography: "{typography.message-user}"
    background-color: "{colors.user-bubble-bg}"
    bar-gutter:   "{spacing.sm}"
    full-row-bg:  true

  AssistantBubble:
    paddingLeft:  "{spacing.sm}"
    marginTop:    "{spacing.xs}"
    text-typography: "{typography.message-assistant}"
    marker:       "{glyphs.assistant-marker}"
    no-label:     true

  ToolBlock:
    indent-per-level: "{spacing.sm}"
    args-truncate:    60
    result-truncate:  80
    subagent-tail-lines: 2
    header-running:
      spinner: "{glyphs.spinner-frames}"
      typography: "{typography.tool-name-running}"
    header-done:
      bullet: "{glyphs.bullet-done}"
      typography: "{typography.tool-name-done}"
    header-failed:
      bullet: "{glyphs.bullet-failed}"
      typography: "{typography.tool-name-failed}"
    args-typography:    "{typography.tool-args}"
    result-typography:  "{typography.tool-result}"
    result-connector:   "{glyphs.tree-connector}"
    connector-typography: "{typography.tree-connector}"

  ThinkingSpinner:
    leading-glyph: "{glyphs.thinking-dot}"
    frames:        "{glyphs.spinner-frames}"
    interval-ms:   "{glyphs.spinner-interval-ms}"
    paddingX:      "{spacing.sm}"
    marginTop:     "{spacing.xs}"
    typography:    "{typography.status-line}"
    suffix-format: "Thinking… ({seconds}s)"

  StatusLine:
    paddingX:   "{spacing.sm}"
    typography: "{typography.status-line}"

  WelcomeScreen:
    border:        "{rounded.round}"
    border-color:  "{colors.border-prompt}"
    marginX:       "{spacing.sm}"
    marginTop:     "{spacing.xs}"
    paddingX:      "{spacing.xs}"
    title-typography:       "{typography.header-label}"
    description-typography: "{typography.header-meta}"
    bullet:        "{glyphs.list-bullet}"
    visibility:    "transcript-empty"
---

## Overview

case-agent's `tui-ts` is a terminal UI for an evidence-driven case-research agent. The visual language is **terminal-native, content-first, and minimal**: chrome (header, prefixes, connectors, status hints) is dim by default; full color is reserved for **state events** (a tool finishing, a tool failing, the user's own turn). Motion is limited to a single Braille spinner that signals "the agent is working" — there is no easing, no gradients, no boxes around messages.

The aesthetic is borrowed directly from Anthropic's Claude Code REPL. It optimizes for two things:

1. **Calm**: long agent turns with many tool calls must not feel busy. A reader scanning the transcript should be able to ignore chrome and follow the conversation.
2. **State legibility**: the three states a tool call can be in (running / done / failed) must be readable in peripheral vision via a single glyph + color.

This document is the **target** design system. Sections below describe how the TUI _should_ render; the [Gaps](#gaps-from-current-implementation) section enumerates what the live code under `src/components/*.tsx` does not yet match.

## Colors

Color is semantic. A token's name is its role; never reference a raw hex/rgb literal in component code — always go through a token.

| Token             | Value                  | Role                                                                 |
| ----------------- | ---------------------- | -------------------------------------------------------------------- |
| `brand`           | `rgb(215,119,87)`      | Reserved. Currently unused after 2026-05-07 — held for future shimmer / emphasis surfaces. |
| `brand-shimmer`   | `rgb(245,149,117)`     | Reserved — future shimmer animation on streaming assistant text.     |
| `user-prefix`     | `ansi:greenBright`     | The `>` prefix on user turns and on the prompt input.                 |
| `text`            | `rgb(255,255,255)`     | Default body text (user message body, header labels).                 |
| `text-dim`        | `rgb(153,153,153)`     | Chrome: header meta, tool args, tool results, connectors, status hints. |
| `border-prompt`   | `rgb(153,153,153)`     | Reserved — future prompt-input border (currently borderless).         |
| `success`         | `rgb(105,219,124)`     | Done bullet `●`, future diff-added.                                   |
| `error`           | `rgb(255,168,180)`     | Failed bullet `●`, error suffix, future diff-removed.                 |
| `warning`         | `rgb(150,108,30)`      | Reserved — non-blocking warnings.                                     |
| `permission`      | `rgb(87,105,247)`      | Reserved — future permission prompts.                                 |
| `plan-mode`       | `rgb(0,102,102)`       | Reserved — future plan-mode indicator.                                |
| `user-bubble-bg`  | `rgb(235,235,235)`     | Full-row background behind `UserBubble` rows. Soft light gray; intentionally not ANSI `gray`, which maps to a dark palette index on most terminals. |

**Truecolor only.** All color values are 24-bit RGB or named ANSI. There is no 256-color or 16-color fallback in v1. Terminals without truecolor will see degraded but legible output (Ink/Chalk auto-clamp).

**Don't introduce a second accent.** Outside of state colors (`success` / `error` / `warning`), the only chromatic accent is `brand`. Anything else lives in `text-dim`.

## Typography

In a terminal, "typography" is the combination of text-modifiers Ink exposes on `<Text>`: `bold`, `dimColor`, `italic`, `inverse`, `underline`. The seven canonical roles below are the only combinations component code may use.

| Role                | bold | dim | color           | inverse | Where it appears                        |
| ------------------- | :--: | :-: | --------------- | :-----: | --------------------------------------- |
| `prompt-prefix`     |  ●   |     | `user-prefix`   |         | The `>` in `UserBubble` and `PromptInput` |
| `header-label`      |  ●   |     | `text`          |         | "case-agent", "Tips" in the header      |
| `header-meta`       |      |  ●  |                 |         | "case: <id>", "model: …", tip lines     |
| `message-user`      |      |     | `text`          |         | User message body                       |
| `message-assistant` |      |     | `brand`         |         | Assistant message body (preText/postText) |
| `tool-name-running` |      |  ●  |                 |         | Tool name while spinner is animating    |
| `tool-name-done`    |      |     | `success`       |         | Tool name after success (color comes from the bullet, name itself remains default; only the bullet is colored — see `ToolBlock`) |
| `tool-name-failed`  |      |     | `error`         |         | Tool name after failure                 |
| `tool-args`         |      |  ●  |                 |         | Truncated input preview after tool name |
| `tool-result`       |      |  ●  |                 |         | Single-line result after `└`            |
| `tree-connector`    |      |  ●  |                 |         | The `└ ` connector itself               |
| `status-line`       |      |  ●  |                 |         | Footer hint, thinking indicator         |
| _cursor_            |      |     |                 |   ●     | The single inverted space in `PromptInput` |

**Don't combine `dim` with a non-default `color`** unless the role table explicitly allows it. Dim + brand (e.g. dim assistant text) reads as a bug.

## Layout

The screen is a vertical flexbox of three zones, top to bottom:

```
┌──────────────────────────────────────────────────────────────────┐
│  Header        (paddingX 2, paddingY 1; first paint only)        │
├──────────────────────────────────────────────────────────────────┤
│  Messages      (transcript: WelcomeScreen on first paint;       │
│                 then UserBubble / AssistantBubble)              │
│                                                                  │
│  ThinkingSpinner   (only while agent is working)                 │
├──────────────────────────────────────────────────────────────────┤
│  PromptInput   (marginX 2, marginTop 1)                          │
│  StatusLine    (paddingX 2)                                      │
└──────────────────────────────────────────────────────────────────┘
```

**Spacing scale.** One unit = one terminal cell. Use only the named tokens:

| Token | Cells | Typical use                                 |
| ----- | :---: | ------------------------------------------- |
| `xs`  | 1     | Vertical breathing room between turns       |
| `sm`  | 2     | Horizontal page gutter; tool nesting indent |
| `md`  | 3     | (reserved)                                  |
| `lg`  | 4     | (reserved)                                  |

**Indentation.** Top-level messages sit at `paddingX = sm`. Tool calls under an `AssistantBubble` indent by `sm` per nesting level (`marginLeft = indent × 2`). Tool result lines indent an additional `sm` past their tool header so the `└` aligns under the tool name's first letter, not under the bullet.

**No boxes around messages.** User and assistant messages render as flush text with a left gutter only. Boxes (Ink `borderStyle`) are reserved for future modal surfaces (slash-command picker, permission prompt). Text-level backgrounds (`<Text backgroundColor>`) are *not* boxes and are allowed for role distinction — see `UserBubble`.

## Iconography & Motion

A small, fixed glyph set carries all non-textual meaning. **Color, not shape, distinguishes done from failed.** Both states use `●`.

| Glyph                 | Codepoint(s)                                               | Meaning                                |
| --------------------- | ---------------------------------------------------------- | -------------------------------------- |
| Braille spinner       | `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏` (10 frames)                          | Agent or tool is working               |
| `●`                   | `U+25CF`                                                   | Tool finished (color = `success` or `error`); also the marker on each assistant text block (no color — default foreground). |
| `>`                   | `U+003E`                                                   | User turn (in `UserBubble` and as the prompt prefix) |
| `└`                   | `U+2514`                                                   | Tree connector under a finished tool, leading to its result |
| `│`                   | `U+2502`                                                   | Vertical divider in the two-column header |
| `…`                   | `U+2026`                                                   | Truncation marker; also the placeholder while input is disabled |
| `·`                   | `U+00B7`                                                   | Leading glyph on the thinking indicator line |
| `•`                   | `U+2022`                                                   | List bullet on `WelcomeScreen` rows                                                          |

**Motion.**

- The Braille spinner advances **one frame every 100 ms** via `setInterval`. The same frame array is used by the thinking indicator and by every running `ToolBlock`; do not introduce per-component spinners.
- Assistant text streams **token-by-token** via React re-renders driven by Python-bridge events (`token` event from `bridge.ts`). There is no character-per-frame easing.
- There are no fades, slides, or transitions. State changes are instantaneous.

## Components

Each subsection has: a one-line role, an ASCII anatomy diagram, the state matrix, the Ink prop mapping, and the source file.

### Header

Fixed two-column block at the top of the screen.

```
case-agent                  │  Tips
case: <id>          dim    │  • smart_search — semantic evidence search    dim
model: <model>      dim    │  • read_with_anchor path#anchor — source section    dim
```

| State    | Visual                                                  |
| -------- | ------------------------------------------------------- |
| Visible  | Rendered when `completedMessages.length === 0 && currentAssistant === null && !isThinking` (first paint only). |
| Hidden   | After the first user submission, never re-rendered for the rest of the session. |

**Anatomy.** Outer `<Box flexDirection="row" paddingX={2} paddingY={1}>`. Three children: left column (`flexGrow=1`, `minWidth=28`), divider (`<Text dimColor>│</Text>` inside `paddingX=1`), right column (`flexGrow=1`, `paddingLeft=1`). First line of each column is `header-label`; subsequent lines are `header-meta`.

**Note on tips content.** The right-column bullets advertise this product's flagship tools. They are application content (not chrome) and live as literal strings in `Header.tsx`, not in `theme.ts`. Decision logged 2026-05-07.

**Source.** `src/components/Header.tsx`.

### PromptInput

Bottom-of-screen single-line input, framed with a rounded border in `colors.borderPrompt`.

```
╭──────────────────────────────╮
│ > hello, what evidence…█     │
╰──────────────────────────────╯
```

| State     | Visual                                                              |
| --------- | ------------------------------------------------------------------- |
| Idle      | Border in `colors.borderPrompt` (dim gray). Inside: `>` in `prompt-prefix`, user's typed text, then a single inverted-space cursor. |
| Disabled  | Same border. Inside: bold-dim `>` (no color), no cursor, `…` placeholder appended. The border does not change color on disable. |

**Anatomy.** Single `<Box marginX={spacing.sm} marginTop={spacing.xs} paddingX={spacing.xs} borderStyle="round" borderColor={colors.borderPrompt}>` containing three inline children: prefix `<Text bold color={colors.userPrefix}>{"> "}</Text>` (or `<Text bold dimColor>{"> "}</Text>` when disabled), user value `<Text>{value}</Text>`, and a cursor `<Text inverse>{" "}</Text>` (enabled) or placeholder `<Text dimColor>…</Text>` (disabled). Input is handled via Ink's `useInput`.

**Source.** `src/components/PromptInput.tsx`.

### UserBubble

Renders one user turn in the transcript on a **full-row light-gray bar** so the user's turn is visually distinct from assistant prose.

```
░░> hello, what evidence do we have on X?░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ← row bg = colors.userBubbleBg
```

| State    | Visual                                                                     |
| -------- | -------------------------------------------------------------------------- |
| Default  | Single row (or one row per `\n`-split line of `text`) painted with `colors.user-bubble-bg` from column 0 to the right edge of the terminal. The first row's body is preceded by a `spacing.sm` gutter (rendered as 2 colored spaces) and the bold green `> ` prefix; continuation rows replace the prefix with 2 aligned blank cells. UserBubble does not stream. |

**Anatomy.** Outer `<Box flexDirection="column" marginTop={spacing.xs}>` (no `paddingX` — the bar must reach the left edge). For each line of `text.split("\n")`, render a single `<Text backgroundColor={colors.userBubbleBg}>` whose children are: 2-space gutter, prefix (`<Text bold color={colors.userPrefix}>{"> "}</Text>` on the first line, 2 spaces on continuation lines), then the line padded with spaces to `cols - GUTTER - PREFIX.length` so the gray bar reaches the right edge. Terminal width comes from Ink's `useStdout()` so the bar reflows on resize.

**Wrap behavior.** When a single `\n`-delimited line is wider than `cols`, Ink's automatic wrap kicks in and the wrapped continuation will render only under the text characters (not full-row). User prompts are short enough in practice that this trade-off is acceptable; revisit if multi-line wraps become common.

**Source.** `src/components/UserBubble.tsx`.

### AssistantBubble

Renders one assistant turn as an **ordered list of blocks** that interleave text and tool calls in stream order. Each text block opens with the `●` marker; tool blocks delegate to `<ToolBlock>`.

```
●  Looking at the transcripts now…              ← AssistantTextBlock (default fg)
   ⠋ smart_search "incident timeline"   dim     ← ToolBlock (running)
     └ 12 hits across 3 docs            dim
●  Let me cross-reference the runbook.          ← AssistantTextBlock (default fg)
   ● smart_search "remediation plan"    success
     └ 4 hits across 1 doc              dim
●  Based on the search, the answer is…          ← AssistantTextBlock (default fg)
```

| State           | Visual                                                                                  |
| --------------- | --------------------------------------------------------------------------------------- |
| Streaming       | The trailing text block grows character-by-character as `token` events arrive. New text after a `tool_end` opens a *new* text block, so successive prose segments stay separated. |
| Tools-in-flight | `ToolBlock`s appear inline at the position they were emitted in.                         |
| Done            | All children stable, no spinner.                                                         |

**Anatomy.** `<Box flexDirection="column" marginTop={1} paddingLeft={2}>`. Children: `message.blocks.map(...)` where each text block renders as `<Box flexDirection="row"><Text>● </Text><Text>{text}</Text></Box>` — both children inherit the terminal's default foreground. Each tool block renders as `<ToolBlock tool={...} />`. **No "Assistant:" label.**

**Source.** `src/components/AssistantBubble.tsx`. Block model: `AssistantBlock` discriminated union in `src/types.ts`.

### ToolBlock

Recursive renderer for one tool call (and its sub-tools, if any).

```
⠋ smart_search "incident timeline"            ← header, running
  scanning ingest/2024-q3.md                  ← subagentText tail (last 2 lines, dim)
  parsed 142 items
  ⠙ read_with_anchor docs/runbook.md#step-3   ← nested sub-tool (running)

● smart_search "incident timeline"   success  ← header, done
  └ 12 hits across 3 docs            dim      ← result line
```

| State     | Header                                                       | Body                                                  |
| --------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| Running   | `⠋` (animating, 100 ms/frame, dim) + tool name (dim) + args (dim) | Last 2 non-empty lines of subagent stream (dim, indent +2). Nested sub-tools below. |
| Done      | `●` (success) + tool name (default) + args (dim)             | `└ <one-line result>` (dim, indent +2). No subagent text. |
| Failed    | `●` (error) + tool name (error) + args (dim) + ` · error` (error) | `└ <one-line result>` (error, indent +2).             |

**Anatomy.** `<Box flexDirection="column" marginLeft={indent * 2}>`. The header row is a single `<Box>` with three or four `<Text>` children. Below it: optional subagent tail box (running only), zero-or-more nested `<ToolBlock indent={indent+1}>`, and optional result box (done or failed).

**Truncation.** `args` truncate at 60 chars + `…`; `result` truncates at 80 chars + `…` and shows only the first newline-delimited line.

**Source.** `src/components/ToolBlock.tsx`.

### ThinkingSpinner

Single line shown between the transcript and the prompt while the agent is working but has not yet produced any tool call or token.

```
  · ⠋ Thinking… (3s)        dim
```

| State     | Visual                                                 |
| --------- | ------------------------------------------------------ |
| Visible   | `paddingX=2 marginTop=1`, all dim, frame advances every 100 ms, elapsed seconds tick every 100 ms. |
| Hidden    | Not rendered when `isThinking === false`.              |

**Anatomy.** `<Box paddingX={2} marginTop={1}><Text dimColor>· {frame} Thinking… ({elapsed}s)</Text></Box>`.

**Source.** `src/components/ThinkingSpinner.tsx`.

### WelcomeScreen

First-paint intro panel that lists the agent's tools (grouped), subagents, and key bindings. Hides as soon as the user submits the first prompt.

```
╭───────────────────────────────────────────────────────────╮
│ case-agent                                                │
│ 변호사 대상 case research · artifact 작성 에이전트.            │
│                                                           │
│ Tools                                                     │
│  • Search    smart_search · read_with_anchor · list_evidence
│  • Verify    verify_citations · check_completeness        │
│  • Compute   calculate                                    │
│  • Memory    read_memory_index · read_memory · write_memory
│  • Plan      enter_strategy_mode · exit_strategy_mode     │
│  • Tasks     write_todos                                  │
│ Subagents                                                 │
│  • explore   task("explore", ...)                         │
│                                                           │
│ Keys      Enter send  ·  Ctrl+C quit                      │
╰───────────────────────────────────────────────────────────╯
```

| State    | Visual                                                  |
| -------- | ------------------------------------------------------- |
| Visible  | Rendered when `completedMessages.length === 0 && currentAssistant === null && !isThinking`. |
| Hidden   | After the first user submission, never re-rendered for the rest of the session. |

**Anatomy.** `<Box flexDirection="column" marginX={spacing.sm} marginTop={spacing.xs} paddingX={spacing.xs} borderStyle="round" borderColor={colors.borderPrompt}>` containing: bold title, dim description, then two grouped sub-`<Box flexDirection="column">`s (Tools, Subagents) where each row is `<Box flexDirection="row">` with a dim `•` bullet, a default-color label, and a dim items string. A trailing dim `Keys` line.

**Tool-list source.** Hardcoded inside the component. Mirrors `case_agent/agent.py:78-90` (the `case_tools` list assembled in `build_case_agent_components`). Manual sync required when the Python registry changes — see Gaps.

**Source.** `src/components/WelcomeScreen.tsx`.

### StatusLine

Bottom-most chrome line. Today only shows a quit hint; future iterations will mirror Claude Code's `model · tokens · mode` line.

```
  ctrl+c to quit            dim
```

**Anatomy.** `<Box paddingX={spacing.sm}><Text dimColor>{children ?? "ctrl+c to quit"}</Text></Box>`. Accepts optional `children` so future iterations can compose `model · tokens · mode` without changing the call site.

**Source.** `src/components/StatusLine.tsx`.

## Do's and Don'ts

**Do**

- Reach for `text-dim` first. Most chrome should be dim.
- Use `<Text bold>` only for header labels and the prompt prefix.
- Use color exclusively for: user prefix (`user-prefix`) and state events (`success`, `error`). Assistant text uses the terminal's default foreground.
- Keep one visible spinner at a time. The thinking indicator hides as soon as a `token` or `tool_start` event arrives.
- Truncate aggressively (60 chars args, 80 chars result, 2 lines subagent tail). Long lines kill scannability.
- When adding a new component, define its tokens here _before_ writing the `.tsx`.

**Don't**

- Don't wrap user or assistant messages in `borderStyle`. Boxes are reserved for modal surfaces.
- Don't use a second accent color besides `brand` for non-state content. New visual signals belong in the existing dim/state palette.
- Don't combine `dimColor` with a non-default `color` prop unless explicitly listed in the typography table.
- Don't add per-component spinner timing. Reuse `100 ms / 10-frame Braille`.
- Don't render an "Assistant:" or "User:" label. The prefix glyphs (`>` and color) carry the role.
- Don't introduce ANSI 16-color fallbacks in v1; keep all values truecolor RGB or `ansi:greenBright` (Ink already degrades gracefully).

## Gaps from current implementation

Snapshot of divergences between this spec and `tui-ts/src/components/*.tsx`. Items checked off were closed in the 2026-05-07 implementation pass.

- [x] **`AssistantBubble` reverted to default foreground (2026-05-07).** Earlier `colors.brand` orange was dropped from both the `●` marker and the text body per user request — the TUI now adapts to light/dark terminals. `colors.brand` becomes a reserved token.
- [x] **Tokenized color source.** `src/theme.ts` exports `colors`, `glyphs`, `spacing`, `truncate`. All components import from it; no Ink color literals (`green`/`red`/`white`/`gray`) remain in `src/components/`.
- [x] **`PromptInput` prefix matches `UserBubble`.** `src/components/PromptInput.tsx` now renders bold `colors.userPrefix` when enabled and bold `dimColor` when disabled.
- [x] **Header model is wired.** `src/index.tsx` parses `--model <name>` (default `claude-sonnet-4-6`) and threads it `App → Header`.
- [x] **`ToolBlock` subagent tail truncates per-line at 80 chars.** Implemented via `truncate.subagentLineWidth` + a `clampLine` helper in `src/components/ToolBlock.tsx`.
- [x] **`StatusLine` extracted.** `src/components/StatusLine.tsx` accepts optional `children` for future composition.
- [x] **`ThinkingSpinner` extracted.** `src/components/ThinkingSpinner.tsx` owns the inline implementation.
- [x] **Single spinner frame array.** Both consumers (`ToolBlock`, `ThinkingSpinner`) import `glyphs.spinnerFrames` from `theme.ts`. `grep -RnE '⠋|⠙|⠹' src/` matches `theme.ts` only.
- [x] **Assistant text blocks render in stream order with `●` marker (fixed 2026-05-07).** `Message` is now a discriminated union with `AssistantBlock[]`; post-tool text no longer collapses into one segment.
- [x] **`PromptInput` rounded border added (2026-05-07).** `borderStyle="round"` + `colors.borderPrompt` per user request; `paddingX={spacing.xs}` inside the frame.
- [x] **`WelcomeScreen` first-paint panel added (2026-05-07).** Rounded box listing tools (6 groups), subagents (`explore`), and key bindings; hides after the first submit.

Decisions logged (not gaps):

- **Header right-column tips kept as tool advertising.** Decision 2026-05-07 — content is product-specific and stays in `Header.tsx`. Future slash-command picker may absorb it.
- **Header gated on `showWelcome` (2026-05-07, supersedes the previous "always visible" stance).** The entire Header (case/model on the left, Tips on the right) renders only at first paint and disappears together with `WelcomeScreen` once the user submits their first prompt. User report: Ink's overflow-into-scrollback caused the Header to appear "again" below the welcome panel as the first response grew the active render. case/model is intentionally **not** mirrored into `StatusLine` — user picked the most minimal option.

Open / future work:

- [ ] **Reserved tokens** — `brandShimmer`, `borderPrompt`, `warning`, `permission`, `planMode` are declared in `theme.ts` but unused. Placeholders for streaming shimmer, prompt focus border, warnings, permission prompts, plan mode.
- [ ] **Live model from Python `meta` event.** Today `--model` is a CLI hint with no enforcement. A future Python-side change can emit the active model as a stream event so the header reflects reality on model swaps.
- [ ] **`StatusLine` content beyond the quit hint.** `model · tokens · mode` follows once the bridge surfaces those fields.
- [ ] **`WelcomeScreen` tool list is hardcoded.** Drift risk vs. `case_agent/agent.py:78-90`. A future Python `meta` stream event listing registered tools/subagents on startup would let the welcome reflect runtime reality.
