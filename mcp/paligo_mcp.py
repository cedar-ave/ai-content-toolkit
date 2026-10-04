"""
Paligo REST API MCP server.
"""

import json
import logging
import mimetypes
import os
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

_instance = os.getenv("PALIGO_INSTANCE", "")
PALIGO_API_URL = f"https://{_instance}/api/v2" if _instance else ""
PALIGO_API_TOKEN = os.getenv("PALIGO_API_TOKEN", "")  # pre-encoded Base64 "username:apikey"

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Basic {PALIGO_API_TOKEN}",
    })
    return s


def _get(path: str, params: dict = None) -> dict:
    r = _session().get(f"{PALIGO_API_URL}{path}", params=params)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict = None, files=None) -> dict:
    s = _session()
    if files:
        s.headers.pop("Content-Type", None)
        r = s.post(f"{PALIGO_API_URL}{path}", data=body, files=files)
    else:
        r = s.post(f"{PALIGO_API_URL}{path}", json=body)
    r.raise_for_status()
    return r.json()


def _put(path: str, body: dict = None) -> dict:
    r = _session().put(f"{PALIGO_API_URL}{path}", json=body)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> str:
    r = _session().delete(f"{PALIGO_API_URL}{path}")
    r.raise_for_status()
    return "ok"

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("paligo")

# --- Folders ---

@mcp.tool()
def list_folders(parent_id: str = "") -> str:
    """List folders. Optionally filter by parent_id."""
    params = {}
    if parent_id:
        params["parent"] = parent_id
    return json.dumps(_get("/folders", params), indent=2)


@mcp.tool()
def get_folder(folder_id: str) -> str:
    """Get properties and children of a folder by ID."""
    return json.dumps(_get(f"/folders/{folder_id}"), indent=2)


@mcp.tool()
def create_folder(name: str, parent_id: str) -> str:
    """Create a folder inside the specified parent folder."""
    return json.dumps(_post("/folders/", {"name": name, "parent": int(parent_id)}), indent=2)


# --- Documents ---

@mcp.tool()
def list_documents(folder_id: str = "", include_xml: bool = False) -> str:
    """List documents. Optionally filter by folder_id. Set include_xml=True to include XML content."""
    params = {}
    if folder_id:
        params["folder"] = folder_id
    if include_xml:
        params["xml"] = "true"
    return json.dumps(_get("/documents", params), indent=2)


@mcp.tool()
def get_document(doc_id: str) -> str:
    """Get properties and XML content of a document by ID."""
    return json.dumps(_get(f"/documents/{doc_id}"), indent=2)


@mcp.tool()
def create_document(name: str, folder_id: str, xml_content: str = "") -> str:
    """Create a new document (component) in the specified folder. Optionally provide XML content."""
    body = {"name": name, "parent": int(folder_id), "subtype": "component"}
    if xml_content:
        body["content"] = xml_content
    return json.dumps(_post("/documents/", body), indent=2)


@mcp.tool()
def update_document(doc_id: str, name: str = "", xml_content: str = "") -> str:
    """Update a document's name and/or XML content."""
    body = {}
    if name:
        body["name"] = name
    if xml_content:
        body["content"] = xml_content
    return json.dumps(_put(f"/documents/{doc_id}", body), indent=2)


@mcp.tool()
def delete_document(doc_id: str) -> str:
    """Delete a document by ID."""
    return _delete(f"/documents/{doc_id}")


# --- Forks ---

@mcp.tool()
def list_forks(parent_id: str) -> str:
    """List forks under the given parent document or folder."""
    return json.dumps(_get("/forks", {"parent": parent_id}), indent=2)


@mcp.tool()
def get_fork(fork_id: str) -> str:
    """Get properties of a fork by ID."""
    return json.dumps(_get(f"/forks/{fork_id}"), indent=2)


@mcp.tool()
def create_fork(parent_id: str, document_id: str = "") -> str:
    """Create a fork linking a document to a publication. Pass publication ID as parent_id for Level 1; pass a fork ID as parent_id for Level 2."""
    body = {"parent": int(parent_id)}
    if document_id:
        body["document"] = int(document_id)
    return json.dumps(_post("/forks/", body), indent=2)


@mcp.tool()
def delete_fork(fork_id: str) -> str:
    """Delete a fork by ID."""
    return _delete(f"/forks/{fork_id}")


# --- Images ---

@mcp.tool()
def list_images(name_filter: str = "", folder_id: str = "") -> str:
    """List images. Optionally filter by name or folder."""
    params = {}
    if name_filter:
        params["name"] = name_filter
    if folder_id:
        params["folder"] = folder_id
    return json.dumps(_get("/images", params), indent=2)


