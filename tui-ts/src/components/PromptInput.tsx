import React, { useEffect, useState } from "react";
import { Box, Text, useInput } from "ink";
import { colors, glyphs, spacing } from "../theme.js";

interface Props {
  onSubmit: (value: string) => void;
  onAbort?: () => void;
  disabled?: boolean;
  planMode?: boolean;
}

export function PromptInput({ onSubmit, onAbort, disabled = false, planMode = false }: Props) {
  const [value, setValue] = useState("");

  // 부모가 turn을 시작(disabled=true)하면 stdin race와 무관하게 입력창을 강제로 비운다.
  useEffect(() => {
    if (disabled) setValue("");
  }, [disabled]);

  useInput((input, key) => {
    if (disabled) {
      if (key.escape) onAbort?.();
      return;
    }
    if (key.return) {
      const trimmed = value.trim();
      if (trimmed) { setValue(""); onSubmit(trimmed); }
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

  return (
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
  );
}
