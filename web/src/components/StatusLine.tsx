import type { ModeState } from "../mode.js";

interface Props {
  mode?: ModeState;
  thinking?: boolean;
  connected?: boolean;
}

export function StatusLine({ mode = "normal", thinking = false, connected = true }: Props) {
  if (!connected) {
    return (
      <div className="px-4 py-1">
        <span style={{ color: "rgb(var(--c-error))" }}>· disconnected</span>
      </div>
    );
  }
  if (mode === "strategy") {
    return (
      <div className="px-4 py-1">
        <span style={{ color: "rgb(var(--c-plan-mode))" }}>
          ⏵⏵ strategy mode on · shift+tab → brief
        </span>
      </div>
    );
  }
  if (mode === "brief") {
    return (
      <div className="px-4 py-1">
        <span style={{ color: "rgb(var(--c-brief-mode))" }}>
          ✎ brief mode on · shift+tab → normal
        </span>
      </div>
    );
  }
  return (
    <div className="px-4 py-1 opacity-60">
      <span>
        {thinking
          ? "esc to abort · shift+tab cycle (normal → strategy → brief)"
          : "enter to send · shift+tab cycle (normal → strategy → brief)"}
      </span>
    </div>
  );
}
