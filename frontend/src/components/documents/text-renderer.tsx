import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * F105.d — inline text / markdown renderer for `kind="text"`.
 *
 * Plain text shows in `<pre>` with preserved whitespace + word-break
 * so long lines wrap. Markdown renders through react-markdown with
 * GFM (tables, strikethrough, task lists) — same toolchain F81.g
 * uses for RAG answers so the styles inherit.
 */

interface TextPayload {
  content: string;
  format: "plain" | "markdown";
}

export function TextRenderer({ data }: { data: unknown }) {
  const payload = data as TextPayload | null | undefined;
  const content = payload?.content ?? "";
  const format = payload?.format ?? "plain";

  if (format === "markdown") {
    return (
      <div className="prose prose-sm dark:prose-invert max-h-[600px] max-w-none overflow-auto rounded-lg border bg-white p-4 dark:bg-neutral-950">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    );
  }

  return (
    <pre className="max-h-[600px] overflow-auto rounded-lg border bg-white p-4 font-mono text-sm whitespace-pre-wrap dark:bg-neutral-950">
      {content}
    </pre>
  );
}
