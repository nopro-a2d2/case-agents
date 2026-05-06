import React from "react";
import { Box, Text } from "ink";

interface Props {
  text: string;
}

export function UserBubble({ text }: Props) {
  return (
    <Box flexDirection="row" marginTop={1} paddingX={2}>
      <Text bold color="green">{">"} </Text>
      <Text>{text}</Text>
    </Box>
  );
}
