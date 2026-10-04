"""
Zendesk Tickets MCP server (read-only).

Covers: tickets, ticket comments, users, organizations, ticket fields,
ticket forms, views, satisfaction ratings, tags, and search.
"""

import base64
import datetime
import json
import logging
import os
import re
from urllib.parse import urlparse
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / "../.env"  # repo root .env — see .env.example
load_dotenv(ENV_FILE)

_subdomain = os.getenv("ZENDESK_SUBDOMAIN", "")
_email = os.getenv("ZENDESK_EMAIL", "")
_api_token = os.getenv("ZENDESK_API_TOKEN", "")

if not all([_subdomain, _email, _api_token]):
    raise EnvironmentError(
        "Missing Zendesk credentials. Set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, "
        f"and ZENDESK_API_TOKEN in {ENV_FILE}"
    )

# Credentials are loaded from a .env file and kept in memory for the lifetime of
# the process. Secure deployment requirements:
#   - The .env file must not be committed to version control.
#   - The process should run as a dedicated low-privilege service account.
#   - The API token should be a scoped Zendesk API token (not a full-access password).
#   - Rotate the token immediately if the .env file or process memory is compromised.
_credentials = base64.b64encode(f"{_email}/token:{_api_token}".encode()).decode()

BASE_URL = f"https://{_subdomain}.zendesk.com/api/v2"
_BASE_URL_PARSED = urlparse(BASE_URL)

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Named custom fields
# ---------------------------------------------------------------------------

# Map Zendesk custom field IDs to human-readable keys returned in ticket responses.
# Add entries here as new fields need to be surfaced.
_CUSTOM_FIELD_NAMES = {
    23470971413523: "{instance}_product_area",
    50879445468179: "ticket_category",
}

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    """Return a requests Session pre-configured with Zendesk auth headers."""
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Basic {_credentials}",
    })
    return s


def _get(path: str, params: dict = None) -> dict:
    """Make a single authenticated GET request and return the parsed JSON response."""
    r = _session().get(f"{BASE_URL}{path}", params=params)
    r.raise_for_status()
    return r.json()


def _paginate(path: str, root_key: str, params: dict = None, max_results: int = 0) -> list:
    """Fetch all pages of an offset-paginated Zendesk list endpoint.

    path: API path relative to BASE_URL (e.g. '/tickets')
    root_key: JSON key whose value is the list of records in each response (e.g. 'tickets')
    params: initial query parameters sent with the first request
    max_results: stop fetching once this many records have been collected (0 = no limit)
    """
    params = params or {}
    results = []
    url = f"{BASE_URL}{path}"
    while url:
        r = _session().get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get(root_key, []))
        if max_results and len(results) >= max_results:
            break
        next_page = data.get("next_page")
        # Validate next_page URL to prevent SSRF: check scheme and netloc, not just prefix,
        # to reject URLs like https://BASE_URL@attacker.com/path that pass startswith().
        if next_page:
            _np = urlparse(next_page)
            if _np.scheme == _BASE_URL_PARSED.scheme and _np.netloc == _BASE_URL_PARSED.netloc:
                url = next_page
                params = {}
            else:
                url = None
        else:
            url = None
    return results


# Safety cap for cursor-paginated endpoints.
# 50 pages × 100 results/page = 5,000 records max. Prevents runaway pagination on
# large accounts where an unbounded loop could exhaust memory or hit API rate limits.
_CURSOR_PAGE_LIMIT = 50

# Truncate ticket description previews in search/list results.
# 500 chars is enough to identify the issue without bloating responses — full text
# is available via get_ticket() when needed.
_DESCRIPTION_PREVIEW_CHARS = 500


