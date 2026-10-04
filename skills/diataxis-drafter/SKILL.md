---
name: diataxis-drafter
user-invocable: true
description: Generates customer-facing Help Center articles following the Diataxis content structure. Always reads source material from the fixed knowledge stacks at content-dev/knowledge-stacks. Uses a three-tier cost-optimized reading strategy — workflow shards and ticket index first, then targeted full reads of confirmed-relevant files across all content types, falling back to the master index only when the topic does not map to a known workflow. Outputs complete article drafts as markdown files in the skill's local outputs directory. Flags all gaps, conflicts, and missing information rather than inferring or fabricating content.
---

# diataxis-drafter

This skill generates customer-facing Help Center articles for a topic provided by the user. Articles follow the Diataxis content structure (how-to guide, tutorial, concept/explanation, troubleshooting, reference). Source material **always** comes from the fixed knowledge stacks at `content-dev/knowledge-stacks` — the user does not need to provide a library path. Output is written as markdown files in this skill's local `outputs/` directory.

This skill does not apply vocabulary or style standards — those are handled by separate postprocessing skills run after this draft is complete.

---

## Knowledge stacks — fixed relative location (resolve at session start)

The knowledge stacks are produced and maintained by the sibling `source-librarian` skill. Their location relative to this repo is fixed:

```
skills/source-librarian/knowledge-stacks/
```

**At session start, resolve `STACKS_DIR` to the absolute path for the current environment** and use it consistently:

1. If the user has already provided the absolute repo or skill path (in a prior turn or via project config), append `skills/source-librarian/knowledge-stacks/` to get `STACKS_DIR`.
2. Otherwise, ask the user once: *"What is the absolute path to the claude-plugins repo (or the source-librarian skill directory) in this environment?"* and derive `STACKS_DIR` from it.
3. In Cowork or other sandboxed environments the working filesystem path will differ from the user's local checkout (e.g., a `/sessions/<session-id>/mnt/...` mount). The user knows the correct path for the active shell; ask, do not guess.

Throughout this document, `<STACKS_DIR>` is a placeholder — substitute the resolved absolute path. Never read from a hardcoded local-username path, and never read from any location other than the resolved `STACKS_DIR`.

The library has the following structure:

```
knowledge-stacks/
  _index.md                          ← Compact master index of all non-ticket files with tags
  _index_tickets.md                  ← Compact ticket index — one line per zendesk_ticket, sorted newest first
  _index_workflow_<name>.md          ← Per-workflow index shards (non-ticket sources only)
  wiki_page/                         ← Wiki pages (reference, conceptual content)
  github_file/                       ← GitHub files (technical specs, code-level docs)
  call_transcript/                   ← Recorded customer call transcripts
  help_center/                       ← Published Help Center articles
  pdf_document/                      ← PDF release notes and internal documents
  product_assistant/                 ← Product reference and concepts
  release_notes/                     ← Release notes
  support_playbook/                  ← Internal support team playbooks and procedures
  implementation_guide/              ← Step-by-step guides with screenshots
  zendesk_ticket/                    ← Customer support tickets and resolutions
```

Each content type offers a different lens on the topic. A thorough evaluation draws from all types, not just the most obvious ones.

**Note on `pdf_document` and `release_notes`:** These are two physical directories but **one evaluation content type**. `pdf_document/` holds PDF-format release notes and other internal documents; `release_notes/` holds release notes in other formats. Treat candidates from either directory under the same relevance guidance (see the cross-type table in Step 4) and count them together as a single content type everywhere this document tallies content types by count.

This gives **nine** distinct content types for evaluation purposes: `wiki_page`, `github_file`, `call_transcript`, `help_center`, `pdf_document`/`release_notes` (combined), `product_assistant`, `support_playbook`, `implementation_guide`, `zendesk_ticket`.

**Note on Zendesk tickets:** Tickets are **not** inline in workflow shards; they're catalogued separately in `_index_tickets.md` and discovered via the tag-filtering procedure in Step 3b. Treat ticket candidates as first-class — tickets often contain callouts, expected-behavior explanations, error messages, and edge cases not found in implementation guides or GitHub files.

