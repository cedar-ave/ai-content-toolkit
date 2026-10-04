"""
Zendesk Help Center MCP server.

Covers: articles, sections, categories, content tags, labels, article search, redirect rules, and theming actions.

Supports two environments:
  - prod    ({instance}.zendesk.com) — write tools require target="prod" explicitly
  - sandbox ({instance}-sandbox.zendesk.com) — write tools default here for safety
"""

import base64
import io
import json
import logging
import os
from pathlib import Path
import zipfile

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / "../.env"  # repo root .env — see .env.example
load_dotenv(ENV_FILE)

_prod_subdomain = os.getenv("ZENDESK_SUBDOMAIN", "")
_prod_email = os.getenv("ZENDESK_EMAIL", "")
_prod_token = os.getenv("ZENDESK_API_TOKEN", "")
_prod_creds = base64.b64encode(f"{_prod_email}/token:{_prod_token}".encode()).decode()

_sandbox_subdomain = os.getenv("ZENDESK_SANDBOX_SUBDOMAIN", "")
_sandbox_client_id = os.getenv("ZENDESK_SANDBOX_CLIENT_ID", "")
_sandbox_client_secret = os.getenv("ZENDESK_SANDBOX_CLIENT_SECRET", "")

_CONFIGS: dict = {
    "prod": {
        "hc": f"https://{_prod_subdomain}.zendesk.com/api/v2/help_center",
        "guide": f"https://{_prod_subdomain}.zendesk.com/api/v2/guide",
        "subdomain": _prod_subdomain,
        "auth_type": "basic",
        "configured": bool(_prod_subdomain and _prod_email and _prod_token),
    },
    "sandbox": {
        "hc": f"https://{_sandbox_subdomain}.zendesk.com/api/v2/help_center",
        "guide": f"https://{_sandbox_subdomain}.zendesk.com/api/v2/guide",
        "subdomain": _sandbox_subdomain,
        "auth_type": "oauth",
        "configured": bool(_sandbox_subdomain and _sandbox_client_id and _sandbox_client_secret),
    },
}

# OAuth token cache for sandbox: (access_token, expiry_epoch)
import time
_oauth_cache: dict[str, tuple[str, float]] = {}


def _get_oauth_token(subdomain: str, client_id: str, client_secret: str) -> str:
    """Return a valid OAuth access token, fetching a new one if expired."""
    cached = _oauth_cache.get(subdomain)
    if cached:
        token, expiry = cached
        if time.time() < expiry - 60:  # 60s buffer before expiry
            return token

    r = requests.post(
        f"https://{subdomain}.zendesk.com/oauth/tokens",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "read write",
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 1800)
    _oauth_cache[subdomain] = (token, time.time() + expires_in)
    return token

logging.basicConfig(level=logging.WARNING)


def _require_env(target: str) -> dict:
    """Return config for target, raising a clear error if not configured."""
    if target not in _CONFIGS:
        raise ValueError(f"Unknown target '{target}'. Must be 'prod' or 'sandbox'.")
    cfg = _CONFIGS[target]
    if not cfg["configured"]:
        raise ValueError(
            f"Zendesk {target} environment is not configured. "
            f"Add ZENDESK_SANDBOX_SUBDOMAIN, ZENDESK_SANDBOX_EMAIL, and "
            f"ZENDESK_SANDBOX_API_TOKEN (or ZENDESK_SANDBOX_PASSWORD) to "
            f"skills/zendesk-guide-pal/.env."
        )
    return cfg


# ---------------------------------------------------------------------------
# HTTP client helpers (all accept target: str)
# ---------------------------------------------------------------------------

def _session(target: str) -> requests.Session:
    cfg = _require_env(target)
    if cfg["auth_type"] == "oauth":
        auth_header = f"Bearer {_get_oauth_token(_sandbox_subdomain, _sandbox_client_id, _sandbox_client_secret)}"
    else:
        auth_header = f"Basic {_prod_creds}"
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    })
    return s


def _url(target: str, base_key: str, path: str) -> str:
    return _CONFIGS[target][base_key] + path


def _get(target: str, base_key: str, path: str, params: dict = None) -> dict:
    r = _session(target).get(_url(target, base_key, path), params=params)
    r.raise_for_status()
    return r.json()


def _post(target: str, base_key: str, path: str, body: dict) -> dict:
    r = _session(target).post(_url(target, base_key, path), json=body)
    r.raise_for_status()
    return r.json()


def _put(target: str, base_key: str, path: str, body: dict) -> dict:
    r = _session(target).put(_url(target, base_key, path), json=body)
    r.raise_for_status()
    return r.json()


def _delete(target: str, base_key: str, path: str) -> dict:
    r = _session(target).delete(_url(target, base_key, path))
    r.raise_for_status()
    return {"status": "deleted"}


def _paginate(target: str, base_key: str, path: str, params: dict = None, root_key: str = None) -> list:
    """Fetch all pages of an offset-paginated list endpoint."""
    params = params or {}
    results = []
    url = _url(target, base_key, path)
    session = _session(target)
    while url:
        r = session.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        key = root_key or next((k for k in data if isinstance(data[k], list)), None)
        if key:
            results.extend(data[key])
        url = data.get("next_page")
        params = {}
    return results


