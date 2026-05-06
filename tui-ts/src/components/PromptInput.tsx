import React, { useState } from "react";
import { Box, Text, useInput } from "ink";

interface Props {
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function PromptInput({ onSubmit, disabled = false }: Props) {
  const [value, setValue] = useState("");

  useInput((input, key) => {
    if (disabled) return;
    if (key.return) {
      const trimmed = value.trim();
      if (trimmed) { onSubmit(trimmed); setValue(""); }
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
    <Box flexDirection="row" paddingX={2} marginTop={1}>
      <Text bold color="green">{">"} </Text>
      <Text>{value}</Text>
      {!disabled && <Text inverse>{" "}</Text>}
      {disabled && <Text dimColor>{"…"}</Text>}
    </Box>
  );
}
