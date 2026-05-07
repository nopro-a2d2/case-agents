import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WSBridge } from "./bridge.js";
import type {
  AssistantBlock,
  Message,
  StreamEvent,
  TodoItem,
  ToolCallState,
} from "./types.js";
import { Header } from "./components/Header.js";
import { WelcomeScreen } from "./components/WelcomeScreen.js";
import { UserBubble } from "./components/UserBubble.js";
import { AssistantBubble } from "./components/AssistantBubble.js";
import { ThinkingSpinner } from "./components/ThinkingSpinner.js";
import { PromptInput } from "./components/PromptInput.js";
import { StatusLine } from "./components/StatusLine.js";
import { TodoPanel } from "./components/TodoPanel.js";

interface Props {
  caseId: string;
  root: string;
  model: string;
}

type AssistantMessage = Extract<Message, { role: "assistant" }>;

function appendToken(blocks: AssistantBlock[], text: string): AssistantBlock[] {
  const last = blocks[blocks.length - 1];
  if (last && last.kind === "text") {
    return [...blocks.slice(0, -1), { kind: "text", text: last.text + text }];
  }
  return [...blocks, { kind: "text", text }];
}

function replaceTool(
  blocks: AssistantBlock[],
  id: string,
  updater: (tool: ToolCallState) => ToolCallState,
): AssistantBlock[] {
  return blocks.map((b) =>
    b.kind === "tool" && b.tool.id === id
      ? { kind: "tool", tool: updater(b.tool) }
      : b,
  );
}

