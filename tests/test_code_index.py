from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import ADWikiError  # noqa: E402
from ad_wiki.code_index.ids import stable_symbol_id  # noqa: E402
from ad_wiki.code_index.model import (  # noqa: E402
    canonical_json_bytes,
    validate_fragment,
    validate_graph,
)
from ad_wiki.code_index.security import read_text_source  # noqa: E402
from ad_wiki.code_index.extractors import extract_file  # noqa: E402
from ad_wiki.code_index.graph import build_graph  # noqa: E402
from ad_wiki.code_index.cache import build_or_update_index, load_current_index  # noqa: E402
from ad_wiki.code_index.query import query_graph  # noqa: E402


TREE_SITTER_AVAILABLE = bool(
    importlib.util.find_spec("tree_sitter") and importlib.util.find_spec("tree_sitter_java")
)


def node(node_id: str, *, path: str = "src/Foo.java", line: int = 1) -> dict:
    return {
        "id": node_id,
        "kind": "method",
        "label": "Foo#start()",
        "language": "java",
        "source_file": path,
        "source_location": {"start_line": line, "end_line": line},
    }


def edge(source: str, target: str, *, evidence: str = "EXTRACTED") -> dict:
    return {
        "source": source,
        "target": target,
        "relation": "calls",
        "evidence": evidence,
        "source_file": "src/Foo.java",
        "source_location": {"start_line": 3, "end_line": 3},
    }


class StableIdTests(unittest.TestCase):
    def test_ids_are_repo_relative_unicode_stable_and_case_sensitive(self) -> None:
        first = stable_symbol_id(
            "java",
            "method",
            "./src/main/java/com/acme/Foo.java",
            "com.acme.Foo.start(String)",
        )
        moved_checkout = stable_symbol_id(
            "java",
            "method",
            "src/main/java/com/acme/Foo.java",
            "com.acme.Foo.start(String)",
        )
        different_case = stable_symbol_id(
            "java",
            "method",
            "src/main/java/com/acme/Foo.java",
            "com.acme.Foo.Start(String)",
        )

        self.assertEqual(first, moved_checkout)
        self.assertEqual(
            first,
            "java:method:src/main/java/com/acme/Foo.java#com.acme.Foo.start(String)",
        )
        self.assertNotEqual(first, different_case)
        self.assertEqual(first, stable_symbol_id("java", "method", "src/main/java/com/acme/Foo.java", "com.acme.Foo.start(String)"))

    def test_ids_reject_absolute_parent_and_unknown_kind(self) -> None:
        with self.assertRaisesRegex(ADWikiError, "repository-relative"):
            stable_symbol_id("java", "method", "/tmp/Foo.java", "Foo.start()")
        with self.assertRaisesRegex(ADWikiError, "repository-relative"):
            stable_symbol_id("java", "method", "../Foo.java", "Foo.start()")
        with self.assertRaisesRegex(ADWikiError, "kind"):
            stable_symbol_id("java", "mystery", "Foo.java", "Foo")


class StructuralSchemaTests(unittest.TestCase):
    def test_fragment_and_graph_validate_and_serialize_deterministically(self) -> None:
        a = node("java:method:src/A.java#A.a()", path="src/A.java")
        b = node("java:method:src/B.java#B.b()", path="src/B.java")
        fragment = {
            "schema_version": "1",
            "extractor": {"name": "java", "version": "1", "grammar": "tree-sitter-java/0.23.5"},
            "source": {"path": "src/A.java", "sha256": "a" * 64, "bytes": 10},
            "nodes": [a, b],
            "edges": [edge(a["id"], b["id"])],
            "unresolved": [],
        }
        graph = {
            "schema_version": "1",
            "revision": "b" * 40,
            "nodes": [b, a],
            "edges": [edge(a["id"], b["id"])],
            "vocab": ["start", "foo"],
        }

        self.assertEqual(validate_fragment(fragment), [])
        self.assertEqual(validate_graph(graph), [])
        encoded = canonical_json_bytes(graph)
        decoded = json.loads(encoded)
        self.assertEqual([item["id"] for item in decoded["nodes"]], sorted([a["id"], b["id"]]))
        self.assertEqual(encoded, canonical_json_bytes(decoded))

    def test_schema_rejects_duplicate_dangling_evidence_and_locations(self) -> None:
        a = node("java:method:src/A.java#A.a()", path="src/A.java")
        graph = {
            "schema_version": "1",
            "revision": "b" * 40,
            "nodes": [a, dict(a)],
            "edges": [edge(a["id"], "missing", evidence="CERTAIN")],
            "vocab": [],
        }
        graph["nodes"][0]["source_location"] = {"start_line": 4, "end_line": 2}

        errors = validate_graph(graph)

        self.assertTrue(any("duplicate node id" in item for item in errors), errors)
        self.assertTrue(any("dangling target" in item for item in errors), errors)
        self.assertTrue(any("invalid evidence" in item for item in errors), errors)
        self.assertTrue(any("source_location" in item for item in errors), errors)


class StructuralSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_reads_bounded_utf8_source_and_rejects_binary_sensitive_and_escape(self) -> None:
        source = self.root / "src/Foo.java"
        source.parent.mkdir(parents=True)
        source.write_text("class Foo {}\n")
        self.assertEqual(read_text_source(self.root, source), b"class Foo {}\n")

        binary = self.root / "src/Binary.java"
        binary.write_bytes(b"class\x00Binary")
        with self.assertRaisesRegex(ADWikiError, "binary"):
            read_text_source(self.root, binary)

        secret = self.root / ".env"
        secret.write_text("TOKEN=secret\n")
        with self.assertRaisesRegex(ADWikiError, "sensitive"):
            read_text_source(self.root, secret)

        outside = self.root.parent / "outside.java"
        outside.write_text("class Outside {}\n")
        with self.assertRaisesRegex(ADWikiError, "outside"):
            read_text_source(self.root, outside)

        large = self.root / "src/Large.java"
        large.write_bytes(b"a" * 20)
        with self.assertRaisesRegex(ADWikiError, "exceeds"):
            read_text_source(self.root, large, max_bytes=10)


@unittest.skipUnless(TREE_SITTER_AVAILABLE, "structural tests run in code-index uv environment")
class JavaAndConfigExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_java_extracts_symbols_relations_calls_annotations_and_tests(self) -> None:
        source = self.write(
            "src/main/java/com/acme/Foo.java",
            """package com.acme;
import java.util.List;
/** Lifecycle component. Additional implementation detail. */
@Deprecated
public class Foo extends Base implements Runnable {
  private String state;
  public Foo(String state) { this.state = state; }
  @Override public void run() { helper(state); service.start(); }
  private void helper(String value) {}
}
""",
        )

        fragment = extract_file(source, root=self.root)

        self.assertEqual(validate_fragment(fragment), [])
        ids = {item["id"] for item in fragment["nodes"]}
        self.assertIn(
            "java:type:src/main/java/com/acme/Foo.java#com.acme.Foo",
            ids,
        )
        self.assertIn(
            "java:method:src/main/java/com/acme/Foo.java#com.acme.Foo.run()",
            ids,
        )
        relations = {item["relation"] for item in fragment["edges"]}
        self.assertTrue({"imports", "extends", "implements", "calls", "annotates"}.issubset(relations))
        self.assertTrue(any(item["evidence"] == "AMBIGUOUS" for item in fragment["edges"] if item["relation"] == "calls"))
        self.assertTrue(all(item["source_location"]["start_line"] >= 1 for item in fragment["nodes"]))
        graph = build_graph([fragment], revision="c" * 40)
        foo_type = next(item for item in graph["nodes"] if item.get("qualified_name") == "com.acme.Foo")
        self.assertEqual(foo_type["summary"], "Lifecycle component.")

        test_source = self.write(
            "src/test/java/com/acme/FooTest.java",
            """package com.acme;
import org.junit.jupiter.api.Test;
class FooTest {
  @Test void starts() { new Foo("ready").run(); }
}
""",
        )
        test_fragment = extract_file(test_source, root=self.root)
        self.assertTrue(any(item.get("is_test") for item in test_fragment["nodes"]))

    def test_maven_and_properties_extract_without_exposing_secret_values(self) -> None:
        pom = self.write(
            "pom.xml",
            """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.acme</groupId><artifactId>demo</artifactId><version>1.0</version>
  <properties><sofa.version>4.0</sofa.version></properties>
  <dependencies><dependency><groupId>com.alipay.sofa</groupId><artifactId>runtime</artifactId><version>${sofa.version}</version></dependency></dependencies>
  <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-surefire-plugin</artifactId></plugin></plugins></build>
</project>""",
        )
        props = self.write(
            "conf/sofa.properties",
            """sofa.module.parallel=true
service.endpoint=${service.host}:8080
db.password=super-secret-value
""",
        )

        pom_fragment = extract_file(pom, root=self.root)
        props_fragment = extract_file(props, root=self.root)

        self.assertEqual(validate_fragment(pom_fragment), [])
        self.assertEqual(validate_fragment(props_fragment), [])
        pom_relations = {item["relation"] for item in pom_fragment["edges"]}
        self.assertTrue({"contains", "uses", "references"}.issubset(pom_relations))
        property_nodes = {item["label"]: item for item in props_fragment["nodes"]}
        self.assertEqual(property_nodes["db.password"]["value"], "<redacted>")
        self.assertTrue(property_nodes["db.password"]["sensitive"])
        self.assertTrue(any(item["relation"] == "references" for item in props_fragment["edges"]))

    def test_xml_external_entities_are_rejected(self) -> None:
        pom = self.write(
            "pom.xml",
            '<!DOCTYPE project [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><project>&xxe;</project>',
        )
        with self.assertRaisesRegex(ADWikiError, "DOCTYPE|ENTITY"):
            extract_file(pom, root=self.root)


