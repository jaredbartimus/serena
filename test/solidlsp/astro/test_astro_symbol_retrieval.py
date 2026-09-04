"""
Symbol retrieval tests for Astro language server.

Tests cover:
- Containing symbol requests
- Referencing symbol requests
- Cross-file type resolution
- Import resolution

Template: test_vue_symbol_retrieval.py
"""

import os
from collections.abc import Iterable
from urllib.parse import unquote

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import TextEdit, WorkspaceEdit
from test.solidlsp.conftest import read_repo_file


def _iter_workspace_edit_entries(workspace_edit: WorkspaceEdit) -> Iterable[tuple[str, TextEdit]]:
    if workspace_edit.get("changes"):
        for uri, edits in workspace_edit["changes"].items():
            for edit in edits:
                yield uri, edit

    for change in workspace_edit.get("documentChanges") or []:
        if "textDocument" not in change or "edits" not in change:
            continue
        uri = change["textDocument"]["uri"]
        for edit in change["edits"]:
            yield uri, edit


def _assert_rename_edit(
    workspace_edit: WorkspaceEdit | None,
    new_name: str,
    expected_path_fragments: set[str],
) -> None:
    assert workspace_edit is not None, "rename should return a WorkspaceEdit"

    entries = list(_iter_workspace_edit_entries(workspace_edit))
    assert entries, workspace_edit

    edited_paths = {unquote(uri).replace("\\", "/") for uri, _edit in entries}
    for expected_path in expected_path_fragments:
        assert any(expected_path in edited_path for edited_path in edited_paths), (
            f"Expected rename edit for {expected_path}, got {sorted(edited_paths)}"
        )

    for uri, edit in entries:
        assert "range" in edit, f"TextEdit in {uri} should have a range"
        assert "newText" in edit, f"TextEdit in {uri} should have newText"
        assert new_name in edit["newText"], f"TextEdit in {uri} should include {new_name}, got {edit['newText']}"
        assert edit["range"]["start"]["line"] >= 0
        assert edit["range"]["start"]["character"] >= 0


@pytest.mark.astro
class TestAstroSymbolRetrieval:
    """Symbol retrieval functionality tests."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_get_containing_symbol_in_typescript(self, language_server: SolidLanguageServer) -> None:
        """Test finding containing symbol in .ts file within Astro project."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        # Line 8 (0-indexed: 7), col 6 contains `let count = 0;` inside createCounter
        containing_symbol = language_server.request_containing_symbol(counter_path, 7, 6)
        assert containing_symbol is not None, "Expected containing symbol but got None"
        assert containing_symbol["name"] in ("count", "createCounter")

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_find_references_to_typescript_export(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to a TypeScript export from an .astro component.

        createCounter is defined in counter.ts and imported + called in
        src/pages/index.astro. This exercises the dual-server cross-file path: the
        companion tsserver (with @astrojs/ts-plugin) must resolve the .astro usage.
        """
        counter_path = os.path.join("src", "stores", "counter.ts")
        # createCounter is on line 7 (0-indexed: 6), function name starts around char 16
        references = language_server.request_references(counter_path, 6, 20)
        assert references is not None, "Expected references but got None"
        # (file basename, 0-indexed start line) for every reference found
        locations = {(ref["uri"].rsplit("/", 1)[-1], ref["range"]["start"]["line"]) for ref in references}
        # Definition in counter.ts (line 6) plus the import (line 4) and the call (line 7) in index.astro.
        # The index.astro hits require the companion tsserver's @astrojs/ts-plugin awareness to resolve.
        assert ("counter.ts", 6) in locations, f"Expected the definition at counter.ts:6, got: {sorted(locations)}"
        assert ("index.astro", 4) in locations, f"Expected the import at index.astro:4, got: {sorted(locations)}"
        assert ("index.astro", 7) in locations, f"Expected the call at index.astro:7, got: {sorted(locations)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_go_to_definition_across_astro_and_typescript(self, language_server: SolidLanguageServer) -> None:
        """Test cross-file go-to-definition from .astro template to TypeScript utility function."""
        index_path = os.path.join("src", "pages", "index.astro")
        # Line 15 (0-indexed: 14), col 18 is formatNumber(counter.count) in index.astro
        definition_list = language_server.request_definition(index_path, 14, 18)
        assert definition_list, "Expected at least one definition"
        definition = definition_list[0]
        assert definition["relativePath"] == os.path.join("src", "utils", "format.ts")
        # formatNumber is defined on line 4 (0-indexed: 3)
        assert definition["range"]["start"]["line"] == 3

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_format_utils_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that format.ts utility file symbols are accessible."""
        format_path = os.path.join("src", "utils", "format.ts")
        symbols = language_server.request_document_symbols(format_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "formatNumber" in symbol_names, f"Expected 'formatNumber' in symbols, got: {symbol_names}"
        assert "formatDate" in symbol_names, f"Expected 'formatDate' in symbols, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_rename_typescript_symbol_updates_astro_importer(self, language_server: SolidLanguageServer) -> None:
        """Test that renaming an exported TypeScript function updates both TS definition and Astro usages."""
        file_path = os.path.join("src", "stores", "counter.ts")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(createCounter)")
        assert coords is not None

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "buildCounter")
        _assert_rename_edit(
            workspace_edit,
            "buildCounter",
            {
                "src/stores/counter.ts",
                "src/pages/index.astro",
            },
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_rename_local_symbol_within_astro_file(self, language_server: SolidLanguageServer) -> None:
        """Test that renaming a local variable in an Astro frontmatter updates template references."""
        file_path = os.path.join("src", "pages", "index.astro")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"const (counter) =")
        assert coords is not None

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "counterInstance")
        _assert_rename_edit(
            workspace_edit,
            "counterInstance",
            {"src/pages/index.astro"},
        )
        entries = list(_iter_workspace_edit_entries(workspace_edit))
        assert len(entries) >= 2, f"Expected at least 2 edit sites for counter in index.astro, got {len(entries)}"
