import React from "react";
import { Box, Text } from "ink";
import type { TodoItem } from "../types.js";
import { colors, glyphs, spacing } from "../theme.js";

interface Props {
  todos: TodoItem[];
}

function statusGlyph(status: TodoItem["status"]): string {
  if (status === "completed") return "✔";
  if (status === "in_progress") return "▸";
  return "○";
}

function statusColor(status: TodoItem["status"]): string | undefined {
  if (status === "completed") return colors.success;
  if (status === "in_progress") return colors.warning;
  return undefined; // pending → dim default
}

export function TodoPanel({ todos }: Props) {
  if (todos.length === 0) return null;

  const completed = todos.filter((t) => t.status === "completed").length;

  return (
    <Box flexDirection="column" paddingX={spacing.sm} marginTop={spacing.xs}>
      <Box>
        <Text dimColor>
          {glyphs.divider} Todos ({completed}/{todos.length})
        </Text>
      </Box>
      {todos.map((todo, i) => {
        const color = statusColor(todo.status);
        const isPending = todo.status === "pending";
        const isDone = todo.status === "completed";
        return (
          <Box key={i} marginLeft={spacing.xs}>
            <Text color={color} dimColor={isPending}>
              {statusGlyph(todo.status)}{" "}
            </Text>
            <Text
              color={color}
              dimColor={isPending || isDone}
              strikethrough={isDone}
            >
              {todo.content}
            </Text>
          </Box>
        );
      })}
    </Box>
  );
}
