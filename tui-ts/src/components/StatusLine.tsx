import React from "react";
import { Box, Text } from "ink";
import { colors, spacing } from "../theme.js";

interface TokenUsage {
  input: number;
  output: number;
  cacheRead: number;
}

interface Props {
  children?: React.ReactNode;
  planMode?: boolean;
  tokenUsage?: TokenUsage;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

export function StatusLine({ children, planMode = false, tokenUsage }: Props) {
  const hasUsage = tokenUsage && (tokenUsage.input > 0 || tokenUsage.output > 0);
  const usageText = hasUsage
    ? `↑${fmt(tokenUsage.input)} ↓${fmt(tokenUsage.output)} tokens${tokenUsage.cacheRead > 0 ? ` (${fmt(tokenUsage.cacheRead)} cached)` : ""}`
    : null;

  return (
    <Box paddingX={spacing.sm} justifyContent="space-between">
      {planMode ? (
        <Text color={colors.planMode}>⏵⏵ plan mode on · shift+tab to exit</Text>
      ) : (
        <Text dimColor>{children ?? "ctrl+c to quit · shift+tab for plan mode"}</Text>
      )}
      {usageText && <Text dimColor>{usageText}</Text>}
    </Box>
  );
}
