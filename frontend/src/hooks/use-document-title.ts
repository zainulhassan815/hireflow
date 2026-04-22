import { useEffect } from "react";
import { useMatches } from "react-router-dom";

const BASE_TITLE = "Hireflow";

export function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${BASE_TITLE}` : BASE_TITLE;
  }, [title]);
}

// Reads the deepest matched route with a `handle.title` string and sets
// the document title accordingly. Mount once in a top-level layout.
export function useRouteTitle() {
  const matches = useMatches();
  const title = [...matches]
    .reverse()
    .map((m) => (m.handle as { title?: string } | undefined)?.title)
    .find((t): t is string => typeof t === "string" && t.length > 0);
  useDocumentTitle(title);
}
