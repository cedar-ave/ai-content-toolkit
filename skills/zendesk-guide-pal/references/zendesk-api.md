# Zendesk Help Center API Reference

## Authentication

### Production — Basic Auth

Prod uses HTTP Basic Auth. The MCP server constructs the `Authorization` header automatically by base64-encoding `{email}/token:{api_token}`.

| Variable | Description |
|---|---|
| `ZENDESK_SUBDOMAIN` | Prod subdomain, e.g. `company` |
| `ZENDESK_EMAIL` | Zendesk account email |
| `ZENDESK_API_TOKEN` | Raw Zendesk API token |

### Sandbox — OAuth client credentials

Sandbox uses OAuth 2.0 client credentials grant. The MCP server fetches a Bearer token automatically and caches it for its 30-minute lifetime.

| Variable | Description |
|---|---|
| `ZENDESK_SANDBOX_SUBDOMAIN` | Sandbox subdomain, e.g. `{instance}123` |
| `ZENDESK_SANDBOX_CLIENT_ID` | OAuth client unique identifier |
| `ZENDESK_SANDBOX_CLIENT_SECRET` | OAuth client secret |

Token request:
```
POST https://{sandbox_subdomain}.zendesk.com/oauth/tokens
grant_type=client_credentials&client_id={id}&client_secret={secret}&scope=read+write
```

Returns `{ "access_token": "...", "expires_in": 1800 }`. Pass as `Authorization: Bearer {token}`.

Base URLs (same pattern for both environments):
- Help Center: `https://{subdomain}.zendesk.com/api/v2/help_center`
- Guide: `https://{subdomain}.zendesk.com/api/v2/guide`
- Theming: `https://{subdomain}.zendesk.com/api/v2/guide/theming`

---

## Article object fields

| Field | Type | Writable | Description |
|---|---|---|---|
| `id` | integer | No | Auto-assigned Zendesk article ID |
| `title` | string | Yes | Article headline |
| `body` | string | Yes | Full HTML body of the article |
| `locale` | string | Yes | Language/region code |
| `section_id` | integer | Yes | Parent section ID |
| `author_id` | integer | Yes | User ID of author |
| `permission_group_id` | integer | Yes | Controls edit/publish access |
| `user_segment_id` | integer | Yes | Viewer access control |
| `content_tag_ids` | array | Yes | Array of content tag ID strings (opaque, e.g. `01JYA6M8KH6ZQP5J7BR2SE57FX`) |
| `label_names` | array | Yes | Array of label name strings (Professional/Enterprise only) |
| `promoted` | boolean | Yes | Featured status |
| `draft` | boolean | Yes | `true` = draft, `false` = published |
| `comments_disabled` | boolean | Yes | Toggles comment capability |
| `html_url` | string | No | Public-facing article URL |
| `created_at` | string | No | Creation timestamp |
| `updated_at` | string | No | Last modification timestamp |

---

## Articles endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/help_center/articles` | List all articles |
| `GET` | `/api/v2/help_center/sections/{section_id}/articles` | List articles in a section |
| `GET` | `/api/v2/help_center/articles/{article_id}` | Get a single article (includes full `body` HTML) |
| `POST` | `/api/v2/help_center/sections/{section_id}/articles` | Create an article |
| `PUT` | `/api/v2/help_center/articles/{article_id}` | Update an article |
| `DELETE` | `/api/v2/help_center/articles/{article_id}` | Archive an article |

### Updating an article

Body fields are sent nested under an `article` key:

```json
PUT /api/v2/help_center/articles/{article_id}
{
  "article": {
    "content_tag_ids": [123, 456],
    "label_names": ["Salesforce app", "Provider credentialing"]
  }
}
```

`content_tag_ids` is a **full replace** — always fetch the existing IDs first and merge before writing.

---

## Content tags

Content tags are managed under the `/guide` base URL, not `/help_center`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/guide/content_tags?filter[name_prefix]={prefix}` | Search tags by name prefix |
| `POST` | `/api/v2/guide/content_tags` | Create a new content tag |

### Search response structure

```json
{
  "records": [
    { "id": "01JYA6M8KH6ZQP5J7BR2SE57FX", "name": "Salesforce app" }
  ]
}
```

The `filter[name_prefix]` search returns partial matches — always find the exact match by comparing `tag.name.toLowerCase() === tagName.toLowerCase()`.

### Create request/response

```json
POST /api/v2/guide/content_tags
{ "content_tag": { "name": "Salesforce app" } }