def _paginate_cursor(path: str, root_key: str, params: dict = None, max_pages: int = _CURSOR_PAGE_LIMIT) -> list:
    """Fetch all pages of a cursor-paginated Zendesk endpoint (meta.has_more / after_cursor).

    path: API path relative to BASE_URL (e.g. '/satisfaction_ratings')
    root_key: JSON key whose value is the list of records in each response
    params: initial query parameters sent with the first request
    max_pages: hard cap on the number of pages fetched (default _CURSOR_PAGE_LIMIT = 50);
               a warning is logged if this cap is reached before exhausting the result set
    """
    params = dict(params or {})
    results = []
    url = f"{BASE_URL}{path}"
    pages = 1
    while url and pages <= max_pages:
        r = _session().get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get(root_key, []))
        meta = data.get("meta", {})
        if meta.get("has_more") and meta.get("after_cursor"):
            # Advance to the next page by passing the cursor as a query param.
            # We always re-use the original path (url is never reassigned) so
            # the cursor cannot redirect us to an untrusted host.
            params = {"page[after]": meta["after_cursor"]}
            pages += 1
        else:
            break
    else:
        # Loop exited because pages > max_pages, not because has_more was False.
        # Log so callers know results may be incomplete.
        logging.warning(
            "_paginate_cursor: hit %d-page cap on %s — results may be truncated",
            max_pages, path,
        )
    return results


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> datetime.datetime:
    """Parse an ISO 8601 date/datetime string into a timezone-aware UTC datetime.

    Accepts full datetime strings (e.g. '2024-01-15T10:30:00Z') and date-only
    strings (e.g. '2024-01-15'). Date-only strings are treated as midnight UTC.
    Raises ValueError with a descriptive message on unrecognised formats.
    """
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        # Fallback for date-only strings (e.g. '2024-01-01') which fromisoformat
        # rejects on Python < 3.11 when a time component is expected.
        try:
            dt = datetime.datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {s!r}. Use ISO 8601 (e.g. '2024-01-01' or '2024-01-01T00:00:00Z')")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _period_key(ts: str, by: str) -> str:
    """Return a grouping key string for a timestamp based on the requested granularity.

    ts: ISO 8601 timestamp string
    by: 'day' → 'YYYY-MM-DD', 'week' → 'YYYY-MM-DD' of the Monday, 'month' → 'YYYY-MM'
    """
    dt = _parse_date(ts)
    if by == "week":
        # ISO week start (Monday)
        start = dt - datetime.timedelta(days=dt.weekday())
        return start.strftime("%Y-%m-%d")
    if by == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


def _zd_quote(value: str) -> str:
    """Sanitize and quote a user-supplied Zendesk search value to prevent query injection.

    Strips characters that introduce Zendesk query operators or wildcards
    (`"`, `:`, `*`, `<`, `>`, `(`, `)`) and removes bare boolean keywords
    (`AND`, `OR`, `NOT`) that would change the query's logical scope.
    Values containing spaces are wrapped in double quotes so Zendesk treats
    them as a phrase rather than multiple tokens.
    """
    # Step 1: remove characters Zendesk uses as field operators or wildcards.
    # `:` introduces field qualifiers (e.g. `type:`), `*` is a wildcard,
    # `<`/`>` are range operators, `"` would break our own quoting, `()` group terms,
    # `\` is a Zendesk escape character that could be used to re-introduce operators.
    sanitized = re.sub(r'[":*<>()\\\\]', '', value)
    # Step 2: remove bare boolean keywords that change query scope or combine clauses.
    sanitized = re.sub(r'\b(AND|OR|NOT)\b', '', sanitized, flags=re.IGNORECASE).strip()
    # Step 3: wrap multi-word values in quotes so Zendesk matches them as a phrase.
    if ' ' in sanitized:
        return f'"{sanitized}"'
    return sanitized


