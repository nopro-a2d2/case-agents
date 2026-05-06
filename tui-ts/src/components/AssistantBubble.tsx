import React from "react";
import { Box, Text } from "ink";
import type { Message } from "../types.js";
import { ToolBlock } from "./ToolBlock.js";

interface Props {
  message: Message;
}

export function AssistantBubble({ message }: Props) {
  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      {message.preText && <Text>{message.preText}</Text>}
      {Array.from(message.toolCalls.values()).map((tool) => (
        <ToolBlock key={tool.id} tool={tool} />
      ))}
      {message.postText && <Text>{message.postText}</Text>}
    </Box>
  );
}
