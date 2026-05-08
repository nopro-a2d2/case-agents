import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, useApp, useInput } from "ink";
import type { AssistantBlock, Message, SubBlock, TodoItem, ToolCallState } from "../types.js";
import type { PythonBridge } from "../bridge.js";
import type { StreamEvent } from "../types.js";
import { AssistantBubble } from "./AssistantBubble.js";
import { UserBubble } from "./UserBubble.js";
import { PromptInput } from "./PromptInput.js";
import { Header } from "./Header.js";
import { ThinkingSpinner } from "./ThinkingSpinner.js";
import { StatusLine } from "./StatusLine.js";
import { TodoPanel } from "./TodoPanel.js";
import { WelcomeScreen } from "./WelcomeScreen.js";
import { PlanApprovalPicker } from "./PlanApprovalPicker.js";
import { APPROVAL_PROMPT } from "../planApproval.js";

interface Props {
  bridge: PythonBridge;
  caseId: string;
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

function appendSubText(blocks: SubBlock[], text: string): SubBlock[] {
  const last = blocks[blocks.length - 1];
  if (last && last.kind === "text") {
    return [...blocks.slice(0, -1), { kind: "text", text: last.text + text }];
  }
  return [...blocks, { kind: "text", text }];
}

function updateSubTool(
  blocks: SubBlock[],
  subId: string,
  updater: (tool: ToolCallState) => ToolCallState,
): SubBlock[] {
  return blocks.map((b) =>
    b.kind === "tool" && b.tool.id === subId
      ? { kind: "tool", tool: updater(b.tool) }
      : b,
  );
}

export function App({ bridge, caseId, model }: Props) {
  const { exit } = useApp();

  const [completedMessages, setCompletedMessages] = useState<Message[]>([]);
  const [currentAssistant, setCurrentAssistant] = useState<AssistantMessage | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [planMode, setPlanMode] = useState(false);
  const [awaitingPlanApproval, setAwaitingPlanApproval] = useState(false);
  const [tokenUsage, setTokenUsage] = useState({ input: 0, output: 0, cacheRead: 0 });
  const planTurnInFlightRef = useRef(false);

  const currentAssistantRef = useRef<AssistantMessage | null>(null);
  useEffect(() => { currentAssistantRef.current = currentAssistant; }, [currentAssistant]);

  const updateCurrentAssistant = useCallback(
    (updater: (msg: AssistantMessage) => AssistantMessage) => {
      setCurrentAssistant((msg) => msg ? updater(msg) : msg);
    },
    [],
  );

  useEffect(() => {
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
            subBlocks: [],
            display: ev.display ?? null,
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
              subBlocks: appendSubText(t.subBlocks, ev.text),
            })),
          }));
          break;
        }
        case "subagent_tool_start": {
          const subTool: ToolCallState = {
            id: ev.sub_id, name: ev.name, input: ev.input,
            output: null, status: "running", subBlocks: [],
            display: ev.display ?? null,
          };
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.tool_id, (parent) => ({
              ...parent,
              subBlocks: [...parent.subBlocks, { kind: "tool", tool: subTool }],
            })),
          }));
          break;
        }
        case "subagent_tool_end": {
          updateCurrentAssistant((msg) => ({
            ...msg,
            blocks: replaceTool(msg.blocks, ev.tool_id, (parent) => ({
              ...parent,
              subBlocks: updateSubTool(parent.subBlocks, ev.sub_id, (t) => ({
                ...t,
                output: ev.output,
                status: ev.is_error ? "failed" : "done",
              })),
            })),
          }));
          break;
        }
        case "todos_updated": {
          setTodos(ev.todos);
          break;
        }
        case "token_usage": {
          setTokenUsage((prev) => ({
            input: prev.input + ev.input_tokens,
            output: prev.output + ev.output_tokens,
            cacheRead: prev.cacheRead + ev.cache_read_tokens,
          }));
          break;
        }
        case "done": {
          setIsThinking(false);
          const finished = currentAssistantRef.current;
          if (finished) {
            let finalMsg: AssistantMessage = finished;
            if (ev.reason !== "completed") {
              const reasonBlock: AssistantBlock = {
                kind: "text",
                text: `[${ev.reason}${ev.error ? `: ${ev.error}` : ""}]`,
              };
              finalMsg = { ...finished, blocks: [...finished.blocks, reasonBlock] };
            }
            setCompletedMessages((msgs) => [...msgs, finalMsg]);
            setCurrentAssistant(null);
            currentAssistantRef.current = null;
          }
          if (planTurnInFlightRef.current) {
            planTurnInFlightRef.current = false;
            if (ev.reason === "completed") setAwaitingPlanApproval(true);
          }
          break;
        }
      }
    });

    bridge.onClose(() => exit());
  }, [bridge, exit, updateCurrentAssistant]);

  useInput((_input, key) => {
    if (key.ctrl && _input === "c") process.exit(0);
    if (key.shift && key.tab) setPlanMode((on) => !on);
  });

  const handleSubmit = useCallback((prompt: string) => {
    const userMsg: Message = { role: "user", text: prompt };
    setCompletedMessages((msgs) => [...msgs, userMsg]);
    setIsThinking(true);
    if (planMode) planTurnInFlightRef.current = true;
    bridge.send(prompt, { forceStrategy: planMode });
  }, [bridge, planMode]);

  const handleAbort = useCallback(() => {
    bridge.abort();
  }, [bridge]);

  const handleApprove = useCallback(() => {
    setAwaitingPlanApproval(false);
    setPlanMode(false);
    const userMsg: Message = { role: "user", text: APPROVAL_PROMPT };
    setCompletedMessages((msgs) => [...msgs, userMsg]);
    setIsThinking(true);
    planTurnInFlightRef.current = false;
    bridge.send(APPROVAL_PROMPT, { forceStrategy: false });
  }, [bridge]);

  const handleReject = useCallback(() => {
    setAwaitingPlanApproval(false);
  }, []);

  const handleChangePlan = useCallback((text: string) => {
    setAwaitingPlanApproval(false);
    const userMsg: Message = { role: "user", text };
    setCompletedMessages((msgs) => [...msgs, userMsg]);
    setIsThinking(true);
    planTurnInFlightRef.current = true;
    bridge.send(text, { forceStrategy: true });
  }, [bridge]);

  const showWelcome =
    completedMessages.length === 0 &&
    currentAssistant === null &&
    !isThinking;

  return (
    <Box flexDirection="column" width="100%">
      {showWelcome && <Header caseId={caseId} model={model} />}

      {showWelcome && <WelcomeScreen />}

      {completedMessages.map((msg, i) =>
        msg.role === "user"
          ? <UserBubble key={i} text={msg.text} />
          : <AssistantBubble key={i} message={msg} />
      )}

      {currentAssistant && <AssistantBubble message={currentAssistant} />}
      {isThinking && <ThinkingSpinner />}

      <TodoPanel todos={todos} />
      {awaitingPlanApproval ? (
        <PlanApprovalPicker
          onApprove={handleApprove}
          onReject={handleReject}
          onChange={handleChangePlan}
          disabled={isThinking}
        />
      ) : (
        <PromptInput onSubmit={handleSubmit} onAbort={handleAbort} disabled={isThinking} planMode={planMode} />
      )}
      <StatusLine planMode={planMode} tokenUsage={tokenUsage} />
    </Box>
  );
}