**Note on shard ordering:** Entries inside each shard are sorted primarily by source type (github_file → implementation_guide → help_center → product_assistant → call_transcript → release_notes → wiki_page → other), then by date (newest first). The order is the only ranking signal — there is no Priority Sources table. Older sources sort to the bottom of their type bucket but are not excluded; evaluate them in full just like the recent ones. This is the canonical sort order referenced elsewhere in this document.

---

## Safety rules — absolute, no exceptions

- **Never fabricate, infer, or hallucinate any content.** Every claim in the draft must be directly traceable to a source file. If information is not in the source material, flag it — do not guess.
- **Never summarize, compress, or drop source content to save context.** If a source file is confirmed relevant, extract all of its information completely. Long drafts are correct drafts.
- **Never edit, create, or write to knowledge stacks files.** This skill reads sources only.
- **Never expose internal information.** Replace any customer names, organization names, internal system names, internal URLs, or API credentials with generic placeholders: "your organization," "the provider," "the customer." If you encounter an internal URL or credential in a source file, omit it from the draft and add a `⚠️ REVIEW NEEDED` flag.
- **Copy UI labels, button names, field names, and step descriptions verbatim** from the source file. Do not paraphrase them.
- **If a source describes a conditional path ("if X then Y, otherwise Z"), extract both branches.** Do not pick one.
- **If information is missing:** Insert a flag and keep writing. Do not stop the draft for a missing piece.
- **If information conflicts across sources:** Include both versions and mark the conflict. Do not resolve it.

### Flag formats — use these exactly

```
⚠️ REVIEW NEEDED: [Describe specifically what information is missing or unclear]
```

```
⚡ CONFLICT: Source A says [X]. Source B says [Y]. A human reviewer must resolve this before publishing.
```

A draft full of flags is a good draft. A draft full of confident-sounding guesses is a dangerous one.

---

## Cost optimization strategy — three-tier reading

This skill handles knowledge stacks that contain thousands of files across nine content types (see "Note on `pdf_document` and `release_notes`" above). To minimize token usage, reading happens in three tiers. **Never skip ahead to a higher tier without completing the lower tiers first.**

- **Tier 1 — Index files only** (very cheap): Read `_index.md` in full (for broad/ambiguous topics), then read every relevant `_index_workflow_<name>.md` shard in full, then read `_index_tickets.md` once and filter its lines by the workflow tag of each shard you read. These files map topics and tags to source file paths with summaries. Do not open any source files at this stage.
- **Tier 2 — Metadata headers only** (cheap): For each candidate file identified from the indexes, read only the metadata front matter — the block between the opening `---` and closing `---` at the top of the file. Stop reading when the closing delimiter is found. This gives tags, summary, and drafting guidance without reading the actual source content (typically 600+ lines per file). Evaluate candidates across all nine content types.
- **Tier 3 — Full reads, targeted** (necessary, scoped): Only after confirming relevance from the metadata, read the full content of high-relevance files — completely, line by line, to the last line. Do not skim, truncate, or stop early.

Tiers 1 and 2 together typically reduce total reading by 70–80% compared to opening every source file.

---

## Step 1 — Gather inputs

Ask the user for the following. Do not proceed until all required items are provided.

**Required:**
1. **Topic**: What is the subject of the articles to be drafted? (e.g., "data import," "user enrollment," "account setup")
2. **Article types**: Which Diataxis article types should be produced for this topic? Options: how-to guide, tutorial, concept/explanation, troubleshooting, reference. The user may request one or several.

**Optional:**
3. **Additional context**: Any background about the topic, audience, or scope that will help filter sources.

**The relative location of the knowledge stacks within the repo is fixed at `content-dev/knowledge-stacks/` — do not ask the user to confirm the relative path.** If `STACKS_DIR` (the absolute path for the current environment) has not already been resolved per the session-start instructions above, resolve it now before proceeding.

Print this confirmation before proceeding:

```
INPUTS CONFIRMED ✓
Topic: [topic]
Article types: [list]
Knowledge stacks: <STACKS_DIR>
Output: <DRAFTER_DIR>/outputs/ (local markdown files)
```

---

## Step 2 — Load article templates