def _paginate_cursor(target: str, base_key: str, path: str, records_key: str = "records") -> list:
    """Fetch all pages of a cursor-paginated endpoint (Guide API style)."""
    results = []
    url = _url(target, base_key, path)
    session = _session(target)
    params: dict = {}
    while True:
        r = session.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get(records_key, []))
        meta = data.get("meta", {})
        if meta.get("has_more") and meta.get("after_cursor"):
            params = {"page[after]": meta["after_cursor"]}
        else:
            break
    return results


def _tag(data: dict | list | str, target: str) -> str:
    """Inject _environment into response so the caller always knows which env was hit."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return json.dumps({"_environment": target, "response": data}, indent=2)
    if isinstance(data, dict):
        data["_environment"] = target
        return json.dumps(data, indent=2)
    # list
    return json.dumps({"_environment": target, "results": data}, indent=2)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("zendesk")


# --- Categories ---

@mcp.tool()
def list_categories(target: str = "prod") -> str:
    """List all Help Center categories.

    target: 'prod' (default) or 'sandbox'
    """
    results = _paginate(target, "hc", "/categories", root_key="categories")
    return _tag(results, target)


@mcp.tool()
def get_category(category_id: str, target: str = "prod") -> str:
    """Get details of a Help Center category by ID.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_get(target, "hc", f"/categories/{category_id}"), target)


# --- Sections ---

@mcp.tool()
def list_sections(category_id: str = "", target: str = "prod") -> str:
    """List Help Center sections. Optionally filter by category_id.

    target: 'prod' (default) or 'sandbox'
    """
    path = f"/categories/{category_id}/sections" if category_id else "/sections"
    results = _paginate(target, "hc", path, root_key="sections")
    return _tag(results, target)


@mcp.tool()
def get_section(section_id: str, target: str = "prod") -> str:
    """Get details of a Help Center section by ID.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_get(target, "hc", f"/sections/{section_id}"), target)


# --- Articles ---

@mcp.tool()
def list_articles(section_id: str = "", target: str = "prod") -> str:
    """List Help Center articles. Optionally filter by section_id.

    target: 'prod' (default) or 'sandbox'
    """
    path = f"/sections/{section_id}/articles" if section_id else "/articles"
    results = _paginate(target, "hc", path, root_key="articles")
    return _tag(results, target)


@mcp.tool()
def get_article(article_id: str, target: str = "prod") -> str:
    """Get a Help Center article by ID, including full body HTML.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_get(target, "hc", f"/articles/{article_id}"), target)


@mcp.tool()
def create_article(section_id: str, title: str, body: str = "", draft: bool = True,
                   locale: str = "en-us", target: str = "sandbox") -> str:
    """Create a new Help Center article in a given section.

    section_id: ID of the section to create the article in.
    title: article headline.
    body: HTML body content (optional, can be added later).
    draft: True (default) to create as draft; False to publish immediately.
    locale: language/region code (default 'en-us').
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    payload = {
        "article": {
            "title": title,
            "body": body,
            "draft": draft,
            "locale": locale,
        }
    }
    return _tag(_post(target, "hc", f"/sections/{section_id}/articles", payload), target)


@mcp.tool()
def update_article(article_id: str, content_tag_ids: list = None, label_names: list = None,
                   title: str = "", draft: bool = None, target: str = "sandbox") -> str:
    """Update a Help Center article's metadata.

    content_tag_ids: full replacement list — always fetch existing IDs and merge before calling this.
    label_names: full replacement list of label name strings.
    title: new article title (optional).
    draft: True to set as draft, False to publish (optional).
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    body: dict = {}
    if content_tag_ids is not None:
        body["content_tag_ids"] = content_tag_ids
    if label_names is not None:
        body["label_names"] = label_names
    if title:
        body["title"] = title
    if draft is not None:
        body["draft"] = draft
    return _tag(_put(target, "hc", f"/articles/{article_id}", {"article": body}), target)


@mcp.tool()
def search_articles(query: str, section_id: str = "", label_names: str = "",
                    locale: str = "", sort_by: str = "", target: str = "prod") -> str:
    """Search Help Center articles by text query, enriched with section and category names.

    label_names: comma-separated label names to filter by.
    sort_by: 'created_at', 'updated_at', or 'relevance'.
    target: 'prod' (default) or 'sandbox'

    Returns:
    - results: full enriched articles with section, category, and label info
    - condensed: lightweight list of {id, html_url, title} for quick reference
    - count: total number of matching articles
    """
    params: dict = {"query": query}
    if section_id:
        params["section"] = section_id
    if label_names:
        params["label_names"] = label_names
    if locale:
        params["locale"] = locale
    if sort_by:
        params["sort_by"] = sort_by

    categories = _paginate(target, "hc", "/categories", root_key="categories")
    category_map = {c["id"]: c["name"] for c in categories}

    sections = _paginate(target, "hc", "/sections", root_key="sections")
    section_map = {s["id"]: {"name": s["name"], "category_id": s["category_id"]} for s in sections}

    articles = _paginate(target, "hc", "/articles/search", params=params, root_key="results")

    enriched = []
    for a in articles:
        sec = section_map.get(a.get("section_id"), {})
        cat_id = sec.get("category_id")
        enriched.append({
            "id": a["id"],
            "title": a.get("title"),
            "html_url": a.get("html_url"),
            "section": sec.get("name", "N/A"),
            "section_id": a.get("section_id"),
            "category": category_map.get(cat_id, "N/A") if cat_id else "N/A",
            "category_id": cat_id,
            "label_names": a.get("label_names", []),
            "draft": a.get("draft"),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
        })

    condensed = [{"id": a["id"], "html_url": a["html_url"], "title": a["title"]} for a in enriched]

    return _tag({"count": len(enriched), "results": enriched, "condensed": condensed}, target)


