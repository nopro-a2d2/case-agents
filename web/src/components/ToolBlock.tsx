import { useEffect, useState } from "react";
import type { ToolCallState } from "../types.js";
import { SPINNER_FRAMES, SPINNER_INTERVAL_MS, TRUNCATE } from "../types.js";

interface Props {
  tool: ToolCallState;
  indent?: number;
}

function fmtInput(input: unknown): string {
  if (input == null) return "";
  if (typeof input === "string") {
    const s = input.trim().replace(/\s+/g, " ");
    return s.length > TRUNCATE.toolArgs ? s.slice(0, TRUNCATE.toolArgs) + "…" : s;
  }
  if (typeof input === "object") {
    const vals = Object.values(input as Record<string, unknown>);
    if (vals.length > 0 && typeof vals[0] === "string") {
      const s = (vals[0] as string).trim().replace(/\s+/g, " ");
      return s.length > TRUNCATE.toolArgs ? s.slice(0, TRUNCATE.toolArgs) + "…" : s;
    }
    try {
      const s = JSON.stringify(input);
      return s.length > TRUNCATE.toolArgs ? s.slice(0, TRUNCATE.toolArgs) + "…" : s;
    } catch {
      return "";
    }
  }
  return String(input).slice(0, TRUNCATE.toolArgs);
}

function fmtOutput(v: unknown): string {
  let s: string;
  if (typeof v === "string") s = v.trim();
  else {
    try { s = JSON.stringify(v); } catch { s = String(v); }
  }
  const first = s.split("\n")[0] ?? "";
  return first.length > TRUNCATE.toolResult
    ? first.slice(0, TRUNCATE.toolResult) + "…"
    : first;
}

function clampLine(line: string): string {
  return line.length > TRUNCATE.subagentLineWidth
    ? line.slice(0, TRUNCATE.subagentLineWidth) + "…"
    : line;
}

export function ToolBlock({ tool, indent = 0 }: Props) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (tool.status !== "running") return;
    const t = setInterval(
      () => setFrame((f) => (f + 1) % SPINNER_FRAMES.length),
      SPINNER_INTERVAL_MS,
    );
    return () => clearInterval(t);
  }, [tool.status]);

  const running = tool.status === "running";
  const failed = tool.status === "failed";
  const done = tool.status === "done";
  const inputStr = fmtInput(tool.input);

  const subagentLines = running
    ? tool.subagentText
        .split("\n")
        .filter(Boolean)
        .slice(-TRUNCATE.subagentTailLines)
        .map(clampLine)
    : [];

  return (
    <div className="flex flex-col" style={{ marginLeft: `${indent * 1}rem` }}>
      {/* Tool header line */}
      <div className="flex flex-row">
        {running ? (
          <span className="opacity-60 mr-2">{SPINNER_FRAMES[frame]}</span>
        ) : (
          <span
            className="mr-2"
            style={{
              color: failed ? "rgb(var(--c-error))" : "rgb(var(--c-success))",
            }}
          >
            ●
          </span>
        )}
        <span
          className={running ? "opacity-60" : ""}
          style={failed ? { color: "rgb(var(--c-error))" } : undefined}
        >
          {tool.name}
        </span>
        {inputStr !== "" && <span className="opacity-60 ml-2">{inputStr}</span>}
        {failed && (
          <span className="ml-2" style={{ color: "rgb(var(--c-error))" }}>
            · error
          </span>
        )}
      </div>

      {/* Subagent streaming text */}
      {subagentLines.length > 0 && (
        <div className="ml-4 opacity-60">
          {subagentLines.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap break-words">
              {l}
            </div>
          ))}
        </div>
      )}

      {/* Nested sub-tools */}
      {Array.from(tool.subTools.values()).map((sub) => (
        <ToolBlock key={sub.id} tool={sub} indent={indent + 1} />
      ))}

      {/* Result line */}
      {done && (
        <div className="ml-4 opacity-60 flex flex-row">
          <span className="mr-2">└</span>
          <span className="whitespace-pre-wrap break-words flex-1">
            {tool.output != null ? fmtOutput(tool.output) : "Done"}
          </span>
        </div>
      )}
      {failed && tool.output != null && (
        <div className="ml-4 flex flex-row">
          <span className="mr-2 opacity-60">└</span>
          <span
            className="whitespace-pre-wrap break-words flex-1"
            style={{ color: "rgb(var(--c-error))" }}
          >
            {fmtOutput(tool.output)}
          </span>
        </div>
      )}
    </div>
  );
}
