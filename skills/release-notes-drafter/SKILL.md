---
name: release-notes-drafter
user-invocable: true
description: Drafts customer-facing release notes for a single audience from a GitHub release and/or a user-provided list of commits and Jira tickets. Outputs a single markdown file in the skill's local outputs directory. Filters out internal maintenance and infrastructure work, keeps only changes that affect end users, and frames every note around customer value.
---

# release-notes-drafter

This skill drafts customer-facing release notes for **one audience per run**:

- **App A** — for App A users. Plain language, not too technical.
- **App B** — for App B users. Plain language, not too technical. A subset of notes may apply only to a specific customer segment — call those out in a dedicated subsection.
- **API** — for technical integrators. Concise; precise; not verbose.

Source data is whatever the user specifies for a given release: a GitHub release URL/tag, a pasted list of commits, a pasted list of Jira keys, or any combination. The user picks the audience; the skill writes one file.

---

## Safety rules

- **Never fabricate.** Every note must be traceable to a commit message or Jira ticket. If a ticket has no usable description, flag it — do not invent customer value.
- **Strip internal references.** Remove customer names, account IDs, internal URLs, engineer handles, Slack links, Sentry links, and any internal-only system names. The output is customer-facing.
- **Exclude internal maintenance and upkeep.** Anything that does not change what an end user sees or can do is out. See **Exclusion filter** below.
- **Formatting is audience-specific.** Bold UI elements in App A/App B notes; use code formatting only in API notes. Full rules in **Audience guidance**.
- **One audience per run.** If the user later asks for a second audience for the same release, start a new run.
- **Read every Jira ticket in full** before drafting the note for it. Do not draft from the title alone.

---

## Critical drafting rules

Never use the em dash (—).

---

## Workflow

### Step 1 — Gather inputs

Ask the user for all of the following before doing any fetching:

1. **Audience** — one of: `app-a`, `app-b`, `api`.
2. **Release label** — the exact string to put in the top heading. Example: `2.99`, `v2.99`, `March 2026`. The heading will render as `Release {label}`.
3. **GitHub release URL** — optional but preferred. The skill will fetch the release body, tag, and the linked commit list. Accept either a release URL (`https://github.com/{owner}/{repo}/releases/tag/{tag}`) or a `{owner}/{repo}` + tag pair.
4. **Pasted commits** — optional. A list of commit subjects or short SHAs, one per line. Use this when the user does not have a GitHub release ready, or wants to override what is in the release body.
5. **Pasted Jira keys** — optional. A list of Jira keys (e.g., `KEY-1234`). These are added on top of any keys inferred from commits.
6. **GitHub release link for the heading** — the URL to display on the third line of the output. Default to the release URL the user provided in step 3. Ask only if step 3 was skipped.

If the user provided neither a GitHub release nor any commits nor any Jira keys, stop and ask for at least one source.

### Step 2 — Fetch the GitHub release (if provided)

If the user provided a GitHub release URL or `{owner}/{repo}/{tag}`:

1. Call `mcp__MCP_DOCKER__get_release_by_tag` to retrieve the release body, name, and tag.
2. From the release body, extract every Jira key. Match the pattern `[A-Z]{2,5}-\d+` (e.g., `KEY-1234`).
3. If the release body lists commits or references a commit range, also collect commit subjects from there.

If the GitHub MCP is not available, see **Edge cases**.

### Step 3 — Collect the work item set

Build a deduplicated list of Jira keys by combining:

- Keys inferred from the GitHub release body.
- Keys inferred from pasted commit subjects (same `[A-Z]{2,5}-\d+` pattern).
- Keys the user pasted directly.

Save the list to `/tmp/release_notes_work_items.txt` before fetching.

### Step 4 — Fetch every Jira ticket

For each Jira key, fetch the full ticket using `mcp__claude_ai_Atlassian__getJiraIssue` (or `mcp__MCP_DOCKER__` Atlassian tools when claude.ai connectors are unavailable). Fetch in parallel — do not loop one at a time. If the Atlassian MCP is not available at all, see **Edge cases**.

Save the raw response for each ticket to `/tmp/release_notes_ticket_{KEY}.json` and then process from disk. This keeps the main conversation lean.

For each ticket, extract:

- Summary
- Description (full text)
- Issue type
- Status
- Labels
- Components
- Fix versions

If a ticket cannot be fetched, do not stop. Add the key to a `[REVIEW NEEDED: could not fetch {KEY}]` flag in the draft and continue.

### Step 5 — Apply the exclusion filter

Drop any work item that matches the **Exclusion filter** below. Keep a list of dropped items (key + one-line reason) so you can both report them to the user at the end and write them into the **Excluded notes** section at the bottom of the output file. Do not include dropped items in the body of the notes (`What's new` / `Bug fixes`) — they belong only in the trailing **Excluded notes** section.

### Step 6 — Draft notes for the chosen audience

For each remaining work item, write one note following **Output format** and the audience-specific tone in **Audience guidance**. If two or more work items describe the same user-visible change, merge them into a single note and list all keys in the metadata line.

**Group notes into two top-level sections:**