@mcp.tool()
def find_articles_by_label(label_name: str, target: str = "prod") -> str:
    """Find all articles that have a specific label, enriched with section and category names.

    target: 'prod' (default) or 'sandbox'
    """
    categories = _paginate(target, "hc", "/categories", root_key="categories")
    category_map = {c["id"]: c["name"] for c in categories}

    sections = _paginate(target, "hc", "/sections", root_key="sections")
    section_map = {s["id"]: {"name": s["name"], "category_id": s["category_id"]} for s in sections}

    articles = _paginate(target, "hc", "/articles/search",
                         params={"label_names": label_name}, root_key="results")

    enriched = []
    for a in articles:
        sec = section_map.get(a.get("section_id"), {})
        cat_id = sec.get("category_id")
        enriched.append({
            "id": a["id"],
            "title": a["title"],
            "html_url": a["html_url"],
            "section": sec.get("name", "N/A"),
            "section_id": a.get("section_id"),
            "category": category_map.get(cat_id, "N/A") if cat_id else "N/A",
            "category_id": cat_id,
            "labels": a.get("label_names", []),
        })

    return _tag({
        "label": label_name,
        "count": len(enriched),
        "articles": enriched,
        "ids": [a["id"] for a in enriched],
    }, target)


@mcp.tool()
def find_article_by_paligo_uuid(section_id: str, paligo_uuid: str, target: str = "prod") -> str:
    """Scan articles in a section to find the one containing a specific Paligo UUID.

    Fetches each article's body HTML and searches for data-zd-article="{paligo_uuid}".
    target: 'prod' (default) or 'sandbox'
    """
    articles = _paginate(target, "hc", f"/sections/{section_id}/articles", root_key="articles")
    for stub in articles:
        article_id = stub["id"]
        full = _get(target, "hc", f"/articles/{article_id}")
        article = full.get("article", {})
        body_html = article.get("body", "")
        if f'data-zd-article="{paligo_uuid}"' in body_html:
            return _tag({
                "found": True,
                "article_id": article["id"],
                "title": article["title"],
                "html_url": article["html_url"],
            }, target)
    return _tag({"found": False, "paligo_uuid": paligo_uuid, "section_id": section_id}, target)


@mcp.tool()
def find_untagged_articles(exclude_section_ids: list = None, target: str = "prod") -> str:
    """Find all articles that have no content tags applied.

    exclude_section_ids: list of section IDs (integers or strings) to skip.
    target: 'prod' (default) or 'sandbox'
    """
    exclude = set(str(i) for i in (exclude_section_ids or []))

    categories = _paginate(target, "hc", "/categories", root_key="categories")
    category_map = {c["id"]: c["name"] for c in categories}

    sections = _paginate(target, "hc", "/sections", root_key="sections")
    section_map = {s["id"]: {"name": s["name"], "category_id": s["category_id"]} for s in sections}

    articles = _paginate(target, "hc", "/articles", root_key="articles")

    untagged = []
    for a in articles:
        section_id = a.get("section_id")
        if str(section_id) in exclude:
            continue
        if not a.get("content_tag_ids"):
            sec = section_map.get(section_id, {})
            cat_id = sec.get("category_id")
            untagged.append({
                "id": a["id"],
                "title": a["title"],
                "html_url": a["html_url"],
                "section": sec.get("name", "N/A"),
                "section_id": section_id,
                "category": category_map.get(cat_id, "N/A") if cat_id else "N/A",
                "category_id": cat_id,
            })

    return _tag({
        "total_articles_checked": len(articles),
        "excluded_sections": len(exclude),
        "untagged_count": len(untagged),
        "untagged": untagged,
    }, target)


@mcp.tool()
def find_articles_by_content_tag(tag_name: str, target: str = "prod") -> str:
    """Find all articles that have a specific content tag applied.

    Resolves the tag by exact name (case-insensitive), then filters articles.
    target: 'prod' (default) or 'sandbox'
    """
    path = f"/content_tags?filter[name_prefix]={requests.utils.quote(tag_name)}"
    tags = _paginate_cursor(target, "guide", path)
    match = next((t for t in tags if t["name"].lower() == tag_name.lower()), None)
    if not match:
        return _tag({"error": f"No content tag found with name: {tag_name}"}, target)

    tag_id = match["id"]
    tag_map = {t["id"]: t["name"] for t in _paginate_cursor(target, "guide", "/content_tags")}

    categories = _paginate(target, "hc", "/categories", root_key="categories")
    category_map = {c["id"]: c["name"] for c in categories}

    sections = _paginate(target, "hc", "/sections", root_key="sections")
    section_map = {s["id"]: {"name": s["name"], "category_id": s["category_id"]} for s in sections}

    articles = _paginate(target, "hc", "/articles", root_key="articles")

    matched = []
    for a in articles:
        if tag_id in (a.get("content_tag_ids") or []):
            sec = section_map.get(a.get("section_id"), {})
            cat_id = sec.get("category_id")
            content_tags = [
                {"content_tag_name": tag_map.get(t_id, t_id), "content_tag_id": t_id}
                for t_id in (a.get("content_tag_ids") or [])
            ]
            matched.append({
                "id": a["id"],
                "title": a["title"],
                "html_url": a["html_url"],
                "section": sec.get("name", "N/A"),
                "section_id": a.get("section_id"),
                "category": category_map.get(cat_id, "N/A") if cat_id else "N/A",
                "category_id": cat_id,
                "content_tags": content_tags,
                "label_names": a.get("label_names", []),
            })

    return _tag({
        "content_tag": {"id": tag_id, "name": match["name"]},
        "count": len(matched),
        "articles": matched,
        "ids": [a["id"] for a in matched],
    }, target)


