import { useEffect, useRef, useState } from "react";
import { SPINNER_FRAMES, SPINNER_INTERVAL_MS } from "../types.js";

interface Props {
  outputTokens?: number;
}

export function ThinkingSpinner({ outputTokens = 0 }: Props) {
  const [frame, setFrame] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const t = setInterval(() => {
      setFrame((f) => (f + 1) % SPINNER_FRAMES.length);
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, SPINNER_INTERVAL_MS);
    return () => clearInterval(t);
  }, []);

  const tokenSuffix = outputTokens > 0
    ? ` · ↓ ${outputTokens.toLocaleString("en-US")} tokens`
    : "";

  return (
    <div className="px-4 mt-2 opacity-60">
      <span>· {SPINNER_FRAMES[frame]} Thinking… ({elapsed}s{tokenSuffix})</span>
    </div>
  );
}