def _strip_quoted_content(body: str) -> str:
    """Remove forwarded message blocks and quoted reply content from email bodies.

    Handles three common quoting patterns:
    - Forwarded message blocks starting with '---------- Forwarded message ---------'
    - Reply quote headers of the form 'On [date] ... wrote:'
    - Inline quoted lines prefixed with '>'
    """
    # Cut off at forwarded message separator
    body = re.split(r'-{5,}\s*Forwarded message\s*-{5,}', body, flags=re.IGNORECASE)[0]
    # Cut off at "On [date] ... wrote:" reply quote headers
    body = re.sub(r'\nOn .+?wrote:\s*$', '', body, flags=re.DOTALL)
    # Remove lines starting with > (inline quoted text)
    lines = [line for line in body.split('\n') if not line.strip().startswith('>')]
    return '\n'.join(lines).strip()


def _resolve_named_custom_fields(raw_fields: list) -> dict:
    """Extract only the named custom fields defined in _CUSTOM_FIELD_NAMES.

    Returns a dict of human-readable key → value for any field whose ID appears
    in _CUSTOM_FIELD_NAMES and whose value is not None.
    """
    resolved = {}
    for f in raw_fields:
        field_id = f.get("id")
        value = f.get("value")
        if field_id in _CUSTOM_FIELD_NAMES and value is not None:
            resolved[_CUSTOM_FIELD_NAMES[field_id]] = value
    return resolved


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("zendesk-tickets")


# --- Tickets ---

@mcp.tool()
def list_tickets(status: str = "", assignee_id: str = "", requester_id: str = "",
                 organization_id: str = "", tag: str = "", ticket_type: str = "",
                 priority: str = "", sort_by: str = "created_at",
                 sort_order: str = "desc", limit: int = 100) -> str:
    """List tickets with optional filters.

    status: 'new', 'open', 'pending', 'hold', 'solved', 'closed'
    assignee_id: Zendesk user ID of the assigned agent
    requester_id: Zendesk user ID of the ticket requester
    organization_id: Zendesk organization ID to scope results
    tag: single tag string; returns only tickets that include this tag
    ticket_type: 'question', 'incident', 'problem', 'task'
    priority: 'low', 'normal', 'high', 'urgent'
    sort_by: 'created_at', 'updated_at', 'priority', 'status', 'ticket_type'
    sort_order: 'asc' or 'desc'
    limit: max number of tickets to return (default 100, max 1000)

    Note: organization_id, requester_id, and assignee_id use dedicated API paths;
    status, tag, ticket_type, and priority are applied as in-memory filters after
    fetching. Only one of organization_id / requester_id / assignee_id is used
    (checked in that priority order).

    Example — open urgent tickets for an org:
        list_tickets(organization_id="123456", status="open", priority="urgent", limit=25)

    Returns tickets with id, subject, status, priority, type, requester_id,
    assignee_id, organization_id, tags, created_at, updated_at, and url.
    """
    params: dict = {
        "sort_by": sort_by,
        "sort_order": sort_order,
        "per_page": min(limit, 100),
    }

    # Build filter path
    if organization_id:
        path = f"/organizations/{organization_id}/tickets"
    elif requester_id:
        path = f"/users/{requester_id}/tickets/requested"
    elif assignee_id:
        path = f"/users/{assignee_id}/tickets/assigned"
    else:
        path = "/tickets"

    all_tickets = _paginate(path, "tickets", params, max_results=limit)

    # Apply in-memory filters (for fields not supported as query params on list endpoints)
    if status:
        all_tickets = [t for t in all_tickets if t.get("status") == status]
    if tag:
        all_tickets = [t for t in all_tickets if tag in (t.get("tags") or [])]
    if ticket_type:
        all_tickets = [t for t in all_tickets if t.get("type") == ticket_type]
    if priority:
        all_tickets = [t for t in all_tickets if t.get("priority") == priority]

    tickets = all_tickets[:limit]

    condensed = [{
        "id": t.get("id"),
        "subject": t.get("subject"),
        "status": t.get("status"),
        "priority": t.get("priority"),
        "type": t.get("type"),
        "requester_id": t.get("requester_id"),
        "assignee_id": t.get("assignee_id"),
        "organization_id": t.get("organization_id"),
        "tags": t.get("tags", []),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{t.get('id')}",
    } for t in tickets]

    return json.dumps({"count": len(condensed), "tickets": condensed}, indent=2)


