# Paligo DocBook 5.1 XML Reference

All document XML content must conform to the Paligo DocBook 5.1 schema with Paligo's `xinfo` extensions. Every document written via `create_document` or `update_document` must follow this spec exactly.

## Required XML declaration and schema binding

```xml
<?xml version="1.0" encoding="UTF-8"?>
<?xml-model href="https://resources.paligo.net/schema/docbookxi-5.1-xinfo.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"?>
```

## Required namespaces

Every root element must declare all of the following namespaces:

```xml
xmlns="http://docbook.org/ns/docbook"
xmlns:xinfo="http://ns.expertinfo.se/cms/xmlns/1.0"
xmlns:xi="http://www.w3.org/2001/XInclude"
xmlns:mml="http://www.w3.org/1998/Math/MathML"
xmlns:xlink="http://www.w3.org/1999/xlink"
xmlns:t="http://ns.expertinfo.se/translation/xmlns/1.0"
```

## Required xinfo attributes on the root element

| Attribute | Description |
|---|---|
| `xinfo:resource` | UUID of the document, e.g. `UUID-3da9c988-744c-b917-1442-34eafb76a0ca` |
| `xinfo:resource-id` | Numeric ID of the document (omit on create — assigned by the API) |
| `xinfo:resource-type` | Must be `component` for standard topics |
| `xinfo:resource-title` | Human-readable title matching `<title>` |
| `xinfo:resource-titlelabel` | Usually empty string `""` |
| `xinfo:version-major` | Major version, typically `1` |
| `xinfo:version-minor` | Minor version, typically `0` |
| `xml:id` | Same value as `xinfo:resource` (the UUID) |
| `xml:lang` | Language code, e.g. `en` |
| `version` | Always `5.0` |

## Creating a document — two-step workflow

**Do not pass XML content to `create_document`.** The API rejects `content` on creation unless `subtype` is also provided. The correct workflow is:

1. Call `create_document` with `name`, `parent` (folder ID), and `subtype=component`. The API assigns the document ID and UUID.
2. Call `update_document` with the assigned ID and the full XML `content`, using the UUID returned in step 1.

```python
# Step 1 — create the shell
POST /documents/  body: {"name": "my-topic", "parent": 4586, "subtype": "component"}
# Response includes: {"id": 72335, "uuid": "UUID-640f8959-...", ...}

# Step 2 — write content using the assigned UUID and ID
PUT /documents/72335  body: {"content": "<section ... xinfo:resource-id=\"72335\" xinfo:resource=\"UUID-640f8959-...\">...</section>"}
```

## Supported subtypes

| Subtype | Description | Root XML element |
|---|---|---|
| `component` | Standard topic / section (most common) | `<section>` |
| `informaltopic` | Topic without a formal title structure | `<section>` |
| `publication` | Publication / table of contents | `<article>` |

The root XML element for topics is always `<section>`. Publications use `<article>`.

## DocBook 5.1 content rules

**Section nesting constraint (critical):** Once a child `<section>` appears inside a parent `<section>`, no further block-level elements (`para`, `informaltable`, `itemizedlist`, etc.) may appear after it at the same level. All block content that follows a `<section>` must be placed inside a section.

Correct:
```xml
<section>
  <title>Parent</title>
  <para>Intro paragraph.</para>       <!-- OK: before any child section -->
  <section>
    <title>Child</title>
    <para>Content.</para>
    <informaltable>...</informaltable> <!-- OK: inside the child section -->
  </section>
</section>
```

Incorrect (causes 422):
```xml
<section>
  <title>Parent</title>
  <para>Intro.</para>
  <section>
    <title>Child</title>
    <para>Content.</para>
  </section>
  <informaltable>...</informaltable>  <!-- INVALID: block after a section -->
</section>
```

## Tables

Paligo uses HTML-style table markup, not CALS `tgroup/row/entry`. Always use `informaltable` with `thead/tbody/tr/th/td`. Each cell must contain a `<para>`.

```xml
<informaltable>
  <thead>
    <tr>
      <th><para>Column A</para></th>
      <th><para>Column B</para></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><para>Row 1, A</para></td>
      <td><para>Row 1, B</para></td>
    </tr>
    <tr>
      <td><para/></td>
      <td><para/></td>
    </tr>
  </tbody>
</informaltable>
```

