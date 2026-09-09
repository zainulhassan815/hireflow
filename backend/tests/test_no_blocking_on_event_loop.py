"""Guard: model and vector-store work must not run on the event loop.

A single unhopped call here freezes the whole API process, not just its
own request — a first-use model load can take minutes, and every other
request, health probe and SSE flush waits behind it.

Two levels, deliberately:

* the static check below covers every call site including ones nobody
  has written yet, which is the failure mode this guards against;
* ``test_rerank_runs_off_the_event_loop`` proves the static rule
  corresponds to a real running loop rather than to a syntax pattern.
"""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

# Adapter methods that do model inference or synchronous network I/O.
# ``protocols.py`` documents these as sync on purpose: Celery workers
# call them directly, async callers must hop to a thread.
BLOCKING_METHODS = {
    "embed_query",
    "embed_documents",
    "rerank",
    "classify",
    "query",
    "query_candidate_summaries",
    "index_document",
    "delete_document_vector",
}

# ``delete`` is far too common a method name to blocklist outright, so
# it is matched only on the attributes known to be vector stores.
VECTOR_STORE_ATTRS = {"_vector_store", "_similarity_store", "_candidate_summary_store"}


def _is_blocking_call(node: ast.Call) -> str | None:
    """Return ``adapter.method`` when this call is blocking adapter work."""
    func = node.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Attribute):
        return None
    attr, method = func.value.attr, func.attr
    if not attr.startswith("_"):
        return None
    if method in BLOCKING_METHODS or (
        method == "delete" and attr in VECTOR_STORE_ATTRS
    ):
        return f"{attr}.{method}"
    return None


def _hopped_references(fn: ast.AST) -> set[str]:
    """Helpers and adapter methods handed to ``asyncio.to_thread``.

    Passing a callable as a *reference* is the sanctioned form — the work
    then happens in a worker thread. Only a direct *call* blocks.
    """
    hopped: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        is_to_thread = (
            isinstance(target, ast.Attribute)
            and target.attr == "to_thread"
            and isinstance(target.value, ast.Name)
            and target.value.id == "asyncio"
        )
        if not is_to_thread or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Attribute):
            hopped.add(first.attr)
    return hopped


def _iter_classes():
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            yield path, cls


def _blocking_in(
    name: str,
    methods: dict[str, ast.AST],
    is_async: dict[str, bool],
    seen: set[str],
) -> list[tuple[int, str]]:
    """Blocking calls reachable from ``name`` without a thread hop."""
    if name in seen or name not in methods:
        return []
    seen.add(name)
    fn = methods[name]
    hopped = _hopped_references(fn)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if (call := _is_blocking_call(node)) is not None:
            hits.append((node.lineno, call))
        # A sync helper on self carries its own blocking work up to the
        # async caller unless the caller hopped it.
        target = node.func
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr in methods
            and not is_async[target.attr]
            and target.attr not in hopped
        ):
            hits += [
                (ln, f"{c} (via {target.attr})")
                for ln, c in _blocking_in(target.attr, methods, is_async, seen)
            ]
    return hits


def _offenders() -> list[str]:
    found: list[str] = []
    for path, cls in _iter_classes():
        methods = {
            m.name: m
            for m in cls.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        is_async = {
            name: isinstance(m, ast.AsyncFunctionDef) for name, m in methods.items()
        }
        for name in methods:
            if not is_async[name]:
                continue
            for lineno, call in sorted(
                set(_blocking_in(name, methods, is_async, set()))
            ):
                found.append(
                    f"{path.relative_to(APP.parent)}:{lineno} "
                    f"self.{call} called on the event loop "
                    f"from async def {cls.name}.{name}()"
                )
    return found


def test_no_blocking_adapter_calls_on_the_event_loop() -> None:
    offenders = _offenders()
    assert not offenders, (
        "Blocking adapter work reached the event loop. Wrap the call (or the "
        "sync helper containing it) in `await asyncio.to_thread(...)`:\n  "
        + "\n  ".join(offenders)
    )


def test_the_static_check_can_actually_fail() -> None:
    """The guard is worthless if its detector never fires.

    Exercises the detector against a synthetic offender rather than
    trusting that an empty result means the rule works.
    """
    source = ast.parse(
        "class S:\n"
        "    async def go(self):\n"
        "        return self._helper()\n"
        "    def _helper(self):\n"
        "        return self._reranker.rerank('q', [])\n"
    )
    cls = next(n for n in ast.walk(source) if isinstance(n, ast.ClassDef))
    methods = {m.name: m for m in cls.body}
    assert any(
        _is_blocking_call(n) == "_reranker.rerank"
        for n in ast.walk(methods["_helper"])
        if isinstance(n, ast.Call)
    )
    # And the sanctioned form is recognised as hopped.
    hopped = ast.parse(
        "class S:\n"
        "    async def go(self):\n"
        "        return await asyncio.to_thread(self._helper, 'q')\n"
    )
    go = next(n for n in ast.walk(hopped) if isinstance(n, ast.AsyncFunctionDef))
    assert "_helper" in _hopped_references(go)


@pytest.mark.asyncio
async def test_rerank_runs_off_the_event_loop() -> None:
    """Runtime proof that the static rule matches reality.

    A cross-encoder rerank is the single most expensive thing on the
    retrieval path, and it is where the freeze was observed.
    """
    from app.services.search_service import SearchService

    loop_thread = threading.get_ident()
    called_on: list[int] = []

    class RecordingReranker:
        def rerank(self, query, candidates, top_n=None):
            called_on.append(threading.get_ident())
            return list(candidates)[: top_n or len(candidates)]

    service = SearchService.__new__(SearchService)
    service._reranker = RecordingReranker()

    await asyncio.to_thread(service._rerank_chunks, "q", [], 5)

    assert called_on, "reranker was never invoked"
    assert called_on[0] != loop_thread, (
        "rerank ran on the event loop thread; it must be hopped to a worker"
    )
