import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Static, Text, useApp, useInput } from "ink";
import type { Message, ToolCallState } from "../types.js";
import type { PythonBridge } from "../bridge.js";
import type { StreamEvent } from "../types.js";
import { AssistantBubble } from "./AssistantBubble.js";
import { UserBubble } from "./UserBubble.js";
import { PromptInput } from "./PromptInput.js";
import { Header } from "./Header.js";

interface Props {
  bridge: PythonBridge;
  caseId: string;
}

const THINK_SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"];

function ThinkingIndicator() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setFrame((f) => (f + 1) % THINK_SPINNER.length), 100);
    return () => clearInterval(t);
  }, []);
  return (
    <Box paddingX={2} marginTop={1}>
      <Text dimColor>{THINK_SPINNER[frame]} Thinking…</Text>
    </Box>
  );
}

export function App({ bridge, caseId }: Props) {
  const { exit } = useApp();

  const [completedMessages, setCompletedMessages] = useState<Message[]>([]);
  const [currentAssistant, setCurrentAssistant] = useState<Message | null>(null);
  const [isThinking, setIsThinking] = useState(false);

  const currentAssistantRef = useRef<Message | null>(null);
  useEffect(() => { currentAssistantRef.current = currentAssistant; }, [currentAssistant]);

  const updateCurrentAssistant = useCallback((updater: (msg: Message) => Message) => {
    setCurrentAssistant((msg) => msg ? updater(msg) : msg);
  }, []);

  useEffect(() => {
    bridge.onEvent((ev: StreamEvent) => {
      switch (ev.type) {
        case "turn_start": {
          if (ev.turn === 1) {
            const msg: Message = { role: "assistant", preText: "", postText: "", toolCalls: new Map() };
            currentAssistantRef.current = msg;
            setCurrentAssistant(msg);
          }
          break;
        }
        case "token": {
          updateCurrentAssistant((msg) =>
            msg.toolCalls.size === 0
              ? { ...msg, preText: msg.preText + ev.text }
              : { ...msg, postText: msg.postText + ev.text }
          );
          break;
        }
        case "tool_start": {
          const tool: ToolCallState = {
            id: ev.id, name: ev.name, input: ev.input,
            output: null, status: "running",
            subagentText: "", subTools: new Map(),
          };
          updateCurrentAssistant((msg) => {
            const toolCalls = new Map(msg.toolCalls);
            toolCalls.set(ev.id, tool);
            return { ...msg, toolCalls };
          });
          break;
        }
        case "tool_end": {
          updateCurrentAssistant((msg) => {
            const toolCalls = new Map(msg.toolCalls);
            const existing = toolCalls.get(ev.id);
            if (existing) {
              toolCalls.set(ev.id, { ...existing, output: ev.output, status: ev.is_error ? "failed" : "done" });
            }
            return { ...msg, toolCalls };
          });
          break;
        }
        case "subagent_token": {
          updateCurrentAssistant((msg) => {
            const toolCalls = new Map(msg.toolCalls);
            const tool = toolCalls.get(ev.tool_id);
            if (tool) toolCalls.set(ev.tool_id, { ...tool, subagentText: tool.subagentText + ev.text });
            return { ...msg, toolCalls };
          });
          break;
        }
        case "subagent_tool_start": {
          const subTool: ToolCallState = {
            id: ev.sub_id, name: ev.name, input: ev.input,
            output: null, status: "running", subagentText: "", subTools: new Map(),
          };
          updateCurrentAssistant((msg) => {
            const toolCalls = new Map(msg.toolCalls);
            const parent = toolCalls.get(ev.tool_id);
            if (parent) {
              const subTools = new Map(parent.subTools);
              subTools.set(ev.sub_id, subTool);
              toolCalls.set(ev.tool_id, { ...parent, subTools });
            }
            return { ...msg, toolCalls };
          });
          break;
        }
        case "subagent_tool_end": {
          updateCurrentAssistant((msg) => {
            const toolCalls = new Map(msg.toolCalls);
            const parent = toolCalls.get(ev.tool_id);
            if (parent) {
              const subTools = new Map(parent.subTools);
              const sub = subTools.get(ev.sub_id);
              if (sub) subTools.set(ev.sub_id, { ...sub, output: ev.output, status: ev.is_error ? "failed" : "done" });
              toolCalls.set(ev.tool_id, { ...parent, subTools });
            }
            return { ...msg, toolCalls };
          });
          break;
        }
        case "done": {
          setIsThinking(false);
          const finished = currentAssistantRef.current;
          if (finished) {
            let finalMsg = finished;
            if (ev.reason !== "completed") {
              finalMsg = { ...finished, postText: finished.postText + `\n[${ev.reason}${ev.error ? `: ${ev.error}` : ""}]` };
            }
            setCompletedMessages((msgs) => [...msgs, finalMsg]);
            setCurrentAssistant(null);
            currentAssistantRef.current = null;
          }
          break;
        }
      }
    });

    bridge.onClose(() => exit());
  }, [bridge, exit, updateCurrentAssistant]);

  useInput((_input, key) => {
    if (key.ctrl && _input === "c") exit();
  });

  const handleSubmit = useCallback((prompt: string) => {
    const userMsg: Message = { role: "user", preText: prompt, postText: "", toolCalls: new Map() };
    setCompletedMessages((msgs) => [...msgs, userMsg]);
    setIsThinking(true);
    bridge.send(prompt);
  }, [bridge]);

  return (
    <Box flexDirection="column" width="100%">
      <Header caseId={caseId} />

      <Static items={completedMessages}>
        {(msg, i) =>
          msg.role === "user"
            ? <UserBubble key={i} text={msg.preText} />
            : <AssistantBubble key={i} message={msg} />
        }
      </Static>

      {currentAssistant && <AssistantBubble message={currentAssistant} />}
      {isThinking && <ThinkingIndicator />}

      <PromptInput onSubmit={handleSubmit} disabled={isThinking} />
      <Box paddingX={2}>
        <Text dimColor>ctrl+c to quit</Text>
      </Box>
    </Box>
  );
}