export function App({ caseId, root, model }: Props) {
  const bridge = useMemo(() => new WSBridge({ url: "/ws", caseId, root }), [caseId, root]);

  const [completedMessages, setCompletedMessages] = useState<Message[]>([]);
  const [currentAssistant, setCurrentAssistant] = useState<AssistantMessage | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [planMode, setPlanMode] = useState(false);
  const [connected, setConnected] = useState(false);

  const currentAssistantRef = useRef<AssistantMessage | null>(null);
  useEffect(() => { currentAssistantRef.current = currentAssistant; }, [currentAssistant]);

  const updateCurrentAssistant = useCallback(
    (updater: (msg: AssistantMessage) => AssistantMessage) => {
      setCurrentAssistant((msg) => (msg ? updater(msg) : msg));
    },
    [],
  );

  useEffect(() => {
    bridge.onOpen(() => setConnected(true));
    bridge.onClose(() => {
      setConnected(false);
      // Don't leave the UI stuck on "Thinking…" if the connection drops mid-turn.
      setIsThinking(false);
    });

    bridge.onEvent((ev: StreamEvent) => {
      switch (ev.type) {
        case "turn_start": {
          if (ev.turn === 1) {
            const msg: AssistantMessage = { role: "assistant", blocks: [] };
            currentAssistantRef.current = msg;
            setCurrentAssistant(msg);
          }
          break;
        }
        case "token": {
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: appendToken(msg.blocks, ev.text),
          }));
          break;
        }
        case "tool_start": {
          const tool: ToolCallState = {
            id: ev.id, name: ev.name, input: ev.input,
            output: null, status: "running",
            subagentText: "", subTools: new Map(),
          };
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: [...msg.blocks, { kind: "tool", tool }],
          }));
          break;
        }
        case "tool_end": {
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.id, (t) => ({
              ...t,
              output: ev.output,
              status: ev.is_error ? "failed" : "done",
            })),
          }));
          break;
        }
        case "subagent_token": {
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.tool_id, (t) => ({
              ...t,
              subagentText: t.subagentText + ev.text,
            })),
          }));
          break;
        }
        case "subagent_tool_start": {
          const subTool: ToolCallState = {
            id: ev.sub_id, name: ev.name, input: ev.input,
            output: null, status: "running", subagentText: "", subTools: new Map(),
          };
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.tool_id, (parent) => {
              const subTools = new Map(parent.subTools);
              subTools.set(ev.sub_id, subTool);
              return { ...parent, subTools };
            }),
          }));
          break;
        }
        case "subagent_tool_end": {
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.tool_id, (parent) => {
              const subTools = new Map(parent.subTools);
              const sub = subTools.get(ev.sub_id);
              if (sub) {
                subTools.set(ev.sub_id, {
                  ...sub,
                  output: ev.output,
                  status: ev.is_error ? "failed" : "done",
                });
              }
              return { ...parent, subTools };
            }),
          }));
          break;
        }
        case "todos_updated": {
          setTodos(ev.todos);
          break;
        }
        case "done": {
          setIsThinking(false);
          // Functional updater captures the LATEST currentAssistant so the
          // last token's setState (queued just above this case) is included
          // before we push the message into completed history. Reading from
          // a ref here would race with React's state-update batching and
          // truncate the tail.
          setCurrentAssistant((latest) => {
            if (latest) {
              let finalMsg: AssistantMessage = latest;
              if (ev.reason !== "completed") {
                const reasonBlock: AssistantBlock = {
                  kind: "text",
                  text: `[${ev.reason}${ev.error ? `: ${ev.error}` : ""}]`,
                };
                finalMsg = {
                  ...latest,
                  blocks: [...latest.blocks, reasonBlock],
                };
              }
              setCompletedMessages((msgs) => [...msgs, finalMsg]);
            }
            currentAssistantRef.current = null;
            return null;
          });
          break;
        }
        case "error": {
          // Unstick the UI and surface the error using the same functional
          // updater pattern as `done` so we always read the freshest state.
          setIsThinking(false);
          setCurrentAssistant((latest) => {
            if (latest) {
              return {
                ...latest,
                blocks: appendToken(latest.blocks, `\n[error: ${ev.error}]`),
              };
            }
            const errorMsg: Message = {
              role: "assistant",
              blocks: [{ kind: "text", text: `[error: ${ev.error}]` }],
            };
            setCompletedMessages((msgs) => [...msgs, errorMsg]);
            return null;
          });
          break;
        }
      }
    });

    bridge.connect();
    return () => bridge.close();
  }, [bridge, updateCurrentAssistant]);

  // auto-scroll to bottom on new content
  useEffect(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }, [completedMessages, currentAssistant, isThinking, todos]);

  const handleSubmit = useCallback((prompt: string) => {
    const userMsg: Message = { role: "user", text: prompt };
    setCompletedMessages((msgs) => [...msgs, userMsg]);
    setIsThinking(true);
    bridge.send(prompt, { forceStrategy: planMode });
  }, [bridge, planMode]);

  const handleAbort = useCallback(() => {
    bridge.abort();
  }, [bridge]);

  const handleTogglePlanMode = useCallback(() => {
    setPlanMode((on) => !on);
  }, []);

  const showWelcome =
    completedMessages.length === 0 &&
    currentAssistant === null &&
    !isThinking;

  return (
    <div className="flex flex-col w-full max-w-[1024px] mx-auto pb-16">
      {showWelcome && <Header caseId={caseId} model={model} />}
      {showWelcome && <WelcomeScreen />}

      {completedMessages.map((msg, i) =>
        msg.role === "user" ? (
          <UserBubble key={i} text={msg.text} />
        ) : (
          <AssistantBubble key={i} message={msg} />
        )
      )}

      {currentAssistant && <AssistantBubble message={currentAssistant} />}
      {isThinking && <ThinkingSpinner />}

      <TodoPanel todos={todos} />

      <div
        className="fixed bottom-0 left-0 right-0 bg-white border-t"
        style={{ borderColor: "rgb(var(--c-border-prompt))" }}
      >
        <div className="max-w-[1024px] mx-auto">
          <PromptInput
            onSubmit={handleSubmit}
            onAbort={handleAbort}
            onTogglePlanMode={handleTogglePlanMode}
            disabled={isThinking}
            planMode={planMode}
          />
          <StatusLine planMode={planMode} thinking={isThinking} connected={connected} />
        </div>
      </div>
    </div>
  );
}
