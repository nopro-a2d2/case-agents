import React, { useEffect, useRef, useState } from "react";
import { Box, Text } from "ink";
import { glyphs, spacing } from "../theme.js";

interface Props {
  outputTokens?: number;
}

export function ThinkingSpinner({ outputTokens = 0 }: Props) {
  const [frame, setFrame] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const t = setInterval(() => {
      setFrame((f) => (f + 1) % glyphs.spinnerFrames.length);
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, glyphs.spinnerIntervalMs);
    return () => clearInterval(t);
  }, []);

  const tokenSuffix = outputTokens > 0
    ? ` · ↓ ${outputTokens.toLocaleString("en-US")} tokens`
    : "";

  return (
    <Box paddingX={spacing.sm} marginTop={spacing.xs}>
      <Text dimColor>
        {glyphs.thinkingDot} {glyphs.spinnerFrames[frame]} Thinking… ({elapsed}s{tokenSuffix})
      </Text>
    </Box>
  );
}
