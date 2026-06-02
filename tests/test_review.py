import pytest
import ast
from pathlib import Path
from github_integration import parse_pr_url, GitHubPRInfo
from diff_parser import (
    parse_unified_diff,
    review_unified_diff,
    _reconstruct_new_file_source,
    _reconstruct_modified_file_source
)
from review_engine import (
    _find_hallucinated_imports,
    _find_dead_code,
    _find_unnecessary_abstractions,
    _find_duplicate_logic,
    _find_suspicious_patterns
)

# --- test github_integration.py ---

def test_parse_pr_url_valid():
    urls = [
        "https://github.com/owner/repo/pull/123",
        "github.com/owner/repo/pull/123",
        "owner/repo/pull/123",
        "owner/repo#123",
        "owner/repo:123",
    ]
    for url in urls:
        info = parse_pr_url(url)
        assert info.owner == "owner"
        assert info.repo == "repo"
        assert info.pr_number == 123

def test_parse_pr_url_invalid():
    with pytest.raises(ValueError):
        parse_pr_url("invalid_url")
    with pytest.raises(ValueError):
        parse_pr_url("owner/repo/123")


# --- test review_engine.py rules ---

def test_find_hallucinated_imports():
    source = """
import sys
import not_a_real_module_abc_xyz
from os import path
from missing_package_xyz import something
"""
    tree = ast.parse(source)
    findings = _find_hallucinated_imports(tree)
    categories = [f.category for f in findings]
    messages = [f.message for f in findings]
    
    assert "Hallucinated import" in categories
    assert any("not_a_real_module_abc_xyz" in m for m in messages)
    assert any("missing_package_xyz" in m for m in messages)
    assert not any("sys" in m for m in messages)


def test_find_dead_code():
    source = """
def _dead_function_helper():
    return 42

def live_function_helper():
    return 100

def main():
    return live_function_helper()
"""
    tree = ast.parse(source)
    findings = _find_dead_code(tree)
    names = [f.message for f in findings]
    assert any("'_dead_function_helper' is defined but never referenced" in m for m in names)
    assert not any("live_function_helper" in m for m in names)


def test_find_unnecessary_abstractions():
    source = """
def wrapper_func(x):
    return real_func(x)

def complex_func(x):
    y = x + 1
    return real_func(y)
"""
    tree = ast.parse(source)
    findings = _find_unnecessary_abstractions(tree)
    categories = [f.category for f in findings]
    assert "Unnecessary abstraction" in categories
    assert any("wrapper_func" in f.message for f in findings)
    assert not any("complex_func" in f.message for f in findings)


def test_find_duplicate_logic():
    source = """
def calculate_double(x):
    return x * 2

def calculate_twice(x):
    return x * 2

def calculate_triple(x):
    return x * 3
"""
    tree = ast.parse(source)
    findings = _find_duplicate_logic(tree, source)
    categories = [f.category for f in findings]
    assert "Duplicate logic" in categories


def test_find_suspicious_patterns():
    source = """
# TODO: fix this later
def risky():
    try:
        do_something()
    except Exception:
        pass
"""
    tree = ast.parse(source)
    findings = _find_suspicious_patterns(tree, source)
    categories = [f.category for f in findings]
    assert "Suspicious AI-generated pattern" in categories
    assert any("broad exception handler swallows the error" in f.message for f in findings)
    assert any("TODO/FIXME" in f.message for f in findings)


# --- test diff_parser.py ---

def test_parse_unified_diff():
    diff_text = """diff --git a/file.py b/file.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/file.py
@@ -0,0 +1,4 @@
+import sys
+def add(a, b):
+    return a + b
"""
    patches = parse_unified_diff(diff_text)
    assert len(patches) == 1
    assert patches[0].new_path == "file.py"
    assert patches[0].old_path == "/dev/null"
    assert len(patches[0].hunks) == 1
    assert patches[0].hunks[0].added_lines == 3


def test_reconstruct_source():
    diff_text = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
 def func():
-    pass
+    # a comment
+    return 42
"""
    patches = parse_unified_diff(diff_text)
    assert len(patches) == 1
    source = _reconstruct_modified_file_source(patches[0])
    assert "def func():" in source
    assert "return 42" in source
    assert "pass" not in source


def test_review_unified_diff():
    diff_text = """diff --git a/file.py b/file.py
new file mode 100644
--- /dev/null
+++ b/file.py
@@ -0,0 +1,4 @@
+import not_a_real_module_abc_xyz
+def _unused_func():
+    try:
+        pass
+    except Exception:
+        pass
"""
    findings = review_unified_diff(diff_text)
    categories = [f.category for f in findings]
    assert "Hallucinated import" in categories
    assert "Suspicious AI-generated pattern" in categories
