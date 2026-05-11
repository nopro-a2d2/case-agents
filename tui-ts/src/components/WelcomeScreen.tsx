import React from "react";
import { Box, Text } from "ink";
import { colors, glyphs, spacing } from "../theme.js";

const TOOL_GROUPS: Array<{ label: string; items: string }> = [
  { label: "Search ", items: "smart_search · read_evidence · list_evidence" },
  { label: "Verify ", items: "verify_citations · check_completeness" },
  { label: "Compute", items: "calculate" },
  { label: "Memory ", items: "read_memory_index · read_memory · write_memory" },
  { label: "Plan   ", items: "enter_strategy_mode · exit_strategy_mode" },
  { label: "Tasks  ", items: "write_todos" },
];

export function WelcomeScreen() {
  return (
    <Box
      flexDirection="column"
      marginX={spacing.sm}
      marginTop={spacing.xs}
      paddingX={spacing.xs}
      borderStyle="round"
      borderColor={colors.borderPrompt}
    >
      <Text bold>case-agent</Text>
      <Text dimColor>변호사 대상 case research · artifact 작성 에이전트.</Text>

      <Box marginTop={spacing.xs} flexDirection="column">
        <Text bold>Tools</Text>
        {TOOL_GROUPS.map((g) => (
          <Box key={g.label} flexDirection="row">
            <Text dimColor> {glyphs.listBullet} </Text>
            <Text>{g.label}</Text>
            <Text dimColor>  {g.items}</Text>
          </Box>
        ))}
      </Box>

      <Box marginTop={spacing.xs} flexDirection="column">
        <Text bold>Subagents</Text>
        <Box flexDirection="row">
          <Text dimColor> {glyphs.listBullet} </Text>
          <Text>explore</Text>
          <Text dimColor>  task("explore", ...)</Text>
        </Box>
      </Box>

      <Box marginTop={spacing.xs}>
        <Text dimColor>Keys      Enter send  ·  Ctrl+C quit</Text>
      </Box>
    </Box>
  );
}
