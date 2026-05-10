import React, { useEffect, useMemo, useState } from "react";
import { Box, Text, useInput, useStdout } from "ink";
import { colors, glyphs, spacing } from "../theme.js";
import type { SkillEntry } from "../types.js";

interface Props {
  onSubmit: (value: string) => void;
  onAbort?: () => void;
  disabled?: boolean;
  planMode?: boolean;
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

export function PromptInput({
  onSubmit,
  onAbort,
  disabled = false,
  planMode = false,
  skills = [],
}: Props) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState(0);
  const { stdout } = useStdout();

  // 부모가 turn을 시작(disabled=true)하면 stdin race와 무관하게 입력창을 강제로 비운다.
  useEffect(() => {
    if (disabled) setValue("");
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
    setValue(`/${entry.name} `);
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
        return;
      }
    }
    if (key.return) {
      const trimmed = value.trim();
      if (trimmed) {
        setValue("");
        onSubmit(trimmed);
      }
      return;
    }
    if (key.backspace || key.delete) {
      setValue((v) => v.slice(0, -1));
      return;
    }
    if (!key.ctrl && !key.meta && input) {
      setValue((v) => v + input);
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
        borderColor={planMode ? colors.planMode : colors.borderPrompt}
      >
        {disabled
          ? <Text bold dimColor>{glyphs.userPrefix} </Text>
          : <Text bold color={colors.userPrefix}>{glyphs.userPrefix} </Text>
        }
        <Text>{value}</Text>
        {!disabled && <Text inverse>{" "}</Text>}
        {disabled && <Text dimColor>{glyphs.ellipsis}</Text>}
      </Box>
    </Box>
  );
}
