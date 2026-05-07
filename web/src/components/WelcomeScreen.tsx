const TOOL_GROUPS: Array<{ label: string; items: string }> = [
  { label: "Search ", items: "smart_search · read_with_anchor · list_evidence" },
  { label: "Verify ", items: "verify_citations · check_completeness" },
  { label: "Compute", items: "calculate" },
  { label: "Memory ", items: "read_memory_index · read_memory · write_memory" },
  { label: "Plan   ", items: "enter_strategy_mode · exit_strategy_mode" },
  { label: "Tasks  ", items: "write_todos" },
];

export function WelcomeScreen() {
  return (
    <div
      className="flex flex-col mx-4 mt-2 px-2 py-2 rounded border"
      style={{ borderColor: "rgb(var(--c-border-prompt))" }}
    >
      <span className="font-bold">case-agent</span>
      <span className="opacity-60">변호사 대상 case research · artifact 작성 에이전트.</span>

      <div className="mt-2 flex flex-col">
        <span className="font-bold">Tools</span>
        {TOOL_GROUPS.map((g) => (
          <div key={g.label} className="flex flex-row">
            <span className="opacity-60"> • </span>
            <span className="whitespace-pre">{g.label}</span>
            <span className="opacity-60">  {g.items}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-col">
        <span className="font-bold">Subagents</span>
        <div className="flex flex-row">
          <span className="opacity-60"> • </span>
          <span>explore</span>
          <span className="opacity-60">  task("explore", ...)</span>
        </div>
      </div>

      <div className="mt-2">
        <span className="opacity-60">Keys      Enter send  ·  Shift+Tab plan mode  ·  Esc abort</span>
      </div>
    </div>
  );
}
