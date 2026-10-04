---
name: paligo-pal
user-invocable: true
description: Perform any Paligo operation via the Paligo REST API — documents, folders, images, productions, imports, translations, taxonomies, variables, users, and assignments.
---

# Safety rules

- Always confirm with the user before executing any write operation (create, update, delete). Read operations may proceed without confirmation.
- Never delete a document, folder, fork, taxonomy, variable set, or assignment without explicit user confirmation that includes the resource name or ID.
- **Always fetch the current XML from Paligo immediately before any update.** Call `get_document(doc_id)` (or `GET /documents/{id}`) right before constructing the PUT payload — never use a cached or previously fetched copy. This ensures manual edits made in the Paligo editor between operations are not overwritten.
- Never overwrite XML content in a document without first showing the user what will change and receiving approval.
- Do not start a production or import without confirming the target resource and publish setting with the user.
- If a destructive action would affect multiple resources (e.g. deleting a folder with children), warn the user of the full scope before proceeding.
- If required information is missing, do not guess IDs or names — use the relevant `list_*` tool to find them, or ask the user.
- Before creating any resource, always ask the user for a name if one was not provided. Do not generate or assume a name. Examples: if the user asks to create a new document without specifying a name, ask "What would you like to name this document?" If the user asks to create a new publication without a name, ask "What would you like to name this publication?" Apply this to folders, forks, taxonomies, variable sets, and any other named resource.
- **Never guess where a new file or document should be placed in the folder structure.** If the user has not specified a destination folder, stop and ask. Do not infer location from context, document name, or surrounding content.
- **Never guess where to move a document.** If the user asks to move a file and has not specified the destination, ask explicitly: "Which folder should this be moved to?" Do not assume it belongs near related documents.
- **Never guess a document title.** If a title is not provided, ask before creating or renaming anything. Do not derive a title from the document body, section headings, or the user's description of the content.
- **When in doubt about placement, title, or destination — always ask. Do not proceed.** A wrong placement or name is harder to fix than a brief pause to confirm.
- Do not expose the API token or credentials in any output.

---

# Paligo Pal

Use this skill to interact with the Paligo content management platform via its REST API. You can read, create, update, and delete any resource that Paligo exposes.

## Content structure in Paligo

Paligo organizes content using a consistent folder structure. At root level, each guide or content area has a parent folder containing two subfolders:

```
Root
└── My Guide                  ← parent folder
    ├── Publication           ← contains the publication document
    └── Topics                ← contains all topic components
```

**Publication** holds the publication document — the master file that defines the table of contents and output structure. There is typically one publication per guide.

**Topics** holds all the individual topic components — the actual content. Topics are standalone reusable units that can be shared across multiple publications.

### Blank placeholder article in every folder

Every Paligo folder is created with a blank article whose name matches the folder name exactly. This placeholder is not the target for Google Doc conversions — it exists only as a structural artifact of folder creation. **When converting a Google Doc to Paligo, always create a new document. Do not ask the user whether to use the existing blank article.** Ignore the blank placeholder entirely and proceed directly to creating a new document named after the Google Doc title.

**Google Doc title as Paligo document name:** When converting a Google Doc, always use the Google Doc title (minus any status tags such as `[Approved]`, `[Draft]`, `[WIP]`) as both the Paligo document name and the root `<title>` element. Never ask the user what to name the document in this context — derive it from the source.

### Why topics must be added to a publication

A topic written in the Topics folder does not appear in any output until it is explicitly added to a publication. The publication is the document Paligo uses to assemble and order content for a given output (HTML, PDF, Zendesk article, etc.). Topics not referenced by a publication are invisible to all outputs.

Topics are added to a publication by creating **forks** — see **Publications and forks** below.

---

## MCP tool prefix

All Paligo operations use tools prefixed with `mcp__paligo__`.

## Authentication

Paligo uses HTTP Basic Auth. Credentials are loaded automatically from the plugin's root `.env` file (see `.env.example`) — no action needed from the user beyond creating it once.

| Variable | Description |
|---|---|
| `PALIGO_INSTANCE` | Paligo host, e.g. `{instance}.paligoapp.com` → `https://{instance}.paligoapp.com/api/v2` |
| `PALIGO_API_TOKEN` | Pre-encoded Base64 `username:apikey` string |

---

## Available tools

