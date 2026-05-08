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
  return n.toLocaleString();
}

function TokenBadge({ usage }: { usage: TokenUsage }) {
  if (usage.input === 0 && usage.output === 0) return null;
  return (
    <span className="ml-auto opacity-60 text-xs tabular-nums">
      ↑{fmt(usage.input)} ↓{fmt(usage.output)} tokens
      {usage.cacheRead > 0 && ` (${fmt(usage.cacheRead)} cached)`}
    </span>
  );
}

export function StatusLine({ planMode = false, thinking = false, connected = true, tokenUsage }: Props) {
  if (!connected) {
    return (
      <div className="px-4 py-1 flex items-center">
        <span style={{ color: "rgb(var(--c-error))" }}>· disconnected</span>
        {tokenUsage && <TokenBadge usage={tokenUsage} />}
      </div>
    );
  }
  if (planMode) {
    return (
      <div className="px-4 py-1 flex items-center">
        <span style={{ color: "rgb(var(--c-plan-mode))" }}>
          ⏵⏵ plan mode on · shift+tab to exit
        </span>
        {tokenUsage && <TokenBadge usage={tokenUsage} />}
      </div>
    );
  }
  return (
    <div className="px-4 py-1 flex items-center opacity-60">
      <span>
        {thinking
          ? "esc to abort · shift+tab for plan mode"
          : "enter to send · shift+tab for plan mode"}
      </span>
      {tokenUsage && <TokenBadge usage={tokenUsage} />}
    </div>
  );
}
