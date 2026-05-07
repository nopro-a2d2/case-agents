import React from "react";
import { Box, Text, useStdout } from "ink";
import { colors, glyphs, spacing } from "../theme.js";

interface Props {
  text: string;
}

const GUTTER = spacing.sm;
const PREFIX = `${glyphs.userPrefix} `;

export function UserBubble({ text }: Props) {
  const { stdout } = useStdout();
  const cols = stdout?.columns ?? 80;
  const lines = text.split("\n");
  const innerWidth = Math.max(0, cols - GUTTER - PREFIX.length);

  return (
    <Box flexDirection="column" marginTop={spacing.xs}>
      {lines.map((line, i) => {
        const padded = line.padEnd(innerWidth, " ");
        return (
          <Text key={i} backgroundColor={colors.userBubbleBg}>
            {" ".repeat(GUTTER)}
            {i === 0
              ? <Text bold color={colors.userPrefix}>{PREFIX}</Text>
              : " ".repeat(PREFIX.length)}
            {padded}
          </Text>
        );
      })}
    </Box>
  );
}