# --- Content Tags ---

@mcp.tool()
def list_all_content_tags(name_prefix: str = "", target: str = "prod") -> str:
    """List all Guide content tags, fully paginated. Optionally filter by name prefix.

    target: 'prod' (default) or 'sandbox'
    """
    path = "/content_tags"
    if name_prefix:
        path += f"?filter[name_prefix]={requests.utils.quote(name_prefix)}"
    tags = _paginate_cursor(target, "guide", path)
    return _tag(tags, target)


@mcp.tool()
def export_articles(section_id: str = "", category_id: str = "", target: str = "prod") -> str:
    """Export all Help Center articles enriched with section name, category name,
    and resolved content tag names.

    Optionally scope to a section or category. Returns two lists:
    - 'articles': full enriched article objects
    - 'condensed': lightweight list of {id, html_url, title} for quick reference

    target: 'prod' (default) or 'sandbox'
    """
    categories = _paginate(target, "hc", "/categories", root_key="categories")
    category_map = {c["id"]: c["name"] for c in categories}

    sections = _paginate(target, "hc", "/sections", root_key="sections")
    section_map = {s["id"]: {"name": s["name"], "category_id": s["category_id"]} for s in sections}

    tags = _paginate_cursor(target, "guide", "/content_tags")
    tag_map = {t["id"]: t["name"] for t in tags}

    if section_id:
        path = f"/sections/{section_id}/articles"
    elif category_id:
        path = f"/categories/{category_id}/articles"
    else:
        path = "/articles"
    articles = _paginate(target, "hc", path, root_key="articles")

    enriched = []
    for a in articles:
        sec = section_map.get(a.get("section_id"), {})
        cat_id = sec.get("category_id")
        content_tags = [
            {"content_tag_name": tag_map.get(t_id, f"Unknown ({t_id})"), "content_tag_id": t_id}
            for t_id in (a.get("content_tag_ids") or [])
        ]
        enriched.append({
            "id": a["id"],
            "url": a.get("url"),
            "html_url": a.get("html_url"),
            "title": a.get("title"),
            "section": sec.get("name", "N/A"),
            "section_id": a.get("section_id"),
            "category": category_map.get(cat_id, "N/A") if cat_id else "N/A",
            "category_id": cat_id,
            "locale": a.get("locale"),
            "author_id": a.get("author_id"),
            "draft": a.get("draft"),
            "promoted": a.get("promoted"),
            "label_names": a.get("label_names", []),
            "content_tag_names": content_tags,
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
            "edited_at": a.get("edited_at"),
        })

    condensed = [{"id": a["id"], "html_url": a["html_url"], "title": a["title"]} for a in enriched]
    return _tag({"articles": enriched, "condensed": condensed}, target)


@mcp.tool()
def remove_article_content_tags(article_id: str, tag_ids: list, target: str = "sandbox") -> str:
    """Remove one or more content tags from an article by tag ID.

    Fetches current content_tag_ids, filters out the specified IDs, and writes back.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    article_data = _get(target, "hc", f"/articles/{article_id}")
    article = article_data.get("article", {})
    current_ids = set(article.get("content_tag_ids") or [])
    remove_set = set(tag_ids)

    updated_ids = [t for t in current_ids if t not in remove_set]
    removed = [t for t in current_ids if t in remove_set]

    if not removed:
        return _tag({
            "article_id": article_id,
            "status": "skipped",
            "message": "None of the specified tags were present on this article",
            "content_tag_ids": list(current_ids),
        }, target)

    updated = _put(target, "hc", f"/articles/{article_id}", {"article": {"content_tag_ids": updated_ids}})
    updated_article = updated.get("article", {})
    return _tag({
        "article_id": article_id,
        "status": "updated",
        "tags_removed": removed,
        "content_tag_ids": updated_article.get("content_tag_ids", updated_ids),
    }, target)


@mcp.tool()
def delete_content_tag(tag_id: str, target: str = "sandbox") -> str:
    """Delete a content tag by ID. Removes it from all articles it is applied to.

    Requires explicit user confirmation before calling — irreversible.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    result = _delete(target, "guide", f"/content_tags/{tag_id}")
    return _tag({"tag_id": tag_id, **result}, target)


