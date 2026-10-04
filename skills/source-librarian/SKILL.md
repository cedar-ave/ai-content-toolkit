---
name: source-librarian
user-invocable: true
description: "Catalogs raw knowledge artifacts from any source (Zendesk tickets, Jira issues, GitHub files, call transcripts, Slack threads, Google Docs, implementation guides, meeting notes, slides, plain text, PDFs) into tagged, indexed markdown files in the knowledge stacks. See the Description section below for full detail."
---

# Source Librarian Skill

## Description

Catalogs raw knowledge artifacts from any source (Zendesk tickets, Jira issues, GitHub files, call transcripts, Slack threads, Google Docs, implementation guides, meeting notes, slides, plain text, PDFs, etc.) by reading each file completely, applying structured taxonomy tags, generating a PII-free summary and drafting guidance block, and storing the enriched markdown file in the knowledge stacks. Maintains two index layers for efficient AI-assisted drafting at scale: a compact top-level index for full-library tag scanning, and per-workflow shard indexes with full summaries for targeted topic lookups.

Zendesk tickets are read not only as troubleshooting sources but as primary inputs for **how-to articles** (when a ticket contains a procedure or step sequence a user must follow) and **conceptual articles** (when a ticket explains why something works a certain way, the purpose of a feature, or the relationship between system components). Every ticket is evaluated across all Diataxis content types before any intent tags are assigned.

**Trigger phrases:** "catalog this file/these files", "add to source library", "tag this source" / "index this knowledge", "prepare sources for drafting", "run source librarian", "extract how-to/conceptual content from tickets"

**Companion files in this skill's directory:**
- `slim_tickets.py` — Phase 1 script for Zendesk batch processing (field slimming, platform filtering, boilerplate stripping)
- `run_catalog_batch.sh` — Unattended batch loop for large NDJSON files; spawns a fresh Claude session per batch and loops until all tickets are cataloged. **Must be run from a terminal outside Claude Code** — it cannot be invoked from within a Claude prompt. Run this instead of opening new sessions manually. Usage: `./run_catalog_batch.sh` or `./run_catalog_batch.sh --batch-size 20`
- `rebuild_indexes.py` — Regenerates `_index.md`, `_index_tickets.md`, and every `_index_workflow_<name>.md` shard from source-file YAML front matter. Applies the canonical sort order (source type → date), unified entry skeleton, relative paths, ≤3-sentence `Use when:` cap, mtime fallback for undated sources, and dedupe. Use for repair runs, format migrations, and sort-order changes. Usage: `python3 rebuild_indexes.py` (operates on `knowledge-stacks/` next to this file)
- `zendesk-field-mapping.md` — Zendesk custom field IDs, valid values, and taxonomy mappings
- `taxonomy.md` — Full valid tag values for all taxonomy dimensions

---

## Path Reference (resolve at the start of each session)

This skill operates on three directories relative to the skill's own location:

- **Skill directory** (`SKILL_DIR`) — the directory containing this `SKILL.md`
- **Input (sources to ingest)** (`SOURCES_DIR`) — `<SKILL_DIR>/sources-to-ingest/`
- **Output (knowledge stacks)** (`STACKS_DIR`) — `<SKILL_DIR>/knowledge-stacks/`

**At session start, resolve `SKILL_DIR` to an absolute path for the current environment** and use it consistently throughout the run:

1. If the user has already provided the absolute path (e.g., in a prior turn or via project config), use it.
2. Otherwise, ask the user once: *"What is the absolute path to the source-librarian skill directory in this environment?"* — and use the value they give.
3. In Cowork or other sandboxed environments the working filesystem path will differ from the user's local checkout (e.g., a `/sessions/<session-id>/mnt/...` mount). The user knows the correct path for the active shell; ask them, do not guess.

Throughout this document, `<SKILL_DIR>`, `<SOURCES_DIR>`, and `<STACKS_DIR>` are placeholders. Substitute the resolved absolute path in every Bash command. Never use a hardcoded local-username path or a stale session ID.

---

## CRITICAL Rules — Read Before Every Run

1. **Read every file completely, line by line, to the very end.** Never stop reading early. If a file exceeds the default read window, use `offset` + `limit` on successive Read calls until confirmed complete.
2. **Never infer, fabricate, or hallucinate information.** Only tag and summarize what is explicitly present in the file.
3. **PII is strictly forbidden in `summary` and `drafting_guidance` fields.** See PII Rules section below.
4. **Apply only tags from the taxonomy.** See `taxonomy.md`. Do not invent tags.
5. **Preserve the original raw content** in the body of the output file, minus stripped boilerplate (Step 3).
6. **Never skip a file.** Process every file provided, one at a time, in full.
7. **Use the minimum tokens necessary.** Read, tag, summarize, write. Do not narrate reasoning extensively.
8. **Skip already-cataloged files.** Before processing, run the per-source-type skip check. For non-ticket sources, skip when the output path exists. For Zendesk tickets, skip based on the completion log — see Step 2B-1. Skip unless `--refresh` was passed.
9. **Write tight.** Omit filler, hedging, and restatement in all summary and guidance fields.
10. **Do not re-read output files after writing.** The Write tool errors on failure — re-reading wastes context.
11. **Release file content after each write.** Once written and indexed, discard raw content from active consideration. Retain only the one-line confirmation.

