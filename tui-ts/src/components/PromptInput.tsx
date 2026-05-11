import React, { useEffect, useMemo, useState } from "react";
import { Box, Text, useInput, useStdout } from "ink";
import { colors, glyphs, spacing } from "../theme.js";
import type { ModeState } from "../mode.js";
import type { SkillEntry } from "../types.js";

interface Props {
  onSubmit: (value: string) => void;
  onAbort?: () => void;
  disabled?: boolean;
  mode?: ModeState;
  skills?: SkillEntry[];
}

const MAX_VISIBLE = 12;
const NAME_GUTTER = 28;

function pad(s: string, n: number): string {
  return s.length >= n ? s + "  " : s + " ".repeat(n - s.length);
}

function truncate(s: string, n: number): string {
  if (n <= 1) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

// Word boundary: skip whitespace then skip non-whitespace.
function prevWordBoundary(s: string, i: number): number {
  let j = i;
  while (j > 0 && /\s/.test(s[j - 1]!)) j--;
  while (j > 0 && !/\s/.test(s[j - 1]!)) j--;
  return j;
}
function nextWordBoundary(s: string, i: number): number {
  let j = i;
  while (j < s.length && /\s/.test(s[j]!)) j++;
  while (j < s.length && !/\s/.test(s[j]!)) j++;
  return j;
}

// Raw escape sequences Ink doesn't decode into Key flags.
const SEQ_HOME = new Set(["\x1b[H", "\x1b[1~", "\x1b[7~", "\x1bOH"]);
const SEQ_END = new Set(["\x1b[F", "\x1b[4~", "\x1b[8~", "\x1bOF"]);
const SEQ_CTRL_LEFT = new Set(["\x1b[1;5D", "\x1b[5D", "\x1bOd"]);
const SEQ_CTRL_RIGHT = new Set(["\x1b[1;5C", "\x1b[5C", "\x1bOc"]);
const SEQ_DELETE = new Set(["\x1b[3~"]);

export function PromptInput({
  onSubmit,
  onAbort,
  disabled = false,
  mode = "normal",
  skills = [],
}: Props) {
  const [value, setValue] = useState("");
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState(0);
  const { stdout } = useStdout();

  // 부모가 turn을 시작(disabled=true)하면 stdin race와 무관하게 입력창을 강제로 비운다.
  useEffect(() => {
    if (disabled) {
      setValue("");
      setCursor(0);
    }
  }, [disabled]);

  const matches = useMemo(() => {
    if (!value.startsWith("/") || value.includes(" ")) return [] as SkillEntry[];
    const token = value.slice(1).toLowerCase();
    if (token === "") return skills.slice(0, MAX_VISIBLE); // backend order (builtins first)
    const filtered = skills.filter((s) => s.name.toLowerCase().includes(token));
    filtered.sort((a, b) => {
      const ap = a.name.toLowerCase().startsWith(token) ? 0 : 1;
      const bp = b.name.toLowerCase().startsWith(token) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return a.name.localeCompare(b.name);
    });
    return filtered.slice(0, MAX_VISIBLE);
  }, [value, skills]);
  const open = matches.length > 0;

  useEffect(() => {
    setSelected(0);
  }, [matches.length, value]);

  const completeWith = (entry: SkillEntry) => {
    const next = `/${entry.name} `;
    setValue(next);
    setCursor(next.length);
  };

  useInput((input, key) => {
    if (disabled) {
      if (key.escape) onAbort?.();
      return;
    }
    if (open) {
      if (key.downArrow) {
        setSelected((i) => (i + 1) % matches.length);
        return;
      }
      if (key.upArrow) {
        setSelected((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (key.tab) {
        completeWith(matches[selected]);
        return;
      }
      if (key.return) {
        completeWith(matches[selected]);
        return;
      }
      if (key.escape) {
        setValue("");
        setCursor(0);
        return;
      }
    }

    // Raw escape sequences Ink doesn't decode (Home/End/Ctrl+Arrow/Delete).
    if (input && input.startsWith("\x1b")) {
      if (SEQ_HOME.has(input)) { setCursor(0); return; }
      if (SEQ_END.has(input)) { setCursor(value.length); return; }
      if (SEQ_CTRL_LEFT.has(input)) { setCursor((c) => prevWordBoundary(value, c)); return; }
      if (SEQ_CTRL_RIGHT.has(input)) { setCursor((c) => nextWordBoundary(value, c)); return; }
      if (SEQ_DELETE.has(input)) {
        setValue((v) => {
          const c = clamp(cursor, 0, v.length);
          if (c >= v.length) return v;
          return v.slice(0, c) + v.slice(c + 1);
        });
        return;
      }
      // Unknown ESC sequence — swallow so it doesn't get inserted as junk.
      return;
    }

    if (key.leftArrow) {
      if (key.ctrl || key.meta) setCursor((c) => prevWordBoundary(value, c));
      else setCursor((c) => clamp(c - 1, 0, value.length));
      return;
    }
    if (key.rightArrow) {
      if (key.ctrl || key.meta) setCursor((c) => nextWordBoundary(value, c));
      else setCursor((c) => clamp(c + 1, 0, value.length));
      return;
    }

    if (key.ctrl && input === "a") { setCursor(0); return; }
    if (key.ctrl && input === "e") { setCursor(value.length); return; }
    if (key.meta && input === "b") { setCursor((c) => prevWordBoundary(value, c)); return; }
    if (key.meta && input === "f") { setCursor((c) => nextWordBoundary(value, c)); return; }
    if (key.ctrl && input === "w") {
      const c = clamp(cursor, 0, value.length);
      const start = prevWordBoundary(value, c);
      setValue(value.slice(0, start) + value.slice(c));
      setCursor(start);
      return;
    }

    if (key.return) {
      const trimmed = value.trim();
      if (trimmed) {
        setValue("");
        setCursor(0);
        onSubmit(trimmed);
      }
      return;
    }
    // Most terminals send 0x7f (DEL) for the Backspace key, which Ink reports
    // as key.delete. The actual Forward Delete key sends ESC[3~ and is handled
    // by SEQ_DELETE above. So treat both flags as backspace here.
    if (key.backspace || key.delete) {
      const c = clamp(cursor, 0, value.length);
      if (c === 0) return;
      setValue(value.slice(0, c - 1) + value.slice(c));
      setCursor(c - 1);
      return;
    }
    if (!key.ctrl && !key.meta && input) {
      const c = clamp(cursor, 0, value.length);
      setValue(value.slice(0, c) + input + value.slice(c));
      setCursor(c + input.length);
    }
  });

  // Terminal columns drive description truncation so the picker never wraps.
  // Margin 2 + name gutter + 1 padding column = chrome reserved.
  const cols = stdout?.columns ?? 80;
  const descBudget = Math.max(10, cols - NAME_GUTTER - spacing.sm * 2 - 1);

  return (
    <Box flexDirection="column">
      {open && (
        <Box flexDirection="column" marginX={spacing.sm} marginTop={spacing.xs}>
          {matches.map((s, i) => {
            const isSelected = i === selected;
            const namePadded = pad(`/${s.name}`, NAME_GUTTER);
            const descTrunc = truncate(s.description ?? "", descBudget);
            return (
              <Box key={`${s.kind ?? "skill"}:${s.name}`}>
                <Text color={isSelected ? colors.suggestion : undefined}>
                  {namePadded}
                </Text>
                <Text
                  color={isSelected ? colors.suggestion : undefined}
                  dimColor={!isSelected}
                >
                  {descTrunc}
                </Text>
              </Box>
            );
          })}
        </Box>
      )}

      <Box
        marginX={spacing.sm}
        marginTop={spacing.xs}
        paddingX={spacing.xs}
        borderStyle="round"
        borderColor={mode === "strategy" ? colors.planMode : mode === "brief" ? colors.briefMode : colors.borderPrompt}
      >
        {disabled
          ? <Text bold dimColor>{glyphs.userPrefix} </Text>
          : <Text bold color={colors.userPrefix}>{glyphs.userPrefix} </Text>
        }
        {disabled ? (
          <>
            <Text>{value}</Text>
            <Text dimColor>{glyphs.ellipsis}</Text>
          </>
        ) : (() => {
          const c = clamp(cursor, 0, value.length);
          const before = value.slice(0, c);
          const at = value.slice(c, c + 1) || " ";
          const after = value.slice(c + 1);
          return (
            <>
              <Text>{before}</Text>
              <Text inverse>{at}</Text>
              <Text>{after}</Text>
            </>
          );
        })()}
      </Box>
    </Box>
  );
}