Do not use `<table>`, `<tgroup>`, `<colspec>`, `<row>`, or `<entry>` — the schema rejects them.

## Common inline elements

| Intent | Element |
|---|---|
| Bold | `<emphasis role="bold">text</emphasis>` |
| Italic | `<emphasis>text</emphasis>` |
| Bold + italic | `<emphasis role="bold"><emphasis>text</emphasis></emphasis>` |
| Inline code | `<code>text</code>` |
| UI element | `<guilabel>Button Name</guilabel>` |
| Hyperlink | `<link xlink:href="URL">text</link>` |
| Custom role | `<para role="articles-h4">text</para>` |

## Document hierarchy constraints (Paligo-specific)

Paligo supports only DocBook elements below `article`. The elements `book`, `part`, and `set` are not used in Paligo.

| DocBook element | Paligo mapping | Notes |
|---|---|---|
| `<article>` | Publication | Contains only `<info>` metadata — no body content |
| `<section>` | Topic / component | Standard content unit; root element for all topics |

Do not use `<book>`, `<part>`, or `<set>` in any Paligo XML.

---

## Procedures and steps

Use `<procedure>` and `<step>` for task-based content where the reader must follow a numbered sequence of actions.

**Content model:**
- `<procedure>` must contain one or more `<step>` elements.
- `<step>` must appear inside `<procedure>`, `<substeps>`, or `<stepalternatives>` — it is **not** valid inside `<itemizedlist>`, `<orderedlist>`, or any other list element.
- `<step>` may optionally start with a `<title>` (step heading), followed by one or more block elements (`<para>`, `<itemizedlist>`, `<informaltable>`, etc.).
- `<substeps>` wraps nested steps inside a `<step>`.

```xml
<procedure>
  <step>
    <title>Create the record</title>
    <para>Navigate to the provider record. Click <emphasis role="bold">New</emphasis>.</para>
  </step>
  <step>
    <title>Select the type</title>
    <para>In the <emphasis role="bold">Type</emphasis> dropdown, select <emphasis role="bold">Off-cycle</emphasis>.</para>
  </step>
  <step>
    <para>Save the record.</para>
  </step>
</procedure>
```

With nested sub-steps:
```xml
<step>
  <para>Main step content.</para>
  <substeps>
    <step><para>Sub-step A.</para></step>
    <step><para>Sub-step B.</para></step>
  </substeps>
</step>
```

**`<procedure>` vs `<orderedlist>`:**
- Use `<procedure>` when each item represents a discrete user action, especially when items have titles or contain multiple paragraphs.
- Use `<orderedlist>` for simple enumerated items that are not user actions.

---

## Admonition elements

Admonitions call out important information set off from the main text. Each admonition wraps one or more `<para>` elements (and other block content). They **cannot** contain `<section>` elements, and admonitions must not be nested inside each other.

| Element | Use case |
|---|---|
| `<note>` | Supplemental information the reader should be aware of |
| `<tip>` | Helpful suggestions or shortcuts |
| `<important>` | Information the reader must not overlook |
| `<caution>` | Potential for data loss or unintended consequences |
| `<warning>` | Risk of harm or severe consequences |

```xml
<note>
  <para>This applies to both provider and facility credentialing.</para>
</note>

<tip>
  <para>Filter by credentialing event type in Report Builder to isolate these events.</para>
</tip>

<warning>
  <para>Deleting this record cannot be undone.</para>
</warning>
```

Admonitions are subject to the same section-nesting constraint as other block elements: they must not appear after a child `<section>` at the same level.

---

## Paligo Schematron validation rules

Paligo applies Schematron rules on top of the DocBook 5.1 schema:

**Maximum 10 sections per topic:** Paligo counts all `<section>` elements in the topic regardless of nesting depth. If a topic would exceed 10 sections, split content across multiple topics or flatten deeper heading levels to bolded `<para>` elements (see heading fallback rules in the conversion skill). Topics embedded via `<xi:include>` or publication forks do not count against this limit.

---

## Element IDs

