import { useEffect, useState } from "react";
import { marked } from "marked";
import { api } from "../api";
import { Section, Spinner } from "../components/ui";

export default function Method() {
  const [parts, setParts] = useState<Record<string, string> | null>(null);
  useEffect(() => { api.method().then(setParts); }, []);
  if (!parts) return <Spinner />;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Method & limits</h1>
      {Object.entries(parts).map(([title, md]) => (
        <Section key={title} title={title}>
          <div className="prose-sm max-w-none space-y-2 text-sm leading-relaxed text-slate-700 [&_li]:ml-5 [&_li]:list-disc [&_ol>li]:list-decimal [&_strong]:text-slate-900"
            dangerouslySetInnerHTML={{ __html: marked.parse(md) as string }} />
        </Section>
      ))}
    </div>
  );
}
