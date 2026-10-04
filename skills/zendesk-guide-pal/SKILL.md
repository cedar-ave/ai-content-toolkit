---
name: zendesk-guide-pal
user-invocable: true
description: Perform Zendesk Help Center actions — apply content tags and labels to articles, look up articles by section or Paligo UUID, manage article metadata, and edit and deploy the Help Center theme.
---

# Safety rules

- Always confirm with the user before writing to Zendesk. Read operations may proceed without confirmation.
- Never remove existing content tags or labels unless the user explicitly asks to remove them. Always merge new tags with existing ones.
- Do not expose API credentials in any output.
- If an article ID is unknown, resolve it before writing — do not guess. Use the section listing or Paligo UUID body-scan method described in `references/zendesk-api.md`.
- If a content tag does not exist, create it only after confirming the tag name with the user.
- Never delete a content tag without explicit user confirmation that includes the tag name and ID. Deleting a tag removes it from every article it is applied to.
- Never delete a label globally without explicit user confirmation that includes the label name and ID. Deleting a label removes it from every article it is applied to.
- Rate limit all write operations to a concurrency of 5. Use exponential backoff on 429 responses.
- Always confirm with the user before writing any local theme file.
- Always confirm with the user before importing or publishing a theme. Publishing replaces the live theme immediately.
- Never delete a theme without explicit user confirmation that includes the theme name and ID.
- Never guess file paths or theme IDs. Use `list_themes()` or `list_theme_files()` to find them first.
- **Theme slot limit:** Zendesk allows a maximum of 10 themes. Before importing a theme, call `list_themes()` for the target environment. If there are already 10 themes, the import will fail — you must delete one first. Delete the oldest non-live theme by `created_at`, but **never delete the Copenhagen theme** (it is the original base theme and must be preserved). Inform the user which theme will be deleted and get confirmation before proceeding.
- The local theme directory is `~/Source/zendesk-theme-flatrock`. Never write theme files outside this directory unless explicitly instructed.

## CRITICAL: Production write safeguard

**Write tools default to `target="sandbox"`. You must NEVER pass `target="prod"` to a write tool unless the user has explicitly confirmed in plain language that they want production changes.**

Required confirmation flow before any `target="prod"` write:
1. Tell the user: "This will write to **production** (`{instance}.zendesk.com`). Confirm to proceed."
2. Wait for explicit user approval (e.g., "yes", "confirmed", "go ahead").
3. Only then pass `target="prod"`.

If in doubt, default to sandbox. A wrong sandbox write is recoverable. A wrong production write may not be.

Always report the `_environment` field from every tool response so it is visible in the output. If a response shows `_environment: "prod"`, call that out explicitly to the user.

---

# Zendesk

Use this skill to interact with the Zendesk Help Center API. See `references/zendesk-api.md` for the full API reference: endpoints, object fields, authentication, content tags vs. labels, rate limits, and pagination.

## MCP tool prefix