### Folders

| Tool | Description |
|---|---|
| `list_folders(parent_id?)` | List all folders, optionally filtered by parent |
| `get_folder(folder_id)` | Get a folder's properties and children |
| `create_folder(name, parent_id)` | Create a folder inside a parent folder |

### Documents

| Tool | Description |
|---|---|
| `list_documents(folder_id?, include_xml?)` | List documents, optionally filtered by folder |
| `get_document(doc_id)` | Get document properties and XML content |
| `create_document(name, folder_id, subtype, xml_content?)` | Create a document shell. `subtype` is required — use `"component"`. Add XML in a separate `update_document` call |
| `update_document(doc_id, name?, xml_content?)` | Update a document's name or XML content |
| `delete_document(doc_id)` | Delete a document |

### Forks

Forks define the table of contents structure of a publication. Each fork links a topic document to a publication at a specific depth and position.

| Tool | Description |
|---|---|
| `list_forks(parent_id)` | List all forks for a publication (pass the publication ID) |
| `get_fork(fork_id)` | Get a fork's depth, position, parent, and linked document |
| `create_fork(parent_id, document_id)` | Add a topic to a publication. Pass publication ID for Level 1; pass a fork ID for Level 2 |
| `delete_fork(fork_id)` | Remove a topic from a publication |

### Images

| Tool | Description |
|---|---|
| `list_images(name_filter?, folder_id?)` | List images, optionally filtered |
| `get_image(image_id)` | Get image properties and download URL |
| `upload_image(file_path, name?)` | Upload a new image from a local file path. Do not pass `folder_id` — Paligo's API rejects any extra form field alongside the file with 422. |
| `update_image(image_id, file_path?, name?)` | Replace an image file or update its name |

### Search

| Tool | Description |
|---|---|
| `search(query)` | **Broken — returns 422 for all tested query formats on this instance. Do not use.** Use `get_folder(folder_id)` instead to enumerate a folder's children. |

### Productions

| Tool | Description |
|---|---|
| `list_productions(status_filter?)` | List recent productions |
| `get_production(production_id)` | Get production details and progress |
| `create_production(publish_setting_id)` | Start a new production. Only `publishsetting` is required — the document is embedded in the publish setting |

### Publish Settings

| Tool | Description |
|---|---|
| `list_publish_settings()` | List all saved publish settings |
| `get_publish_settings(setting_id)` | Get a specific publish setting |

### Outputs

| Tool | Description |
|---|---|
| `get_output(output_name)` | Retrieve a published output archive by name |

### Imports

| Tool | Description |
|---|---|
| `list_imports(status_filter?)` | List recent imports |
| `get_import(import_id)` | Get import properties and progress |
| `create_import(folder_id, file_path)` | Start a new import from a local archive file |

### Translation Exports

| Tool | Description |
|---|---|
| `list_translation_exports()` | List all translation exports |
| `get_translation_export(export_id)` | Get translation export details |
| `create_translation_export(document_id, languages)` | Export a document for translation |

### Translation Imports

| Tool | Description |
|---|---|
| `list_translation_imports()` | List all translation imports |
| `get_translation_import(import_id)` | Get translation import details |
| `create_translation_import(file_path)` | Import a translated XLIFF/ZIP file |

### Taxonomies

| Tool | Description |
|---|---|
| `list_taxonomies()` | List all taxonomies |
| `get_taxonomy(taxonomy_id)` | Get taxonomy details |
| `create_taxonomy(name, parent_id?)` | Create a new taxonomy |
| `update_taxonomy(taxonomy_id, name)` | Update a taxonomy name |
| `delete_taxonomy(taxonomy_id)` | Delete a taxonomy |

### Variables

| Tool | Description |
|---|---|
| `list_variable_sets()` | List all variable sets |
| `get_variable_set(variable_set_id)` | Get a variable set |
| `create_variable_set(name)` | Create a variable set |
| `update_variable_set(variable_set_id, name)` | Update a variable set name |
| `delete_variable_set(variable_set_id)` | Delete a variable set |

### Groups & Users

| Tool | Description |
|---|---|
| `list_groups()` | List all groups |
| `get_group(group_id)` | Get group details |
| `list_users()` | List all users |
| `get_user(user_id)` | Get user details |

### Assignments

