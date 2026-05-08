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
  const display = tool.display;
  const headerColor = failed
    ? "rgb(var(--c-error))"
    : done
    ? "rgb(var(--c-success))"
    : undefined;

  return (
    <div className="flex flex-col" style={{ marginLeft: `${indent * 1}rem` }}>
      {/* Tool header line */}
      <div className={running ? "flex flex-row tool-running" : "flex flex-row"}>
        {running ? (
          <span className="mr-2">{SPINNER_FRAMES[frame]}</span>
        ) : (
          <span className="mr-2" style={{ color: headerColor }}>
            ●
          </span>
        )}
        {display ? (
          <>
            <span style={{ color: headerColor }}>{display.action}</span>
            <span className="opacity-60 ml-2">- {display.subject}</span>
          </>
        ) : (
          <>
            <span style={{ color: headerColor }}>{tool.name}</span>
            {inputStr !== "" && <span className="opacity-60 ml-2">{inputStr}</span>}
          </>
        )}
        {failed && (
          <span className="ml-2" style={{ color: "rgb(var(--c-error))" }}>
            · error
          </span>
        )}
      </div>

      {/* Subagent's interleaved text + sub-tools (main-agent-style streaming) */}
      {tool.subBlocks.map((blk, i) =>
        blk.kind === "text" ? (
          blk.text === "" ? null : (
            <div key={i} className="ml-4 whitespace-pre-wrap break-words">
              {blk.text}
            </div>
          )
        ) : (
          <ToolBlock key={i} tool={blk.tool} indent={indent + 1} />
        ),
      )}
    </div>
  );
}