Read the file at `references/templates.md` in this skill's folder **in full**. Do not select a template from memory — read the file now.

Print this confirmation before proceeding: `TEMPLATES LOADED ✓`

---

## Step 3 — Tier 1: Scan library indexes

The knowledge stacks use a two-level index system. Work through both levels completely before identifying candidates.

### 3a — Choose a starting point

Before reading the master index, get the actual list of workflow shards: list the files in `<STACKS_DIR>` matching `_index_workflow_*.md` (e.g. with the `Glob` tool). **Never assume a shard name exists from memory or a guess** — a shard filename not present in this listing does not exist, and reading it as if it does is a fabrication under the Safety rules above.

**Workflow shard names** follow the pattern `_index_workflow_<name>.md`.

**If the topic clearly maps to one or more of the listed workflow shard names:** skip reading `_index.md` and go directly to step 3b. Record:
```
MASTER INDEX SKIPPED — topic maps directly to workflow shard(s): [list]
```

**If the topic is broad, ambiguous, or does not map to a known workflow name:** read `_index.md` in full. Zendesk ticket entries are not in `_index.md` — tickets are catalogued separately in `_index_tickets.md` and are scanned in step 3b after each shard read.

Each line in `_index.md` has the format:
```
[source_type] tag1 tag2 tag3 ... · [Title](path)
```
Scan each line for tags or title words that relate to the topic — including indirect relationships (e.g., if the topic is "monitoring," also note files tagged `data types` or `user screening` if those workflows involve monitoring steps). Record which content types appear to have relevant files.

Print a brief summary:
```
MASTER INDEX READ ✓
Potentially relevant content types found: [list]
Initial tag matches: [list of tags that matched the topic]
```

### 3b — Read relevant workflow index shards (`_index_workflow_*.md`) and the ticket index (`_index_tickets.md`)

The `knowledge-stacks/` root contains one `_index_workflow_<name>.md` file per workflow. These shards contain full entries for every **non-ticket** source file associated with that workflow.

From the master index scan, identify which workflow shard(s) are relevant to the topic. A workflow shard is relevant if:
- Its name matches or overlaps with the topic (e.g., topic "data monitoring" → `_index_workflow_data_monitoring.md`)
- The master index showed files from that workflow with matching tags

**For each relevant shard, read it in full using the `Read` tool.** Shards follow the sort order described in "Note on shard ordering" above. Read top-to-bottom and do not skim or stop early.

**After reading the relevant shard(s), read `_index_tickets.md` once.** This file is sorted newest-ticket-first and contains every cataloged Zendesk ticket as a one-line compact entry. For each shard you read in this session, filter the ticket index for lines that contain that shard's workflow tag — those are the ticket candidates for that workflow. Tickets often map to multiple workflows, so the same ticket can be a candidate for several shards in the same drafting session. Add every matching ticket file path to the candidate list.

After reading all relevant shards and filtering the ticket index, print:
```
WORKFLOW SHARDS READ ✓
Shards read: [list of filenames]
Shards skipped (with reason): [list]
Ticket index filtered for tags: [list of workflow tags]
Ticket candidates found: [count]
```

### 3c — Produce the candidate list

From the master index and workflow shard reads, compile the **candidate list** — every source file that may be relevant to the topic. Cast a wide net: it is better to over-include at this stage than to miss content.

Candidates must span all relevant content types. Do not limit candidates to a single type (e.g., only implementation guides or only wiki pages). If a `call_transcript` or `zendesk_ticket` discusses the topic, include it.

```
CANDIDATE FILES (from index scan):
1. [relative path from knowledge-stacks/] — [content type] — [reason relevant]
2. [relative path] — [content type] — [reason relevant]
...

Content types represented in candidates:
- wiki_page: [count] files
- github_file: [count] files
- call_transcript: [count] files
- help_center: [count] files
- pdf_document / release_notes (combined): [count] files
- product_assistant: [count] files
- support_playbook: [count] files
- implementation_guide: [count] files
- zendesk_ticket: [count] files
```

If a content type has zero candidates, state explicitly why (e.g., "No zendesk_ticket files appeared in the workflow shards for this topic") — do not silently omit a type.

---

## Step 4 — Tier 2: Metadata-only scan and cross-type evaluation

