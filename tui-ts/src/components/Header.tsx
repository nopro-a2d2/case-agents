import React from "react";
import { Box, Text } from "ink";
import { glyphs, spacing } from "../theme.js";

interface Props {
  caseId: string;
  model: string;
}

export function Header({ caseId, model }: Props) {
  return (
    <Box flexDirection="row" paddingX={spacing.sm} paddingY={spacing.xs}>
      <Box flexDirection="column" flexGrow={1} minWidth={28}>
        <Text bold>case-agent</Text>
        <Text dimColor>case: {caseId}</Text>
        <Text dimColor>model: {model}</Text>
      </Box>

      <Box paddingX={spacing.xs}>
        <Text dimColor>{glyphs.divider}</Text>
      </Box>

      <Box flexDirection="column" flexGrow={1} paddingLeft={spacing.xs}>
        <Text bold>Tips</Text>
        <Text dimColor>• smart_search — semantic evidence search</Text>
        <Text dimColor>• read_evidence @@[id] — source section</Text>
      </Box>
    </Box>
  );
}
