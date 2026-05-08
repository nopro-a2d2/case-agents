import React from "react";
import { Box, Text } from "ink";
import { colors, spacing } from "../theme.js";

interface Props {
  children?: React.ReactNode;
  planMode?: boolean;
}

export function StatusLine({ children, planMode = false }: Props) {
  return (
    <Box paddingX={spacing.sm}>
      {planMode ? (
        <Text color={colors.planMode}>⏵⏵ plan mode on · shift+tab to exit</Text>
      ) : (
        <Text dimColor>{children ?? "ctrl+c to quit · shift+tab for plan mode"}</Text>
      )}
    </Box>
  );
}
