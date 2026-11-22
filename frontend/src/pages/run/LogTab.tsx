import { useEffect, useState } from "react";
import { api } from "../../api";
import type { RunDetail } from "../../types";
import { Section } from "../../components/ui";

export default function LogTab({ run }: { run: RunDetail }) {
  const [logs, setLogs] = useState<{ file: string; lines: string[] }[]>([]);
  useEffect(() => { api.log(run.id).then(setLogs); }, [run.id, run.status.state]);
  return (
    <div className="space-y-6">
      {logs.map((l) => (
        <Section key={l.file} title={l.file === "run.log" ? "Run log" : "Process output"}>
          <pre className="max-h-[600px] overflow-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{l.lines.join("\n")}</pre>
        </Section>
      ))}
    </div>
  );
}