| Tool | Description |
|---|---|
| `list_assignments()` | List all assignments |
| `get_assignment(assignment_id)` | Get assignment details |
| `create_assignment(document_id, user_id, role, due_date?)` | Create an assignment |
| `update_assignment(assignment_id, status?, due_date?)` | Update assignment status or due date |
| `delete_assignment(assignment_id)` | Delete an assignment |

---

## How to run this skill

1. Confirm the user's Paligo intent (what resource, what operation).
2. If IDs are needed but unknown, use `list_*` tools first to find them.
3. Call the appropriate `mcp__paligo__` tool.
4. Return results clearly — format JSON responses as readable summaries unless the user asks for raw output.
5. For long-running operations (productions, imports), poll `get_production` or `get_import` periodically to report progress.

## XML format for documents

See `references/docbook-spec.md` for the full DocBook 5.1 spec: required namespaces, xinfo attributes, section nesting rules, tables, inline elements, role= attribute, publications, forks, publishing, XInclude, and a full example.

---

## Pagination

Paligo API responses include `page`, `next_page`, and `total_pages` fields. If `next_page` is present, fetch subsequent pages and combine all results before presenting them to the user.

## Error handling

- **400 Unsupported document type**: The `subtype` field is missing or unsupported on `create_document`. Use `subtype=component`.
- **Productions POST field names**: The correct body field is `publishsetting` (not `publishsettingid`, `publishsetting_id`, or `publish_setting_id`). The document is already embedded in the publish setting — do not pass `document` or `documentid`. Correct: `{"publishsetting": 35}`.
- **Publish settings path**: The correct endpoint is `/publishsettings` (plural), not `/publishsetting`.
- **401**: Invalid credentials — ask the user to verify `PALIGO_API_TOKEN` and `PALIGO_INSTANCE` in the `.env` file.
- **403**: Insufficient permissions — the API key's user account may not have access to this resource.
- **404**: Resource not found — confirm the ID is correct using the relevant `list_*` tool.
- **422 Invalid request body on create**: The correct body is `{"name": "...", "parent": <folder_id>, "subtype": "component"}`. Using `folder` instead of `parent`, or omitting `subtype`, causes a 422.
- **422 Invalid request body on update**: The XML content field is `content`, not `xml`. Correct: `{"content": "<section ...>...</section>"}`.
- **422 on image upload**: Should not happen — the `upload_image` MCP tool was fixed to send only the file field. If 422 recurs, see `references/paligo-api-gotchas.md` for the direct curl equivalent.
- **422 on search**: The `search()` MCP tool returns 422 for all tested query formats against this Paligo instance. Do not use it. Use `get_folder(folder_id)` — already called in Step 2, results are cached.
- **`list_documents` returns empty**: The `list_documents(folder_id=...)` tool may return `{"documents": []}` even when documents exist. Use `get_folder(folder_id)` instead — it reliably returns all children including documents.
- **422 element X not allowed here**: The XML violates DocBook 5.1 schema rules. Most common causes: block elements after a child `<section>`, using CALS table elements instead of HTML-style, or a missing required wrapper element.
- **429**: Rate limited — wait a few seconds and retry.
- **Document subtype cannot be changed via API**: The `subtype` field (`component`, `informaltopic`, etc.) is set at creation time and is not writable via PUT. Changing the XML root element (e.g. `<sidebar>` → `<section>`) updates the content but does not change the subtype shown in the Paligo UI. To change a document's type, the user must do it in the Paligo UI: open the document, go to document properties, and change the topic type there.
- **All confirmed API field names and gotchas**: See `references/paligo-api-gotchas.md`.

---

## Google Doc to Paligo pipeline

Use this workflow to read a Google Doc, convert its content to Paligo DocBook 5.1 XML, and save it as an XML file in the `skills/paligo-pal/outputs/` directory. Do not write to the Google Doc.

**Two modes — run independently or together:**
- **Convert only:** Run Steps 1–6 to produce the XML file. Stop there and show the user the output path.
- **Convert and upload:** After the user confirms the output looks correct, continue to Step 7 to post the XML to Paligo via the API.

### MCP tool prefixes

| Service | Prefix |
|---|---|
| Google Drive | `mcp__gdrive__` |
| Paligo | `mcp__paligo__` |

### Step 1 — Identify the source Google Doc

