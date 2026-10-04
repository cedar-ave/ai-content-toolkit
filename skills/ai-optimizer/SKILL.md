---
name: ai-optimizer
user-invocable: true
description: Reviews drafted Help Center articles against research-backed best practices for AI agent consumption and provides clear, executable recommendations. Analyzes structure, self-containment, terminology, visual dependencies, and other optimization criteria. Does not edit the article unless explicitly instructed.
---

# ai-optimizer

This skill reviews a drafted Help Center article and identifies concrete, executable opportunities to improve how well the content performs when consumed by AI agents (RAG systems, web fetch/search, and MCP/tool calling). It produces a prioritized recommendation report.

---

## Why AI optimization matters

AI agents access documentation differently than human readers:

- **RAG systems** split content into chunks by heading structure. Each chunk must be independently intelligible — agents retrieve individual sections out of document order, without surrounding context.
- **Web fetch** strips HTML to plain text. Visual formatting, images, and dynamically loaded content are invisible. The agent chooses which page to fetch based on the title alone.
- **MCP / tool calling** selects tools and pages by semantic alignment between user queries and content descriptions.

Content optimized for human reading often fails in all three patterns. This skill identifies the gaps.

---

## How to invoke

Provide the article text directly in the chat, or provide a link to a Google Doc or Zendesk article. You may also paste a section of a draft.

Optionally specify:
- **Article type** (how-to guide, tutorial, concept/explanation, troubleshooting, reference) — enables type-specific checks
- **Scope** (full article, specific section, heading structure only)

If no article type is specified, infer it from content structure and state the inferred type at the start of the report.

---

## What to analyze

Apply every check from the five categories below. For each issue found, write a recommendation (see format rules). Skip checks that are not applicable and say why.

---

### Category 1: Self-containment and context

These checks are **critical for RAG systems** — each H2/H3 section becomes a retrievable chunk that may be fetched without surrounding context.

**Checks:**

1. **Forward/backward references** — Scan for phrases: "see above," "as described earlier," "as mentioned above," "now that you've," "with everything configured," "see the previous section," "click the button shown below," "refer to step X." Each occurrence breaks self-containment. Flag every instance.

2. **Missing prerequisites inline** — Does each major section (H2/H3) state its own prerequisites, required permissions, or required setup? Or does it rely on an earlier section having been read? Flag any section where prerequisites are assumed rather than stated.

3. **Missing product/feature name in section body** — The product or feature name must appear in the section body, not only in a parent heading. If a chunk is separated from its heading (as happens in RAG chunking), it must still be identifiable. Flag sections where the product or feature name is absent from the body text.

4. **Missing navigation paths** — Any reference to a UI location must include the full navigation path ("Settings > Webhooks," not just "the Webhooks page"). Flag every UI reference that lacks a path.

5. **Front-loading** — Does each section open with a brief statement of scope, prerequisites, and what it accomplishes? Flag sections that begin mid-action without orientation.

---

### Category 2: Terminology consistency

These checks are **critical for RAG and MCP** — inconsistent terminology causes retrieval failures and tool selection errors.

**Checks:**

6. **Synonym cycling** — Identify any concept referred to by more than one name within the article (e.g., "archive" / "deactivate" / "disable," or "provider record" / "provider profile" / "provider account"). Flag each synonym pair and identify the preferred term.

7. **Acronym discipline** — Acronyms must be spelled out on first use **within each section**, not just once in the full document. A chunk retrieved mid-document has no access to an earlier definition. Flag any acronym that is defined once in the document but used undefined in later sections.

8. **Ambiguous pronouns** — Flag "it," "this," "that," "they," or "these" used across paragraph boundaries where the referent is not immediately clear. These become untraceable when a chunk starts mid-section.

9. **Paraphrased error messages** — Error messages, error codes, and system strings must be quoted exactly as they appear in the product. Flag any error text that appears to be paraphrased or described rather than quoted verbatim.

---

### Category 3: Visual and layout dependencies

These checks are **critical for web fetch and RAG** — images and layout are stripped during HTML-to-text conversion.

**Checks:**

10. **Screenshots without text equivalents** — Any screenshot or image that conveys required information (navigation path, field values, expected UI state) must have a text equivalent in the adjacent caption or body text. Flag screenshots that carry essential information without a text alternative.

11. **Diagrams without text equivalents** — Workflow diagrams, architecture charts, or comparison visuals must have a text-based equivalent (numbered list, table, or structured prose). Flag any diagram where the visual is the only way to understand the content.

