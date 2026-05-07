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

function fmtOutput(v: unknown): string {
  let s: string;
  if (typeof v === "string") s = v.trim();
  else { try { s = JSON.stringify(v); } catch { s = String(v); } }
  const first = s.split("\n")[0] ?? "";
  return first.length > truncate.toolResult
    ? first.slice(0, truncate.toolResult) + glyphs.ellipsis
    : first;
}

function clampLine(line: string): string {
  return line.length > truncate.subagentLineWidth
    ? line.slice(0, truncate.subagentLineWidth) + glyphs.ellipsis
    : line;
}

export function ToolBlock({ tool, indent = 0 }: Props) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (tool.status !== "running") return;
    const t = setInterval(
      () => setFrame((f) => (f + 1) % glyphs.spinnerFrames.length),
      glyphs.spinnerIntervalMs,
    );
    return () => clearInterval(t);
  }, [tool.status]);

  const running = tool.status === "running";
  const failed  = tool.status === "failed";
  const done    = tool.status === "done";
  const inputStr = fmtInput(tool.input);

  const subagentTail = running
    ? tool.subagentText
        .split("\n")
        .filter(Boolean)
        .slice(-truncate.subagentTailLines)
        .map(clampLine)
        .join("\n")
    : "";

  return (
    <Box flexDirection="column" marginLeft={indent * spacing.sm}>
      {/* Tool header line: spinner/bullet + name + input hint */}
      <Box>
        {running
          ? <Text dimColor>{glyphs.spinnerFrames[frame]} </Text>
          : <Text color={failed ? colors.error : colors.success}>{failed ? glyphs.bulletFailed : glyphs.bulletDone} </Text>
        }
        <Text dimColor={running} color={failed ? colors.error : undefined}>
          {tool.name}
        </Text>
        {inputStr !== "" && <Text dimColor> {inputStr}</Text>}
        {failed && <Text color={colors.error}> · error</Text>}
      </Box>

      {/* Subagent streaming text (last few lines while running) */}
      {subagentTail !== "" && (
        <Box marginLeft={spacing.sm}>
          <Text dimColor>{subagentTail}</Text>
        </Box>
      )}

      {/* Nested sub-tools */}
      {Array.from(tool.subTools.values()).map((sub) => (
        <ToolBlock key={sub.id} tool={sub} indent={indent + 1} />
      ))}

      {/* Result line with tree connector */}
      {done && (
        <Box marginLeft={spacing.sm}>
          <Text dimColor>{glyphs.treeConnector} </Text>
          <Text dimColor>{tool.output != null ? fmtOutput(tool.output) : "Done"}</Text>
        </Box>
      )}
      {failed && tool.output != null && (
        <Box marginLeft={spacing.sm}>
          <Text dimColor>{glyphs.treeConnector} </Text>
          <Text color={colors.error}>{fmtOutput(tool.output)}</Text>
        </Box>
      )}
    </Box>
  );
}
