import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ToolCallState } from "../types.js";
import { colors, glyphs, spacing, truncate } from "../theme.js";

interface Props {
  tool: ToolCallState;
  indent?: number;
}

function fmtInput(input: unknown): string {
  if (input == null) return "";
  if (typeof input === "string") {
    const s = input.trim().replace(/\s+/g, " ");
    return s.length > truncate.toolArgs ? s.slice(0, truncate.toolArgs) + glyphs.ellipsis : s;
  }
  if (typeof input === "object") {
    const vals = Object.values(input as Record<string, unknown>);
    if (vals.length > 0 && typeof vals[0] === "string") {
      const s = (vals[0] as string).trim().replace(/\s+/g, " ");
      return s.length > truncate.toolArgs ? s.slice(0, truncate.toolArgs) + glyphs.ellipsis : s;
    }
    try {
      const s = JSON.stringify(input);
      return s.length > truncate.toolArgs ? s.slice(0, truncate.toolArgs) + glyphs.ellipsis : s;
    } catch { return ""; }
  }
  return String(input).slice(0, truncate.toolArgs);
}

export function ToolBlock({ tool, indent = 0 }: Props) {
  const [frame, setFrame] = useState(0);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    if (tool.status !== "running") return;
    const t = setInterval(
      () => setFrame((f) => (f + 1) % glyphs.spinnerFrames.length),
      glyphs.spinnerIntervalMs,
    );
    return () => clearInterval(t);
  }, [tool.status]);

  // Slow pulse while running — Ink has no opacity, so we toggle dimColor.
  useEffect(() => {
    if (tool.status !== "running") {
      setPulse(false);
      return;
    }
    const t = setInterval(() => setPulse((p) => !p), 800);
    return () => clearInterval(t);
  }, [tool.status]);

  const running = tool.status === "running";
  const failed  = tool.status === "failed";
  const done    = tool.status === "done";
  const inputStr = fmtInput(tool.input);
  const display  = tool.display;
  const headerColor = failed ? colors.error : done ? colors.success : undefined;
  const headerDim = running && pulse;

  return (
    <Box flexDirection="column" marginLeft={indent * spacing.sm}>
      {/* Tool header line: spinner/bullet + name + input hint */}
      <Box>
        {running
          ? <Text dimColor={headerDim}>{glyphs.spinnerFrames[frame]} </Text>
          : <Text color={headerColor}>{failed ? glyphs.bulletFailed : glyphs.bulletDone} </Text>
        }
        {display ? (
          <>
            <Text dimColor={headerDim} color={headerColor}>
              {display.action}
            </Text>
            <Text dimColor> - {display.subject}</Text>
          </>
        ) : (
          <>
            <Text dimColor={headerDim} color={headerColor}>
              {tool.name}
            </Text>
            {inputStr !== "" && <Text dimColor> {inputStr}</Text>}
          </>
        )}
        {failed && <Text color={colors.error}> · error</Text>}
      </Box>

      {/* Subagent's interleaved text + sub-tools (main-agent-style streaming) */}
      {tool.subBlocks.map((blk, i) =>
        blk.kind === "text" ? (
          blk.text === "" ? null : (
            <Box key={i} marginLeft={spacing.sm}>
              <Text>{blk.text}</Text>
            </Box>
          )
        ) : (
          <ToolBlock key={i} tool={blk.tool} indent={indent + 1} />
        ),
      )}
    </Box>
  );
}
