# Paligo API Field Names and Known Gotchas

Confirmed field names and failure modes discovered through live API testing against `{instance}.paligoapp.com`. When an MCP tool returns 422, check this file first before debugging.

---

## Document creation — `POST /documents/`

**Correct body:**
```json
{"name": "My Topic", "parent": 73210, "subtype": "component"}
```

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Display name of the document |
| `parent` | Yes | Numeric folder ID — **not** `folder` |
| `subtype` | Yes | Must be `"component"` for standard topics; `"publication"` for publications |

**Wrong (causes 422):**
- `folder` instead of `parent`
- Missing `subtype`
- Passing `content` or `xml` at creation time — content must be set in a separate `PUT` call

---

## Document update — `PUT /documents/{id}`

**Correct body:**
```json
{"content": "<section ...>...</section>"}
```

| Field | Notes |
|---|---|
| `content` | The XML string — **not** `xml` |
| `name` | Optional; omit to leave the name unchanged |

**Wrong (causes 422):**
- Using `xml` instead of `content`

---

## Image upload — `POST /images/`

**Correct multipart request:**
- Form field for the file: `image` — **not** `file`
- **No additional form body fields** — do not include `folder`, `parent`, or `name`; any extra field causes 422
- Response includes `id`, `uuid`, `name`, and `content_url`

```bash
# Correct curl
curl -X POST "https://{instance}.paligoapp.com/api/v2/images/" \
  -H "Authorization: Basic {PALIGO_API_TOKEN}" \
  -F "image=@/tmp/image.png;filename=my-image.png"
```

```python
# Correct Python
with open("/tmp/image.png", "rb") as f:
    r = requests.post(
        "https://{instance}.paligoapp.com/api/v2/images/",
        headers={"Authorization": f"Basic {PALIGO_API_TOKEN}"},
        files={"image": ("my-image.png", f, "image/png")},
    )
image_uuid = r.json()["uuid"]
```

**Wrong (causes 422):**
- `-F "file=@..."` — wrong field name
- Including `-F "folder=73210"` — causes 422
- Including `-F "parent=73210"` — causes 422
- Including `-F "name=..."` — causes 422

**The `upload_image` MCP tool signature (fixed):** `upload_image(file_path, name?)` — `folder_id` parameter removed. The tool now sends only the `image` file field with no extra form data.

---

## Image fileref after upload

When Paligo ingests an `<imagedata>` element, it normalizes `fileref` to its internal path format:
```
../images/{UUID}/size/hpr
```

You can author `fileref="{UUID}"` (just the UUID) and Paligo will rewrite it. Both the authored value and Paligo's rewritten value are functionally equivalent. Always set `xinfo:image` to the same UUID.

---

## Search API — `POST /search/`

**The Paligo `search()` MCP tool and `/search/` endpoint return 422 for all tested query formats:**
- `{"title": "my document"}`
- `{"text": "my document"}`
- `{"q": "my document"}`

**Do not use `search()` to find documents.** Use `get_folder(folder_id)` instead — it returns all children with `id`, `name`, and `uuid`.

---

## `list_documents` returns empty

The `list_documents(folder_id=...)` MCP tool may return `{"documents": []}` even when documents exist in the folder. The cause is unknown but it is reproducible.

**Reliable alternative:** `get_folder(folder_id)` — always returns all children including documents, folders, and images.

---

## Finding sibling documents for internal cross-references

To resolve a Help Center link to a Paligo resource ID:
1. Call `get_folder(folder_id)` on the destination folder.
2. Match the link anchor text to a child document name.
3. Use the child's `id` in `<xref xlink:href="urn:resource:component:{id}"/>`.

Most internal links point to siblings in the same folder. This resolves them in a single API call — no Zendesk lookup, no search, no extra tokens.

---

## Productions — `POST /productions/`

**Correct body:**
```json
{"publishsetting": 35}
```

| Field | Notes |
|---|---|
| `publishsetting` | Integer ID of the publish setting — **not** `publishsettingid`, `publishsetting_id`, or `publish_setting_id` |

Do not pass `document` or `documentid` — the publication is already embedded in the publish setting.

The correct list/get endpoint is `/publishsettings` (plural).

---

## MCP tool vs. direct API

When an MCP tool returns an unexpected 422, the usual cause is a wrong field name in the request body. Fall back to Python or curl using credentials from the plugin's root `.env`:

```python
import requests, os
from dotenv import load_dotenv
load_dotenv(".env")  # repo root

TOKEN = os.getenv("PALIGO_API_TOKEN")
BASE  = f"https://{os.getenv('PALIGO_INSTANCE')}/api/v2"

r = requests.post(
    f"{BASE}/documents/",
    headers={"Authorization": f"Basic {TOKEN}", "Content-Type": "application/json"},
    json={"name": "My Topic", "parent": 73210, "subtype": "component"},
)
print(r.status_code, r.json())
```

The MCP and direct API share the same credentials; MCP failures are always field name or body format issues, not auth issues.