@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Get key details of a single ticket by ID.

    Returns subject, status, priority, type, requester, assignee, organization,
    tags, timestamps, url, and the named custom fields {instance}_product_area
    and ticket_category (when set). All null custom fields are omitted.
    """
    data = _get(f"/tickets/{ticket_id}")
    ticket = data.get("ticket", data)

    result = {
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "type": ticket.get("type"),
        "requester_id": ticket.get("requester_id"),
        "assignee_id": ticket.get("assignee_id"),
        "organization_id": ticket.get("organization_id"),
        "tags": ticket.get("tags", []),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{ticket_id}",
        **_resolve_named_custom_fields(ticket.get("custom_fields") or ticket.get("fields", [])),
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_ticket_comments(ticket_id: str) -> str:
    """Get all comments (conversation thread) for a ticket.

    Returns each comment with id, author_id, public (true/false), created_at,
    and body (plain text only — html_body omitted, forwarded/quoted content stripped).
    """
    comments = _paginate(f"/tickets/{ticket_id}/comments", "comments")
    cleaned = []
    for c in comments:
        cleaned.append({
            "id": c.get("id"),
            "author_id": c.get("author_id"),
            "public": c.get("public"),
            "created_at": c.get("created_at"),
            "body": _strip_quoted_content(c.get("plain_body") or c.get("body", "")),
        })
    return json.dumps({"ticket_id": ticket_id, "count": len(cleaned), "comments": cleaned}, indent=2)


@mcp.tool()
def get_ticket_with_comments(ticket_id: str) -> str:
    """Get a ticket's key fields and its full comment thread in a single call.

    Combines get_ticket and get_ticket_comments to avoid two round trips.
    Returns subject, status, named custom fields ({instance}_product_area,
    ticket_category), and all comments as plain text with quoted content stripped.
    """
    ticket_data = _get(f"/tickets/{ticket_id}").get("ticket", {})
    comments_raw = _paginate(f"/tickets/{ticket_id}/comments", "comments")

    result = {
        "id": ticket_data.get("id"),
        "subject": ticket_data.get("subject"),
        "status": ticket_data.get("status"),
        "priority": ticket_data.get("priority"),
        "type": ticket_data.get("type"),
        "requester_id": ticket_data.get("requester_id"),
        "assignee_id": ticket_data.get("assignee_id"),
        "organization_id": ticket_data.get("organization_id"),
        "tags": ticket_data.get("tags", []),
        "created_at": ticket_data.get("created_at"),
        "updated_at": ticket_data.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{ticket_id}",
        **_resolve_named_custom_fields(ticket_data.get("custom_fields") or ticket_data.get("fields", [])),
        "comments": [
            {
                "id": c.get("id"),
                "author_id": c.get("author_id"),
                "public": c.get("public"),
                "created_at": c.get("created_at"),
                "body": _strip_quoted_content(c.get("plain_body") or c.get("body", "")),
            }
            for c in comments_raw
        ],
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def search_tickets(query: str, status: str = "", ticket_type: str = "",
                   priority: str = "", assignee: str = "", requester: str = "",
                   organization: str = "", tag: str = "",
                   created_after: str = "", created_before: str = "",
                   updated_after: str = "", updated_before: str = "",
                   sort_by: str = "", sort_order: str = "desc",
                   limit: int = 100) -> str:
    """Search tickets using Zendesk's unified search API.

    query: free-text search query (e.g. 'API error', 'login issue')
    status: filter by status (appended to query as 'status:X')
    ticket_type: filter by type (appended as 'type:X')
    priority: filter by priority (appended as 'priority:X')
    assignee: assignee email or name (appended as 'assignee:X')
    requester: requester email or name (appended as 'requester:X')
    organization: organization name (appended as 'organization:X')
    tag: tag to filter by (appended as 'tags:X')
    created_after / created_before: ISO 8601 date strings (e.g. '2024-01-01')
    updated_after / updated_before: ISO 8601 date strings
    sort_by: 'created_at', 'updated_at', 'priority', 'status'
    sort_order: 'asc' or 'desc'
    limit: max results to return (default 100)

    Returns enriched ticket results with agent URL.
    """
    _ALLOWED_STATUSES = {"new", "open", "pending", "hold", "solved", "closed"}
    _ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}
    _ALLOWED_TYPES = {"ticket", "problem", "incident", "question", "task"}
    _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    resolved_type = (ticket_type or "ticket").strip().lower()
    if resolved_type not in _ALLOWED_TYPES:
        resolved_type = "ticket"

    q = f"type:{resolved_type} {_zd_quote(query)}"
    if status:
        s = status.strip().lower()
        if s in _ALLOWED_STATUSES:
            q += f" status:{s}"
    if priority:
        p = priority.strip().lower()
        if p in _ALLOWED_PRIORITIES:
            q += f" priority:{p}"
    if assignee:
        q += f" assignee:{_zd_quote(assignee.strip())}"
    if requester:
        q += f" requester:{_zd_quote(requester.strip())}"
    if organization:
        q += f" organization:{_zd_quote(organization.strip())}"
    if tag:
        q += f" tags:{_zd_quote(tag.strip())}"
    if created_after and _DATE_RE.match(created_after.strip()):
        q += f" created>{created_after.strip()}"
    if created_before and _DATE_RE.match(created_before.strip()):
        q += f" created<{created_before.strip()}"
    if updated_after and _DATE_RE.match(updated_after.strip()):
        q += f" updated>{updated_after.strip()}"
    if updated_before and _DATE_RE.match(updated_before.strip()):
        q += f" updated<{updated_before.strip()}"

    params: dict = {"query": q, "per_page": 100}
    if sort_by:
        params["sort_by"] = sort_by
        params["sort_order"] = sort_order

    all_results = _paginate("/search", "results", params, max_results=limit)
    tickets = [r for r in all_results if r.get("result_type") == "ticket"][:limit]

    enriched = [{
        "id": t.get("id"),
        "subject": t.get("subject"),
        "description": t.get("description", "")[:_DESCRIPTION_PREVIEW_CHARS],
        "status": t.get("status"),
        "priority": t.get("priority"),
        "type": t.get("type"),
        "requester_id": t.get("requester_id"),
        "assignee_id": t.get("assignee_id"),
        "organization_id": t.get("organization_id"),
        "tags": t.get("tags", []),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{t.get('id')}",
    } for t in tickets]

    return json.dumps({"query": q, "count": len(enriched), "tickets": enriched}, indent=2)


@mcp.tool()
def get_ticket_metrics(ticket_id: str) -> str:
    """Get time-tracking and SLA metrics for a single ticket.

    Returns reply_time_in_minutes, first_resolution_time_in_minutes,
    full_resolution_time_in_minutes, agent_wait_time_in_minutes,
    requester_wait_time_in_minutes, on_hold_time_in_minutes, reopens,
    replies, assignee_updated_at, and solved_at.
    """
    return json.dumps(_get(f"/tickets/{ticket_id}/metrics"), indent=2)


@mcp.tool()
def list_ticket_fields() -> str:
    """List all ticket fields defined in the account.

    Returns each field's id, type, title, description, active status,
    and any custom field options (for dropdown/checkbox fields).
    """
    fields = _paginate("/ticket_fields", "ticket_fields")
    return json.dumps({"count": len(fields), "ticket_fields": fields}, indent=2)


@mcp.tool()
def list_ticket_forms() -> str:
    """List all ticket forms defined in the account.

    Returns each form's id, name, active status, default status,
    and the list of ticket_field_ids it contains.
    """
    forms = _paginate("/ticket_forms", "ticket_forms")
    return json.dumps({"count": len(forms), "ticket_forms": forms}, indent=2)


# --- Views ---

@mcp.tool()
def list_views() -> str:
    """List all ticket views defined in the account.

    Returns each view's id, title, active status, and conditions summary.
    Views are the saved filters agents use in the Zendesk UI.
    """
    views = _paginate("/views", "views")
    return json.dumps({"count": len(views), "views": views}, indent=2)


@mcp.tool()
def get_view(view_id: str) -> str:
    """Get details of a specific view by ID, including its conditions and columns."""
    return json.dumps(_get(f"/views/{view_id}"), indent=2)


@mcp.tool()
def execute_view(view_id: str, sort_by: str = "", sort_order: str = "asc") -> str:
    """Execute a view and return its current ticket results.

    Returns the tickets that currently match the view's conditions,
    with id, subject, status, priority, requester_id, assignee_id,
    tags, created_at, updated_at, and url.
    sort_by: field to sort by (optional, uses view default if omitted)
    sort_order: 'asc' or 'desc'
    """
    params: dict = {}
    if sort_by:
        params["sort_by"] = sort_by
        params["sort_order"] = sort_order
    tickets = _paginate(f"/views/{view_id}/tickets", "tickets", params)
    condensed = [{
        "id": t.get("id"),
        "subject": t.get("subject"),
        "status": t.get("status"),
        "priority": t.get("priority"),
        "requester_id": t.get("requester_id"),
        "assignee_id": t.get("assignee_id"),
        "tags": t.get("tags", []),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{t.get('id')}",
    } for t in tickets]
    return json.dumps({"view_id": view_id, "count": len(condensed), "tickets": condensed}, indent=2)


# --- Users ---

@mcp.tool()
def get_user(user_id: str) -> str:
    """Get details of a Zendesk user (agent, admin, or end-user) by ID.

    Returns name, email, role, organization_id, tags, time_zone,
    created_at, updated_at, and last_login_at.
    """
    return json.dumps(_get(f"/users/{user_id}"), indent=2)


@mcp.tool()
def search_users(query: str) -> str:
    """Search for Zendesk users by name or email.

    Returns matching users with id, name, email, role, organization_id,
    and created_at. Useful for resolving requester/assignee names from IDs.
    """
    results = _paginate("/users/search", "users", {"query": query})
    return json.dumps({"count": len(results), "users": results}, indent=2)


@mcp.tool()
def list_agents() -> str:
    """List all agents and admins in the account.

    Returns each user's id, name, email, role (agent/admin), and active status.
    Useful for building assignee → name lookup tables.
    """
    results = _paginate("/users", "users", {"role[]": ["agent", "admin"]})
    agents = [{
        "id": u.get("id"),
        "name": u.get("name"),
        "email": u.get("email"),
        "role": u.get("role"),
        "active": u.get("active"),
    } for u in results]
    return json.dumps({"count": len(agents), "agents": agents}, indent=2)


# --- Organizations ---

@mcp.tool()
def list_organizations() -> str:
    """List all organizations (customer accounts) in the account.

    Returns each org's id, name, domain_names, tags, created_at, and updated_at.
    """
    orgs = _paginate("/organizations", "organizations")
    return json.dumps({"count": len(orgs), "organizations": orgs}, indent=2)


@mcp.tool()
def get_organization(organization_id: str) -> str:
    """Get details of a specific organization by ID."""
    return json.dumps(_get(f"/organizations/{organization_id}"), indent=2)


@mcp.tool()
def search_organizations(query: str) -> str:
    """Search for organizations by name or domain.

    Returns matching organizations with id, name, domain_names, tags, and created_at.
    """
    results = _paginate("/organizations/search", "organizations", {"query": query})
    return json.dumps({"count": len(results), "organizations": results}, indent=2)


@mcp.tool()
def list_organization_tickets(organization_id: str, status: str = "") -> str:
    """List all tickets belonging to an organization.

    organization_id: the Zendesk organization ID
    status: optional filter — 'new', 'open', 'pending', 'hold', 'solved', 'closed'

    Returns condensed ticket list with id, subject, status, priority,
    requester_id, assignee_id, tags, and agent URL.
    """
    tickets = _paginate(f"/organizations/{organization_id}/tickets", "tickets")
    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    condensed = [{
        "id": t.get("id"),
        "subject": t.get("subject"),
        "status": t.get("status"),
        "priority": t.get("priority"),
        "type": t.get("type"),
        "requester_id": t.get("requester_id"),
        "assignee_id": t.get("assignee_id"),
        "tags": t.get("tags", []),
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{t.get('id')}",
    } for t in tickets]
    return json.dumps({
        "organization_id": organization_id,
        "count": len(condensed),
        "tickets": condensed,
    }, indent=2)


# --- Satisfaction Ratings ---

@mcp.tool()
def list_satisfaction_ratings(score: str = "", start_time: str = "",
                               end_time: str = "") -> str:
    """List CSAT satisfaction ratings.

    score: filter by 'good', 'bad', 'offered' (not yet rated)
    start_time / end_time: Unix timestamps or ISO 8601 strings to bound the date range

    Returns each rating's id, score, ticket_id, requester_id, assignee_id,
    comment (if provided by the customer), and created_at.
    """
    params: dict = {}
    if score:
        params["score"] = score
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    ratings = _paginate("/satisfaction_ratings", "satisfaction_ratings", params)
    return json.dumps({"count": len(ratings), "satisfaction_ratings": ratings}, indent=2)


@mcp.tool()
def get_satisfaction_rating(rating_id: str) -> str:
    """Get a single satisfaction rating by ID, including the customer's comment."""
    return json.dumps(_get(f"/satisfaction_ratings/{rating_id}"), indent=2)