12. **Layout-dependent meaning** — Flag any content where meaning depends on column relationships, visual groupings, sidebars, or positioning. Complex tables with merged or spanning headers lose their relationships when converted to plain text.

13. **Dynamically loaded content risk** — Flag any references to expandable sections, tabs, accordions, or click-to-reveal UI components. If these are implemented in JavaScript, the content may be invisible to agents fetching the page. Note: this is a production-environment risk, not something visible in a draft — flag it as a reminder for the publishing step.

---

### Category 4: Page and section structure

These checks affect **all access patterns** and also improve human readability.

**Checks:**

14. **Page title format** — Is the page title phrased as a task completion or question ("How to configure webhooks," "What is a data export?") rather than a noun phrase ("Webhooks," "Data Export")? Noun-phrase titles underperform in search because they don't match how agents and users phrase queries. Flag noun-phrase titles.

15. **Section heading specificity** — Flag generic headings like "Overview," "Details," "Introduction," "More information," or "Additional notes." These give agents no signal about what to retrieve. Each heading should describe its specific content.

16. **Consistent heading patterns** — For same-type articles (e.g., all how-to guides), heading patterns should be consistent and predictable across the content set. If this article deviates from the standard pattern for its type, flag the deviation and suggest alignment. Use this as the baseline standard pattern per type (prefer the `diataxis-drafter` skill's `references/templates.md` instead, if it's available in this environment, since that is the authoritative source the articles were drafted against):
    - **How-to guide:** Prerequisites → numbered steps (one action per step) → verification/expected result → related links
    - **Tutorial:** Overview of what you'll build → prerequisites → steps → summary of what you learned
    - **Concept/explanation:** Definition → why it matters → how it works → related concepts → (optional) "X vs. Y" or "This is NOT X"
    - **Troubleshooting:** Symptom → cause → fix (repeated per issue) → symptom-to-cause map
    - **Reference:** Scope statement (what it covers / does not cover) → definitions or parameters table → examples → related reference

17. **TL;DR or summary block** — Long pages (more than ~5 sections) benefit from a 2–4 sentence summary at the top. Agents doing a quick scan can extract the gist without processing the full page. Flag long articles missing a summary block.

18. **"When to use / When NOT to use" block** — For features with overlapping alternatives, an explicit "When to use this" and "When not to use this" section is critical. Agents making planning decisions cannot infer suitability from prose — they need it stated directly. Flag feature articles that lack this block when alternatives exist.

19. **Page length vs. task complexity** — Multi-step planning workflows degrade faster under context pressure than simple lookups. Flag any how-to or tutorial that is unusually long (more than ~8 major steps) and suggest whether it should be split at a natural checkpoint boundary. If split, each resulting page must state its sequencing inline ("This is step 2 of 3 in the X workflow. After completing step 1 (link), you should have Y.").

20. **Multi-path branching** — If the article contains significant branching logic ("if you use OAuth do X; if you use API keys do Y"), flag it. Multi-path branching inflates page length and forces agents following one path to process irrelevant content. Each path should be a separate page.

---

### Category 5: Content completeness for agents

These checks address information gaps that human readers can fill from context but agents cannot.

**Checks:**

21. **Implicit prerequisites** — Flag any instruction that assumes prior setup without stating it. Phrases like "Configure your endpoint URL…" or "With your data points ready…" signal an implicit assumption. An agent cannot infer unstated information and will hallucinate or fail silently.

22. **Missing failure modes and error recovery** — Does the article include what to do when things go wrong? Structured error information (symptom, cause, fix) helps agents significantly. Flag procedures that end without a "Common issues" or troubleshooting section.

23. **Missing verification checkpoints** — After key steps in a procedure, readers (and agents) need confirmation signals: "Expected result: The status changes to Enabled." Flag procedural sections that complete major actions without stating what success looks like.

24. **Code examples — presence and quality** — Code examples materially improve an agent's ability to correctly reproduce an API call, integration, or configuration, compared to prose description alone. Flag any technical section that describes an API call, integration, or configurable value without a code example. Also flag code examples that lack inline comments explaining intent.

25. **Concept page structure** — For concept/explanation articles: the definition, rationale, and operational implications should be in distinct sections. One concept per page. The article should open with a single-sentence definition using the exact product term. An "X vs. Y" or "This is NOT X" section should be present when confusion with a similar concept is likely. Flag any of these that are missing.

---

## Output format

Produce the report in this structure. Do not produce a modified article draft unless the user asks for one.

---

### AI Optimization Report: [Article title]