@unittest.skipUnless(TREE_SITTER_AVAILABLE, "structural tests run in code-index uv environment")
class GraphAssemblyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_graph_resolves_unique_calls_preserves_ambiguity_and_is_deterministic(self) -> None:
        caller = self.write(
            "src/Caller.java",
            """package demo;
class Caller { void run() { Target.start(); duplicate(); } }
""",
        )
        target = self.write(
            "src/Target.java",
            """package demo;
class Target { static void start() {} void duplicate() {} }
""",
        )
        other = self.write(
            "src/Other.java",
            """package demo;
class Other { void duplicate() {} }
""",
        )
        fragments = [extract_file(path, root=self.root) for path in (caller, target, other)]

        first = build_graph(fragments, revision="a" * 40)
        second = build_graph(list(reversed(fragments)), revision="a" * 40)

        self.assertEqual(validate_graph(first), [])
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        start_edges = [item for item in first["edges"] if "start" in item["target"]]
        self.assertTrue(any(item["evidence"] == "INFERRED" for item in start_edges))
        unresolved = [item for item in first["nodes"] if item["kind"] == "unresolved"]
        self.assertTrue(any("duplicate" in item["label"] for item in unresolved))
        file_nodes = [item for item in first["nodes"] if item["kind"] == "file"]
        self.assertTrue(all(len(item.get("summary", "")) <= 300 for item in file_nodes))
        self.assertIn("target", first["vocab"])


@unittest.skipUnless(TREE_SITTER_AVAILABLE, "structural tests run in code-index uv environment")
class IncrementalIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.code = self.root / "code"
        self.cache = self.root / "cache"
        self.code.mkdir()
        self.write("src/A.java", "package demo; class A { void run() { B.start(); } }\n")
        self.write("src/B.java", "package demo; class B { static void start() {} }\n")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.code / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_content_cache_incremental_add_change_delete_and_stable_rebuild(self) -> None:
        first = build_or_update_index(
            self.code,
            cache_root=self.cache,
            revision="1" * 40,
            workers=1,
        )
        graph_one, manifest_one = load_current_index(self.cache)
        second = build_or_update_index(
            self.code,
            cache_root=self.cache,
            revision="1" * 40,
            workers=4,
        )
        graph_two, manifest_two = load_current_index(self.cache)

        self.assertEqual(first["metrics"]["parsed"], 2)
        self.assertEqual(second["metrics"]["cache_hits"], 2)
        self.assertEqual(canonical_json_bytes(graph_one), canonical_json_bytes(graph_two))
        self.assertEqual(manifest_one["graph_sha256"], manifest_two["graph_sha256"])

        (self.code / "src/A.java").unlink()
        self.write("src/B.java", "package demo; class B { static void start() {} void stop() {} }\n")
        self.write("src/C.java", "package demo; class C { void call() { B.start(); } }\n")
        updated = build_or_update_index(
            self.code,
            cache_root=self.cache,
            revision="2" * 40,
            workers=2,
        )
        graph, manifest = load_current_index(self.cache)

        self.assertEqual(updated["metrics"]["added"], 1)
        self.assertEqual(updated["metrics"]["changed"], 1)
        self.assertEqual(updated["metrics"]["deleted"], 1)
        self.assertNotIn("src/A.java", manifest["files"])
        self.assertTrue(all(item["source_file"] != "src/A.java" for item in graph["nodes"]))

        rebuilt_cache = self.root / "rebuilt"
        build_or_update_index(
            self.code,
            cache_root=rebuilt_cache,
            revision="2" * 40,
            workers=4,
        )
        rebuilt_graph, _ = load_current_index(rebuilt_cache)
        self.assertEqual(canonical_json_bytes(graph), canonical_json_bytes(rebuilt_graph))

    def test_manifest_last_publish_preserves_previous_success_and_corrupt_fragment_rebuilds(self) -> None:
        build_or_update_index(
            self.code,
            cache_root=self.cache,
            revision="1" * 40,
        )
        old_graph, old_manifest = load_current_index(self.cache)
        self.write("src/A.java", "package demo; class A { void changed() {} }\n")

        with self.assertRaisesRegex(ADWikiError, "injected publish failure"):
            build_or_update_index(
                self.code,
                cache_root=self.cache,
                revision="2" * 40,
                fail_before_manifest=True,
            )
        current_graph, current_manifest = load_current_index(self.cache)
        self.assertEqual(canonical_json_bytes(current_graph), canonical_json_bytes(old_graph))
        self.assertEqual(current_manifest["revision"], old_manifest["revision"])

        fragment_path = (
            self.cache
            / "fragments"
            / f"{old_manifest['files']['src/B.java']['fragment']}.json"
        )
        fragment_path.write_text("not-json\n")
        repaired = build_or_update_index(
            self.code,
            cache_root=self.cache,
            revision="2" * 40,
        )
        self.assertGreaterEqual(repaired["metrics"]["corrupt_fragments"], 1)
        self.assertGreaterEqual(repaired["metrics"]["parsed"], 1)

    def test_cache_lock_rejects_concurrent_builder(self) -> None:
        self.cache.mkdir(parents=True)
        (self.cache / ".lock").write_text("other\n")
        with self.assertRaisesRegex(ADWikiError, "cache lock"):
            build_or_update_index(
                self.code,
                cache_root=self.cache,
                revision="1" * 40,
            )