# --- Tags ---

@mcp.tool()
def list_ticket_tags() -> str:
    """List all tags used across tickets, sorted by usage count (most used first).

    Returns each tag's name and count of tickets it appears on.
    Useful for understanding categorization patterns and common issue themes.
    """
    tags = _paginate("/tags", "tags")
    sorted_tags = sorted(tags, key=lambda t: t.get("count", 0), reverse=True)
    return json.dumps({"count": len(sorted_tags), "tags": sorted_tags}, indent=2)


# --- Reporting / Analytics ---

@mcp.tool()
def ticket_volume_report(start_date: str, end_date: str,
                          group_by: str = "day") -> str:
    """Report ticket creation volume over a date range using the incremental tickets API.

    start_date / end_date: ISO 8601 date strings (e.g. '2024-01-01')
    group_by: 'day', 'week', or 'month'

    Returns a breakdown of tickets created per period with counts by status,
    priority, and ticket type, plus total volume.

    Note: Uses the incremental export API which requires Admin access and
    returns all tickets updated after start_time. Large date ranges may be slow.
    """
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=datetime.timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
    start_unix = int(start_dt.timestamp())

    # Use incremental tickets export
    in_range: list = []
    url = f"{BASE_URL}/incremental/tickets.json"
    params: dict = {"start_time": start_unix}
    while url:
        r = _session().get(url, params=params)
        r.raise_for_status()
        data = r.json()
        batch = data.get("tickets", [])
        for t in batch:
            created = t.get("created_at", "")
            try:
                if created and start_dt <= _parse_date(created) <= end_dt:
                    in_range.append(t)
            except ValueError:
                logging.warning(
                    "ticket_volume_report: skipping ticket %s with malformed created_at %r",
                    t.get("id"), created,
                )
                continue
        if data.get("end_of_stream", False):
            break
        next_page = data.get("next_page")
        if next_page:
            _np = urlparse(next_page)
            if _np.scheme == _BASE_URL_PARSED.scheme and _np.netloc == _BASE_URL_PARSED.netloc:
                url = next_page
                params = {}
            else:
                url = None
        else:
            url = None

    # Group
    groups: dict = {}
    for t in in_range:
        # created_at is guaranteed non-empty: in_range only contains tickets
        # that passed parse_date() validation in the collection loop above.
        key = _period_key(t.get("created_at"), group_by)
        if key not in groups:
            groups[key] = {"period": key, "total": 0, "by_status": {}, "by_priority": {}, "by_type": {}}
        g = groups[key]
        g["total"] += 1
        s = t.get("status", "unknown")
        g["by_status"][s] = g["by_status"].get(s, 0) + 1
        p = t.get("priority") or "none"
        g["by_priority"][p] = g["by_priority"].get(p, 0) + 1
        tp = t.get("type") or "none"
        g["by_type"][tp] = g["by_type"].get(tp, 0) + 1

    periods = sorted(groups.values(), key=lambda x: x["period"])

    return json.dumps({
        "start_date": start_date,
        "end_date": end_date,
        "group_by": group_by,
        "total_tickets": len(in_range),
        "periods": periods,
    }, indent=2)


