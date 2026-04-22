FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    # F105.b — LibreOffice headless is used by OfficeToPdfProvider to
    # convert docx / pptx / odt / rtf into a PDF viewable asset at
    # ingest time. Component subset keeps image size down (~500 MB vs
    # ~900 MB for the meta-package): core + Writer (docx/odt/rtf),
    # Impress (pptx/odp). Spreadsheet support arrives with F105.c and
    # will append libreoffice-calc to this list.
    libreoffice-core libreoffice-writer libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
