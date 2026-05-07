import type { Message } from "../types.js";
import { ToolBlock } from "./ToolBlock.js";

interface Props {
  message: Extract<Message, { role: "assistant" }>;
}

function AssistantTextBlock({ text }: { text: string }) {
  if (text === "") return null;
  return (
    <div className="flex flex-row">
      <span className="mr-2">●</span>
      <span className="whitespace-pre-wrap break-words flex-1">{text}</span>
    </div>
  );
}

export function AssistantBubble({ message }: Props) {
  return (
    <div className="flex flex-col mt-2 pl-4">
      {message.blocks.map((block, i) =>
        block.kind === "text" ? (
          <AssistantTextBlock key={i} text={block.text} />
        ) : (
          <ToolBlock key={i} tool={block.tool} />
        )
      )}
    </div>
  );
}
