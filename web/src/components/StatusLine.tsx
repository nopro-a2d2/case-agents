interface TokenUsage {
  input: number;
  output: number;
  cacheRead: number;
}

interface Props {
  planMode?: boolean;
  thinking?: boolean;
  connected?: boolean;
  tokenUsage?: TokenUsage;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

export function StatusLine({ planMode = false, thinking = false, connected = true, tokenUsage }: Props) {
  const hasUsage = tokenUsage && (tokenUsage.input > 0 || tokenUsage.output > 0);

  if (!connected) {
    return (
      <div className="px-4 py-1 flex justify-between">
        <span style={{ color: "rgb(var(--c-error))" }}>· disconnected</span>
      </div>
    );
  }
  if (planMode) {
    return (
      <div className="px-4 py-1 flex justify-between">
        <span style={{ color: "rgb(var(--c-plan-mode))" }}>
          ⏵⏵ plan mode on · shift+tab to exit
        </span>
        {hasUsage && (
          <span className="opacity-50 text-sm">
            ↑{fmt(tokenUsage.input)} ↓{fmt(tokenUsage.output)} tokens
            {tokenUsage.cacheRead > 0 ? ` (${fmt(tokenUsage.cacheRead)} cached)` : ""}
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="px-4 py-1 opacity-60 flex justify-between">
      <span>
        {thinking
          ? "esc to abort · shift+tab for plan mode"
          : "enter to send · shift+tab for plan mode"}
      </span>
      {hasUsage && (
        <span className="text-sm">
          ↑{fmt(tokenUsage.input)} ↓{fmt(tokenUsage.output)} tokens
          {tokenUsage.cacheRead > 0 ? ` (${fmt(tokenUsage.cacheRead)} cached)` : ""}
        </span>
      )}
    </div>
  );
}
