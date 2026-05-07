import React from "react";
import { Box, Text } from "ink";
import type { Message } from "../types.js";
import { glyphs, spacing } from "../theme.js";
import { ToolBlock } from "./ToolBlock.js";

interface Props {
  message: Extract<Message, { role: "assistant" }>;
}

function AssistantTextBlock({ text }: { text: string }) {
  if (text === "") return null;
  return (
    <Box flexDirection="row">
      <Text>{glyphs.assistantMarker} </Text>
      <Text>{text}</Text>
    </Box>
  );
}

export function AssistantBubble({ message }: Props) {
  return (
    <Box flexDirection="column" marginTop={spacing.xs} paddingLeft={spacing.sm}>
      {message.blocks.map((block, i) =>
        block.kind === "text"
          ? <AssistantTextBlock key={i} text={block.text} />
          : <ToolBlock key={i} tool={block.tool} />
      )}
    </Box>
  );
}
