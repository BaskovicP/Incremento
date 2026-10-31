"""Dependency-free client setup; exported MCPB bundles contain no credentials."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from .i18n import t
except ImportError:
    from i18n import t


def connection_snippets(token):
    if not isinstance(token, str) or not token or not all(c.isalnum() or c in "_-" for c in token):
        raise ValueError("Invalid connection token.")
    url = "http://127.0.0.1:8767/mcp"
    values = {
        "codex": '[mcp_servers.incremento]\nurl = "' + url + '"\n'
                 'http_headers = { Authorization = "Bearer ' + token + '" }\n',
        "claude_code": json.dumps({"mcpServers": {"incremento": {
            "type": "http", "url": url, "headers": {"Authorization": "Bearer " + token}}}}, indent=2),
        "claude_code_command": "claude mcp add --transport http --scope user incremento " + url +
                               " --header 'Authorization: Bearer " + token + "'",
        "token": token,
    }
    values["codex_prompt"] = t("mcp_connections_codex_setup_prompt", configuration=values["codex"])
    values["claude_code_prompt"] = t("mcp_connections_claude_code_setup_prompt", command=values["claude_code_command"])
    return values


def export_claude_bundle(source, destination):
    source, destination = Path(source), Path(destination)
    files = {"manifest.json": source / "manifest.json", "incremento.mjs": source / "incremento.mjs",
             "LICENSE": source.parents[1] / "LICENSE"}
    for path in files.values():
        if source.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
            raise ValueError("Invalid MCP connector source.")
    # Exclusive creation: the file picker must not authorize overwriting a
    # symlink or an unrelated existing file.
    with destination.open("xb") as stream:
        with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
            for name, path in files.items():
                archive.write(path, name)
    return destination