@mcp.tool()
def get_or_create_content_tag(name: str, target: str = "sandbox") -> str:
    """Find a content tag by exact name (case-insensitive) or create it if not found.

    Returns the tag object with id and name.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    params = {"filter[name_prefix]": name}
    data = _get(target, "guide", "/content_tags", params)
    records = data.get("records", [])
    existing = next((t for t in records if t["name"].lower() == name.lower()), None)
    if existing:
        return _tag({"found": True, "id": existing["id"], "name": existing["name"]}, target)
    created = _post(target, "guide", "/content_tags", {"content_tag": {"name": name}})
    tag = created.get("content_tag", created)
    return _tag({"found": False, "created": True, "id": tag["id"], "name": tag["name"]}, target)


@mcp.tool()
def apply_article_content_tags(article_id: str, tag_names: list, target: str = "sandbox") -> str:
    """Apply one or more content tags to an article by name.

    Fetches existing content_tag_ids, resolves or creates each tag by name,
    merges, and writes back. Skips tags already present.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    tag_ids = []
    tag_results = []
    for name in tag_names:
        result = json.loads(get_or_create_content_tag(name, target=target))
        tag_ids.append(result["id"])
        tag_results.append(result)

    article_data = _get(target, "hc", f"/articles/{article_id}")
    article = article_data.get("article", {})
    existing_ids = set(article.get("content_tag_ids") or [])

    new_ids = [t for t in tag_ids if t not in existing_ids]
    if not new_ids:
        return _tag({
            "article_id": article_id,
            "status": "skipped",
            "message": "All specified content tags already present",
            "content_tag_ids": list(existing_ids),
        }, target)

    merged = list(existing_ids) + new_ids
    updated = _put(target, "hc", f"/articles/{article_id}", {"article": {"content_tag_ids": merged}})
    updated_article = updated.get("article", {})
    return _tag({
        "article_id": article_id,
        "status": "updated",
        "tags_added": new_ids,
        "content_tag_ids": updated_article.get("content_tag_ids", merged),
    }, target)


@mcp.tool()
def bulk_apply_article_content_tags(article_ids: list, tag_names: list, target: str = "sandbox") -> str:
    """Apply one or more content tags to multiple articles by tag name.

    Resolves (or creates) each tag by name once, then merges onto each article.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    resolved = []
    for name in tag_names:
        result = json.loads(get_or_create_content_tag(name, target=target))
        resolved.append(result)
    tag_ids = [r["id"] for r in resolved]

    results = []
    for article_id in article_ids:
        try:
            article_data = _get(target, "hc", f"/articles/{article_id}")
            article = article_data.get("article", {})
            existing_ids = set(article.get("content_tag_ids") or [])
            new_ids = [t for t in tag_ids if t not in existing_ids]
            if not new_ids:
                results.append({"article_id": article_id, "status": "skipped", "tags_added": []})
                continue
            merged = list(existing_ids) + new_ids
            _put(target, "hc", f"/articles/{article_id}", {"article": {"content_tag_ids": merged}})
            results.append({"article_id": article_id, "status": "updated", "tags_added": new_ids})
        except Exception as e:
            results.append({"article_id": article_id, "status": "error", "error": str(e)})

    return _tag({
        "tags_resolved": resolved,
        "articles_processed": len(article_ids),
        "results": results,
    }, target)


@mcp.tool()
def bulk_remove_article_content_tags(article_ids: list, tag_ids: list, target: str = "sandbox") -> str:
    """Remove one or more content tags from multiple articles by tag ID.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    results = []
    remove_set = set(tag_ids)
    for article_id in article_ids:
        try:
            article_data = _get(target, "hc", f"/articles/{article_id}")
            article = article_data.get("article", {})
            current_ids = set(article.get("content_tag_ids") or [])
            removed = [t for t in current_ids if t in remove_set]
            if not removed:
                results.append({"article_id": article_id, "status": "skipped", "tags_removed": []})
                continue
            updated_ids = [t for t in current_ids if t not in remove_set]
            _put(target, "hc", f"/articles/{article_id}", {"article": {"content_tag_ids": updated_ids}})
            results.append({"article_id": article_id, "status": "updated", "tags_removed": removed})
        except Exception as e:
            results.append({"article_id": article_id, "status": "error", "error": str(e)})

    return _tag({
        "articles_processed": len(article_ids),
        "results": results,
    }, target)


# --- Labels ---

@mcp.tool()
def list_all_labels(target: str = "prod") -> str:
    """List all labels defined across the Help Center.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_get(target, "hc", "/articles/labels"), target)


@mcp.tool()
def label_report(target: str = "prod") -> str:
    """Generate a label usage report across all Help Center articles.

    Returns all labels and a distribution of how many articles have N labels.
    target: 'prod' (default) or 'sandbox'
    """
    labels_data = _get(target, "hc", "/articles/labels")
    all_labels = labels_data.get("labels", [])

    articles = _paginate(target, "hc", "/articles", root_key="articles")

    distribution: dict = {}
    for a in articles:
        count = len(a.get("label_names") or [])
        distribution[count] = distribution.get(count, 0) + 1

    sorted_distribution = [
        {"label_count": k, "article_count": v}
        for k, v in sorted(distribution.items())
    ]

    return _tag({
        "total_articles": len(articles),
        "total_unique_labels": len(all_labels),
        "all_labels": all_labels,
        "distribution": sorted_distribution,
    }, target)


@mcp.tool()
def list_article_labels(article_id: str, target: str = "prod") -> str:
    """List labels on a single Help Center article by article ID.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_get(target, "hc", f"/articles/{article_id}/labels"), target)


