interface Props {
  caseId: string;
  model: string;
}

export function Header({ caseId, model }: Props) {
  return (
    <div className="flex flex-row px-4 py-2">
      <div className="flex flex-col flex-1 min-w-[14rem]">
        <span className="font-bold">case-agent</span>
        <span className="opacity-60">case: {caseId}</span>
        <span className="opacity-60">model: {model}</span>
      </div>

      <div className="px-2">
        <span className="opacity-60">│</span>
      </div>

      <div className="flex flex-col flex-1 pl-2">
        <span className="font-bold">Tips</span>
        <span className="opacity-60">• smart_search — semantic evidence search</span>
        <span className="opacity-60">• read_with_anchor path#anchor — source section</span>
      </div>
    </div>
  );
}