Ask the user for the Google Doc URL or ID if not provided. Extract the document ID from the URL:

```
https://docs.google.com/document/d/{DOC_ID}/edit
```

### Step 2 — Read the Google Doc

Call all four tools **in parallel** at the start. Do not call them sequentially — they are independent and parallelism cuts total time to the slowest single call.

- `mcp__gdrive__get_doc_structure(doc_id)` — structured JSON with paragraph text, indices, and named styles (e.g. `HEADING_1`, `NORMAL_TEXT`)
- `mcp__gdrive__read_doc_text(doc_id)` — plain text fallback
- `mcp__gdrive__get_doc_images(doc_id)` — exports the doc as HTML, extracts every embedded image, saves each to `/tmp/doc-image-N.png`, and returns `[{file_path, size_bytes, preceding_text, following_text}]`
- `mcp__paligo__get_folder(folder_id)` — pre-fetches all children of the destination folder (names + IDs) for internal link resolution

Store the `get_folder` results. Use them to resolve every internal Help Center link during Step 4 with no additional API calls — do not call `get_folder` again per link.

Use `get_doc_structure` as the primary source for content. The `namedStyleType` field on each paragraph identifies heading levels. Inline formatting (bold, italic, code) comes from `textRun.textStyle` fields within each paragraph's elements.

### Step 3 — Count headings and determine section strategy

Before converting, count H1 and H2 headings in the doc. Paligo allows a maximum of 10 sections per document, including sub-sections.

**H1 rule:**
- If H1 count ≤ 9: each H1 becomes a `<section>` with its associated content nested inside.
- If H1 count > 9: each H1 becomes a `<para role="articles-h1"><emphasis role="bold">text</emphasis></para>` — no section wrapper.

**H2 rule (only evaluated when H1s are converted to sections):**
- Count total sections that would result from converting all H1s and H2s to sections.
- If total ≤ 10: each H2 becomes a child `<section>` nested inside its parent H1 section.
- If total > 10: each H2 becomes a `<para role="articles-h2"><emphasis role="bold">text</emphasis></para>` inside its parent H1 section.

**H3 and below:** Always render as bolded `<para>` with the corresponding role — never as sections.

| Heading level | Always-section condition | Fallback (too many) |
|---|---|---|
| H1 | count ≤ 9 | `<para role="articles-h1"><emphasis role="bold">...</emphasis></para>` |
| H2 | total sections ≤ 10 | `<para role="articles-h2"><emphasis role="bold">...</emphasis></para>` |
| H3 | never a section | `<para role="articles-h3"><emphasis role="bold">...</emphasis></para>` |
| H4 | never a section | `<para role="articles-h4"><emphasis role="bold">...</emphasis></para>` |
| H5+ | never a section | `<para role="articles-h5"><emphasis role="bold">...</emphasis></para>` |

### Step 4 — Convert to DocBook 5.1 XML

Apply these rules to every element in the doc. Preserve all formatting — do not flatten or strip inline styles.

**Normal paragraphs:** `<para>text</para>`

**Inline formatting** (apply within any `<para>` or `<title>`):

| Google Doc style | DocBook output |
|---|---|
| Bold | `<emphasis role="bold">text</emphasis>` |
| Italic | `<emphasis>text</emphasis>` |
| Bold + italic | `<emphasis role="bold"><emphasis>text</emphasis></emphasis>` |
| Monospace / inline code | `<code>text</code>` |
| External hyperlink | `<link xlink:href="URL">text</link>` |
| Internal cross-reference (Paligo topic) | `<xref xlink:href="urn:resource:component:{paligo_resource_id}"/>` |

**Hyperlink resolution — internal vs. external:**

For every hyperlink in the source document, check whether it points to a Help Center article:

- **URL matches `help.{instance}.com/hc/...`** → attempt to resolve to a Paligo `<xref>`:
  1. **First — use `get_folder(folder_id)` on the destination folder.** Call it on the folder where the new document will be created. It returns all children with `id` and `name`. Match the link anchor text against document names — most internal links point to siblings. This resolves the majority of internal links in a single API call with no extra token cost.
  2. **If not found in the folder** — fall back to the Zendesk lookup:
     a. Extract the Zendesk article ID from the URL.
     b. Call `get_article(article_id)` (zendesk-guide MCP) to get the article body HTML.
     c. Search the body for `data-zd-article="{UUID}"` to extract the Paligo UUID.
     d. Call `get_document(UUID)` — the Paligo API accepts UUIDs as path parameters and returns the numeric `id` directly.
  3. If resolved by either method: replace the hyperlink with `<xref xlink:href="urn:resource:component:{id}"/>`. The link text is dropped — Paligo renders the target topic's title at publish time.
  4. If the lookup fails at every step: keep as `<link xlink:href="...">link text</link>` and flag for review.
  - **Never use `search()`** — see **Available tools → Search** above.