For each candidate file from Step 3, read **only the metadata header** — the block between the opening `---` and the closing `---` at the top of the file (see "Metadata header format" in the Appendix). Use the `Read` tool with `limit: 100` to fetch just the top of each file.

**Stop reading each file at the closing `---` delimiter.** Do not read the content body.

For each file, record:
- Full path (from `knowledge-stacks/` root)
- Content type (from the subdirectory name)
- Tags (from metadata)
- Summary (from metadata)
- Drafting guidance (from metadata, if present)
- Your relevance assessment: HIGH, MEDIUM, or LOW, with a one-sentence reason

### Cross-type evaluation — mandatory

Before finalizing relevance ratings, evaluate the candidates against each content type using the guidance below. Each type contributes something different to an article draft. Do not skip a type simply because you already have enough files from another type.

| Content type | What it contributes | When to rate HIGH |
|---|---|---|
| `wiki_page` | Conceptual definitions, reference data, admin configuration specs | When the topic needs authoritative "what is this" or "how is this configured" content |
| `github_file` | Technical implementation details, API behavior, field-level specs | When the topic involves integration, field mapping, API calls, or technical setup |
| `call_transcript` | Real customer workflows, spoken step-by-step procedures, common questions and pain points | When the topic involves a multi-step process customers perform — transcripts often contain undocumented steps |
| `help_center` | Previously published Help Center articles — existing phrasing, structure, and scope precedent | When an article on this or a closely related topic already exists and should inform tone, structure, or avoid duplicating/contradicting it |
| `pdf_document` / `release_notes` (combined type) | Release notes, versioned feature behavior, historical context | When the topic involves a feature whose behavior may have changed across versions |
| `product_assistant` | Curated product knowledge — what features are, how the system works, object/sync behavior, gotchas | When the topic needs authoritative product reference or conceptual grounding spanning the product |
| `support_playbook` | Known failure modes, escalation paths, internal resolution steps | When the topic has a troubleshooting component or known edge cases |
| `implementation_guide` | UI navigation with exact button/field labels at each step | When the topic involves a procedural workflow — implementation guides are the most reliable source for verbatim UI labels |
| `zendesk_ticket` | Customer-reported symptoms, actual error messages, edge cases in the wild | When the topic has a troubleshooting component or involves errors customers encounter |

After reading all candidate headers, produce a **relevance table organized by content type**:

```
RELEVANCE ASSESSMENT BY CONTENT TYPE:

── wiki_page ──
HIGH: [path] — [tags]. [summary]. Reason: [why]
MEDIUM: [path] — ...
LOW: [path] — ...

── github_file ──
HIGH: [path] — ...
(etc.)

── call_transcript ──
HIGH: [path] — ...
(etc.)

── help_center ──
HIGH: [path] — ...
(etc.)

── pdf_document / release_notes ──
HIGH: [path] — ...
(etc.)

── product_assistant ──
HIGH: [path] — ...
(etc.)

── support_playbook ──
HIGH: [path] — ...
(etc.)

── implementation_guide ──
HIGH: [path] — ...
(etc.)

── zendesk_ticket ──
HIGH: [path] — ...
(etc.)

CROSS-TYPE COVERAGE NOTE:
[State which types have HIGH candidates and which do not. For any type with no HIGH candidates,
explain why — e.g., "No support_playbook files were found in the workflow shards for this topic"
or "zendesk_ticket candidates were all rated LOW because none described symptoms related to this workflow."]
```

Then ask the user:

> "Before I read any source files in full, please review this relevance assessment. 
> - Confirm the HIGH list, or move any files to a different tier.
> - Decide what to do with MEDIUM files: include or skip?
> - Confirm the LOW list, or pull any files up.
>
> Once you confirm, I will read only the confirmed HIGH files in their entirety."

**Wait for explicit user confirmation before proceeding to Step 5.**

---

## Step 5 — Tier 3: Full source reads

Read every confirmed HIGH-relevance file **completely** — from the first line to the last line, including both the metadata header and the full content body. Do not skim, stop early, or truncate for length.

As you read each file, build a **raw extraction log** — a running record of every piece of information in the file that may be relevant to the topic. Record it in this format:

