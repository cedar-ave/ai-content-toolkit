---
name: style-pal
user-invocable: true
description: Reviews any document against the company's Technical Style Guide style guidelines (ampersands, case, headings, voice, punctuation, UI text formatting, etc.) and flags violations with suggested fixes. Use this skill when someone asks to check, review, or audit a document for style, formatting, or writing conventions — separate from vocabulary/terminology checks. Works with Google Docs (by URL or title), markdown files (.md), plain text (.txt), and Word documents (.docx).
---

# Style Pal

This skill audits a document against the company's Technical Style Guide style guidelines and reports every instance where content does not align with the guidelines. It outputs findings as a numbered list so the user can approve or reject individual fixes.

## What you'll need from the user

If they haven't already provided it, ask for one of:
- A **Google Doc** URL or title
- A **file path** to a markdown (.md), plain text (.txt), or Word (.docx) file in their workspace

One input is enough — don't ask for multiple.

## Step 1: Read the style guidelines

Before scanning anything, read the company's style reference:

```
references/style.md
```

This file contains company-specific style guidelines. **The company's guidelines take precedence over the Microsoft Style Guide in all cases.**

Also read both Microsoft Style Guide references:

```
references/microsoft-az.md
references/microsoft-style-guide.md
```

`microsoft-az.md` contains Microsoft's complete A–Z terminology and word choice recommendations. `microsoft-style-guide.md` covers grammar, punctuation, procedures, scannable content, text formatting, word choice, developer content, and general guidelines.

## Step 2: Fetch the document

**Google Doc:** Use the Google Docs connector (search by title or fetch by URL) to retrieve the full text. If the user gives a URL, extract the document ID from it.

**Markdown / plain text:** Use the Read tool to read the file directly.

**Word document (.docx):** Use `python-docx` via Bash to extract text before scanning.

## Step 3: Scan for style violations

Go through every guideline in `references/style.md`. For each one:

- Search the document text for patterns that violate the guideline.
- Note the violation, the surrounding sentence or phrase for context, and the correct treatment.

**Guidelines to apply:**

- **Ampersands:** Flag any & that isn't a literal UI element label.
- **Case:** Flag title case in headings. Flag non-sentence-case text before colons in bullet lists.
- **Checkboxes:** Flag *click the checkbox* or *check the checkbox* — suggest *Check the box*.
- **Commas:** Flag missing serial commas in lists of three or more items.
- **Contractions:** Flag awkward avoidance of contractions (e.g., *do not* where *don't* reads more naturally) — note this as a suggestion, not a hard violation.
- **Exclamation points:** Flag headings or sentences ending in !
- **Files:** Flag unbolded filenames or filepaths. Flag uppercase file extensions (.CSV, .MD).
- **Headings:** Flag title case. Flag headings beginning with a gerund (*-ing* form). Flag headings ending with punctuation.
- **Links and buttons:** Flag *click on* — suggest *click*. Flag *button* after a UI element name.
- **Quotation marks:** Flag quotation marks used for emphasis, UI elements, or terms (not quoting a source).
- **Split infinitives:** Flag split infinitives (e.g., *to quickly open*).
- **Tense / person:** Flag third-person instructions (*the user should…*) — suggest second person.
- **UI text elements:** Flag UI element names that are not bolded, or that are wrapped in quotes instead of bold.
- **Voice:** Flag passive voice constructions — suggest active voice rewrites.

## Step 4: Report findings

Output findings as a numbered list using this exact structure:

---

## Style check: [Document name]

**[N] issue(s) found**

---

### 1. [Guideline name]
**Found:** "[surrounding sentence or phrase as it appears in the document]"
**Issue:** [one-sentence description of what's wrong]
**Suggested fix:** [the corrected sentence or phrase]

### 2. ...

---

After presenting all findings, ask:

> Which items would you like me to fix? You can say "fix 1, 3, 5" or "fix all" — or "skip" for any you want to leave as-is.

Then apply only the approved fixes.

## If no issues are found

> ✓ No style issues found. The document follows the company's Technical Style Guide.

## Tips for a thorough scan

- Run your search across the full document text, not just headings.
- Skip code blocks and literal UI screenshots — style rules don't apply to literal code strings or quoted UI labels.
- For voice and tense issues, flag only clear cases — don't flag every passive construction, only ones where active voice is clearly better and achievable.
- If a document is long, work section by section and consolidate before reporting.
- Contractions: flag avoidance only when the result is stilted or formal in a way that's out of step with the rest of the document's tone.
