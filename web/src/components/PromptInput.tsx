import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface Props {
  onSubmit: (value: string) => void;
  onAbort: () => void;
  onTogglePlanMode: () => void;
  disabled?: boolean;
  planMode?: boolean;
}

export function PromptInput({
  onSubmit,
  onAbort,
  onTogglePlanMode,
  disabled = false,
  planMode = false,
}: Props) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  // auto-grow
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [value]);

  // refocus when re-enabled
  useEffect(() => {
    if (!disabled) taRef.current?.focus();
  }, [disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Tab" && e.shiftKey) {
      e.preventDefault();
      onTogglePlanMode();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      if (disabled) onAbort();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (disabled) return;
      const trimmed = value.trim();
      if (trimmed) {
        setValue("");
        onSubmit(trimmed);
      }
    }
  };

  const borderColor = planMode ? "rgb(var(--c-plan-mode))" : "rgb(var(--c-border-prompt))";
  const promptColor = disabled ? "rgb(0 0 0 / 0.55)" : "rgb(var(--c-user-prefix))";

  return (
    <div
      className="mx-4 mt-2 px-2 py-1 rounded border flex flex-row items-start"
      style={{ borderColor }}
    >
      <span className="font-bold mr-2 select-none" style={{ color: promptColor }}>
        &gt;
      </span>
      <textarea
        ref={taRef}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder={disabled ? "…  (Esc to abort)" : "Type a message — Enter to send, Shift+Tab for plan mode"}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="flex-1 bg-transparent outline-none resize-none font-mono"
        style={{ minHeight: "1.5em" }}
        autoFocus
      />
    </div>
  );
}
