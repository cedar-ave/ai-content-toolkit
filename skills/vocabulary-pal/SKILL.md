---
name: vocabulary-pal
user-invocable: true
description: Checks any document against the company's controlled vocabulary and flags non-preferred terminology with preferred replacements. Works with Google Docs, markdown files, plain text, and Word documents.
---

# Vocabulary Pal

This skill audits a document against the company's Technical Style Guide and reports every instance of a non-preferred term along with the preferred replacement and guidance from the style guide.

## What you'll need from the user

If they haven't already provided it, ask for one of:
- A **Google Doc** URL or title
- A **file path** to a markdown (.md), plain text (.txt), or Word (.docx) file in their workspace

One input is enough — don't ask for multiple.

## Context-Sensitive Terms

Some terms are correct in one context and incorrect in another. When context is ambiguous, flag the term and note both possible correct usages rather than silently choosing one.

## Step 1: Read the vocabulary

Before scanning anything, read the full vocabulary reference:

```
references/vocabulary.md
```

This file contains every entry in the company's controlled vocabulary: the preferred term, what makes it preferred (casing, hyphenation, acronym rules), and the non-preferred forms to flag.

## Step 2: Fetch the document

**Google Doc:** Use the Google Docs connector (search by title or fetch by URL) to retrieve the full text. If the user gives a URL, extract the document ID from it.

**Markdown / plain text:** Use the Read tool to read the file directly.

**Word document (.docx):** Use the docx skill's reading approach or run `python-docx` via Bash to extract text before scanning.

## Step 3: Scan for non-preferred terms

Go through every entry in `references/vocabulary.md`. For each non-preferred term listed:

- Search the document text for that exact string, matching case-sensitively where the issue is casing (so the wrong casing is actually caught) and case-insensitively where the issue is word choice or hyphenation (so casing at a sentence start, etc. doesn't hide a real match).
- Note: some issues are about casing only, some are about word choice, and some are about hyphenation. Apply the right kind of matching for each.
- Record every match: the non-preferred term found, the surrounding sentence or phrase for context, and the preferred replacement.
- If a match falls under the Context-Sensitive Terms rule above, don't silently pick one meaning — record it as a flagged item noting both possible correct usages, and mark it as context-sensitive in Step 4's report instead of giving a single "Preferred" replacement.

## Step 4: Report findings

Use this exact report structure:

---

## Vocabulary check: [Document name]

**[N] issue(s) found**

---

### 1. "[non-preferred term as found in doc]"
**Found:** "[surrounding sentence or phrase]"
**Preferred:** [preferred term]
**Guidance:** [one sentence from the style guide explaining why]
**Suggested rewrite:** the corrected sentence or phrase

### 2. ...

---

If no issues are found, say:

> ✓ No vocabulary issues found. The document follows the company's Technical Style Guide.

For a context-sensitive term, use the same numbered structure but replace **Preferred** with **Possible readings:** listing each valid usage, and note in **Guidance** why the context didn't resolve it.

## Examples

**Input:** "The provider's profile shows their SSN and DOB. The org uses Continuous Monitoring."

**Output:**

---

## Vocabulary check: example-doc

**3 issue(s) found**

---

### 1. "SSN"
**Found:** "The provider's profile shows their SSN and DOB."
**Preferred:** Social Security Number
**Guidance:** Acronyms for personal identifiers must be spelled out on first use.
**Suggested rewrite:** "The provider's profile shows their Social Security Number and date of birth."

### 2. "DOB"
**Found:** "The provider's profile shows their SSN and DOB."
**Preferred:** date of birth
**Guidance:** Acronyms for personal identifiers must be spelled out on first use.
**Suggested rewrite:** "The provider's profile shows their Social Security Number and date of birth."

### 3. "org"
**Found:** "The org automates creating accounts."
**Preferred:** organization
**Guidance:** Informal abbreviations should be spelled out in formal documentation.
**Suggested rewrite:** "The organization automates creating accounts."

## Tips for a thorough scan

- Run your search across the full document text, not just headings.
- Watch for plural and possessive forms: "orgs", "org's" are also non-preferred.
- If a document is long, work section by section and consolidate before reporting.
- If the document contains code blocks or UI screenshots, skip those — the style guide exempts
  literal UI text and code strings from vocabulary rules.
