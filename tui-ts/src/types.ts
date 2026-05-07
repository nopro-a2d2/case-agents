export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoItem {
  content: string;
  status: TodoStatus;
}

export type StreamEvent =
  | { type: "turn_start"; turn: number }
  | { type: "token"; text: string }
  | { type: "tool_start"; id: string; name: string; input: unknown }
  | { type: "tool_end"; id: string; output: unknown; is_error: boolean }
  | { type: "subagent_token"; tool_id: string; text: string }
  | { type: "subagent_tool_start"; tool_id: string; sub_id: string; name: string; input: unknown }
  | { type: "subagent_tool_end"; tool_id: string; sub_id: string; output: unknown; is_error: boolean }
  | { type: "todos_updated"; todos: TodoItem[] }
  | { type: "done"; reason: string; final_text: string | null; error: string | null }
  | { type: "error"; error: string }
  | { type: "unknown" };

export type ToolStatus = "running" | "done" | "failed";

export interface ToolCallState {
  id: string;
  name: string;
  input: unknown;
  output: unknown;
  status: ToolStatus;
  subagentText: string;
  subTools: Map<string, ToolCallState>;
}

export type AssistantBlock =
  | { kind: "text"; text: string }
  | { kind: "tool"; tool: ToolCallState };

export type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; blocks: AssistantBlock[] };