→ { "content_tag": { "id": "01JYA6M8KH6ZQP5J7BR2SE57FX", "name": "Salesforce app" } }
```

### Applying content tags to an article — workflow

1. `GET /api/v2/guide/content_tags?filter[name_prefix]={name}` — find the tag by exact name match
2. If not found, `POST /api/v2/guide/content_tags` to create it
3. `GET /api/v2/help_center/articles/{article_id}` — fetch existing `content_tag_ids`
4. Merge new tag IDs into existing array (deduplicate)
5. `PUT /api/v2/help_center/articles/{article_id}` with `{ "article": { "content_tag_ids": [...merged...] } }`

Never pass only the new tag IDs — always merge with existing to avoid removing tags already on the article.

---

## Labels

Labels are string-based and managed via a separate endpoint. **Professional and Enterprise plans only.**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/help_center/articles/labels` | List all labels |
| `GET` | `/api/v2/help_center/articles/{article_id}/labels` | List labels on an article |
| `POST` | `/api/v2/help_center/articles/{article_id}/labels` | Add a label to an article |
| `DELETE` | `/api/v2/help_center/articles/labels/{label_id}` | Delete a label (removes from all articles) |
| `DELETE` | `/api/v2/help_center/articles/{article_id}/labels/{label_id}` | Remove a label from one article |

### Label object fields

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-assigned label ID |
| `name` | string | Label name string |
| `created_at` | string | Creation timestamp |
| `updated_at` | string | Last update timestamp |
| `url` | string | API endpoint URL |

### Adding a label to an article

```json
POST /api/v2/help_center/articles/{article_id}/labels
{ "label": { "name": "getting-started" } }
```

Labels are additive — posting a label that already exists on an article is a no-op (does not duplicate).

---

## Sections endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/help_center/sections` | List all sections |
| `GET` | `/api/v2/help_center/categories/{category_id}/sections` | List sections in a category |
| `GET` | `/api/v2/help_center/sections/{section_id}` | Get a single section |

### Section object fields

| Field | Type | Description |
|---|---|---|
| `id` | integer | Section ID |
| `name` | string | Section name |
| `category_id` | integer | Parent category ID |
| `html_url` | string | Public URL |
| `position` | integer | Sort order |

---

## Categories endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/help_center/categories` | List all categories |
| `GET` | `/api/v2/help_center/categories/{category_id}` | Get a single category |

---

## Search

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/help_center/articles/search?query={q}` | Search articles by text |

Query parameters: `query`, `category`, `section`, `label_names`, `locale`, `brand_id`, `created_before/after`, `updated_before/after`, `sort_by`, `sort_order`.

**Limitation:** The search API does not support searching inside `body` HTML content. You cannot query by `data-zd-article` UUID or any other HTML attribute value via search.

---

## Locating a Zendesk article by Paligo UUID

Paligo embeds the document UUID in the published article body as a `data-zd-article` attribute:

```html
<a data-zd-article="UUID-5c8953c1-0a12-efbb-dbd0-6385fb24f55d" id="..."></a>
```

Since the search API does not index body HTML, the only reliable way to map a Paligo UUID to a Zendesk article ID is:

1. `GET /api/v2/help_center/sections/{section_id}/articles` — list articles in the target section
2. For each article, `GET /api/v2/help_center/articles/{article_id}` — retrieve the full `body`
3. Check whether the body contains `data-zd-article="{PALIGO_UUID}"`
4. When matched, record `article_id`

This is duplicate-safe — two articles with the same title will have different UUIDs in their body HTML.

---

## Redirect rules

Redirect rules are managed under the `/guide` base URL, not `/help_center`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v2/guide/redirect_rules` | List all redirect rules |
| `GET` | `/api/v2/guide/redirect_rules/{rule_id}` | Get a single redirect rule |
| `POST` | `/api/v2/guide/redirect_rules` | Create a redirect rule |
| `DELETE` | `/api/v2/guide/redirect_rules/{rule_id}` | Delete a redirect rule |

### Creating a redirect rule

```json
POST /api/v2/guide/redirect_rules
{
  "redirect_rule": {
    "redirect_from": "/hc/en-us/articles/50861704357139",
    "redirect_to": "/hc/en-us/articles/50925987130003",
    "redirect_status": 301
  }
}
```

Returns HTTP 204 on success (no body). Required fields:

| Field | Type | Description |
|---|---|---|
| `redirect_from` | string | Source path (e.g. `/hc/en-us/articles/{id}`) |
| `redirect_to` | string | Destination path |
| `redirect_status` | integer | `301` (permanent) or `302` (temporary) |

**Note:** The source article must be archived or deleted before the redirect will take effect. Zendesk requires the source URL to return a 404 before it will serve the redirect.

