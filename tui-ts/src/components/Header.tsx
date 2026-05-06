import React from "react";
import { Box, Text } from "ink";

interface Props {
  caseId: string;
}

export function Header({ caseId }: Props) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box paddingX={2} paddingY={0}>
        <Text bold>case-agent</Text>
        <Text dimColor>{"  "}{caseId}</Text>
      </Box>

      <Box flexDirection="row" paddingX={2} paddingTop={1} paddingBottom={1}>
        <Box flexDirection="column" flexGrow={1} minWidth={28}>
          <Text bold>Welcome back!</Text>
          <Text dimColor>case: {caseId}</Text>
          <Text dimColor>model: claude-sonnet-4-6</Text>
        </Box>

        <Box paddingX={1}>
          <Text dimColor>│</Text>
        </Box>

        <Box flexDirection="column" flexGrow={1} paddingLeft={1}>
          <Text bold>Tips for getting started</Text>
          <Text dimColor>• smart_search — semantic evidence search</Text>
          <Text dimColor>• read_with_anchor path#anchor — read a source section</Text>
          <Box
            borderStyle="single"
            borderLeft
            borderTop={false}
            borderBottom={false}
            borderRight={false}
            borderColor="yellow"
            paddingLeft={1}
            marginTop={1}
          >
            <Text color="yellow">What{"'"}s new  </Text>
            <Text dimColor>check CLAUDE.md for latest agent updates</Text>
          </Box>
        </Box>
      </Box>

      <Box paddingX={2}>
        <Text dimColor>{"─".repeat(60)}</Text>
      </Box>
    </Box>
  );
}
