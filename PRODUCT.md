# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: HR and recruiting staff at a single company, using Hireflow as an
internal tool. They drop in for **short visits a few times a week** — check a
candidate, ask a question of the document set, look at what arrived from the
recruiting inbox — rather than living in it for hours.

That session shape is the governing design fact: comfort, obvious
affordances, and legible-at-a-glance state matter more than maximum
information density. A returning user should not have to re-learn where
things are.

## Product Purpose

Screen candidates and answer questions about hiring documents without
reading every file.

- Documents (resumes, job descriptions, reports) are uploaded or ingested,
  then extracted, classified, chunked and embedded.
- Search and a RAG chat answer natural-language questions over that corpus
  with citations back to the source chunk.
- Resumes become Candidates, who apply to Jobs and move through
  Applications with a match breakdown.
- A connected Gmail mailbox auto-ingests resume attachments, with optional
  historical backfill and opt-in mirroring of permanent deletions.

Success is a recruiter answering a question about the pipeline in seconds
that would otherwise mean opening a dozen PDFs.

## Positioning

The corpus is the company's own hiring documents, and every answer cites the
chunk it came from. Retrieval is hybrid (vector + lexical + reranker) and
answers carry an explicit confidence and classified intent, so an operator
can tell a grounded answer from a guess — the product is deliberately
willing to say "not in the provided documents".

## Constraints

- **Runs locally.** Deployed per-installation rather than as hosted SaaS;
  the browser talks to a local FastAPI backend.
- **Owner-scoped everywhere.** Documents, candidates, Gmail connections and
  conversations belong to a user; a wrong-owner id is a 404, never a leak.
- **Answers must stay auditable.** Citations, confidence and intent are
  product surface, not debug output, and must remain visible in the UI.
- **Destructive actions are opt-in and reversible where possible.** Gmail
  deletion mirroring defaults off; conversations soft-delete.

## Terminology

Document, Candidate, Job, Application, Conversation, Connection (a Gmail
mailbox). "Ingest" is what happens to a file; "sync" is what happens to a
mailbox.

## Assets

`public/logo.svg` and its `components/ui/logo.tsx` twin — an ascending
four-bar chart in amber, pink, violet and blue. **Confirmed as a
commitment: the mark is preserved as-is.** Everything around it is open.

## Stack

React 19 · TypeScript · Vite · Tailwind v4 · shadcn/ui on Base UI ·
TanStack Query · react-router. Backend is FastAPI; the frontend consumes a
generated OpenAPI client and never hand-writes API types.

## Accessibility

Not formally committed to a WCAG level. Undecided — treat AA contrast as the
working floor until the user says otherwise.
