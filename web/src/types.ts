export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoItem {
  content: string;
  status: TodoStatus;
}

export interface ToolDisplay {
  action: string;
  subject: string;
}

export type StreamEvent =
  | { type: "turn_start"; turn: number }
  | { type: "token"; text: string }
  | { type: "tool_start"; id: string; name: string; input: unknown; display?: ToolDisplay | null }
  | { type: "tool_end"; id: string; output: unknown; is_error: boolean }
  | { type: "subagent_token"; tool_id: string; text: string }
  | { type: "subagent_tool_start"; tool_id: string; sub_id: string; name: string; input: unknown; display?: ToolDisplay | null }
  | { type: "subagent_tool_end"; tool_id: string; sub_id: string; output: unknown; is_error: boolean }
  | { type: "todos_updated"; todos: TodoItem[] }
  | { type: "token_usage"; input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_creation_tokens: number }
  | { type: "done"; reason: string; final_text: string | null; error: string | null }
  | { type: "error"; error: string }
  | { type: "unknown" };

export type ToolStatus = "running" | "done" | "failed";

export type AssistantBlock =
  | { kind: "text"; text: string }
  | { kind: "tool"; tool: ToolCallState };

export type SubBlock = AssistantBlock;

export interface ToolCallState {
  id: string;
  name: string;
  input: unknown;
  output: unknown;
  status: ToolStatus;
  subBlocks: SubBlock[];
  display?: ToolDisplay | null;
}

export type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; blocks: AssistantBlock[] };

export const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
export const SPINNER_INTERVAL_MS = 100;

export const TRUNCATE = {
  toolArgs: 60,
  toolResult: 80,
  subagentTailLines: 2,
  subagentLineWidth: 80,
} as const;