- **Any other URL** → `<link xlink:href="URL">link text</link>` (external link, no lookup needed).

When a link is replaced by `<xref>`, the link text from the source doc is dropped — Paligo generates the anchor text from the target topic's title at publish time.

Mixed runs in a single paragraph: wrap each run in its own inline element; plain runs are bare text nodes.

**Lists:**

```xml
<!-- Unordered -->
<itemizedlist>
  <listitem><para>Item</para></listitem>
</itemizedlist>

<!-- Ordered -->
<orderedlist>
  <listitem><para>Step</para></listitem>
</orderedlist>
```

Nested lists are supported — wrap in another list element inside the parent `<listitem>`.

**Procedures (numbered task steps):** When a numbered list represents a sequence of user actions — especially when items have bold titles, span multiple paragraphs, or the enclosing heading uses language like "How to…" or "Steps to…" — convert to `<procedure>` with `<step>` elements instead of `<orderedlist>`. `<step>` elements are only valid inside `<procedure>`, `<substeps>`, or `<stepalternatives>` — never inside list elements.

```xml
<!-- Task procedure: items are user actions, may have titles and multi-para content -->
<procedure>
  <step>
    <title>Create the record</title>
    <para>Navigate to the record. Click <emphasis role="bold">New</emphasis>.</para>
  </step>
  <step>
    <para>Fill in the fields and save.</para>
  </step>
</procedure>

<!-- Simple ordered list: items are enumerated entries, not actions -->
<orderedlist>
  <listitem><para>First consideration.</para></listitem>
  <listitem><para>Second consideration.</para></listitem>
</orderedlist>
```

Use `<substeps>` for nested step groups inside a `<step>`.

**Admonitions:** Detect note/tip/warning/caution/important callouts and convert to the matching admonition element. Each admonition wraps `<para>` content. Admonitions cannot be nested inside each other, and cannot contain `<section>` elements.

| Google Doc pattern | DocBook element |
|---|---|
| Paragraph or box starting with "Note:" | `<note><para>…</para></note>` |
| Paragraph or box starting with "Tip:" | `<tip><para>…</para></tip>` |
| Paragraph or box starting with "Important:" | `<important><para>…</para></important>` |
| Paragraph or box starting with "Caution:" | `<caution><para>…</para></caution>` |
| Paragraph or box starting with "Warning:" | `<warning><para>…</para></warning>` |

Strip the "Note:", "Tip:", etc. prefix from the paragraph text — the element itself carries that semantic label. If the admonition spans multiple paragraphs in the source, include all of them as sibling `<para>` elements inside the admonition.

**Tables:** Use `<informaltable>` per the rules in `references/docbook-spec.md`. If the table has no header row, omit `<thead>`.

**Images:** `get_doc_structure` does not return image data. Images were already extracted in Step 2 by `get_doc_images` — each image is saved to `/tmp/doc-image-N.png` and the result includes `preceding_text` and `following_text` to identify where it goes in the doc.

**Image pipeline (Steps 2 already done the extraction):**

1. **Locate the insertion point** using `preceding_text` and `following_text` from the `get_doc_images` result. Find those text fragments in the converted `<para>` elements and note the insertion point in the XML.

2. **Upload each image to Paligo** using `upload_image`:
   ```
   upload_image(file_path="/tmp/doc-image-0.png")
   ```
   The response includes the image `uuid`.

3. **Reference the image in the XML** using both `fileref` and `xinfo:image` set to the image UUID:
   ```xml
   <mediaobject>
     <imageobject>
       <imagedata fileref="UUID-14c9b5aa-058a-4a8a-d443-8e326be84796" xinfo:image="UUID-14c9b5aa-058a-4a8a-d443-8e326be84796"/>
     </imageobject>
   </mediaobject>
   ```
   Paligo normalizes `fileref` to its internal path format (`../images/{UUID}/size/hpr`) on ingest — set it to the UUID and let Paligo rewrite it.