```
SOURCE: [file path]
---
[EXTRACT] [Section or line reference if visible]: [Exact content — verbatim quotes for UI labels, step text, field names, error messages. Paraphrase only for background context, and mark paraphrases as (paraphrase).]
[VARIANT] [If the file describes a label or name that differs from another source]: Label "[X]" in this source. Compare with "[Y]" in [other source].
[CONDITION] [If the file describes conditional behavior]: If [condition], then [outcome A]; otherwise [outcome B].
[GAP] [If information appears to be missing from this file that you expected to find]: [Describe what's missing]
[CONFLICT] [If this file contradicts another already-read file]: This file says [X]. [Other source] says [Y].
---
```

After reading all confirmed files, print:

```
SOURCE READS COMPLETE ✓
Files read: [count]
Total extracts logged: [approximate count]
Variants found: [list any UI label variants discovered across sources]
Conflicts found: [list any conflicts]
Gaps noted: [list any gaps already detected]
```

---

## Step 6 — Build section maps

For each article type the user requested, map the extracted content to the appropriate template sections.

Read `references/templates.md` again if needed to confirm section structure for each article type.

For each article type, produce a **section map**:

```
SECTION MAP — [Article type]: [Proposed title]
---
[Section name from template]
  Sources: [list of source files contributing to this section]
  Content: [brief description of what goes here, referencing extracts from Step 5]

[Next section]
  Sources: ...
  Content: ...

UNMAPPED EXTRACTS:
  [List any extracts from Step 5 that did not fit a section, with a note on why]

SECTIONS WITH NO SOURCE MATERIAL:
  [List template sections that have no supporting source content — these will become ⚠️ REVIEW NEEDED flags in the draft]
```

If any extracted content does not fit cleanly into the article type the user requested, ask before omitting:

> "The following content from the sources does not fit a [article type] template section:
> - [Extract]: [proposed reason for omission]
>
> Should I omit this, or does this suggest we need an additional article type?"

**Wait for confirmation on any proposed omissions before writing the draft.**

---

## Step 7 — Write the draft

Write each requested article one at a time. For each article:

### 7a — Select the correct template

From `references/templates.md`, select the template matching this article type. Copy its full section structure as your skeleton before writing a single word of content.

### 7b — Draft section by section

Work through every section of the skeleton in order. For each section:

1. Consult the section map from Step 6 to identify which source extracts belong here.
2. Write the section using only the extracted content from Step 5. Do not introduce any information not present in the extracts.
3. Apply the formatting rules below as you write each section.
4. After finishing the section, check: is every claim traceable to an extract? Is every UI label verbatim? If no — fix it before moving on.

**Do not write the entire draft first and then apply rules afterward. Apply rules section by section as you write.**

### 7c — Formatting rules (apply throughout)

**Voice and person:**
- Active voice. "Click **Save**" not "Save should be clicked."
- Second person. "You can…" not "Users can…"
- Present tense. "The page displays…" not "The page will display…"

**UI elements:**
- Bold every UI element name on every reference: **Save**, **Provider profile**, **NPI**.
- Never put quotes or inline code around UI element names.
- Copy UI labels exactly as they appear in the source, do not paraphrase or normalize.
- Inline code only for typed values and system strings: `Active`, `1234567890`, `POST /api/v2/providers`.

**Structure:**
- Sentence case throughout, in headings, list items, and body text.
- Serial comma in all lists.
- "Expected result:" prefix for all verification checkpoints; never "You will see" or "Notice that."
- Colon separator in definition list entries; never an em dash.
- Steps start with a bare infinitive verb: "Click", "Select", "Enter"; not "Clicking", "Selecting".
- Do not use horizontal rules (`---`) anywhere in the article draft. Use headings to separate sections instead.

**Punctuation:**
- **Never use em dashes (—) anywhere in the article draft.** This applies to body text, headings, lists, tables, callouts, and flag descriptions. Em dashes are stylistically inconsistent with the company's content standards and impede AI-agent parsing.
- Rewrite sentences to avoid em dashes. Use one of the following instead, whichever best fits the meaning:
  - A period (separate sentences) when the clause stands on its own.
  - A semicolon when joining two closely related independent clauses.
  - A colon when introducing a list, definition, or explanation.
  - A comma (or pair of commas) for parenthetical asides.
  - Parentheses for true asides or clarifications.
