interface Props {
  text: string;
}

export function UserBubble({ text }: Props) {
  const lines = text.split("\n");
  return (
    <div className="flex flex-col mt-2">
      {lines.map((line, i) => (
        <div
          key={i}
          className="w-full px-4 whitespace-pre-wrap break-words"
          style={{ background: "rgb(var(--c-user-bubble))" }}
        >
          {i === 0 ? (
            <span
              className="font-bold mr-2"
              style={{ color: "rgb(var(--c-user-prefix))" }}
            >
              &gt;
            </span>
          ) : (
            <span className="mr-2">&nbsp;&nbsp;</span>
          )}
          <span>{line || " "}</span>
        </div>
      ))}
    </div>
  );
}
