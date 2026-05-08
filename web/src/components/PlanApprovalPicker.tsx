import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { APPROVAL_OPTIONS } from "../planApproval.js";

interface Props {
  onApprove: () => void;
  onReject: () => void;
  onChange: (text: string) => void;
  disabled?: boolean;
}

type Mode = "picker" | "typing";

export function PlanApprovalPicker({ onApprove, onReject, onChange, disabled = false }: Props) {
  const [mode, setMode] = useState<Mode>("picker");
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (mode === "typing") taRef.current?.focus();
  }, [mode]);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [value, mode]);

  const handleClick = (key: string) => {
    if (disabled) return;
    if (key === "approve") onApprove();
    else if (key === "reject") onReject();
    else setMode("typing");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setMode("picker");
      setValue("");
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      if (disabled) return;
      const trimmed = value.trim();
      if (trimmed) {
        setValue("");
        onChange(trimmed);
      }
    }
  };

  const planBorder = "rgb(var(--c-plan-mode))";

  if (mode === "typing") {
    return (
      <div className="flex flex-col">
        <div
          className="mx-4 mt-2 px-2 py-1 rounded border flex flex-row items-start"
          style={{ borderColor: planBorder }}
        >
          <span className="font-bold mr-2 select-none" style={{ color: planBorder }}>
            &gt;
          </span>
          <textarea
            ref={taRef}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder="Tell Ailex what to change · Enter to send · Esc to go back"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent outline-none resize-none font-mono"
            style={{ minHeight: "1.5em" }}
            autoFocus
          />
        </div>
        <div className="mx-4 mt-1 text-xs opacity-60">
          Enter to send · Esc to go back
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div
        className="mx-4 mt-2 p-3 rounded border flex flex-col gap-1"
        style={{ borderColor: planBorder }}
      >
        <div className="font-bold mb-2" style={{ color: planBorder }}>
          Would you like to proceed?
        </div>
        {APPROVAL_OPTIONS.map((opt, i) => (
          <button
            key={opt.key}
            type="button"
            disabled={disabled}
            onClick={() => handleClick(opt.key)}
            className="text-left px-2 py-1 rounded font-mono transition-colors hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              backgroundColor: "transparent",
            }}
            onMouseEnter={(e) => {
              if (!disabled) e.currentTarget.style.backgroundColor = planBorder;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
            }}
          >
            <span className="mr-2 opacity-70">{i + 1}.</span>
            {opt.label}
          </button>
        ))}
      </div>
      <div className="mx-4 mt-1 text-xs opacity-60">
        Click to select
      </div>
    </div>
  );
}