- Do not substitute en dashes (–) or double hyphens (`--`) for em dashes. The goal is to eliminate the construction, not disguise it.
- Hyphens (-) in compound modifiers (e.g., "data-source capture", "customer-facing") are fine and unaffected by this rule.
- **Use tables generously.** Whenever source material contains comparisons, multi-attribute lists, field definitions, option sets, or parallel structures (e.g., symptom/cause/fix, value/description/default), render them as a markdown table rather than prose or bullet lists. Tables significantly improve scannability for both human readers and AI agents. Do not reserve tables only for reference articles — use them in how-to guides, concept articles, and troubleshooting articles wherever the content has two or more attributes per item.

**Callout blocks — use throughout the draft:**
Whenever source material contains a best practice, warning, or important note, render it as a labeled callout block using blockquote syntax. Use exactly one of these three labels — do not invent others.

> **Best practice:** [Content from source describing a recommended approach, optimal workflow sequence, or tip that improves outcomes.]

> **Warning:** [Content from source describing a risk, destructive action, irreversible state, or condition that can cause data loss or errors if ignored.]

> **Important:** [Content from source describing a requirement, constraint, or behavioral detail that users must know before or during a task — but that does not rise to the level of a warning.]

Rules for callouts:
- Use callouts only when the source material explicitly frames content as advisory, cautionary, or noteworthy — not for every piece of supplemental information.
- Place the callout immediately adjacent to the step or section it applies to.
- Never use a callout to replace a step. If content is both a required action and a warning, include it as a step and add the callout below it.
- Apply these consistently across all article types (how-to, tutorial, concept, troubleshooting, reference).

**Handling variants (environment-specific terminology):**
When source files describe the same UI element under different names in different customer environments, document all observed names using this pattern:

