"""Prevent new JavaScript syntax from silently breaking the embedded browser."""

from pathlib import Path

import esprima

WEB = Path(__file__).resolve().parents[1] / "web"


def test_frontend_stays_within_es5_syntax():
    forbidden = {"ArrowFunctionExpression", "TemplateLiteral", "ClassDeclaration",
                 "ClassExpression", "SpreadElement", "RestElement", "AwaitExpression",
                 "YieldExpression", "ForOfStatement", "ImportDeclaration", "ExportNamedDeclaration",
                 "ObjectPattern", "ArrayPattern", "AssignmentPattern"}

    def walk(node):
        if isinstance(node, dict):
            assert node.get("type") not in forbidden
            if node.get("type") == "VariableDeclaration":
                assert node["kind"] == "var"
            if node.get("type") == "Property":
                assert not node.get("shorthand") and not node.get("method") and not node.get("computed")
            assert not node.get("async") and not node.get("generator")
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for path in WEB.glob("*.js"):
        walk(esprima.parseScript(path.read_text(encoding="utf-8")).toDict())