@mcp.tool()
def ticket_summary_by_tag(tag: str, status: str = "", limit: int = 500) -> str:
    """Summarize all tickets with a specific tag.

    tag: the tag to filter by
    status: optional status filter ('new', 'open', 'pending', 'hold', 'solved', 'closed')
    limit: max tickets to scan across the entire account before applying the tag filter
           (default 500). Because tag filtering is done in-memory after fetching, this caps
           the total number of API records retrieved, not the number of matching results
           returned. Reduce if the call times out; increase if you suspect matches are being
           missed on high-volume accounts.

    Returns total count, breakdown by status and priority, and the list of matching tickets.
    Useful for understanding the scope of a specific issue category (e.g. 'bug', 'api-error').
    """
    all_tickets = _paginate("/tickets", "tickets", {"per_page": 100}, max_results=limit)
    tagged = [t for t in all_tickets if tag in (t.get("tags") or [])]
    if status:
        tagged = [t for t in tagged if t.get("status") == status]

    by_status: dict = {}
    by_priority: dict = {}
    for t in tagged:
        s = t.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        p = t.get("priority") or "none"
        by_priority[p] = by_priority.get(p, 0) + 1

    condensed = [{
        "id": t.get("id"),
        "subject": t.get("subject"),
        "status": t.get("status"),
        "priority": t.get("priority"),
        "created_at": t.get("created_at"),
        "url": f"https://{_subdomain}.zendesk.com/agent/tickets/{t.get('id')}",
    } for t in tagged]

    return json.dumps({
        "tag": tag,
        "total": len(condensed),
        "by_status": by_status,
        "by_priority": by_priority,
        "tickets": condensed,
    }, indent=2)