@unittest.skipUnless(TREE_SITTER_AVAILABLE, "structural tests run in code-index uv environment")
class StructuralQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        paths = {
            "src/A.java": "package demo; class A { void run() { B.start(); } }\n",
            "src/B.java": "package demo; class B { static void start() {} }\n",
            "src/C.java": "package demo; class C { void run() { B.start(); } }\n",
        }
        fragments = []
        for relative, content in paths.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            fragments.append(extract_file(path, root=self.root))
        self.graph = build_graph(fragments, revision="a" * 40)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_search_explain_path_bfs_and_affected_are_bounded_and_evidence_linked(self) -> None:
        search = query_graph(self.graph, {"mode": "search", "tokens": ["start"]})
        self.assertTrue(search["nodes"])
        start_id = next(item["id"] for item in search["nodes"] if "start" in item["label"])

        explain = query_graph(self.graph, {"mode": "explain", "source_id": start_id})
        self.assertEqual(explain["start_nodes"], [start_id])
        self.assertTrue(all(item["evidence"] in {"EXTRACTED", "INFERRED", "AMBIGUOUS"} for item in explain["edges"]))

        callers = [
            item["source"]
            for item in self.graph["edges"]
            if item["relation"] == "calls" and item["target"] == start_id
        ]
        path = query_graph(
            self.graph,
            {"mode": "path", "source_id": callers[0], "target_id": start_id},
        )
        self.assertTrue(path["nodes"])

        affected = query_graph(
            self.graph,
            {"mode": "affected", "source_id": start_id, "max_depth": 2},
        )
        self.assertTrue(any(item["id"] in callers for item in affected["nodes"]))
        self.assertTrue(all("source_location" in item for item in affected["edges"]))

        target_file = next(
            item["id"]
            for item in self.graph["nodes"]
            if item["kind"] == "file" and item["source_file"] == "src/B.java"
        )
        file_impact = query_graph(
            self.graph,
            {"mode": "affected", "source_id": target_file, "max_depth": 2},
        )
        self.assertTrue(any(item["id"] in callers for item in file_impact["nodes"]))

        truncated = query_graph(
            self.graph,
            {"mode": "bfs", "source_id": start_id, "max_nodes": 1, "max_edges": 1, "max_chars": 500},
        )
        self.assertTrue(truncated["truncated"])

    def test_query_rejects_invented_vocab_and_returns_name_ambiguity(self) -> None:
        missing = query_graph(self.graph, {"mode": "search", "tokens": ["invented-token"]})
        self.assertEqual(missing["nodes"], [])
        self.assertIn("not present in graph vocabulary", missing["diagnostics"][0])

        ambiguous = query_graph(self.graph, {"mode": "search", "tokens": ["run"]})
        self.assertGreaterEqual(len(ambiguous["ambiguities"]), 1)


if __name__ == "__main__":
    unittest.main()
