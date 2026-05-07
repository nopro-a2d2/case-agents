interface Props {
  planMode?: boolean;
  thinking?: boolean;
  connected?: boolean;
}

export function StatusLine({ planMode = false, thinking = false, connected = true }: Props) {
  if (!connected) {
    return (
      <div className="px-4 py-1">
        <span style={{ color: "rgb(var(--c-error))" }}>· disconnected</span>
      </div>
    );
  }
  if (planMode) {
    return (
      <div className="px-4 py-1">
        <span style={{ color: "rgb(var(--c-plan-mode))" }}>
          ⏵⏵ plan mode on · shift+tab to exit
        </span>
      </div>
    );
  }
  return (
    <div className="px-4 py-1 opacity-60">
      <span>
        {thinking
          ? "esc to abort · shift+tab for plan mode"
          : "enter to send · shift+tab for plan mode"}
      </span>
    </div>
  );
}