If `get_doc_images` returns an empty array (no images in the doc), skip this section entirely.

If the Drive HTML export fails (access error), insert a placeholder and note the location for manual upload:
```xml
<!-- IMAGE: [description or alt text] — upload manually via Paligo UI and replace with mediaobject -->
```

**Element IDs:** Do not add `xml:id` to any inner element. Only the root `<section>` carries `xml:id` (the Paligo UUID). Never generate or assign IDs to inner sections, paragraphs, steps, or any other element.

**Omit:** page breaks, document headers/footers, comments, suggestions, and empty spacing paragraphs.

**Section nesting constraint:** Once a child `<section>` has opened, no further block elements (`<para>`, `<informaltable>`, `<itemizedlist>`) may appear after it at the same level. All such content must be inside a section. See `references/docbook-spec.md` for the full rule and examples.

### Step 5 — Wrap in the DocBook envelope

Use the full XML wrapper from `references/docbook-spec.md`. For the root `<section>` attributes:

- **Uploading to an existing Paligo document:** call `get_document(paligo_doc_id)` first to retrieve the UUID and resource ID, then use those values (see the fresh-fetch rule in **Safety rules**).
- **Creating a new Paligo document (Step 7):** use placeholder values `xinfo:resource="UUID-placeholder"` and `xinfo:resource-id="0"` for the file output. The real values will be substituted in Step 7 after `create_document` returns them.
- **Convert-only (no upload planned):** use placeholder values — note them clearly in a comment at the top of the file.

### Step 6 — Write output file

Derive a filename from the document title: lowercase, spaces replaced with hyphens, date-suffixed.

Example: a doc titled "Add account" → `add-account-2026-08-04.xml`

Write the complete XML to:
```
skills/paligo-pal/outputs/{filename}.xml
```

Create the `outputs/` directory if it does not exist. After writing, report the full file path to the user. Do not print the full XML to the console — the file is the output.

**Stop here unless the user explicitly asks to upload to Paligo.**

### Step 7 — Upload to Paligo (on request)

**Google Doc conversions always create a new document** — never the folder's blank placeholder article (see **Blank placeholder article in every folder** above). Only ask "updating or creating?" when the user explicitly says they want to update an existing Paligo document (not a Google Doc conversion).

**Updating an existing document:**
1. Call `get_document(paligo_doc_id)` immediately before updating, per the fresh-fetch rule in **Safety rules** — even if you fetched it earlier in the session. Use the UUID and resource ID from this fresh fetch.
2. Substitute the real UUID and resource ID into the converted XML (replacing any placeholders).
3. Confirm the change with the user, then call `update_document(paligo_doc_id, xml_content=<full XML>)`.
4. Update the output file with the final XML (real IDs substituted).

**Creating a new document:**
1. Ask for the document name and target folder if not already provided.
2. Call `create_document(name, folder_id, subtype="component")`. Note the returned `id` and `uuid`.
3. Substitute the real UUID and ID into the XML, replacing the placeholders.
4. Call `update_document(new_doc_id, xml_content=<full XML>)`.
5. Update the output file with the final XML (real IDs substituted).

### Conversion edge cases

| Situation | Handling |
|---|---|
| No H1 in doc | Use the document title as the root `<section><title>` |
| Body text before the first heading | Place as `<para>` directly inside root `<section>`, before any child sections |
| Table with merged cells | Add `colspan="N"` or `rowspan="N"` on `<td>`/`<th>`; flag for review |
| Heading with inline formatting | Apply inline mapping inside `<title>` or inside the fallback `<para>` |
| gdrive 404 | Doc may not be shared with the authenticated account — ask user to check sharing settings |

### Step 8 — Apply Zendesk content tags and labels (optional)

After posting to Paligo and triggering a production, if the user wants to apply content tags or labels to the published Zendesk articles, hand off to the `zendesk-pal` skill. That skill handles: resolving Zendesk article IDs from Paligo UUIDs, resolving or creating content tags via `/api/v2/guide/content_tags` and applying them via `PUT /api/v2/help_center/articles/{id}` with `content_tag_ids`, and applying labels via `POST /api/v2/help_center/articles/{id}/labels`.