Do not add `xml:id` attributes to inner `<section>`, `<para>`, or any other inner element. Only the root `<section>` carries an `xml:id` — set to the Paligo-assigned UUID.

```xml
<!-- Correct: no xml:id on inner sections -->
<section>
  <title>My Section</title>
  <para>Content.</para>
</section>

<!-- Wrong: do not add xml:id to inner elements -->
<section xml:id="my-section">
  <title>My Section</title>
</section>
```

---

## Images

Use `<mediaobject>` to embed an image in a topic. Paligo requires **both** `fileref` and `xinfo:image` set to the image UUID.

```xml
<mediaobject>
  <imageobject>
    <imagedata fileref="UUID-14c9b5aa-058a-4a8a-d443-8e326be84796" xinfo:image="UUID-14c9b5aa-058a-4a8a-d443-8e326be84796"/>
  </imageobject>
</mediaobject>
```

Both attributes take the same value: the image UUID returned by `upload_image` or `get_image`. `xinfo:image` is Paligo's internal reference; `fileref` seeds the DocBook path — Paligo normalizes `fileref` to its own internal path (`../images/{UUID}/size/hpr`) on ingest, so the UUID value you send gets rewritten automatically.

**Upload workflow:**
1. Images are extracted in Step 2 of the pipeline via `get_doc_images(doc_id)`. Each image is saved to `/tmp/doc-image-N.png`.
2. Upload each image via `upload_image(file_path="/tmp/doc-image-0.png")`. Note the `uuid` in the response.
3. Insert the `<mediaobject>` block with both `fileref="{uuid}"` and `xinfo:image="{uuid}"` at the correct position in the XML.
4. Upload the updated XML via `update_document`.

If `upload_image` fails with 422, fall back to curl — send only the file field, no extra form data:
```bash
curl -X POST "https://{instance}.paligoapp.com/api/v2/images/" \
  -H "Authorization: Basic {PALIGO_API_TOKEN}" \
  -F "image=@/tmp/doc-image-0.png;filename=my-image.png"
```

`<mediaobject>` is a block element subject to the same section-nesting constraint as `<para>` and `<informaltable>` — it must not appear after a child `<section>` at the same level.

---

## The role= attribute and Zendesk CSS classes

The `role` attribute can be applied to any DocBook element. When Paligo publishes to Zendesk, the `role` value is output as an HTML `class` attribute on the rendered element.

```xml
<!-- Paligo XML -->
<para role="articles-h4">Section heading text</para>

<!-- Rendered in Zendesk HTML -->
<p class="articles-h4">Section heading text</p>
```

This means `role` values are a direct bridge to Zendesk CSS. Any class defined in your Zendesk theme stylesheet can be applied to content by setting the corresponding `role` in the XML.

**Supported on any element**, including:

```xml
<para role="articles-h4">styled paragraph</para>
<section role="callout-box">...</section>
<procedure role="reuse-range">...</procedure>
<emphasis role="bold">bold text</emphasis>
<informaltable role="compact-table">...</informaltable>
```

**Rules:**
- Use `role` values that correspond to classes defined in the Zendesk theme. Applying an undefined class has no visible effect but is not an error.
- Multiple roles are not supported via a space-separated list in this schema — use a single role value per element.
- `role="bold"` on `<emphasis>` is a built-in DocBook convention for bold text and does not require a Zendesk CSS class.

## Publications and forks

A publication is a document with `subtype: publication` and `<article>` as its XML root element. The publication XML itself contains only the `<info>` metadata block — **it never contains `<xi:include>` entries**. The table of contents structure is managed entirely through **forks**, not through the publication's XML.

A fork is an API object that links a topic to a publication at a specific `depth` and `position`. The fork — not the XML — defines what appears in the output and in what order.

```
POST /forks/  body: {"parent": <publication-id-or-fork-id>, "document": <topic-id>}
```

The API automatically assigns `depth` and `position` based on what `parent` refers to:
- Pass the **publication ID** as `parent` → topic lands at depth 1 (Level 1)
- Pass a **fork ID** as `parent` → topic lands at depth 2 (Level 2, child of that fork)

**Creating a publication — workflow:**