@mcp.tool()
def csat_summary(start_time: str = "", end_time: str = "") -> str:
    """CSAT score summary across a date range.

    start_time / end_time: ISO 8601 strings or Unix timestamps (optional)

    Returns total ratings, good/bad counts, CSAT score percentage,
    and all 'bad' ratings with their comments for qualitative review.
    """
    params: dict = {}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    ratings = _paginate("/satisfaction_ratings", "satisfaction_ratings", params)

    total = len(ratings)
    good = sum(1 for r in ratings if r.get("score") == "good")
    bad = sum(1 for r in ratings if r.get("score") == "bad")
    offered = sum(1 for r in ratings if r.get("score") == "offered")
    score_pct = round((good / (good + bad) * 100), 1) if (good + bad) > 0 else None

    bad_ratings = [
        {
            "id": r.get("id"),
            "ticket_id": r.get("ticket_id"),
            "comment": r.get("comment"),
            "assignee_id": r.get("assignee_id"),
            "created_at": r.get("created_at"),
        }
        for r in ratings if r.get("score") == "bad"
    ]

    return json.dumps({
        "total_ratings": total,
        "good": good,
        "bad": bad,
        "offered_not_rated": offered,
        "csat_score_pct": score_pct,
        "bad_ratings": bad_ratings,
    }, indent=2)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