@mcp.tool()
def get_image(image_id: str) -> str:
    """Get properties and download URL of an image by ID."""
    return json.dumps(_get(f"/images/{image_id}"), indent=2)


@mcp.tool()
def upload_image(file_path: str, name: str = "") -> str:
    """Upload a new image file from a local path to Paligo.

    Note: Paligo's API does not accept folder assignment at upload time — any
    extra form field alongside the file causes a 422. Images are placed in the
    root images library and can be moved in the Paligo UI after upload.
    """
    p = Path(file_path)
    mime_type, _ = mimetypes.guess_type(str(p))
    mime_type = mime_type or "image/png"
    with open(p, "rb") as f:
        files = {"image": (name or p.name, f, mime_type)}
        return json.dumps(_post("/images/", files=files), indent=2)


@mcp.tool()
def update_image(image_id: str, file_path: str = "", name: str = "") -> str:
    """Replace an image's file and/or update its name."""
    body = {}
    files = None
    if name:
        body["name"] = name
    if file_path:
        p = Path(file_path)
        with open(p, "rb") as f:
            s = _session()
            s.headers.pop("Content-Type", None)
            r = s.put(f"{PALIGO_API_URL}/images/{image_id}", data=body, files={"file": (p.name, f)})
            r.raise_for_status()
            return json.dumps(r.json(), indent=2)
    return json.dumps(_put(f"/images/{image_id}", body), indent=2)


# --- Search ---

@mcp.tool()
def search(query: str) -> str:
    """Search Paligo content. query is a JSON string matching the Paligo search operator schema."""
    body = json.loads(query)
    return json.dumps(_post("/search/", body), indent=2)


# --- Productions ---

@mcp.tool()
def list_productions(status_filter: str = "") -> str:
    """List recent productions. Optionally filter by status (e.g. 'done', 'running', 'failed')."""
    params = {}
    if status_filter:
        params["status"] = status_filter
    return json.dumps(_get("/productions/", params), indent=2)


@mcp.tool()
def get_production(production_id: str) -> str:
    """Get details and progress of a production by ID."""
    return json.dumps(_get(f"/productions/{production_id}"), indent=2)


@mcp.tool()
def create_production(publish_setting_id: str, document_id: str = "") -> str:
    """Start a new production using a saved publish setting. Optionally target a specific document."""
    body = {"publishsetting": publish_setting_id}
    if document_id:
        body["document"] = document_id
    return json.dumps(_post("/productions/", body), indent=2)


# --- Publish Settings ---

@mcp.tool()
def list_publish_settings() -> str:
    """List all saved publish settings."""
    return json.dumps(_get("/publishsettings"), indent=2)


@mcp.tool()
def get_publish_settings(setting_id: str) -> str:
    """Get details of a specific publish setting by ID."""
    return json.dumps(_get(f"/publishsettings/{setting_id}"), indent=2)


# --- Outputs ---

@mcp.tool()
def get_output(output_name: str) -> str:
    """Retrieve a published output archive by its name. Returns metadata and download info."""
    return json.dumps(_get(f"/outputs/{output_name}"), indent=2)


# --- Imports ---

@mcp.tool()
def list_imports(status_filter: str = "") -> str:
    """List recent imports. Optionally filter by status."""
    params = {}
    if status_filter:
        params["status"] = status_filter
    return json.dumps(_get("/imports/", params), indent=2)


@mcp.tool()
def get_import(import_id: str) -> str:
    """Get properties and progress of an import by ID."""
    return json.dumps(_get(f"/imports/{import_id}"), indent=2)


@mcp.tool()
def create_import(folder_id: str, file_path: str) -> str:
    """Start a new import from a local archive file into the specified folder."""
    p = Path(file_path)
    with open(p, "rb") as f:
        files = {"file": (p.name, f)}
        data = {"folder": folder_id}
        return json.dumps(_post("/imports/", body=data, files=files), indent=2)


# --- Translation Exports ---

@mcp.tool()
def list_translation_exports() -> str:
    """List all translation exports."""
    return json.dumps(_get("/translationexport"), indent=2)


@mcp.tool()
def get_translation_export(export_id: str) -> str:
    """Get details of a translation export by ID."""
    return json.dumps(_get(f"/translationexport/{export_id}"), indent=2)


@mcp.tool()
def create_translation_export(document_id: str, languages: list) -> str:
    """Create a new translation export for a document and target languages."""
    return json.dumps(_post("/translationexport", {"document": document_id, "languages": languages}), indent=2)