> Click **Add User** (also called **Enable User** or **Enter User**, depending on your organization's configuration).

Rules for variants:
- Never suppress a variant to simplify the text. Include every name observed across all sources.
- If the sources describe which customers or configurations use which name, include that context: "called **Add Account** in organizations using the legacy interface."
- If two sources use different names for the same element and you cannot confirm they refer to the same element, flag it:

```
⚡ CONFLICT: Source A refers to this action as **Add User**. Source B refers to **Enable User**. It is not confirmed whether these are the same control. A human reviewer must verify before publishing.
```

**Handling missing information:**
When a template section requires information that is not present in any source file, write the section heading and insert the ⚠️ REVIEW NEEDED flag (format defined in "Safety rules" above), describing specifically what's missing — e.g., "No source file describes the expected result after clicking Save on the account screen."

Then continue to the next section. Do not stop the draft.

**Handling conflicting information:**
When two source files provide contradictory information, include both and insert the ⚡ CONFLICT flag (format defined in "Safety rules" above), quoting or paraphrasing what each source states.

Do not pick one version. Do not average them. Present both.

**Handling internal information:**
If a source file contains customer names, organization names, internal system names, internal URLs, or API tokens, replace with a generic placeholder in the draft text and add:

```
⚠️ REVIEW NEEDED: Internal reference removed. The source file contains [describe what was omitted, e.g., "a specific customer organization name" or "an internal API endpoint"]. Replace with the appropriate customer-facing reference before publishing.
```

### 7d — Article length

There is no upper length limit. The goal is to cover all information offered in the relevant source files, not a subset. A longer, complete draft is correct. A shorter draft that drops source content is not.

### 7e — AI-agent optimization

Because these articles will be consumed by AI agents as well as human readers, apply these structural conventions throughout:

- **Every section heading is a complete, standalone label.** A reader or agent that lands on any section heading should immediately understand what that section covers without reading the rest of the article.
- **Verification checkpoints use the exact prefix "Expected result:"** on every instance — never varied — so agents can reliably locate confirmation signals.
- **Error messages are bolded verbatim** — never paraphrased — so agents can match them against live product output.
- **The Symptom-to-cause map in troubleshooting articles** provides a machine-traversable index of symptoms to causes.
- **The Key terms section in concept articles** lists canonical term → synonyms explicitly, so agents can map variant phrasings to the correct concept.
- **Related concepts in concept articles** use explicit directional relationship labels ("is a type of," "depends on," "is distinct from") rather than vague prose, so agents can traverse concept relationships.
- **Scope statements in reference articles** explicitly name what the page covers and does not cover, enabling agents to confirm relevance before parsing.
- **Definition sections in concept articles** label each dimension explicitly (What it is, Who uses it, When it applies, Where it fits, Why it exists, How it works) so individual dimensions are individually locatable.
- **Use case triplets** (Situation / Application / Outcome) are presented as structured, labeled blocks — not narrative prose — so agents can extract discrete scenarios.

---

## Step 8 — Review flags summary

After all articles are drafted, produce a consolidated flags summary:

```
FLAGS SUMMARY
=============

⚠️ REVIEW NEEDED (missing information):
1. [Article title], [Section]: [Description]
2. ...

⚡ CONFLICTS (contradictory source information):
1. [Article title], [Section]: [Description]
2. ...

Internal references removed:
1. [Article title], [Section]: [Description]
2. ...

Total flags: [count]
```

---

## Step 9 — Save drafts locally

Save each article draft as a markdown file in this skill's `outputs/` directory:

```
<DRAFTER_DIR>/outputs/draft-[article-slug].md
```

Where `<DRAFTER_DIR>` is the absolute path to this skill's directory (`skills/diataxis-drafter/`) — resolve it from the repo path the user confirmed at session start. Never use a hardcoded local-username path.

Use a descriptive slug derived from the article title: e.g., `draft-add-user.md`, `draft-about-data-entities.md`.

Create the `outputs/` directory if it does not already exist.

After saving each file, print the confirmation:

```
SAVED ✓
Article: [title]
File: <DRAFTER_DIR>/outputs/draft-[article-slug].md
```

---

## Step 10 — Handoff message

After all drafts are saved locally, print this message:

---

**Draft complete.**

The following articles have been written to `<DRAFTER_DIR>/outputs/`:

[List each article title and its local file path]

**Before these articles are published, a human reviewer must:**
- Resolve all ⚡ CONFLICT flags — these represent contradictory information across source files that this skill cannot resolve.
- Fill all ⚠️ REVIEW NEEDED flags — these represent information that is missing from the source material and must be supplied by a subject matter expert.
- Test all procedural steps end-to-end in the actual product.
- Verify that all UI labels, button names, and field names are current and match the live product.
- Remove or replace all generic placeholders (e.g., "your organization") with the appropriate customer-facing language if specific context is needed.

**Next steps:** Run the vocabulary and style postprocessing skills on each draft to apply terminology and writing standards.

---

## Appendix: Knowledge stacks reference

The knowledge stacks are always at `<STACKS_DIR>` (resolved at session start — see "Knowledge stacks — fixed relative location" above; relative path within the repo is `skills/source-librarian/knowledge-stacks/`). Its structure is fixed and known — do not ask the user about its contents or layout.

**Metadata header format (all source files):**
```
---
topic: [topic name]
tags: [tag1, tag2, tag3]
summary: [one or more sentences describing the content of this file]
drafting_guidance: [optional notes for the drafter about how to use this file]
---
[source content begins here]
```

**`_index.md` format:**
One line per file after the header block:
```
[content_type] tag1 tag2 tag3 ... · [Title](relative/path.md)
```

**`_index_tickets.md` format:**
One line per ticket, same shape as `_index.md`:
```
[zendesk_ticket] tag1 tag2 tag3 ... · [Title](zendesk_ticket/zd-ticket-<id>.md)
```
Sorted by date (newest first). Filter by workflow tag to discover ticket candidates for a workflow.

**`_index_workflow_<name>.md` format:**
Full entries for non-ticket sources associated with the workflow: file path, source type, ID, created date, status, tags, summary, and "Use when" guidance (capped at 3 sentences). Sorted using the same source-type-then-date order described in "Note on shard ordering" above. Read each relevant shard in full — do not skip sections. Discover ticket candidates separately via `_index_tickets.md`.
