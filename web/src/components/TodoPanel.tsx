import type { TodoItem } from "../types.js";

interface Props {
  todos: TodoItem[];
}

function statusGlyph(status: TodoItem["status"]): string {
  if (status === "completed") return "✔";
  if (status === "in_progress") return "▸";
  return "○";
}

function statusColor(status: TodoItem["status"]): string | undefined {
  if (status === "completed") return "rgb(var(--c-success))";
  if (status === "in_progress") return "rgb(var(--c-warning))";
  return undefined;
}

export function TodoPanel({ todos }: Props) {
  if (todos.length === 0) return null;
  const completed = todos.filter((t) => t.status === "completed").length;

  return (
    <div className="flex flex-col px-4 mt-2">
      <div className="opacity-60">
        │ Todos ({completed}/{todos.length})
      </div>
      {todos.map((todo, i) => {
        const isPending = todo.status === "pending";
        const isDone = todo.status === "completed";
        const color = statusColor(todo.status);
        return (
          <div key={i} className="ml-2 flex flex-row">
            <span
              className={isPending ? "opacity-60 mr-2" : "mr-2"}
              style={color ? { color } : undefined}
            >
              {statusGlyph(todo.status)}
            </span>
            <span
              className={
                (isPending ? "opacity-60 " : "") +
                (isDone ? "opacity-60 line-through " : "") +
                "flex-1"
              }
              style={color && !isPending ? { color } : undefined}
            >
              {todo.content}
            </span>
          </div>
        );
      })}
    </div>
  );
}