All Zendesk operations — Help Center content and theme management — use tools prefixed with `mcp__zendesk-guide__` (the server name declared in this plugin's `.mcp.json`).

## Environments

Two environments are supported. Each tool has a `target` parameter.

| Environment | Subdomain | `target` value | Write default? |
|---|---|---|---|
| Production | `{instance}.zendesk.com` | `"prod"` | No — must be explicit |
| Sandbox | `{instance}-sandbox.zendesk.com` | `"sandbox"` | **Yes — all write tools default here** |

### Environment defaults

| Tool type | Default `target` |
|---|---|
| Read tools (`list_*`, `get_*`, `search_*`, `find_*`, `export_*`, `label_report`) | `"prod"` |
| Write tools (`update_*`, `apply_*`, `bulk_apply_*`, `remove_*`, `bulk_remove_*`, `add_*`, `bulk_add_*`, `delete_*`, `create_*`, `get_or_create_*`) | `"sandbox"` |

### How to work in sandbox mode

Tell Claude: "We're working in sandbox today." For that session, pass `target="sandbox"` on read tools too so you see sandbox state rather than prod state.

### How to work in production mode

Tell Claude: "We're working in production." Claude will ask you to confirm before each write. Only after you confirm will it pass `target="prod"`.

## Authentication

All credentials — for Help Center content operations and theme management — are loaded from a single file at the plugin root: `.env` (see `.env.example`).

| Variable | Description |
|---|---|
| `ZENDESK_SUBDOMAIN` | Prod subdomain, e.g. `{instance}` |
| `ZENDESK_EMAIL` | Prod Zendesk account email |
| `ZENDESK_API_TOKEN` | Prod raw Zendesk API token |
| `ZENDESK_SANDBOX_SUBDOMAIN` | Sandbox subdomain, e.g. `{instance}-sandbox` |
| `ZENDESK_SANDBOX_CLIENT_ID` | Sandbox OAuth client unique identifier |
| `ZENDESK_SANDBOX_CLIENT_SECRET` | Sandbox OAuth client secret |

The MCP theme tools (`import_theme`, `publish_theme`, `export_theme`) use prod credentials (`ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN`) by default.

Sandbox theme deploys **are** supported but use OAuth (not Basic Auth) and require all three `ZENDESK_SANDBOX_*` variables. When the user asks to deploy a theme to sandbox, use the Bash tool to run the OAuth + Theming API flow directly (see the Sandbox theme deploy workflow below) rather than calling `import_theme`/`publish_theme`.

Sandbox article/tag/label tools use OAuth client credentials grant — Bearer token, auto-refreshed every 30 min. Sandbox tools will return a clear error if sandbox credentials have not been filled in.

---

## First-time setup

Work through these steps in order. All of them are required before any tool will work.

- [ ] Install the ai-content-toolkit plugin
- [ ] Locate the plugin directory and create `.env`
- [ ] Add prod credentials to `.env`
- [ ] Add sandbox credentials to `.env`
- [ ] Install Python dependencies
- [ ] Restart Claude Code
- [ ] (Optional) Install zcli for local theme preview

### Step 1 — Install the plugin

In Claude Code, run:

```
/plugin marketplace add cedar-ave/ai-content-toolkit
/plugin install ai-content-toolkit
```

If you already have the marketplace added and just need to pick up new changes:

```
/plugin marketplace update cedar-ave/ai-content-toolkit
```

### Step 2 — Create the `.env` file

The MCP servers read credentials from a single `.env` file at the plugin root that does **not** exist until you create it. If you installed via `/plugin install`, Claude Code caches the plugin under `~/.claude/plugins/cache/<marketplace>/ai-content-toolkit/`; find the exact path with `/plugin` → select the plugin → "Open plugin folder" (or see the path printed after install). If you're running the plugin from a local clone instead, the path is just the repo root.

Copy the template and fill in your values (see Steps 3 and 4):

```bash
cp .env.example .env
```

```bash
# .env
# Production ({instance}.zendesk.com) — Basic Auth
ZENDESK_SUBDOMAIN="{instance}"
ZENDESK_EMAIL="your.name@{instance}.com"
ZENDESK_API_TOKEN="your-api-token-here"

# Sandbox ({instance}-sandbox.zendesk.com) — OAuth client credentials
ZENDESK_SANDBOX_SUBDOMAIN="{instance}-sandbox"
ZENDESK_SANDBOX_CLIENT_ID="your-oauth-client-id"
ZENDESK_SANDBOX_CLIENT_SECRET="your-oauth-client-secret"
```

`.env` is git-ignored — never commit it. See `.env.example` at the repo root for every variable every MCP server in this plugin reads.

### Step 3 — Get your prod API token

1. Log into [{instance}.zendesk.com](https://{instance}.zendesk.com)
2. Click your avatar → **Profile**
3. In the left sidebar, click **API** → **Add API token**
4. Give it a label (e.g. "Claude Code"), copy the token — it is only shown once
5. Set `ZENDESK_API_TOKEN` in `.env` to that value
6. Set `ZENDESK_EMAIL` to the email address of the account you logged in as

### Step 4 — Get your sandbox OAuth credentials

The sandbox uses OAuth (not API tokens). You need to create an OAuth client in the sandbox admin panel.

1. Log into the **sandbox**: [{instance}-sandbox.zendesk.com](https://{instance}-sandbox.zendesk.com)
2. Go to **Admin Center** → **Apps and Integrations** → **Zendesk API** → **OAuth Clients**
3. Click **Add OAuth client**
4. Fill in:
   - **Client name**: anything (e.g. `claude-code`)
   - **Redirect URLs**: `https://localhost` (required but unused for client credentials)
5. Save — the page will show you the **client ID** and **client secret**
6. Set `ZENDESK_SANDBOX_CLIENT_ID` and `ZENDESK_SANDBOX_CLIENT_SECRET` in `.env`

> If an OAuth client already exists (e.g. `help_center_demo`), ask the team for the secret — it cannot be retrieved after creation, only regenerated.

### Step 5 — Install Python dependencies

Each MCP server in this plugin is a Python process. Install dependencies for all of them in one pass from the repo root:

```bash
pip3 install -r requirements.txt
```

If you see `ModuleNotFoundError` when using any tool, this step was missed.

### Step 6 — Restart Claude Code

The MCP server reads `.env` at startup, not on every call. After creating or editing `.env`, you must restart Claude Code for changes to take effect.

After restarting, verify the server is running by asking Claude: *"list all Zendesk sections"* — if it returns results, you're connected.

### Step 7 (optional) — Install zcli for local theme preview

`zcli` is the Zendesk CLI tool. It is **only** needed for `zcli themes:preview` (live local preview in the browser). It is **not** used for import, publish, or any other MCP tool.

```bash
npm install -g @zendesk/zcli
```

After installing, add your prod Zendesk account (browser login — run in your terminal, not in Claude Code):

```bash
zcli login -s {instance} -i
```

To verify your profiles:

```bash
zcli profiles:list
```

> **Note on sandbox preview:** `zcli themes:preview` targets whatever profile is active. A sandbox preview profile would be added with `zcli login -s {instance}-sandbox -i`, but this has not been tested — it is the command zcli's own help documents for adding a profile, but interactive browser OAuth against the sandbox subdomain may behave differently. If you need to preview against sandbox, try it and update this doc with what you find. For sandbox **import/publish** (not preview), zcli is not involved at all — that goes direct to the Theming API via OAuth (see Sandbox theme deploy workflow below).

---

## Content tags vs. labels

These are different things. Do not confuse them.

| | Content tags | Labels |
|---|---|---|
| API base | `/api/v2/guide/content_tags` | `/api/v2/help_center/articles/{id}/labels` |
| Stored on article as | `content_tag_ids` (array of ID strings) | `label_names` (array of name strings) |
| Applied by | Merging IDs into `content_tag_ids` via `PUT /articles/{id}` | `POST` to `/articles/{id}/labels` |
| Plan requirement | All plans | Professional and Enterprise only |
| Identified by | Opaque ID string (e.g. `01JYA6M8KH6ZQP5J7BR2SE57FX`) | Name string (e.g. `getting-started`) |

---

## Workflows

### Apply content tags to articles

1. For each tag name, call `get_or_create_content_tag(name, target=...)`:
   - Search: `GET /api/v2/guide/content_tags?filter[name_prefix]={name}`
   - Find exact match by case-insensitive name comparison
   - If not found, confirm tag name with user, then `POST /api/v2/guide/content_tags`
2. For each article, call `get_article(article_id, target=...)` to fetch existing `content_tag_ids`
3. Merge new tag IDs with existing (deduplicate)
4. Call `update_article(article_id, content_tag_ids=[...merged...], target=...)` — `PUT /api/v2/help_center/articles/{id}` with `{ "article": { "content_tag_ids": [...] } }`
5. Report which articles were updated and which already had all tags (skipped)

### Apply labels to articles

1. For each article, call `add_article_label(article_id, label_name, target=...)`:
   - `POST /api/v2/help_center/articles/{article_id}/labels` with `{ "label": { "name": "..." } }`
   - Posting an existing label is a no-op — no duplicate check needed
2. Report results

### Look up articles by section

```
GET /api/v2/help_center/sections/{section_id}/articles
```

Returns all articles in the section with `id`, `title`, `html_url`. Paginate if `next_page` is present.

### Look up a Zendesk article by Paligo UUID

Used when you know the Paligo document UUID but not the Zendesk article ID. See `references/zendesk-api.md` — **Locating a Zendesk article by Paligo UUID** for the full body-scan procedure.

1. Ask the user for the target section ID (or list sections to find it)
2. List all articles in the section
3. Fetch each article body and search for `data-zd-article="{PALIGO_UUID}"`
4. Return the matched Zendesk article ID

---

## Available MCP tools

All tools accept a `target` parameter (`"prod"` or `"sandbox"`). See defaults in the Environments section above.

| Tool | Write? | Default target | Description |
|---|---|---|---|
| `list_categories()` | No | prod | List all Help Center categories |
| `get_category(category_id)` | No | prod | Get category details |
| `list_sections(category_id?)` | No | prod | List sections, optionally filtered by category |
| `get_section(section_id)` | No | prod | Get section details |
| `list_articles(section_id?)` | No | prod | List articles, optionally filtered by section |
| `get_article(article_id)` | No | prod | Get full article including body HTML and current tag/label state |
| `create_article(section_id, title, body?, draft?, locale?)` | **Yes** | **sandbox** | Create a new article in a section (draft by default) |
| `update_article(article_id, content_tag_ids?, label_names?, title?, draft?)` | **Yes** | **sandbox** | Update article metadata |
| `search_articles(query, section?, label_names?)` | No | prod | Search articles by text and filters |
| `export_articles(section_id?, category_id?)` | No | prod | All articles enriched with section, category, and resolved content tag names |
| `find_untagged_articles(exclude_section_ids?)` | No | prod | Find articles with no content tags applied |
| `find_articles_by_label(label_name)` | No | prod | Find all articles with a specific label |
| `find_articles_by_content_tag(tag_name)` | No | prod | Find all articles that have a specific content tag applied |
| `find_article_by_paligo_uuid(section_id, paligo_uuid)` | No | prod | Locate a Zendesk article by scanning for a Paligo UUID in body HTML |
| `list_all_content_tags(name_prefix?)` | No | prod | List all content tags |
| `get_or_create_content_tag(name)` | **Yes** | **sandbox** | Find a content tag by exact name or create it |
| `apply_article_content_tags(article_id, tag_names)` | **Yes** | **sandbox** | Resolve tag names and merge onto an article |
| `bulk_apply_article_content_tags(article_ids, tag_names)` | **Yes** | **sandbox** | Apply content tags to multiple articles at once |
| `remove_article_content_tags(article_id, tag_ids)` | **Yes** | **sandbox** | Remove specific content tags from an article |
| `bulk_remove_article_content_tags(article_ids, tag_ids)` | **Yes** | **sandbox** | Remove content tags from multiple articles at once |
| `delete_content_tag(tag_id)` | **Yes** | **sandbox** | Delete a content tag globally (removes from all articles) |
| `list_redirect_rules()` | No | prod | List all redirect rules |
| `list_redirect_rules_enriched()` | No | prod | List all redirect rules with article titles and URLs resolved |
| `find_redirect_rule(redirect_from)` | No | prod | Find a redirect rule by its source path |
| `create_redirect_rule(from_article_id, to_article_id, status?)` | **Yes** | **sandbox** | Create a 301/302 redirect between two article IDs |
| `delete_redirect_rule(rule_id)` | **Yes** | **sandbox** | Delete a redirect rule by ID |
| `list_all_labels()` | No | prod | List every label defined across the Help Center |
| `label_report()` | No | prod | Label usage report |
| `list_article_labels(article_id)` | No | prod | List labels on a single article |
| `add_article_label(article_id, label_name)` | **Yes** | **sandbox** | Add a label to an article |
| `bulk_add_article_labels(article_ids, label_names)` | **Yes** | **sandbox** | Apply multiple labels to multiple articles |
| `bulk_remove_article_labels(article_ids, label_ids)` | **Yes** | **sandbox** | Remove multiple labels from multiple articles |
| `remove_article_label(article_id, label_id)` | **Yes** | **sandbox** | Remove a label from one article |
| `delete_label(label_id)` | **Yes** | **sandbox** | Delete a label globally — removes it from every article (irreversible) |
| `bulk_delete_labels(label_ids)` | **Yes** | **sandbox** | Delete multiple labels globally (irreversible) |

---

## Zendesk Theme

Use this section to edit the Help Center theme locally and deploy changes to Zendesk. The MCP theme tools target prod by default. Sandbox deploys use a separate OAuth flow (see below).

### Theme directory structure

```
zendesk-theme-flatrock/
├── manifest.json          # Theme metadata and settings variables
├── script.js              # Global JavaScript
├── style.css              # Global CSS
├── templates/             # Handlebars page templates (.hbs)
│   ├── article_page.hbs
│   ├── header.hbs
│   ├── footer.hbs
│   ├── home_page.hbs
│   ├── custom_pages/      # Custom page templates
│   └── ...
├── assets/                # JS, CSS, SVG, image assets
│   ├── paligo-zd.css
│   ├── custom.css
│   ├── config_*.json      # Category/page config files
│   └── ...
└── settings/              # Theme setting images and SVGs
```

### Standard theme workflow (prod)

```
# 1. Export current live theme from Zendesk
list_themes()                              → find the live theme ID (live: true)
export_theme(theme_id, destination_dir)   → download and extract to local directory

# 2. Edit local files
list_theme_files(theme_dir)               → see all files grouped by type
read_theme_file(theme_dir, path)          → read a specific file
write_theme_file(theme_dir, path, content) → write changes back

# 3. Remove any stale zip, then package
#    Any .zip files already in the theme directory should be deleted first —
#    zip_theme excludes them from the archive but they are noise.
Bash: rm {theme_dir}/*.zip 2>/dev/null
zip_theme(theme_dir)
#    Output lands one level UP from theme_dir: {theme_dir}/../theme.zip
#    Pass that path to import_theme.

# 4. Pre-flight: check theme slot limit
#    list_themes() again and count. If count >= 10, identify the oldest non-live,
#    non-Copenhagen theme by created_at, confirm with user, then delete_theme(id).
#    Never delete the Copenhagen theme. Never delete the live theme.

# 5. Deploy to prod
import_theme("{theme_dir}/../theme.zip")  → upload zip, returns new theme_id
publish_theme(theme_id)                   → make imported theme live (confirm first)

# 6. Cleanup
delete_theme(theme_id)                    → remove an old/unused theme (confirm first)
```

### Example prompts

Tell Claude what you want and it will run the remove-zip → zip → upload → publish sequence end to end:

> "Remove the old Archive.zip from the theme directory, zip the theme, upload it to sandbox, and make it live."

> "Deploy the local theme to production."

### Local theme directory

All theme file operations (`list_theme_files`, `read_theme_file`, `write_theme_file`, `zip_theme`) work against your local clone of the theme repo. Clone it if you haven't already:

```bash
git clone git@github.com:{instance}/zendesk-theme-flatrock.git
```

The local theme directory is `~/Source/zendesk-theme-flatrock` (see Safety rules above) — tell Claude if your clone lives elsewhere.

### Sandbox theme deploy workflow

The MCP `import_theme`/`publish_theme` tools use prod credentials. To deploy to sandbox, use the Bash tool to run the OAuth flow directly:

```python
import os, time, requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv("{plugin_root}/skills/zendesk-guide-pal/.env")

subdomain     = os.getenv("ZENDESK_SANDBOX_SUBDOMAIN")
client_id     = os.getenv("ZENDESK_SANDBOX_CLIENT_ID")
client_secret = os.getenv("ZENDESK_SANDBOX_CLIENT_SECRET")
brand_id      = "53983368476179"   # auto-fetched from /api/v2/brands.json on first run
base          = f"https://{subdomain}.zendesk.com"

# 1. OAuth token
r = requests.post(f"{base}/oauth/tokens",
    data={"grant_type": "client_credentials", "client_id": client_id,
          "client_secret": client_secret, "scope": "read write"},
    headers={"Accept": "application/json"})
token = r.json()["access_token"]
session = requests.Session()
session.headers.update({"Accept": "application/json", "Authorization": f"Bearer {token}",
                         "X-Zendesk-Request-Originator": "zcli themes:import"})

# 2. Create import job  ← correct endpoint (not /jobs)
job = session.post(f"{base}/api/v2/guide/theming/jobs/themes/imports",
    json={"job": {"attributes": {"brand_id": brand_id, "format": "zip"}}}).json()["job"]

# 3. Upload zip to presigned S3 URL (no auth required)
upload = job["data"]["upload"]
zip_bytes = open(zip_path, "rb").read()
fields = {k: (None, v) for k, v in upload["parameters"].items()}
fields["file"] = ("theme.zip", zip_bytes, "application/zip")
requests.post(upload["url"], files=fields).raise_for_status()

# 4. Poll job status  ← correct poll endpoint
while True:
    status = session.get(f"{base}/api/v2/guide/theming/jobs/{job['id']}").json()["job"]["status"]
    if status in ("completed", "failed"): break
    time.sleep(3)

# 5. Publish
theme_id = job["data"]["theme_id"]
session.post(f"{base}/api/v2/guide/theming/themes/{theme_id}/publish", json={})
```

**Pre-flight theme slot check (sandbox):** Before step 2, call `GET {base}/api/v2/guide/theming/themes` and count the themes. If count >= 10, identify the oldest non-live, non-Copenhagen theme by `created_at`, confirm with the user, then `DELETE {base}/api/v2/guide/theming/themes/{id}` before proceeding with the import. Never delete the Copenhagen theme. Never delete the live theme.

**Key endpoint note:** The import job endpoint is `/api/v2/guide/theming/jobs/themes/imports` — the older `/api/v2/guide/theming/jobs` returns 404 on sandbox.

### Local preview (zcli)

When the user asks to "launch a preview", "start preview", or similar, run these shell commands via Bash (Claude Code only — requires shell access):

```bash
kill $(lsof -ti :4567) 2>/dev/null
cd ~/Source/zendesk-theme-flatrock && zcli themes:preview
```

Wait ~5 seconds for "Ready" output, then open the preview:

```bash
open -a "Google Chrome" "https://{instance}.zendesk.com/hc/admin/local_preview/start"
```

> **Note:** `zcli themes:preview` uploads the local theme to Zendesk as part of startup (non-live draft). It does NOT publish or replace the live theme.

### Theme MCP tools

The local file tools (`list_theme_files`, `read_theme_file`, `write_theme_file`, `zip_theme`) operate only on local disk — no Zendesk API call is made. The remote tools (`list_themes`, `get_theme`, `export_theme`, `import_theme`, `publish_theme`, `delete_theme`) call the prod Theming API using Basic Auth. For sandbox deploys, use the Bash-based OAuth workflow above instead.

| Tool | Description |
|---|---|
| `list_themes()` | List all themes with id, name, version, live status |
| `get_theme(theme_id)` | Get details of a specific theme |
| `export_theme(theme_id, destination_dir)` | Download and extract a theme to a local directory |
| `list_theme_files(theme_dir)` | List all local theme files grouped by type |
| `read_theme_file(theme_dir, relative_path)` | Read contents of a local theme file |
| `write_theme_file(theme_dir, relative_path, content)` | Write content to a local theme file |
| `zip_theme(theme_dir, output_path?)` | Zip the local theme directory for upload |
| `import_theme(zip_path)` | Upload a theme zip to Zendesk — creates but does NOT publish |
| `publish_theme(theme_id)` | Publish a theme, replacing the current live theme |
| `delete_theme(theme_id)` | Delete a theme by ID (cannot delete live theme) |

---

## Troubleshooting

### Tools return auth errors

- Check that `.env` exists at the correct path and has no typos in variable names
- Restart Claude Code after any `.env` change — credentials are loaded at MCP server startup, not per-call
- Verify the API token is active: log into Zendesk → Profile → API and confirm the token appears

### Sandbox tools return errors

- Confirm all three `ZENDESK_SANDBOX_*` variables are set in `.env`
- OAuth client secrets cannot be retrieved after creation — if the secret is lost, regenerate it in the sandbox admin panel and update `.env`

### `ModuleNotFoundError: No module named 'requests'`

Run `pip3 install requests python-dotenv` and restart Claude Code.

### Theme import fails with 404

The Zendesk Theming API has two generations of import endpoints. The MCP uses the correct current endpoint (`/api/v2/guide/theming/jobs/themes/imports`). If you see 404, the old endpoint (`/api/v2/guide/theming/jobs`) was likely cached somewhere — fully restart Claude Code to pick up the latest MCP server code.

### `zcli themes:preview` fails

- Make sure the `{instance}` zcli profile is configured: `zcli profiles:list`
- If missing, run `zcli login -s {instance} -i` in your terminal (requires browser)
- Port 4567 must be free: `kill $(lsof -ti :4567) 2>/dev/null`
- **Sandbox preview via zcli is untested.** `zcli themes:preview` is only known to work against the prod profile. For sandbox deploys, use the OAuth + Theming API flow — zcli is not needed.
