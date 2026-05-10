import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { SkillEntry } from "../types.js";

interface Props {
  onSubmit: (value: string) => void;
  onAbort: () => void;
  onTogglePlanMode: () => void;
  disabled?: boolean;
  planMode?: boolean;
  skills?: SkillEntry[];
}

const MAX_VISIBLE = 16;

export function PromptInput({
  onSubmit,
  onAbort,
  onTogglePlanMode,
  disabled = false,
  planMode = false,
  skills = [],
}: Props) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState(0);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Slash dropdown only while the user is still typing the command name
  // (no space typed yet). After space, free-text args follow.
  const { matches, commands, userSkills } = useMemo(() => {
    if (!value.startsWith("/") || value.includes(" ")) {
      return { matches: [] as SkillEntry[], commands: [] as SkillEntry[], userSkills: [] as SkillEntry[] };
    }
    const token = value.slice(1).toLowerCase();
    let filtered: SkillEntry[];
    if (token === "") {
      filtered = skills.slice(0, MAX_VISIBLE);
    } else {
      filtered = skills.filter((s) => s.name.toLowerCase().includes(token));
      filtered.sort((a, b) => {
        const ap = a.name.toLowerCase().startsWith(token) ? 0 : 1;
        const bp = b.name.toLowerCase().startsWith(token) ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return a.name.localeCompare(b.name);
      });
      filtered = filtered.slice(0, MAX_VISIBLE);
    }
    const c = filtered.filter((s) => s.kind === "command");
    const u = filtered.filter((s) => s.kind !== "command");
    // Render order = nav order: commands first (control plane), then skills (model plane).
    return { matches: [...c, ...u], commands: c, userSkills: u };
  }, [value, skills]);
  const open = matches.length > 0;

  // Reset highlight when the candidate set changes.
  useEffect(() => {
    setSelected(0);
  }, [matches.length, value]);

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

  const completeWith = (entry: SkillEntry) => {
    setValue(`/${entry.name} `);
    requestAnimationFrame(() => taRef.current?.focus());
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (open) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((i) => (i + 1) % matches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((i) => (i - 1 + matches.length) % matches.length);
        return;
      }
      if (e.key === "Tab" && !e.shiftKey) {
        e.preventDefault();
        completeWith(matches[selected]);
        return;
      }
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        completeWith(matches[selected]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setValue("");
        return;
      }
    }

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
      if (e.nativeEvent.isComposing) return;
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

  // Active row tint — light blue accent. Falls back to a neutral dim if the
  // theme variable is missing.
  const activeBg = "rgba(59, 130, 246, 0.10)";

  const renderRow = (s: SkillEntry, globalIndex: number) => {
    const active = globalIndex === selected;
    return (
      <div
        key={`${s.kind ?? "skill"}:${s.name}`}
        onMouseDown={(e) => {
          e.preventDefault();
          setSelected(globalIndex);
          completeWith(s);
        }}
        onMouseEnter={() => setSelected(globalIndex)}
        className="px-4 py-2 cursor-pointer flex flex-col"
        style={{ backgroundColor: active ? activeBg : "transparent" }}
      >
        <div className="flex items-baseline gap-2">
          <span className="font-mono" style={{ color: promptColor }}>
            /{s.name}
          </span>
          {s.argument_hint && (
            <span className="font-mono opacity-50 text-xs">{s.argument_hint}</span>
          )}
        </div>
        {s.description && (
          <div className="text-xs opacity-60 truncate">{s.description}</div>
        )}
      </div>
    );
  };

  return (
    <div className="relative mx-4 mt-2">
      {open && (
        <div
          className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border bg-white shadow-md overflow-hidden text-sm"
          style={{ borderColor: "rgb(var(--c-border-prompt))" }}
        >
          {commands.length > 0 && (
            <>
              <div className="px-4 pt-2 pb-1 text-xs uppercase opacity-50 tracking-wide">
                Commands
              </div>
              {commands.map((s, i) => renderRow(s, i))}
            </>
          )}
          {userSkills.length > 0 && (
            <>
              <div
                className="px-4 pt-2 pb-1 text-xs uppercase opacity-50 tracking-wide"
                style={{
                  borderTop: commands.length > 0
                    ? "1px solid rgb(var(--c-border-prompt))"
                    : undefined,
                }}
              >
                Skills
              </div>
              {userSkills.map((s, i) => renderRow(s, commands.length + i))}
            </>
          )}
        </div>
      )}

      <div
        className="px-2 py-1 rounded border flex flex-row items-start"
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
          placeholder={disabled ? "…  (Esc to abort)" : "Type a message — Enter to send, / for slash command, Shift+Tab for plan mode"}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 bg-transparent outline-none resize-none font-mono"
          style={{ minHeight: "1.5em" }}
          autoFocus
        />
      </div>
    </div>
  );
}