**Article type:** [Inferred or stated type]
**Overall readiness:** [RAG: High / Medium / Low] | [Web fetch: High / Medium / Low] | [MCP: High / Medium / Low]

> One-sentence summary of the article's current AI-optimization posture.

---

#### Priority: Critical

Issues that will cause retrieval failures, context loss, or agent errors. Fix these before publishing.

**[C1] [Short issue name]**
- **Where:** [Section heading or line reference]
- **Issue:** [What the problem is and why it matters for AI consumption]
- **Recommendation:** [Exact, executable change — what to add, remove, or rewrite. Include example text where it helps.]

*(Repeat for each Critical issue)*

---

#### Priority: High

Issues that meaningfully degrade agent performance. Fix before publishing if possible.

*(Same format as Critical)*

---

#### Priority: Medium

Issues that reduce optimization but don't cause failures. Address in a follow-up pass.

*(Same format as Critical)*

---

#### Passed checks

List the check numbers and names that passed. For example:

- [14] Page title format — title is phrased as a task completion. ✓
- [6] Synonym cycling — terminology is consistent throughout. ✓

*(List all passing checks by number and name)*

---

#### Checks not applicable

List any checks skipped because they don't apply to this article type or content, with a one-line reason.

- [24] Code examples — no technical integration content in this article.

---

#### Quick diagnostic summary

Covers all 25 checks. Use `N/A` in Result for any check listed under "Checks not applicable" above.

| Check | Result | Priority |
|---|---|---|
| [1] No forward/backward references | [Pass / Issue found / N/A] | [—/ Critical / High / Medium] |
| [2] Prerequisites stated per section | [Pass / Issue found / N/A] | |
| [3] Product/feature name in section bodies | [Pass / Issue found / N/A] | |
| [4] Navigation paths spelled out | [Pass / Issue found / N/A] | |
| [5] Sections front-loaded with scope | [Pass / Issue found / N/A] | |
| [6] Consistent terminology (no synonym cycling) | [Pass / Issue found / N/A] | |
| [7] Acronyms defined per-section | [Pass / Issue found / N/A] | |
| [8] No ambiguous pronouns | [Pass / Issue found / N/A] | |
| [9] Error messages quoted verbatim | [Pass / Issue found / N/A] | |
| [10] Screenshots have text equivalents | [Pass / Issue found / N/A] | |
| [11] Diagrams have text equivalents | [Pass / Issue found / N/A] | |
| [12] No layout-dependent meaning | [Pass / Issue found / N/A] | |
| [13] Dynamically loaded content flagged | [Pass / Issue found / N/A] | |
| [14] Page title is task/question format | [Pass / Issue found / N/A] | |
| [15] Section headings are specific | [Pass / Issue found / N/A] | |
| [16] Consistent heading pattern for type | [Pass / Issue found / N/A] | |
| [17] TL;DR/summary block present (if needed) | [Pass / Issue found / N/A] | |
| [18] "When to use / not use" block present (if needed) | [Pass / Issue found / N/A] | |
| [19] Page length matches task complexity | [Pass / Issue found / N/A] | |
| [20] No unresolved multi-path branching | [Pass / Issue found / N/A] | |
| [21] Implicit prerequisites flagged | [Pass / Issue found / N/A] | |
| [22] Failure modes documented | [Pass / Issue found / N/A] | |
| [23] Verification checkpoints present | [Pass / Issue found / N/A] | |
| [24] Code examples present and commented (if applicable) | [Pass / Issue found / N/A] | |
| [25] Concept page structure followed (if applicable) | [Pass / Issue found / N/A] | |

---

## Behavior rules

- **Recommendations only.** Do not rewrite, restructure, or edit the article unless the user explicitly instructs you to. The report is advisory.
- **Be executable.** Every recommendation must tell the writer exactly what to do — not just what is wrong. Where phrasing is needed, provide example text.
- **Be specific about location.** Always name the section heading, paragraph, or line where an issue appears. "The article lacks X" is not enough — say "The 'Prerequisites' section lacks X."
- **Prioritize accurately.** Critical = retrieval failure or information loss for agents. High = measurable degradation. Medium = optimization opportunity. Do not inflate severity.
- **Do not add scope.** Do not recommend changes unrelated to AI optimization (style, branding, voice, accuracy). Those are handled by other skills (`style-pal`, `vocabulary-pal`).
- **Be concise.** One recommendation per issue. Do not editorialize.
- **If the user asks you to apply the recommendations:** Make only the changes identified in the report. Do not make additional improvements beyond what was flagged.