---

## Process

### Step 1 — Receive Input and Check for Existing Catalog Entry

Accept: a single file path, a list of paths, or a directory path. Optionally: `--refresh` flag.

If a directory is given, list all files and process each individually and completely before moving to the next.

**Skip check — run before processing each file:**
1. Compute the expected output path (Step 10 logic)
2. Run: `test -f <expected_output_path> && echo exists` via Bash
3. If exists and no `--refresh`: output `⟳ Skipped (already cataloged): <path>` and move on
4. If exists and `--refresh`: proceed and overwrite
5. If not exists: proceed

---

### Step 2 — Convert to Markdown (if needed)

| Format | Action |
|--------|--------|
| `.md`, `.txt`, `.csv` | Use as-is |
| `.pdf` | `pdftotext` via Bash or pdf skill |
| `.docx` | `python3 -c "import docx; doc=docx.Document('path'); print('\n'.join([p.text for p in doc.paragraphs]))"` |
| `.pptx` | `python3 -c "from pptx import Presentation; prs=Presentation('path'); [print(s.text) for slide in prs.slides for s in slide.shapes if s.has_text_frame]"` |
| `.html` | Strip tags via `python3` HTMLParser or `lynx --dump` |
| `.json` / `.ndjson` | Inspect first — if Zendesk ticket batch, use **Step 2B** below. Otherwise pretty-print. |
| `.xlsx` | Convert to markdown table via pandas |
| Images | Use Claude vision to transcribe visible text |

---

### Step 2B — Zendesk Ticket Batch Processing (JSON / NDJSON source)

Use this step when the input is a `.json` or `.ndjson` file containing Zendesk ticket objects (each with `id`, `subject`, `description`, `custom_fields`, `comments`, `tags`). This path replaces Steps 3–12 for batch ticket inputs. Each ticket produces one output file at `knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md`.

---

#### Phase 1 — Slim and Filter (run once per source file, in Python)