- `## What's new` — enhancements, new features, new capabilities, new endpoints/fields, behavior changes, and deprecations. Use Jira issue type (Story, Task, Epic, New Feature, Improvement) and the ticket content to decide.
- `## Bug fixes` — anything where the Jira issue type is Bug, or where the ticket clearly describes a fix to broken or incorrect behavior.

If a section has no notes, omit that section entirely. Each individual note within a section is an `###` heading (one level deeper than before — see **Output format**).

For the **App B** audience, identify changes that apply only to a specific customer segment (work items tagged for that segment, or whose description makes it clear the change is only visible to that segment's customers). Group those into a `## Segment-only` subsection at the bottom of the body, and within it use the same `### What's new` / `### Bug fixes` split (with `####` for individual notes). If there are no segment-only changes, omit the subsection.

### Step 7 — Write the output file

Filename: `outputs/{YYYY-MM-DD}-{audience}-notes-{release-label-slug}.md`, relative to this skill's own directory, where:

- `{YYYY-MM-DD}` is today's date.
- `{audience}` is `app-a`, `app-b`, or `api`.
- `{release-label-slug}` is the release label lowercased with spaces replaced by `-` (e.g., `2.99`, `v2.99`, `march-2026`).

At the bottom of the file, after all notes, add an **Excluded notes** section listing every work item dropped by the exclusion filter (see **Excluded notes section** under **Output format**). If nothing was excluded, omit the section.

After writing, tell the user:

1. The absolute path of the output file.
2. The count of notes included.
3. The list of work items that were excluded by the filter, with the reason for each.
4. Any `[REVIEW NEEDED]` flags that remain in the draft.

---

## Output format

Every output file follows this exact structure:

```
# Release {release-label}

{Month D, YYYY}

[GitHub release]({github-release-url})

## What's new

### {Value-based heading in sentence case}

{Note body. Plain prose, optionally with a short bullet list. Formatting
follows Audience guidance.}

[{KEY-123}]({jira-url}), [{KEY-456}]({jira-url})

### {Next value-based heading in sentence case}

...

## Bug fixes

### {Value-based heading in sentence case}

{Note body.}

[{KEY-789}]({jira-url})
```

### Required elements

- The top heading is `# Release {label}` exactly.
- Line 2 is today's date in long form: `June 25, 2026`. No `Date:` prefix.
- Line 3 is the GitHub release link (format in **Hyperlinks**), pointing to the URL the user provided. If no URL was provided, write `[GitHub release](TBD)` and add a `[REVIEW NEEDED: no GitHub release URL provided]` flag immediately below.
- The body is split into `## What's new` and `## Bug fixes` sections. Omit any section that has no notes.
- Each note is an `###` heading in sentence case (only the first word capitalized, plus proper nouns), describing the customer value — not the engineering change.
- The note body is one or two short paragraphs. Use a bullet list when listing more than two distinct items.
- The metadata line immediately follows the note body and lists every Jira key associated with that note, comma-separated, as markdown links (format in **Hyperlinks**). No `Fix version` or `For review purposes only` text — that format is not used here.

### App B — segment-only subsection

If any notes apply only to a specific customer segment on App B, place them in a single subsection at the bottom of the body:

```
## Segment-only

### What's new

#### {Value-based heading in sentence case}

{Note body.}

[{KEY-123}]({jira-url})

### Bug fixes

#### {Value-based heading in sentence case}

{Note body.}

[{KEY-456}]({jira-url})
```

Inside the segment-only subsection, use `###` for the `What's new` / `Bug fixes` split and `####` for individual note headings. Omit either split section if it has no notes.

### Excluded notes section

At the very bottom of every output file, after all `What's new`, `Bug fixes`, and any segment-only content, list the work items that were dropped by the **Exclusion filter** as internal-only. This gives the reviewer a record of what was intentionally left out and why. Omit the entire section if nothing was excluded.

```
---

## Excluded notes

_The following work items were determined to be internal-only and are not part of the customer-facing notes above._

- [{KEY-123}]({jira-url}) — {one-line reason, e.g. "CI/CD pipeline change, no user-visible impact"}
- [{KEY-456}]({jira-url}) — {one-line reason}
```

- Precede the section with a `---` horizontal rule so it is visually separated from the notes.
- Use the same Jira link format as the note metadata lines (see **Hyperlinks**).
- The reason is the same one-line reason you report to the user in Step 7 — keep them identical.
- Do not apply customer-value framing here; state the plain reason for exclusion.

---

## Audience guidance

### App A

- Reader is a business user of App A. Not a developer.
- Plain language. No query languages, scripting APIs, or backend platform terms unless the user already sees them in the UI.
- Bold UI elements: **Request**, **Status**, **Mark Complete**, etc.
- Do not use code formatting.
- Avoid engineering terms like "scraper," "sync worker," "queue," "lambda." Translate to user outcomes.

### App B

- Reader is a business user of App B. Not a developer.
- Same tone as App A. Bold UI elements. No code formatting.
- Group segment-only changes into the `## Segment-only` subsection if any exist.
- Refer to the product by its proper name, not an abbreviation or nickname.

### API

- Reader is a technical integrator building against the API.
- Concise. Skip background and motivation that a developer can infer from endpoint behavior.
- Use code formatting for endpoints (`GET /accounts/{id}`), parameters (`accountId`), fields (`versionsAffected`), header names (`Authorization`), and response keys.
- Do not bold UI elements — there are none in this audience.
- When a change affects multiple endpoints, list them as a bulleted set of code-formatted lines.
- Avoid marketing tone. Keep verbs precise: "now returns," "now accepts," "deprecated," "removed."

---

## Exclusion filter

Drop work items that match any of the following. These are internal-only and have no end-user impact.

**Always exclude:**

- Any Jira ticket whose project key is `AI` (e.g., `AI-123`). These are internal AI initiatives and never appear in customer-facing release notes.
- Anything referencing an unreleased internal initiative by its internal project or program codename in the ticket summary, description, components, or labels.
- Anything referencing an internal-only platform or engine by its internal name in the ticket summary, description, components, or labels.
- Infrastructure, observability, monitoring, alerting, logging, tracing, and Datadog/Sentry work that the customer cannot see.
- CI/CD, GitHub Actions, build pipeline, dependency upgrades, library version bumps, and lockfile updates.
- Internal developer tooling, local-dev scripts, internal CLIs, and internal Slack bot commands.
- Internal console endpoints (e.g., "internal console endpoints to manage X"), unless the change is also exposed to customers.
- Test-only changes, QA harnesses, fixture updates, and automated test additions.
- Refactors with no behavior change ("rename module," "split file," "extract helper").
- Code cleanup, dead code removal, comment changes, typo fixes in internal docs.
- Performance work that does not change a user-visible behavior or latency the user notices.
- Background job tuning (lock contention, retry windows, polling intervals) unless the user can observe the difference.
- Permission/role grants for internal teams ("Grant UserAdmin role access to X").
- Database migrations, schema changes, and index additions with no API or UI surface change.

**Exclude unless the user has explicitly said otherwise for this release:**

- Sentry noise reduction.
- Internal log routing changes.
- Feature flag plumbing that has not yet shipped a user-visible change.

**Always include:**

- New features and capabilities a customer can use.
- Behavior changes a customer will notice (UI updates, response shape changes, new endpoints, new fields).
- Bug fixes a customer encountered or would have encountered.
- Deprecations and breaking changes.
- New documentation pages that customers will read.

When uncertain whether a work item belongs to the user-facing or internal bucket, read the full Jira description before deciding. If after reading you still cannot tell, include it with a `[REVIEW NEEDED: confirm user-facing impact]` flag.

---

## Customer value framing

Every heading and body answers: *What does this mean for someone using the product today?*

Translate engineering changes into one of these outcomes:

- **Saves time or reduces effort** — manual steps become automatic.
- **Expands what's possible** — a new capability or integration.
- **Increases confidence or trust** — more reliable data, fewer errors.
- **Reduces friction** — fewer clicks, clearer messages, fewer support requests.
- **Supports compliance or audit** — relevant where the product touches regulated or audited workflows.

### Rewrite test

Before finalizing a heading, check that it reads as *what the customer gains*, not *what was built*.

| Raw                                              | Rewritten                                                           |
|---------------------------------------------------|----------------------------------------------------------------------|
| Fix null pointer in getWidgetStatus              | Improved reliability for widget status checks                        |
| Added retry logic to sync job                     | Data stays current even when sources are temporarily unavailable     |
| Exposed new filter parameter on GET /widgets      | Narrow widget searches by category without post-processing           |
| Review modal closes after action                  | Review modal stays open after action                                 |
| Refactor widget state machine                     | (Excluded — no user-visible change)                                  |

---

## Edge cases

- **Ticket only has a title, no description** — Use the title to write a value-based heading. Leave the body empty and add `[REVIEW NEEDED: ticket had no description — verify customer impact]`.
- **Ticket title contains implementation language** (class names, error codes, method names) — Rewrite as a customer-facing heading. If you cannot tell what the customer-facing change is, add `[REVIEW NEEDED: cannot infer customer impact — original title: "{title}"]`.
- **Multiple tickets describe the same change** — Merge into one note; list all keys in the metadata line.
- **Ticket spans multiple fix versions** — Include in this release if any of its fix versions matches what the user is drafting. Do not mention other fix versions in the note body.
- **Conflicting descriptions across linked tickets** — Add `[REVIEW NEEDED: tickets {KEY-A}, {KEY-B} describe this differently — verify before publishing]`.
- **GitHub MCP unavailable** — Ask the user to paste the release body text. Continue from step 3.
- **Atlassian MCP unavailable** — Ask the user to paste the description of each ticket. Continue from step 5.

---

## Hyperlinks

- Jira key links: `[KEY-123](https://{instance}.atlassian.net/browse/KEY-123)`. Use the bare key as link text — no title, no "Fix version," no pipes.
- GitHub release link on line 3 of the output: `[GitHub release]({url})`. Always use `GitHub release` as the link text.
- Help center, marketing site, and API docs links — only include if the user provided the URL or it appears verbatim in a ticket or commit. Do not infer or construct doc URLs.