### Listing and verifying redirect rules

The redirect rules list endpoint uses **cursor-based pagination**, not offset pagination. Do not use `per_page` or `page` — they only return the first page. Always paginate with `page[size]` and `page[after]`:

```
GET /api/v2/guide/redirect_rules?page[size]=30
GET /api/v2/guide/redirect_rules?page[size]=30&page[after]={after_cursor}
```

**`page[size]` is capped at 30.** Any larger value returns an error, not results — and not a truncated page:

```json
{ "errors": [{ "title": "Value `100` for /page/size/0 is of type `string`; expected `integer less than or equal to 30`", "code": "TypeError" }] }
```

Because the failure is an HTTP 4xx error body (with no `records`/`meta`), a pagination loop that only checks `meta.has_more` will silently see zero rules and conclude a rule is missing. Always use `page[size]=30` (or smaller), and treat a response lacking `records`/`meta` as an error, not an empty result.

Response structure:

```json
{
  "records": [...],
  "meta": {
    "has_more": true,
    "after_cursor": "xxx",
    "before_cursor": "yyy"
  }
}
```

Continue fetching while `meta.has_more` is `true`, using `meta.after_cursor` as the `page[after]` value. A successful POST returns 204 with no body — always paginate through all pages to verify the rule was created.

---

## Theming API

Base URL: `https://{subdomain}.zendesk.com/api/v2/guide/theming`

Auth: prod uses Basic Auth; sandbox uses OAuth Bearer token (same credentials as all other sandbox calls).

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/themes` | List all themes (id, name, version, live status, brand_id) |
| `GET` | `/themes/{theme_id}` | Get details of a specific theme |
| `POST` | `/themes/{theme_id}/publish` | Make a theme live — replaces the current live theme |
| `DELETE` | `/themes/{theme_id}` | Delete a theme (cannot delete the live theme) |
| `POST` | `/jobs/themes/imports` | Create an async import job to upload a theme zip |
| `POST` | `/jobs/themes/exports` | Create an async export job to download a theme zip |
| `GET` | `/jobs/{job_id}` | Poll a job's status |

### Import flow

Theme import is async and uses a presigned S3 upload — there is no direct zip upload endpoint.

**Step 1 — Create import job**

```
POST /api/v2/guide/theming/jobs/themes/imports
Header: X-Zendesk-Request-Originator: zcli themes:import
{
  "job": {
    "attributes": {
      "brand_id": "{brand_id}",
      "format": "zip"
    }
  }
}
```

Returns HTTP 202:
```json
{
  "job": {
    "id": "abc123",
    "status": "pending",
    "data": {
      "theme_id": "uuid-of-new-theme",
      "upload": {
        "url": "https://theme.zdassets.com",
        "parameters": { "key": "...", "policy": "...", ... }
      }
    }
  }
}
```

**Step 2 — Upload zip to presigned S3 URL**

POST the zip as `multipart/form-data` to `job.data.upload.url`. Include all `job.data.upload.parameters` as form fields first, then `file` last. No auth header — this goes directly to S3.

**Step 3 — Poll until complete**

```
GET /api/v2/guide/theming/jobs/{job_id}
```

Returns `job.status`: `"pending"` → keep polling; `"completed"` → done; `"failed"` → check `job.errors`.

**Step 4 — Publish**

```
POST /api/v2/guide/theming/themes/{theme_id}/publish
```

`theme_id` comes from `job.data.theme_id` in the Step 1 response. The imported theme is not live until this call is made.

### brand_id

Required for the import job. Fetch from:
```
GET https://{subdomain}.zendesk.com/api/v2/brands.json
```
Returns `{ "brands": [{ "id": 53983368476179, ... }] }`. On a single-brand account, always use `brands[0].id`.

### Critical endpoint note

The correct import endpoint is `/jobs/themes/imports`. The older endpoint `/jobs` (used in some documentation) returns **404 on sandbox** and should not be used.

---

## Rate limits

Zendesk's general API rate limit is 200 requests per minute. Use a concurrency limit of 5 concurrent requests and exponential backoff on 429 responses (retry up to 3 times, starting at 1 second, doubling each attempt).

---

## Pagination

Most Help Center list endpoints (`/help_center/...`) use offset-based pagination with a `next_page` URL in the response. Fetch the `next_page` URL and combine results until `next_page` is null.

Guide endpoints (`/guide/...`) — including redirect rules — use **cursor-based pagination**. Use `page[size]` and `page[after]` query parameters, and check `meta.has_more` and `meta.after_cursor` in the response. Do not use `per_page` or `page` on these endpoints — they silently return only the first page with no indication that more pages exist.