Run `slim_tickets.py` (companion file in this skill's directory) via Bash. It produces a lean NDJSON that Claude can process ticket-by-ticket without loading the full export into context.

**What the script does:**
- Keeps only the 10 custom fields listed in `zendesk-field-mapping.md` (drops all others)
- Excludes API-tagged tickets (API is a separate product), App B product areas/tags without an `app-a` tag, and known-ambiguous product areas (`misc`, `api`); untagged tickets (no product area set) pass through for Claude to infer platform from content
- Strips boilerplate from description and comment text (signatures, email headers, HTML entities, filler ack lines, social footers, Paubox banners, forwarded message dividers)
- Deduplicates comments that repeat the description verbatim
- Collapses excessive blank lines
- Outputs slimmed records as NDJSON (one ticket per line) — ~85% smaller than the raw export

**Run it:**
```bash
python3 skills/source-librarian/slim_tickets.py \
  sources-to-ingest/zendesk/sf-tickets.ndjson
# Produces: sources-to-ingest/zendesk/sf-tickets_slimmed.ndjson
```

Confirm the output line count before continuing:
```bash
wc -l <output_slimmed.ndjson>
# Expected: total lines = (input lines) minus exclusions
# Excluded: API-tagged tickets, App-B-only tickets, and known-ambiguous product areas without an `app-a` tag.
# Untagged tickets (no product area set) pass through for content-based inference by Claude.
```

---

#### Phase 2 — Per-Ticket Cataloging (Claude processes the slimmed file)

Process one ticket at a time from the slimmed NDJSON. For each ticket:

**2B-1. Determine output path and skip check.**

Output path: `knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md`

Use the completion log as the authoritative skip signal — not file existence. A file that exists but is absent from the log was interrupted mid-write and must be reprocessed:

```bash
grep -qx "<id>" knowledge-stacks/zendesk_ticket/_completed.log 2>/dev/null && echo exists
```

If the ID is in the log and no `--refresh`: output `⟳ Skipped: <id>` and move to the next ticket.

If the output file exists but the ID is **not** in the log: delete the file and reprocess — it was interrupted mid-write.

```bash
test -f knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md && \
  ! grep -qx "<id>" knowledge-stacks/zendesk_ticket/_completed.log 2>/dev/null && \
  rm knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md && echo "Purged incomplete file for <id>"
```

**2B-2. Read the slimmed NDJSON incrementally.**

Do NOT load the entire slimmed file into context. Read it line by line using a Python one-liner that emits only the next unprocessed ticket:

```bash
# Find the next ticket not yet cataloged
python3 - <<'EOF'
import json, os

slimmed = "sources-to-ingest/zendesk/sf-tickets_slimmed.ndjson"
output_dir = "knowledge-stacks/zendesk_ticket"
batch_size = 10  # Default per Step 2B-7; override with the count the caller specified

count = 0
with open(slimmed) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        out = os.path.join(output_dir, f"zd-ticket-{r['id']}.md")
        if not os.path.exists(out):
            print(json.dumps(r))
            count += 1
            if count >= batch_size:
                break
EOF
```

This emits only the next N unprocessed tickets as JSON lines, keeping Claude's context small.

**2B-3. For each emitted ticket record, apply Steps 5–9 (metadata, taxonomy, summary, drafting guidance, output assembly) using the ticket's slimmed fields.**

Field mapping for metadata extraction:
- `title` ← `subject`
- `source_id` ← `id`
- `source_url` ← `https://{instance}.zendesk.com/agent/tickets/<id>`
- `created_at`, `updated_at`, `status`, `priority` ← direct fields
- Taxonomy signals ← `tags` + `custom_fields` per `zendesk-field-mapping.md`
- AI-generated signals ← custom field `4923340758635` (Summary AI) and `4923308340499` (Intent AI) when non-null

**Platform determination — infer from content when metadata is absent:**

The slimmed NDJSON excludes the clearest non-App-A tickets, but some ambiguous tickets may pass through (e.g., product area `Feature A` with no platform tag). For these, read the ticket body and comments to infer platform before deciding whether to catalog:

- References to managed package concepts: "managed package", "package version", "sandbox", "production org"
- App A signals: `app-a` tags, or references to a customer's App A instance

**App B signals in content** — assign `platform: app-b` if content references App B without any App A context: the web portal, web login, browser-based account pages

**If platform still cannot be determined after reading content** — **skip the ticket, do not write the output file.** Output `⊘ Skipped (platform unclear): <id>` and move to the next ticket. Do not catalog tickets that cannot be attributed to App A.

**2B-4. Body content in the output file.**

The body section (after the YAML front matter) is structured to maximize extractability by the diataxis-drafter skill, which reads these files in full and maps content to troubleshooting/how-to template sections.

**Description section** — use labeled sub-sections when the ticket description contains structured fields (the support request template produces these consistently):

```
## Description

<stripped description prose>

**Steps taken:**
- <step>
- <step>

**Error:** `<exact error message string>`

**Customer impact:** <impact>

**Environment:** <Sandbox or Production>
```

If the description is plain prose with no template structure, write it as-is without forcing labels.

**Bold all verbatim error message strings** wherever they appear — in the description, in comments, and in the resolution. This signals to the diataxis-drafter that the string is a literal product output that must not be paraphrased. Example: **"user creation failed: entity is deleted"**

**Comments section** — use a semantic label in the heading when the content type is clear:

```
## Comments

### [Symptom detail]
<content>

### [Resolution]
**Root cause:** <what caused the issue>
**Fix:** <what was done to resolve it>

### [Secondary issue: <brief label>]
<content>
```

Semantic label options: `Symptom detail`, `Resolution`, `Agent investigation`, `Secondary issue: <label>`, `Escalation note`. Use the label that best describes what the comment contributes. If no clear type applies, omit the heading entirely and write the content as plain prose under `## Comments`.

When a comment contains a resolution, always use two explicit sub-labels even if both are in the same comment:

```
**Root cause:** <what caused the issue — be specific>
**Fix:** <what was done — be specific>
```

This lets the diataxis-drafter map directly to troubleshooting template sections (Cause, Resolution) without inference.

Before including a comment body, apply semantic cleanup — remove content that Python cannot strip reliably because it lacks a consistent structural anchor:

**Strip from each comment body:**
- Trailing closer lines and everything after: "Best,", "Best regards,", "Kindly,", "Sincerely,", "Thanks,", "Thank you," when used as a sign-off (i.e., followed by a name or end-of-text — not when "thank you" appears mid-sentence with meaningful content after it)
- Name/title/contact blocks at the end of a comment — lines that are only a person's name, job title, phone number, email address, organization name, or URL, with no product-relevant content
- Standalone pleasantries with no issue content: "Have a great weekend!", "Hope you have a great rest of your week!", "Enjoy the rest of your Friday!", "I just recently got back from the holidays", "Happy Friday!", "I appreciate your patience here!" when it is the entire sentence
- Filler closer sentences: "If anything else comes up, don't hesitate to reach out", "Feel free to let me know if you have any follow-up questions", "Let me know if you have any questions and I'd be happy to help!", "I'll go ahead and close this out" when it contains no issue-specific detail

**Preserve:**
- Any sentence where a pleasantry is attached to a substantive update: "Our team added the account admin to your list. Can you please try to create the account again?" — keep the whole sentence
- Closer lines that contain a decision or status: "Hi George, please close out this ticket - it has since been resolved." — the resolution status is signal; keep it, strip "Hi George" only

**Omit the entire comment** if nothing remains after cleanup, or if the comment is:
- A verbatim duplicate of the description
- A pure agent acknowledgement with no issue-specific content ("Thank you for reaching out, we're looking into it")
- A customer confirmation that the fix worked: "Thank you. This has resolved.", "Thank you! That fixed it.", "We should be all good now!", "Looks good, thanks!" — these add no drafting signal
- Only a name, a greeting, or a single word/emoji

If all comments reduce to nothing after cleanup, omit the Comments section entirely.

**2B-5. Write the file immediately.**

Write `knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md` using the Write tool as soon as the output is assembled for that ticket. Do not batch multiple tickets before writing. This ensures no data is lost if the session compresses or is interrupted.

After the Write tool confirms success, append the ticket ID to the completion log using the absolute path resolved at session start (see Path Reference):
```bash
echo "<id>" >> <STACKS_DIR>/zendesk_ticket/_completed.log
```

Substitute `<STACKS_DIR>` with the absolute path resolved at session start (see Path Reference) — a relative path would silently create the log in the wrong location, breaking all completion tracking.

This must happen after the Write tool confirms success — not before. The completion log is the authoritative record that a ticket was fully written. A ticket whose output file exists but whose ID is absent from the log was interrupted mid-write and will be deleted and reprocessed on the next run.

After writing, output one confirmation line and release the ticket from context:
```
✓ Cataloged: knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md
```

**2B-6. Update indexes.**

After writing the file, append a line to `_index_tickets.md` per Step 11 (Index B) — not to any workflow shard (see Step 11 for why).

**2B-7. Batch limit and resumability.**

Process the number of tickets specified by the caller (default: 10). Stop cleanly after that count — do not prompt the user to continue or open a new session. The slimmed NDJSON is the persistent source of truth; the per-ticket output files are the progress state.

When running via `run_catalog_batch.sh`, the script handles looping and session management automatically. Each session starts fresh and the skip-check (2B-1) ensures no ticket is processed twice.

When running manually: re-run the Phase 2 Python snippet (2B-2) to resume — it skips already-cataloged tickets and emits only the next unprocessed batch.

---

#### Git Repository — Reading and Tagging

When the input is a git repository path or a set of source files from a codebase, use the following reading order and tagging guidance. Process each file as a `github_file` (or `github_issue` / `github_pr` if applicable). Do not catalog every file — prioritize high-signal files per the order below.

**Recommended reading order:**

1. **Model and entity files** (ORM models, Apex objects, schema definitions) — establish the object vocabulary; tag `object`, `module`, `platform`
2. **Enums, constants, and status definitions** — reveal valid statuses and lifecycle stages; tag `stage`, `object`, `module`
3. **Service and domain layer** (business logic classes, use-case handlers) — each public method is typically one user-facing operation; tag `feature`, `workflow`, `module`
4. **Event, trigger, and queue files** (platform events, async handlers, batch jobs) — reveal async workflows and integration patterns; tag `workflow`, `integration`, `technical`
5. **Exception and error classes** (custom exceptions, error message strings, validation failure branches) — tag `issue`, `stage: error-handling`, `stage: resolution`
6. **Permission sets, roles, and auth guards** — reveal who can do what and setup requirements; tag `role`, `stage: setup`, `intent: configuration`
7. **Configuration and metadata** (custom metadata types, feature flags, settings objects) — reveal configurable vs. hardcoded behavior; tag `module` (administration), `intent: configuration`
8. **Test files** — test names are plain-language descriptions of behaviors; use as a cross-check and gap-filler for `feature`, `workflow`, and `issue` tags

**What to extract per file:**

| File type | What to extract |
|---|---|
| Model / entity | Object names, field names, relationships, validation rules |
| Enum / constants | Valid values, state transitions, lifecycle phases |
| Service / domain | Public method names (→ features), call sequences (→ workflows), guard conditions (→ stages/issues) |
| Event / trigger | Event names, trigger conditions, consumers, retry logic |
| Exception / error | Exception class names, message strings, resolution paths |
| Permission / auth | Permission names, role checks, object/field security |
| Config / metadata | Configurable settings, admin-facing options, dependencies |
| Test | Behavioral descriptions in test names; happy path and error cases |

**Taxonomy signal mapping:**

| Taxonomy dimension | Where to find the signal |
|---|---|
| `platform` | Runtime target → `app-a`; REST handler → `api`; browser code → `app-b` |
| `module` | Directory structure (e.g., `/enrollment/` → enrollment module) |
| `feature` | Public service method names, use-case class names, controller actions |
| `workflow` | Call sequences within service methods; event chains across classes |
| `stage` | Status enum values, lifecycle annotations, phase-labeled methods |
| `object` | Domain model class names, App A object names |
| `technical` | Technology used |
| `issue` | Exception type names, error message strings, validation failure branches |
| `intent` | `reference` for model/constant files; `conceptual` for architecture; `task-oriented` for workflow/service files |
| `role` | Permission set names, role-guard method parameters |

**Skip these files** — they produce no drafting signal:
- Lock files (`package-lock.json`, `yarn.lock`, `Pipfile.lock`)
- Build artifacts and compiled output
- Auto-generated files (migration auto-files, generated stubs)
- CI/CD workflow configs (`.github/workflows/`, `Jenkinsfile`)
- IDE and editor config (`.vscode/`, `.editorconfig`)
- Dependency manifests unless inspecting package names for integration signals (`package.json`, `pom.xml`)

**`source_type` for git repo artifacts:**

| Artifact | `source_type` |
|---|---|
| Individual source file | `github_file` |
| GitHub issue | `github_issue` |
| Pull request with behavior description | `github_pr` |

**Skip Step 3** (boilerplate stripping) for source code files — code has no boilerplate to strip. Proceed directly to Step 4.

---

### Step 3 — Strip Boilerplate

Strip zero-knowledge content. Set `boilerplate_stripped: true` in YAML if anything is removed.

**Strip:**
- Email signature blocks (everything after a standalone `--` line, plus name/title/social links)
- Email security banners ("Secured by Paubox", "HITRUST certified")
- Support system footers (help center link-only lines, ticket auto-footers)
- Filler opener/closer lines containing no issue-specific content
- Verbatim duplicate blocks (keep one copy)
- Reaction-only Slack lines (emoji / "+1" with no text)
- Call join/leave noise ("[User joined]", "[Silence]", etc.)
- Legal disclaimers and confidentiality notices
- Marketing footers and social media follow links

**Never strip:** error messages, status updates, resolution notes, technical descriptions, user-reported symptoms, diagnostic steps, or any content describing product behavior.

---

### Step 4 — Read Cleaned Content Completely

Read every line to the end. For files over 2000 lines, use successive Read calls (offset + limit) until fewer lines are returned than requested. Do not proceed to Step 5 until all content is confirmed read.

---

### Step 5 — Determine Metadata Fields

Extract if present (omit if not):
- `title` — descriptive title; use filename if none in content
- `source_type` — see the full list in Output Location Reference at the end of this document
- `source_id` — ticket number, issue key, document ID, or equivalent
- `source_url` — URL to the original source
- `created_at`, `updated_at`, `status`, `priority`

---

### Step 6 — Apply Taxonomy Tags

Read `taxonomy.md` in this skill's directory for valid values. Use only listed values. Do not invent tags.

**Dimensions:** `platform` · `package` · `section` · `module` · `feature` · `workflow` · `stage` · `object` · `integration` · `role` · `intent` · `lifecycle` · `compliance` · `issue` · `technical` · `implementation`

**Required for every file:** `platform`, `section`, `module`, `workflow`, `intent` — at least one value each. If the content gives no clear signal for `platform`, assign `platform: undetermined` rather than omitting the field or guessing.
**Strongly recommended when applicable:** `package`, `feature`, `object`, `role`, `lifecycle`
**Required for troubleshooting content:** `issue`, `technical`
**Required for integration content:** `integration`, `workflow`, `technical`

Be inclusive: over-tagging is safer than under-tagging for retrieval. Tag only what the content directly addresses — no aspirational tags. When uncertain, apply the tag.

**`intent` tagging for Zendesk tickets — do not default to `troubleshooting` alone.** Tickets regularly contain content that maps to multiple intent values. Apply all that apply:
- `troubleshooting` — when the ticket describes an error, failure, or unexpected behavior
- `task-oriented` — when the ticket contains a procedure, step sequence, or how-to instruction a user must follow (including resolution steps)
- `conceptual` — when the ticket explains why something works a certain way, the purpose of a feature, or the relationship between system components
- `faq` — when the ticket is a recurring how-do-I or what-does-X-mean question with a clear answer
- `configuration` — when the ticket involves setup, settings, or admin configuration decisions
- A ticket with a troubleshooting resolution may also carry `conceptual` intent if the agent explains the underlying mechanism, or `task-oriented` intent if the resolution includes steps a user must perform. Tag all that apply.

For Zendesk tickets: read `zendesk-field-mapping.md` for exact field value → taxonomy tag mappings.

---

### Step 7 — Write Summary

Write a `summary` field (YAML block scalar `>`) covering: primary subject, key workflows or features, errors or issues described, resolution or outcome if present, key App A objects or technical components involved.

**No PII.** Use generic references: "a user", "a provider", "a customer", "a specialist", "a support agent". Written to answer: "Is this file relevant to my topic?"

---

### Step 8 — Write Drafting Guidance

Write a `drafting_guidance` field (YAML block scalar `>`) in the individual source file. This field is the deep per-source guide: which artifact types the source serves, specific patterns or steps a drafter should extract, gaps and caveats (e.g., "symptom context only — no resolution steps"), and pairing recommendations.

In the workflow shard indexes (Step 11), this same content is surfaced as **`Use when:`** — a shorter signal telling the diataxis-drafter skill the conditions under which it should reach for this source. The two fields are complementary: `drafting_guidance` in the source file is the full detail; `Use when:` in the index shard is the routing signal.

**No PII.** Same rules as `summary`.

#### Zendesk Ticket Drafting Guidance

Per the note above, a single ticket may simultaneously serve as a troubleshooting source, a how-to step source, a conceptual explanation, a warning callout, a best practice tip, or an FAQ entry. For `zendesk_ticket` sources, be specific and actionable. Apply these heuristics:

**1. Evaluate all Diataxis artifact types — not just troubleshooting.**
Identify every content type this ticket can serve. A ticket may serve multiple types simultaneously:
- **Troubleshooting** — "Strong source for a troubleshooting article on [symptom]" when root cause and fix are both present; "Symptom context only — no resolution" when the fix is absent
- **How-to** — "Source for a how-to step on [action]" when the ticket contains a step sequence, configuration instruction, or procedure a user must perform
- **Warning / caution callout** — "Contains a warning for [scenario]" when the ticket describes a consequence, data-loss risk, irreversible action, or common mistake customers make
- **Best practice / tip** — "Contains a best practice recommendation: [recommendation]" when an agent or the resolution includes a recommendation about approach, order of operations, or setup pattern
- **Concept / explanation** — "Contains a conceptual explanation of [concept]" when the ticket explains why a system behaves a certain way, the purpose of a feature, or the relationship between objects/processes
- **FAQ / how-do-I** — "Source for an FAQ entry on [question]" when the ticket is a recurring how-do-I question with a clear answer
- **Background context** — "Background context only" when the ticket adds nuance but no standalone drafting value

**2. Extract the "why" behind steps.**
When a ticket explains the reason a step is required, why an action causes a downstream effect, or why a configuration matters — call it out explicitly. Example: "Agent comment explains why the file must be locked before triggering automated account creation — suitable for a 'why this step matters' note in a how-to article." These explanations are often the only place this context is documented.

**3. State what is explicit vs. what requires inference.**
If root cause is directly stated: "Root cause is explicit: [specific cause]." If only implied: "Root cause implied from fix steps — not stated."
If the fix is directly stated: "Fix is clearly stated: [action]." If not: "No resolution documented."

**4. Name specific reusable content elements.**
Call out exact strings and patterns worth citing in documentation:
- Error messages that appear verbatim in the product
- Step sequences the drafter should extract (e.g., "Three-step modal sequence is documented")
- Warning conditions: irreversible actions, data loss risks, timing constraints, order-of-operations requirements
- Best practice recommendations made by agents or in the resolution
- Conceptual explanations of how or why something works
- Workarounds the customer used (worth noting as known coping patterns)
- Preconditions or environment details (sandbox vs. production, specific object types)

**5. Flag gaps and pairing needs.**
Note when the ticket is incomplete or needs to be combined with another source:
- "Workaround only — no root cause fix documented"
- "Pair with [implementation guide or other file] for the full workflow"
- "No reproduction steps; symptom description only"
- "Agent investigation is internal — not suitable for customer-facing content without reframing"

**6. Note if the ticket documents a recurring pattern.**
If the subject, tags, or comments suggest this is a common scenario (multiple mentions of "same issue", escalations, or matching other ticket themes), note it: "Likely recurring issue based on [signal] — prioritize for documentation."

**Keep it tight.** The full guidance should be 3–6 sentences. Do not summarize the ticket again — the `summary` field covers that. The `drafting_guidance` field answers: "How should a drafter use this source, and for which article types?" The `Use when:` line in the index shard answers: "Under what conditions should the diataxis-drafter reach for this source?"

---

### Step 9 — Assemble the Output File

```
---
title: "<title>"
source_type: "<source_type>"
source_id: <id or omit>
source_url: "<url or omit>"
created_at: "<datetime or omit>"
updated_at: "<datetime or omit>"
status: "<status or omit>"
priority: "<priority or omit>"
boilerplate_stripped: <true or omit>
summary: >
  <PII-free summary>
drafting_guidance: >
  <PII-free drafting guidance>
platform:
  - <value>
[...remaining taxonomy dimensions, omit any with no applicable tags...]
---

<cleaned body content>
```

Omit any taxonomy key entirely if no tags in that category apply.

---

### Step 10 — Store the Output File

- **Base directory:** `<STACKS_DIR>` (the absolute path resolved at session start — see Path Reference)
- **Subdirectory:** the `source_type` value (e.g., `zendesk_ticket/`, `implementation_guide/`)
- **Filename:** original filename with `.md` extension. **Exception:** Zendesk tickets processed via Step 2B use `zd-ticket-<id>.md` — see Step 2B-1.

Create the subdirectory if needed (`mkdir -p` via Bash). Write using the Write tool. Do not re-read afterward.

---

### Step 11 — Update the Indexes

There are three indexes to maintain: a compact top-level index, a compact ticket index, and per-workflow shards. **Ticket entries live only in `_index_tickets.md`.** Workflow shards (Index C) never contain inline `zendesk_ticket` entries — each shard header instead points the drafter to `_index_tickets.md`, filtered by workflow tag, for ticket candidates.

**Shared mechanics for all three indexes:** append with `>>` Bash append; write the header shown below the first time the file doesn't exist; on `--refresh`, replace the existing entry in place rather than duplicating it (matching rule noted per index below). For large repair runs (format migrations, sort-order changes, dedupe), use the `rebuild_indexes.py` companion script instead of hand-editing — it regenerates the affected index(es) from source-file front matter in one pass.

**Shared sort order** (Index A and Index C): source type first — github_file → implementation_guide → help_center → call_transcript → sf_release_notes → confluence_page → other — then by date, newest first within each type bucket. Sources with no `created_at` in their front matter sort by file mtime, computed fresh on every rebuild.

---

#### Index structure

| Index | Scope | What goes in it |
|---|---|---|
| `_index.md` (A) | All non-ticket sources | One compact line per file |
| `_index_tickets.md` (B) | Zendesk tickets only | One compact line per ticket |
| `_index_workflow_<name>.md` (C) | Non-ticket sources only | Full entries; pointer to `_index_tickets.md` for ticket candidates |

---

#### Index A — Compact Top-Level Index: `_index.md`

Scope: all source types **except** `zendesk_ticket`. One line per file.

Header (see shared sort order above):
```markdown
# Knowledge Stacks — Compact Index

Auto-maintained by source-librarian. Do not edit manually.
**Scope:** All source types except zendesk_ticket. For Zendesk tickets, see _index_tickets.md.

**Format:** `[source_type] tags · [Title](path)`

**Usage:**
- Known topic: skip this file — read the relevant `_index_workflow_<name>.md` shard directly for full summaries.
- Broad or unknown topic: scan this file, match tags to your topic, then read the matching workflow shards for candidates.

---
```

Append one entry per file — a single line, no separator:
```
[<source_type>] <every applied tag value from all categories, space-separated> · [<title>](<relative path from knowledge-stacks/>)
```

Paths are always relative to `knowledge-stacks/` (e.g., `implementation_guide/Feature A.md`). Never use absolute paths. On `--refresh`, match on the path substring.

---

#### Index B — Compact Ticket Index: `_index_tickets.md`

Scope: `zendesk_ticket` only. One line per ticket. This is the **only** index that contains ticket entries.

Header:
```markdown
# Knowledge Stacks — Ticket Index

Auto-maintained by source-librarian. Do not edit manually.
**Scope:** zendesk_ticket source type only. For all other sources, see _index.md.

**Format:** `[zendesk_ticket] tags · [Title](path)`

**Ordering:** Entries are sorted by date (newest first). Tickets with no `created_at` sort by file mtime, computed fresh on every rebuild.

**Usage:**
- The diataxis-drafter reads this file after each workflow shard and filters lines by `workflow:` tag to discover ticket candidates for the topic.
- Broad or unknown topic: scan this file, match tags to your topic, then open the source ticket file for the full body.

---
```

Append one line per ticket, no separator. Paths are always relative to `knowledge-stacks/`:
```
[zendesk_ticket] <every applied tag value, space-separated> · [<title>](zendesk_ticket/zd-ticket-<id>.md)
```

The line must be unique per ticket. On `--refresh` or if an entry for the same ticket already exists, replace it rather than appending a duplicate.

---

#### Index C — Workflow Shard Indexes: `_index_workflow_<name>.md`

One shard per workflow value. **Non-ticket sources only.** A file tagged with multiple workflows appears in each matching shard.

Header (see shared sort order above):
```markdown
# Workflow Index: <workflow-name>

Auto-maintained by source-librarian. Contains non-ticket sources tagged `workflow: <workflow-name>`.
**For Zendesk ticket sources:** read `_index_tickets.md` and filter lines containing `workflow: <workflow-name>`.
Read this file when drafting content related to the <workflow-name> workflow.

---
```

There is no Priority Sources table. The sort order is the only ranking signal — the diataxis-drafter reads the shard top-to-bottom and treats the order as authoritative for breadth/recency.

**For non-ticket sources** — append one full entry per shard:
```markdown
## <title>

**File:** `<relative path from knowledge-stacks/>`
**Source type:** `<source_type>` | **ID:** `<source_id or —>` | **Created:** `<YYYY-MM-DD or —>` | **Status:** `<status or —>`
**Tags:** `<platform>` | `<section>` | `<module>` | `<feature>` | `<workflow>` | `<intent>` | `<issue if any>`

**Summary:** <summary text, inline>

**Use when:** <≤3 sentences stating the conditions under which the diataxis-drafter should reach for this source — article type, topic, gaps it fills, sources it should be paired with. Longer guidance lives in the source file's drafting_guidance front matter and is read by the drafter in Tier 2.>

---
```

**Skeleton rules:**
- Title is `## <Title>` only — no `[T]` prefix, no link wrapping
- `**File:**` path is relative to `knowledge-stacks/` — never absolute, never `/Users/...`
- `**Created:**` is the `created_at` from the source file's front matter, formatted `YYYY-MM-DD`. If absent, the rebuild script substitutes the file's mtime; the field renders as `—` only when neither is determinable
- Tag groups are pipe-separated in this fixed order: `platform | section | module | feature | workflow | intent | issue`
- `**Summary:**` is inline (single paragraph, no soft-wrap), copied from the source file's `summary` field
- `**Use when:**` is capped at **3 sentences**. Anything longer belongs in the source file's `drafting_guidance` field, where the drafter reads it during the Tier 2 metadata scan
- Trailing `---` separator after every entry

On `--refresh`: replace the entry in every shard the file appears in; remove from any shard whose workflow tag was removed.

---

### Step 12 — Confirm, Flush, and Continue

Output one line and release the file from memory:
```
✓ Cataloged: <output file path>
```

Proceed immediately to the next file without waiting for user input.

**Batch size:**
- **Single-file inputs** (implementation guides, GitHub files, call transcripts, single Zendesk tickets): Process no more than 10 files per session.
- **Zendesk NDJSON via `run_catalog_batch.sh`**: Process exactly the count passed by the script (default 10). Stop cleanly after that count — the script loops automatically.

This skill is fully resumable — already-cataloged files are skipped automatically on re-run (Step 1 skip check). For large NDJSON batches, use `run_catalog_batch.sh` in the skill directory rather than opening new sessions manually.

After all files are processed:
```
Source library updated: <N> cataloged | <M> skipped (already exist) | <P> refreshed
Main index: knowledge-stacks/_index.md
Ticket index: knowledge-stacks/_index_tickets.md
Workflow shards updated: knowledge-stacks/_index_workflow_<name>.md (non-ticket sources only; tickets discovered via _index_tickets.md pointer)
```

---

## PII Rules

**Never include in `summary` or `drafting_guidance`:** customer names, organization names, company names, provider names, agent names, support rep names, email addresses, phone numbers, org-specific URLs, or ticket submitter names.

**Permitted generic references:** "a user" · "a provider" · "a customer" · "a specialist" · "a support user" · "an App A admin" · "an implementation admin" · "the reporting organization" · "the requester" · ticket/issue IDs alone (not linked to a named person) · state names · license types · specialty names · App A object names

---

## Output Location Reference

Base: `<STACKS_DIR>/<source_type>/` (substitute the absolute `STACKS_DIR` resolved at session start)

Source types: `zendesk_ticket` · `jira_ticket` · `github_issue` · `github_pr` · `github_file` · `call_transcript` · `implementation_guide` · `slack_thread` · `google_doc` · `confluence_page` · `meeting_notes` · `slides` · `help_center` · `product_assistant` · `support_playbook` · `plain_text` · `pdf_document` · `email` · `other`

**Zendesk tickets** are written one file per ticket at `knowledge-stacks/zendesk_ticket/zd-ticket-<id>.md` — see Step 2B.

**Indexes:**
- `knowledge-stacks/_index.md` — non-ticket sources only
- `knowledge-stacks/_index_tickets.md` — zendesk_ticket sources only
- `knowledge-stacks/_index_workflow_<name>.md` — non-ticket workflow shards; each shard header contains a pointer to filter `_index_tickets.md` by workflow tag for ticket candidates
