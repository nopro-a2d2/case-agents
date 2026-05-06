import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ToolCallState } from "../types.js";

interface Props {
  tool: ToolCallState;
  indent?: number;
}

const SPINNER = ["⣾","⣽","⣻","⢿","⡿","⣟","⣯","⣷"];
const TRUNCATE = 160;

function fmtInput(input: unknown): string {
  if (input == null) return "";
  if (typeof input === "string") {
    const s = input.trim().replace(/\s+/g, " ");
    return s.length > 50 ? s.slice(0, 50) + "…" : s;
  }
  if (typeof input === "object") {
    const vals = Object.values(input as Record<string, unknown>);
    if (vals.length > 0 && typeof vals[0] === "string") {
      const s = (vals[0] as string).trim().replace(/\s+/g, " ");
      return s.length > 50 ? s.slice(0, 50) + "…" : s;
    }
    try {
      const s = JSON.stringify(input);
      return s.length > 50 ? s.slice(0, 50) + "…" : s;
    } catch { return ""; }
  }
  return String(input).slice(0, 50);
}

function fmtOutput(v: unknown): string {
  let s: string;
  if (typeof v === "string") s = v;
  else { try { s = JSON.stringify(v, null, 2); } catch { s = String(v); } }
  return s.length > TRUNCATE ? s.slice(0, TRUNCATE) + `… (${s.length} chars)` : s;
}

export function ToolBlock({ tool, indent = 0 }: Props) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (tool.status !== "running") return;
    const t = setInterval(() => setFrame((f) => (f + 1) % SPINNER.length), 80);
    return () => clearInterval(t);
  }, [tool.status]);

  const running = tool.status === "running";
  const failed  = tool.status === "failed";
  const bullet  = running ? SPINNER[frame] : "•";
  const inputStr = fmtInput(tool.input);

  return (
    <Box flexDirection="column" marginTop={1} marginLeft={indent * 2}>
      <Box>
        <Text color={failed ? "red" : undefined} dimColor={running}>
          {bullet}{" "}
        </Text>
        <Text dimColor={running} color={failed ? "red" : undefined}>
          {tool.name}
        </Text>
        {inputStr !== "" && (
          <Text dimColor>{"("}{inputStr}{")"}</Text>
        )}
        {failed && <Text color="red">{" · error"}</Text>}
      </Box>

      {tool.subagentText && (
        <Box marginLeft={2}>
          <Text dimColor>{tool.subagentText}</Text>
        </Box>
      )}

      {Array.from(tool.subTools.values()).map((sub) => (
        <ToolBlock key={sub.id} tool={sub} indent={(indent ?? 0) + 1} />
      ))}

      {!running && tool.output != null && (
        <Box marginLeft={2}>
          <Text color={failed ? "red" : undefined} dimColor>
            {fmtOutput(tool.output)}
          </Text>
        </Box>
      )}
    </Box>
  );
}
