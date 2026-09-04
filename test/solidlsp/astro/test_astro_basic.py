"""
Basic tests for Astro language server functionality.

Tests cover:
- Language server startup
- Symbol tree extraction from .astro files
- Cross-file reference finding between Astro and TypeScript
- Dual server coordination
- Reference deduplication

Template: test_vue_basic.py
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.astro
class TestAstroLanguageServer:
    """Core Astro language server functionality tests."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the Astro language server starts and stops successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_astro_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are extracted from .astro files."""
        layout_path = os.path.join("src", "layouts", "Layout.astro")
        symbols = language_server.request_document_symbols(layout_path)
        assert symbols is not None, "Expected document symbols but got None"
        # Layout.astro defines: interface Props { title: string; }
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        # Verify we found the Props interface from frontmatter
        assert "Props" in symbol_names, f"Expected 'Props' interface in symbols, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_typescript_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that TypeScript files in Astro project have document symbols."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        symbols = language_server.request_document_symbols(counter_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "CounterStore" in symbol_names, f"Expected 'CounterStore' in symbols, got: {symbol_names}"
        assert "createCounter" in symbol_names, f"Expected 'createCounter' in symbols, got: {symbol_names}"


@pytest.mark.astro
class TestAstroDefinition:
    """Go-to-definition tests for Astro language server."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_find_definition_within_typescript(self, language_server: SolidLanguageServer) -> None:
        """Test finding definition within TypeScript file."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        definition_list = language_server.request_definition(counter_path, 6, 35)
        assert definition_list, "Expected at least one definition"
        assert len(definition_list) >= 1
        definition = definition_list[0]
        assert definition["uri"].endswith("counter.ts"), f"Expected counter.ts, got: {definition['uri']}"
        assert definition["range"]["start"]["line"] == 0, "Expected definition at line 0"


@pytest.mark.astro
class TestAstroReferences:
    """Reference finding tests for Astro language server."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_find_references_within_typescript(self, language_server: SolidLanguageServer) -> None:
        """Test finding references within TypeScript file."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        # CounterStore interface on line 0 (0-indexed), column 20
        references = language_server.request_references(counter_path, 0, 20)
        assert references, "Expected at least one reference"
        # (file basename, 0-indexed start line) for every reference found
        locations = {(ref["uri"].rsplit("/", 1)[-1], ref["range"]["start"]["line"]) for ref in references}
        # CounterStore is declared on line 0 and used as the createCounter return type on line 6,
        # both within counter.ts (this symbol is not referenced from .astro files).
        assert ("counter.ts", 0) in locations, f"Expected the declaration at counter.ts:0, got: {sorted(locations)}"
        assert ("counter.ts", 6) in locations, f"Expected the return-type use at counter.ts:6, got: {sorted(locations)}"


@pytest.mark.astro
class TestAstroDualLspArchitecture:
    """Tests for TypeScript server coordination in Astro."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_astro_and_typescript_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Test that full symbol tree includes symbols from both Astro and TypeScript files."""
        symbols = language_server.request_full_symbol_tree()

        # Layout.astro contains Props interface
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Props"), "Props interface not found in symbol tree"
        # counter.ts contains CounterStore interface and createCounter function
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CounterStore"), "CounterStore not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "createCounter"), "createCounter not found in symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_dual_server_definition_lookup(self, language_server: SolidLanguageServer) -> None:
        """Test that definitions work with both Astro and TypeScript servers."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        ts_definition = language_server.request_definition(counter_path, 6, 35)
        assert ts_definition, "Expected definition from TypeScript server"


@pytest.mark.astro
class TestAstroEdgeCases:
    """Edge case tests for Astro language server."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_astro_file_with_frontmatter(self, language_server: SolidLanguageServer) -> None:
        """Test handling of .astro files with frontmatter section."""
        index_path = os.path.join("src", "pages", "index.astro")
        # index.astro has imports and variable declarations in frontmatter
        symbols = language_server.request_document_symbols(index_path)
        # Should handle frontmatter without errors
        assert symbols is not None, "Expected document symbols but got None"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_layout_astro_with_props_interface(self, language_server: SolidLanguageServer) -> None:
        """Test Layout.astro which has Props interface in frontmatter."""
        layout_path = os.path.join("src", "layouts", "Layout.astro")
        # Layout.astro defines: interface Props { title: string; }
        symbols = language_server.request_document_symbols(layout_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        # Verify Props interface is found
        assert "Props" in symbol_names, f"Expected 'Props' interface in Layout.astro, got: {symbol_names}"
