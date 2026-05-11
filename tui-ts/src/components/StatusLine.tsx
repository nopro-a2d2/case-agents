import React from "react";
import { Box, Text } from "ink";
import { colors, spacing } from "../theme.js";
import type { ModeState } from "../mode.js";

interface Props {
  children?: React.ReactNode;
  mode?: ModeState;
}

export function StatusLine({ children, mode = "normal" }: Props) {
  return (
    <Box paddingX={spacing.sm}>
      {mode === "strategy" ? (
        <Text color={colors.planMode}>⏵⏵ strategy mode on · shift+tab → brief</Text>
      ) : mode === "brief" ? (
        <Text color={colors.briefMode}>✎ brief mode on · shift+tab → normal</Text>
      ) : (
        <Text dimColor>{children ?? "ctrl+c to quit · shift+tab cycle (normal → strategy → brief)"}</Text>
      )}
    </Box>
  );
}
