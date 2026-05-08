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
  return n.toLocaleString();
}

export function StatusLine({ children, planMode = false, tokenUsage }: Props) {
  const hasTokens = tokenUsage && (tokenUsage.input > 0 || tokenUsage.output > 0);
  const tokenText = hasTokens
    ? `↑${fmt(tokenUsage.input)} ↓${fmt(tokenUsage.output)} tokens${tokenUsage.cacheRead > 0 ? ` (${fmt(tokenUsage.cacheRead)} cached)` : ""}`
    : "";

  return (
    <Box paddingX={spacing.sm} justifyContent="space-between">
      {planMode ? (
        <Text color={colors.planMode}>⏵⏵ plan mode on · shift+tab to exit</Text>
      ) : (
        <Text dimColor>{children ?? "ctrl+c to quit · shift+tab for plan mode"}</Text>
      )}
      {hasTokens && <Text dimColor>{tokenText}</Text>}
    </Box>
  );
}