@mcp.tool()
def add_article_label(article_id: str, label_name: str, target: str = "sandbox") -> str:
    """Add a label to a Help Center article. No-op if the label already exists on the article.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    return _tag(
        _post(target, "hc", f"/articles/{article_id}/labels", {"label": {"name": label_name}}),
        target,
    )


@mcp.tool()
def bulk_add_article_labels(article_ids: list, label_names: list, target: str = "sandbox") -> str:
    """Apply one or more labels to one or more articles.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    results = []
    for article_id in article_ids:
        article_result = {"article_id": article_id, "applied": [], "errors": []}
        for label_name in label_names:
            try:
                _post(target, "hc", f"/articles/{article_id}/labels", {"label": {"name": label_name}})
                article_result["applied"].append(label_name)
            except Exception as e:
                article_result["errors"].append({"label": label_name, "error": str(e)})
        results.append(article_result)

    total_applied = sum(len(r["applied"]) for r in results)
    total_errors = sum(len(r["errors"]) for r in results)
    return _tag({
        "articles_processed": len(article_ids),
        "total_applied": total_applied,
        "total_errors": total_errors,
        "results": results,
    }, target)


@mcp.tool()
def delete_label(label_id: str, target: str = "sandbox") -> str:
    """Delete a label globally by ID. Removes it from every article it is applied to.

    Requires explicit user confirmation before calling — irreversible.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    result = _delete(target, "hc", f"/articles/labels/{label_id}")
    return _tag({"label_id": label_id, **result}, target)


@mcp.tool()
def bulk_delete_labels(label_ids: list, target: str = "sandbox") -> str:
    """Delete multiple labels globally by ID.

    Requires explicit user confirmation including all label IDs — irreversible.
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    results = []
    for label_id in label_ids:
        try:
            _delete(target, "hc", f"/articles/labels/{label_id}")
            results.append({"label_id": label_id, "status": "deleted"})
        except Exception as e:
            results.append({"label_id": label_id, "status": "error", "error": str(e)})

    return _tag({
        "total": len(label_ids),
        "deleted": sum(1 for r in results if r["status"] == "deleted"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }, target)


@mcp.tool()
def bulk_remove_article_labels(article_ids: list, label_ids: list, target: str = "sandbox") -> str:
    """Remove one or more labels from multiple articles by label ID.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    results = []
    for article_id in article_ids:
        article_result = {"article_id": article_id, "removed": [], "errors": []}
        for label_id in label_ids:
            try:
                _delete(target, "hc", f"/articles/{article_id}/labels/{label_id}")
                article_result["removed"].append(label_id)
            except Exception as e:
                article_result["errors"].append({"label_id": label_id, "error": str(e)})
        results.append(article_result)

    total_removed = sum(len(r["removed"]) for r in results)
    total_errors = sum(len(r["errors"]) for r in results)
    return _tag({
        "articles_processed": len(article_ids),
        "total_removed": total_removed,
        "total_errors": total_errors,
        "results": results,
    }, target)


@mcp.tool()
def remove_article_label(article_id: str, label_id: str, target: str = "sandbox") -> str:
    """Remove a label from a Help Center article by label ID.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    result = _delete(target, "hc", f"/articles/{article_id}/labels/{label_id}")
    return _tag({"article_id": article_id, "label_id": label_id, **result}, target)


# --- Redirect Rules ---

@mcp.tool()
def list_redirect_rules(target: str = "prod") -> str:
    """List all redirect rules defined in the Help Center, fully paginated.

    target: 'prod' (default) or 'sandbox'
    """
    return _tag(_paginate_cursor(target, "guide", "/redirect_rules"), target)


@mcp.tool()
def find_redirect_rule(redirect_from: str, target: str = "prod") -> str:
    """Find a redirect rule by its redirect_from path.

    redirect_from: source path, e.g. '/hc/en-us/articles/12345'
    target: 'prod' (default) or 'sandbox'
    """
    rules = _paginate_cursor(target, "guide", "/redirect_rules")
    match = next((r for r in rules if r.get("redirect_from") == redirect_from), None)
    if match:
        return _tag({"found": True, "rule": match}, target)
    return _tag({"found": False, "redirect_from": redirect_from}, target)


@mcp.tool()
def create_redirect_rule(from_article_id: str, to_article_id: str, status: int = 301,
                         target: str = "sandbox") -> str:
    """Create a redirect rule from one article URL to another.

    from_article_id: the article ID to redirect from
    to_article_id: the article ID to redirect to
    status: HTTP redirect status code (default 301)
    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).

    Constructs paths as /hc/en-us/articles/{id} automatically.
    """
    payload = {
        "redirect_rule": {
            "redirect_from": f"/hc/en-us/articles/{from_article_id}",
            "redirect_to": f"/hc/en-us/articles/{to_article_id}",
            "redirect_status": status,
        }
    }
    result = _post(target, "guide", "/redirect_rules", payload)
    return _tag(result, target)


@mcp.tool()
def list_redirect_rules_enriched(target: str = "prod") -> str:
    """List all redirect rules enriched with article titles where resolvable.

    target: 'prod' (default) or 'sandbox'
    """
    import re

    rules = _paginate_cursor(target, "guide", "/redirect_rules")

    def extract_article_id(path: str):
        m = re.search(r"/articles/(\d+)", path or "")
        return m.group(1) if m else None

    def resolve_article(article_id: str):
        if not article_id:
            return None, None
        try:
            data = _get(target, "hc", f"/articles/{article_id}")
            a = data.get("article", {})
            return a.get("title"), a.get("html_url")
        except Exception:
            return None, None

    enriched = []
    for rule in rules:
        from_path = rule.get("redirect_from", "")
        to_path = rule.get("redirect_to", "")
        from_id = extract_article_id(from_path)
        to_id = extract_article_id(to_path)
        from_title, from_url = resolve_article(from_id)
        to_title, to_url = resolve_article(to_id)
        enriched.append({
            "id": rule.get("id"),
            "redirect_status": rule.get("redirect_status"),
            "from_path": from_path,
            "from_article_id": from_id,
            "from_title": from_title,
            "from_url": from_url,
            "to_path": to_path,
            "to_article_id": to_id,
            "to_title": to_title,
            "to_url": to_url,
            "created_at": rule.get("created_at"),
            "updated_at": rule.get("updated_at"),
        })

    return _tag({"count": len(enriched), "rules": enriched}, target)


@mcp.tool()
def delete_redirect_rule(rule_id: str, target: str = "sandbox") -> str:
    """Delete a redirect rule by ID.

    target: 'sandbox' (default — safe) or 'prod' (requires explicit confirmation from user first).
    """
    result = _delete(target, "guide", f"/redirect_rules/{rule_id}")
    return _tag({"rule_id": rule_id, **result}, target)


# ---------------------------------------------------------------------------
# Theming API helpers (prod only — uses same _prod_creds)
# ---------------------------------------------------------------------------

THEMING_URL = f"https://{_prod_subdomain}.zendesk.com/api/v2/guide/theming"


def _theming_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Authorization": f"Basic {_prod_creds}",
    })
    return s


