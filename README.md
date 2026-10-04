# AI Content Toolkit

A Claude Code plugin for technical documentation teams: eight Skills and four MCP servers that cover the full lifecycle of a Help Center article — cataloging raw source material, drafting against a structured content model, reviewing for AI-agent readability, enforcing vocabulary and style, and publishing through Paligo and Zendesk Guide. A ninth skill drafts audience-specific release notes from GitHub releases and Jira tickets.

This repo is a sanitized extract from a production content-ops setup — all customer names, internal URLs, API tokens, and proprietary reference tables have been removed or replaced with placeholders (see [Known gaps](#known-gaps) below). The Skills and MCP server code are otherwise unmodified from what ran in production.

## What's in here

### Skills

| Skill | What it does |
|---|---|
| [`source-librarian`](skills/source-librarian) | Catalogs raw knowledge artifacts (Zendesk tickets, Jira issues, GitHub files, call transcripts, Google Docs, PDFs, etc.) into tagged, indexed markdown — the knowledge base every other drafting skill reads from. |
| [`diataxis-drafter`](skills/diataxis-drafter) | Drafts customer-facing Help Center articles (how-to, tutorial, concept, troubleshooting, reference) from the cataloged knowledge base, following the [Diataxis](https://diataxis.fr/) framework. Flags gaps and conflicts instead of inferring or fabricating content. |
| [`ai-optimizer`](skills/ai-optimizer) | Reviews a drafted article against 25 checks for how well it performs when consumed by AI agents — RAG chunking, web fetch, and MCP/tool-calling access patterns — and produces a prioritized, executable recommendation report. |
| [`vocabulary-pal`](skills/vocabulary-pal) | Checks a document against a controlled vocabulary and flags non-preferred terminology with preferred replacements. |
| [`style-pal`](skills/style-pal) | Checks a document against a house style guide (voice, punctuation, UI text conventions, headings) layered on top of the Microsoft Writing Style Guide. |
| [`release-notes-drafter`](skills/release-notes-drafter) | Drafts customer-facing release notes for one audience at a time from a GitHub release and/or pasted commits and Jira tickets. Filters out internal-only work and reframes every note around customer value. |
| [`paligo-pal`](skills/paligo-pal) | Drives the Paligo CCMS via its REST API — documents, folders, images, productions, translations, taxonomies — including a full Google Doc → DocBook 5.1 XML conversion pipeline. |
| [`zendesk-guide-pal`](skills/zendesk-guide-pal) | Drives Zendesk Help Center — articles, content tags, labels, redirect rules — across separate prod and sandbox environments, plus theme export/edit/import/publish. |

### MCP servers

| Server | Backs | Covers |
|---|---|---|
| [`mcp/gdrive_mcp.py`](mcp/gdrive_mcp.py) | `paligo-pal` | Google Drive, Docs, Sheets, Slides — read, create, export, and convert content. |
| [`mcp/paligo_mcp.py`](mcp/paligo_mcp.py) | `paligo-pal` | The full Paligo REST API surface used above. |
| [`mcp/zendesk_guide_mcp.py`](mcp/zendesk_guide_mcp.py) | `zendesk-guide-pal` | Zendesk Help Center content + theming API, dual prod/sandbox environments. |
| [`mcp/zendesk_tickets_mcp.py`](mcp/zendesk_tickets_mcp.py) | `source-librarian`, `diataxis-drafter` | Read-only Zendesk ticket search, lookup, and reporting (volume, CSAT, tag breakdowns) — a knowledge source, not a write path. |

Each server is a plain Python script built on [`mcp.server.fastmcp`](https://github.com/modelcontextprotocol/python-sdk). None of this is Claude-specific — point any MCP-capable client at them.

### How they fit together

```
source-librarian  ──catalogs──▶  knowledge-stacks/  ──reads──▶  diataxis-drafter ──▶ draft .md
                                                                        │
                                                   vocabulary-pal ◀─────┤
                                                        style-pal ◀─────┤
                                                    ai-optimizer ◀──────┘
                                                                        │
                                                                        ▼
                                           paligo-pal (Google Doc → DocBook XML → Paligo)
                                                                        │
                                                                        ▼
                                                        zendesk-guide-pal (publish)

release-notes-drafter is independent: GitHub release + Jira ──▶ audience-specific notes.md
```

`diataxis-drafter` never talks to Paligo or Zendesk directly — it only writes markdown. `paligo-pal` and `zendesk-guide-pal` are the only skills with write access to an external system, and both default to the safest option (sandbox, or explicit confirmation) before changing anything live. See each skill's **Safety rules** section.

## Install

```
/plugin marketplace add cedar-ave/ai-content-toolkit
/plugin install ai-content-toolkit
```

Then finish setup below before using any skill that calls an MCP server (`paligo-pal`, `zendesk-guide-pal`, and the Google Drive step inside `paligo-pal`'s conversion pipeline). `source-librarian`, `diataxis-drafter`, `ai-optimizer`, `vocabulary-pal`, `style-pal`, and `release-notes-drafter` work with no setup — they only read/write local files (and, for `release-notes-drafter`, whatever GitHub/Jira MCP connectors you already have configured).

### Setup

1. **Install Python dependencies** (once, from the plugin's installed directory — find it via `/plugin` → select the plugin → "Open plugin folder"):

   ```bash
   pip3 install -r requirements.txt
   ```

2. **Create your `.env`** from the template:

   ```bash
   cp .env.example .env
   ```

   Fill in whichever sections you need — Paligo, Zendesk, or both. `.env` is git-ignored; never commit it. Every MCP server reads this one file via `python-dotenv`.

3. **Google Drive** (only needed for `paligo-pal`'s Google Doc conversion step) uses OAuth, not an env var:
   - Create a Google Cloud project, enable the Drive/Docs/Sheets/Slides APIs, and download an OAuth client secret as `mcp/credentials.json`.
   - The first Drive tool call opens a browser consent screen and caches the resulting token at `mcp/token.json` (git-ignored).

4. **Restart Claude Code** — MCP servers read `.env` at startup, not per-call.

## Known gaps

This is a sanitized extract, not the full original repo. A few skills reference companion files that lived alongside them in the source environment and are intentionally **not** included here because they're company-specific (proprietary vocabulary lists, internal field-ID mappings) rather than anything that failed to copy:

- **`vocabulary-pal`** and **`style-pal`** reference `references/vocabulary.md`, `references/style.md`, `references/microsoft-az.md`, and `references/microsoft-style-guide.md`. These are the controlled-vocabulary and style-guide source files; the skill logic (how to scan, how to report) is complete, but you'll need to supply your own reference files in those `references/` directories to run them as-is.
- **`source-librarian`** references four companion files (`slim_tickets.py`, `run_catalog_batch.sh`, `rebuild_indexes.py`, `zendesk-field-mapping.md`, `taxonomy.md`) that aren't included. The `SKILL.md` process documentation is complete and demonstrates the full cataloging workflow; the batch-processing scripts and taxonomy tables were specific to the originating Zendesk instance.

Everything else — all four MCP servers in full, and all eight `SKILL.md` process definitions — is included and runnable.

## License

MIT — see [LICENSE](LICENSE).