1. Call `create_document` with `name`, `parent` (the Publication folder ID), and `subtype=publication`. The API creates the document and generates a complete `<info>` block automatically.
2. Do not modify the publication XML. It stays as generated — title only inside `<info>`.
3. Add topics by creating forks. Pass the publication ID as `parent` for Level 1 topics.

**Creating a two-level publication (blank heading + child topics):**

The standard pattern used across all guides is:

- A **blank document** (title only, no body content) serves as the Level 1 section heading. In Zendesk this renders as a section header, not an article.
- All real content topics are added at Level 2 beneath it.
- The blank document must stay blank — do not add `<xi:include>` entries or body content to it.

```python
# Step 1 — create publication
POST /documents/  {"name": "My Guide", "parent": <Publication-folder-id>, "subtype": "publication"}
# → returns pub_id

# Step 2 — add blank heading doc as Level 1 (parent = publication ID)
POST /forks/  {"parent": pub_id, "document": <blank-doc-id>}
# → returns fork_id (depth=1)

# Step 3 — add content topics as Level 2 (parent = fork ID from step 2)
POST /forks/  {"parent": fork_id, "document": <topic-id-1>}
POST /forks/  {"parent": fork_id, "document": <topic-id-2>}
# → each returns depth=2, position increments automatically
```

```
My Guide (publication)
└── Blank heading doc          ← fork, depth=1 → renders as section heading in Zendesk
    ├── Topic A                ← fork, depth=2
    ├── Topic B                ← fork, depth=2
    └── Topic C                ← fork, depth=2
```

**Rules for publications and forks:**
- Never add `<xi:include>` entries to a publication's XML. The XML is managed by the API and contains only `<info>`.
- Never modify the publication XML at all after creation — leave it as generated.
- Do not add body content or `<xi:include>` entries to a blank heading document. It must stay blank (title only) so Zendesk renders it as a section heading rather than an article.
- To list the current fork structure of a publication, use `list_forks(parent_id=<publication-id>)`. Each fork has `depth`, `position`, `parent`, and `root_document` fields.
- To add all topics from a Topics folder at Level 2: call `get_folder` to get all children and their IDs, create the Level 1 fork first, then loop through the topics creating one fork per topic with the Level 1 fork ID as `parent`.

## Publishing a publication

Publishing converts a publication and its topics into a final output (HTML, Zendesk, PDF, etc.) using a saved publish setting. Each publish setting is pre-configured in the Paligo UI with a target format, output destination, and the publication it applies to — the document is embedded in the setting, so only the setting ID is needed to trigger a production.

**Full end-to-end workflow to publish a publication:**

1. **Find the publish setting** — call `list_publish_settings()` and identify the setting by name. Each setting has an `id`, `name`, `format`, and `resource` (the publication ID it is associated with).
2. **Trigger the production** — call `create_production(publish_setting_id)` passing only the setting ID. Do not pass a document ID.
3. **Poll for completion** — call `get_production(production_id)` every few seconds until `status` is `done`, `cancelled`, or `failed`.
4. **Retrieve the output** — the completed production response includes a `url` field with the download link for the output archive.

```python
# Step 1 — find the publish setting
GET /publishsettings  → find id=35, name="Test 4", resource=72363

# Step 2 — trigger production
POST /productions/  body: {"publishsetting": 35}
# → returns {"id": "production-xxx", "status": "pending", ...}

# Step 3 — poll
GET /productions/production-xxx
# → {"status": "done", "url": "https://...", "steps": {"total": 24, "count": 25}}
```

**Rules:**
- The correct POST body field is `publishsetting` (integer). Do not use `publishsettingid`, `publish_setting_id`, or `publishsetting_id` — all return 422.
- Do not pass `document` or `documentid` — the publication is already embedded in the publish setting.
- The correct endpoint is `/publishsettings` (plural) for both list and get.
- Productions complete quickly (typically under 30 seconds). Poll every 5 seconds.
- A `status` of `done` with a `url` means the output is ready to download.
- If `status` is `failed`, check the `message` field for the error.

## Cross-references to other Paligo topics