def _theming_get(path: str, params: dict = None) -> dict:
    r = _theming_session().get(f"{THEMING_URL}{path}", params=params or {})
    r.raise_for_status()
    return r.json()


def _theming_post_json(path: str, body: dict) -> dict:
    r = _theming_session().post(f"{THEMING_URL}{path}", json=body)
    r.raise_for_status()
    return r.json() if r.content else {}


def _theming_delete(path: str) -> str:
    r = _theming_session().delete(f"{THEMING_URL}{path}")
    r.raise_for_status()
    return json.dumps({"status": "deleted", "path": path}, indent=2)


def _theming_poll_job(job_id: str, timeout: int = 120, interval: int = 3) -> dict:
    """Poll /jobs/{job_id} — the general status endpoint used by all job types."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = _theming_get(f"/jobs/{job_id}")
        job = data.get("job", data)
        status = job.get("status", "").lower()
        if status in ("completed", "failed"):
            return job
        time.sleep(interval)
    return {"status": "timeout", "job_id": job_id}


def _theming_brand_id() -> str:
    """Return the first (usually only) brand ID for this Zendesk account."""
    r = _theming_session().get(f"https://{_prod_subdomain}.zendesk.com/api/v2/brands.json")
    r.raise_for_status()
    brands = r.json().get("brands", [])
    if not brands:
        raise ValueError("No brands found on this Zendesk account.")
    return str(brands[0]["id"])


# --- Themes ---

@mcp.tool()
def list_themes() -> str:
    """List all themes in the Zendesk Help Center.

    Returns id, name, version, author, live status, brand_id, created_at, updated_at.
    The live theme has live=true.
    """
    return json.dumps(_theming_get("/themes"), indent=2)


@mcp.tool()
def get_theme(theme_id: str) -> str:
    """Get details of a specific theme by ID."""
    return json.dumps(_theming_get(f"/themes/{theme_id}"), indent=2)


@mcp.tool()
def export_theme(theme_id: str, destination_dir: str) -> str:
    """Export a Zendesk theme to a local directory by downloading and extracting the zip.

    theme_id: the Zendesk theme ID to export.
    destination_dir: absolute path to the local directory where theme files will be written.
                     The directory will be created if it does not exist.

    Creates an async export job, polls until complete, downloads the zip, and
    extracts all files to destination_dir.
    """
    dest = Path(destination_dir)
    dest.mkdir(parents=True, exist_ok=True)

    job_data = _theming_post_json("/jobs/themes/exports", {
        "job": {"attributes": {"theme_id": theme_id, "format": "zip"}}
    })
    job_id = job_data.get("job", {}).get("id") or job_data.get("id")
    if not job_id:
        return json.dumps({"error": "No job ID returned", "response": job_data}, indent=2)

    job = _theming_poll_job(job_id)
    if job.get("status") != "completed":
        return json.dumps({"error": "Export job did not complete", "job": job}, indent=2)

    download_url = job.get("data", {}).get("download", {}).get("url")
    if not download_url:
        return json.dumps({"error": "No download URL in completed job", "job": job}, indent=2)

    r = _theming_session().get(download_url)
    r.raise_for_status()

    extracted = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        for name in zf.namelist():
            target_path = (dest / name).resolve()
            if not str(target_path).startswith(str(dest.resolve())):
                return json.dumps({
                    "error": f"Zip slip detected: entry '{name}' would extract outside destination",
                    "destination": str(dest),
                }, indent=2)
            zf.extract(name, dest)
            extracted.append(name)

    return json.dumps({
        "status": "exported",
        "theme_id": theme_id,
        "destination": str(dest),
        "files_extracted": len(extracted),
        "files": extracted,
    }, indent=2)


@mcp.tool()
def list_theme_files(theme_dir: str) -> str:
    """List all files in a local theme directory, grouped by type (templates, assets, settings, other).

    theme_dir: absolute path to the local theme directory.
    """
    root = Path(theme_dir)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {theme_dir}"}, indent=2)

    groups: dict = {"templates": [], "assets": [], "settings": [], "other": []}
    for f in sorted(root.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            rel = str(f.relative_to(root))
            if rel.startswith("templates/"):
                groups["templates"].append(rel)
            elif rel.startswith("assets/"):
                groups["assets"].append(rel)
            elif rel.startswith("settings/"):
                groups["settings"].append(rel)
            else:
                groups["other"].append(rel)

    return json.dumps({"theme_dir": theme_dir, "files": groups}, indent=2)


@mcp.tool()
def read_theme_file(theme_dir: str, relative_path: str) -> str:
    """Read the contents of a file in the local theme directory.

    theme_dir: absolute path to the local theme directory.
    relative_path: path relative to theme_dir, e.g. 'templates/article_page.hbs' or 'style.css'
    """
    root = Path(theme_dir).resolve()
    path = (root / relative_path).resolve()
    if not str(path).startswith(str(root)):
        return json.dumps({"error": f"Path traversal detected: '{relative_path}' resolves outside theme directory"}, indent=2)
    if not path.exists():
        return json.dumps({"error": f"File not found: {relative_path}"}, indent=2)
    if not path.is_file():
        return json.dumps({"error": f"Not a file: {relative_path}"}, indent=2)
    try:
        content = path.read_text(encoding="utf-8")
        return json.dumps({"relative_path": relative_path, "content": content}, indent=2)
    except UnicodeDecodeError:
        return json.dumps({"error": f"File is binary and cannot be read as text: {relative_path}"}, indent=2)


@mcp.tool()
def write_theme_file(theme_dir: str, relative_path: str, content: str) -> str:
    """Write content to a file in the local theme directory.

    theme_dir: absolute path to the local theme directory.
    relative_path: path relative to theme_dir, e.g. 'style.css' or 'templates/header.hbs'
    content: the full new content to write to the file. Overwrites existing file.
    """
    root = Path(theme_dir).resolve()
    path = (root / relative_path).resolve()
    if not str(path).startswith(str(root)):
        return json.dumps({"error": f"Path traversal detected: '{relative_path}' resolves outside theme directory"}, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return json.dumps({
        "status": "written",
        "relative_path": relative_path,
        "absolute_path": str(path),
        "bytes": len(content.encode("utf-8")),
    }, indent=2)


@mcp.tool()
def zip_theme(theme_dir: str, output_path: str = "") -> str:
    """Create a zip archive of a local theme directory for upload.

    theme_dir: absolute path to the local theme directory.
    output_path: absolute path for the output zip file. Defaults to theme_dir/../theme.zip

    Excludes .git, .DS_Store, and any existing .zip files.
    """
    root = Path(theme_dir)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {theme_dir}"}, indent=2)

    if not output_path:
        output_path = str(root.parent / "theme.zip")

    out = Path(output_path)
    included = []

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            if any(p.startswith(".") for p in rel.parts):
                continue
            if f.suffix == ".zip":
                continue
            zf.write(f, rel)
            included.append(str(rel))

    return json.dumps({
        "status": "zipped",
        "zip_path": str(out),
        "files_included": len(included),
        "files": included,
    }, indent=2)


@mcp.tool()
def import_theme(zip_path: str) -> str:
    """Upload a local theme zip to Zendesk as a new theme via an async import job.

    zip_path: absolute path to the theme zip file to upload.

    Creates an import job, uploads the zip to the presigned S3 URL, polls until complete,
    and returns the new theme ID. The imported theme is NOT published — call publish_theme() to go live.
    """
    zp = Path(zip_path)
    if not zp.exists():
        return json.dumps({"error": f"Zip file not found: {zip_path}"}, indent=2)

    brand_id = _theming_brand_id()
    job_data = _theming_post_json("/jobs/themes/imports", {
        "job": {"attributes": {"brand_id": brand_id, "format": "zip"}}
    })
    job = job_data.get("job", job_data)
    job_id = job.get("id")
    upload = job.get("data", {}).get("upload", {})
    upload_url = upload.get("url")
    upload_parameters = upload.get("parameters", {})

    if not job_id or not upload_url:
        return json.dumps({"error": "No upload URL returned from import job", "response": job_data}, indent=2)

    with open(zp, "rb") as f:
        zip_bytes = f.read()

    fields = {k: (None, v) for k, v in upload_parameters.items()}
    fields["file"] = (zp.name, zip_bytes, "application/zip")
    upload_r = requests.post(upload_url, files=fields)
    upload_r.raise_for_status()

    completed = _theming_poll_job(job_id)
    if completed.get("status") != "completed":
        return json.dumps({"error": "Import job did not complete", "job": completed}, indent=2)

    theme_id = completed.get("data", {}).get("theme_id") or completed.get("theme_id")
    return json.dumps({
        "status": "imported",
        "theme_id": theme_id,
        "job_id": job_id,
        "message": "Theme imported but not yet published. Call publish_theme(theme_id) to go live.",
    }, indent=2)


@mcp.tool()
def publish_theme(theme_id: str) -> str:
    """Publish a theme, making it the live theme in the Help Center.

    This replaces whatever theme is currently live. Confirm with the user before calling.
    """
    return json.dumps(_theming_post_json(f"/themes/{theme_id}/publish", {}), indent=2)


@mcp.tool()
def delete_theme(theme_id: str) -> str:
    """Delete a theme by ID. Cannot delete the currently live theme.

    Requires explicit user confirmation before calling.
    """
    return _theming_delete(f"/themes/{theme_id}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()