# --- Translation Imports ---

@mcp.tool()
def list_translation_imports() -> str:
    """List all translation imports."""
    return json.dumps(_get("/translationimport"), indent=2)


@mcp.tool()
def get_translation_import(import_id: str) -> str:
    """Get details of a translation import by ID."""
    return json.dumps(_get(f"/translationimport/{import_id}"), indent=2)


@mcp.tool()
def create_translation_import(file_path: str) -> str:
    """Start a new translation import from a local XLIFF/ZIP file."""
    p = Path(file_path)
    with open(p, "rb") as f:
        files = {"file": (p.name, f)}
        return json.dumps(_post("/translationimport", body={}, files=files), indent=2)


# --- Taxonomies ---

@mcp.tool()
def list_taxonomies() -> str:
    """List all taxonomies."""
    return json.dumps(_get("/taxonomies"), indent=2)


@mcp.tool()
def get_taxonomy(taxonomy_id: str) -> str:
    """Get details of a taxonomy by ID."""
    return json.dumps(_get(f"/taxonomies/{taxonomy_id}"), indent=2)


@mcp.tool()
def create_taxonomy(name: str, parent_id: str = "") -> str:
    """Create a new taxonomy."""
    body = {"name": name}
    if parent_id:
        body["parent"] = parent_id
    return json.dumps(_post("/taxonomies", body), indent=2)


@mcp.tool()
def update_taxonomy(taxonomy_id: str, name: str) -> str:
    """Update the name of a taxonomy."""
    return json.dumps(_put(f"/taxonomies/{taxonomy_id}", {"name": name}), indent=2)


@mcp.tool()
def delete_taxonomy(taxonomy_id: str) -> str:
    """Delete a taxonomy by ID."""
    return _delete(f"/taxonomies/{taxonomy_id}")


# --- Variables ---

@mcp.tool()
def list_variable_sets() -> str:
    """List all variable sets."""
    return json.dumps(_get("/variables"), indent=2)


@mcp.tool()
def get_variable_set(variable_set_id: str) -> str:
    """Get details of a variable set by ID."""
    return json.dumps(_get(f"/variables/{variable_set_id}"), indent=2)


@mcp.tool()
def create_variable_set(name: str) -> str:
    """Create a new variable set."""
    return json.dumps(_post("/variables", {"name": name}), indent=2)


@mcp.tool()
def update_variable_set(variable_set_id: str, name: str) -> str:
    """Update the name of a variable set."""
    return json.dumps(_put(f"/variables/{variable_set_id}", {"name": name}), indent=2)


@mcp.tool()
def delete_variable_set(variable_set_id: str) -> str:
    """Delete a variable set by ID."""
    return _delete(f"/variables/{variable_set_id}")


# --- Groups ---

@mcp.tool()
def list_groups() -> str:
    """List all groups."""
    return json.dumps(_get("/group"), indent=2)


@mcp.tool()
def get_group(group_id: str) -> str:
    """Get details of a group by ID."""
    return json.dumps(_get(f"/group/{group_id}"), indent=2)


# --- Users ---

@mcp.tool()
def list_users() -> str:
    """List all users."""
    return json.dumps(_get("/users"), indent=2)


@mcp.tool()
def get_user(user_id: str) -> str:
    """Get details of a user by ID."""
    return json.dumps(_get(f"/users/{user_id}"), indent=2)


# --- Assignments ---

@mcp.tool()
def list_assignments() -> str:
    """List all assignments."""
    return json.dumps(_get("/assignments"), indent=2)


@mcp.tool()
def get_assignment(assignment_id: str) -> str:
    """Get details of an assignment by ID."""
    return json.dumps(_get(f"/assignments/{assignment_id}"), indent=2)


@mcp.tool()
def create_assignment(document_id: str, user_id: str, role: str, due_date: str = "") -> str:
    """Create an assignment for a user on a document."""
    body = {"document": document_id, "user": user_id, "role": role}
    if due_date:
        body["dueDate"] = due_date
    return json.dumps(_post("/assignments", body), indent=2)


@mcp.tool()
def update_assignment(assignment_id: str, status: str = "", due_date: str = "") -> str:
    """Update the status or due date of an assignment."""
    body = {}
    if status:
        body["status"] = status
    if due_date:
        body["dueDate"] = due_date
    return json.dumps(_put(f"/assignments/{assignment_id}", body), indent=2)


@mcp.tool()
def delete_assignment(assignment_id: str) -> str:
    """Delete an assignment by ID."""
    return _delete(f"/assignments/{assignment_id}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