Use `<xref>` to insert a navigable link from one topic to another Paligo topic. In the published output (Zendesk, HTML, PDF), Paligo renders `<xref>` as a clickable anchor using the target topic's title.

**Syntax:**

```xml
<xref xlink:href="urn:resource:component:{paligo_resource_id}"/>
```

`{paligo_resource_id}` is the numeric `xinfo:resource-id` of the target document. Get it by calling `get_document(target_doc_id)` and reading the `id` field from the response (or the `xinfo:resource-id` attribute inside the returned XML).

**In context:**

```xml
<para>See <xref xlink:href="urn:resource:component:71746"/> for the full list of sources.</para>
```

**Cross-reference vs. XInclude vs. external link:**

| Goal | Element |
|---|---|
| Link to another Paligo topic (navigable) | `<xref xlink:href="urn:resource:component:{id}"/>` |
| Embed another topic's content inline | `<xi:include parse="xml" href="{UUID}">` |
| Link to an external URL | `<link xlink:href="https://...">link text</link>` |

**Resolving a Help Center URL to a Paligo resource ID:**

If the source document links to a Help Center article (`help.{instance}.com/hc/...`), the article was likely published from Paligo. To convert it to an `<xref>`:

1. **Try `get_folder(folder_id)` first** on the folder where the new document will be created. It returns all children with `id` and `name`. Match the link anchor text to a document name. Most internal links point to sibling documents in the same folder — this resolves the link in a single fast call with no extra token cost.
2. **If not found in the folder**, fall back to the Zendesk lookup:
   a. Extract the Zendesk article ID from the URL (numeric segment, e.g. `51811543442323`).
   b. Call `get_article(article_id)` via the zendesk-guide MCP to retrieve the article body HTML.
   c. Search the body HTML for `data-zd-article="{UUID}"` to extract the Paligo UUID.
   d. Call `get_document(UUID)` — the Paligo API accepts UUIDs as the path parameter and returns the numeric `id`.
3. Use that `id` as `{paligo_resource_id}` in the `<xref>`.

**Never use `search()`** — it returns 422 for all tested query formats. See `paligo-api-gotchas.md`.

If the lookup fails or the article was not published from Paligo, keep the link as `<link xlink:href="...">` with the original URL.

---

## XInclude (content reuse within a topic)

`<xi:include>` is used to reuse one topic's content inside another topic's XML body — for example, embedding a shared note or a reusable step inside a procedure. It is **not** used to add topics to a publication (that is done via forks).

```xml
<xi:include parse="xml" href="UUID-e783cd4e-d114-4895-3277-4d0974eab366">
  <xi:fallback>
    <para xinfo:translate="no">Reusing topic #UUID-e783cd4e-d114-4895-3277-4d0974eab366</para>
  </xi:fallback>
</xi:include>
```

## Full example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<?xml-model href="https://resources.paligo.net/schema/docbookxi-5.1-xinfo.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"?>
<section xmlns="http://docbook.org/ns/docbook"
         xmlns:xinfo="http://ns.expertinfo.se/cms/xmlns/1.0"
         xmlns:xi="http://www.w3.org/2001/XInclude"
         xmlns:mml="http://www.w3.org/1998/Math/MathML"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         xmlns:t="http://ns.expertinfo.se/translation/xmlns/1.0"
         xml:id="UUID-640f8959-a380-5762-dace-21de908bf040"
         version="5.0"
         xml:lang="en"
         xinfo:resource="UUID-640f8959-a380-5762-dace-21de908bf040"
         xinfo:resource-id="72335"
         xinfo:resource-type="component"
         xinfo:resource-title="My Topic"
         xinfo:resource-titlelabel=""
         xinfo:version-major="1"
         xinfo:version-minor="0">
  <title>My Topic</title>
  <para role="articles-h4">Intro paragraph with custom role.</para>
  <section>
    <title>My Section</title>
    <para>Section content.</para>
    <informaltable>
      <thead>
        <tr>
          <th><para>A</para></th>
          <th><para>B</para></th>
        </tr>
      </thead>
      <tbody>
        <tr><td><para/></td><td><para/></td></tr>
        <tr><td><para/></td><td><para/></td></tr>
      </tbody>
    </informaltable>
  </section>
</section>
```
