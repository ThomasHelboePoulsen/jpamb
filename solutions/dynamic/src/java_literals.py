"""Find Java method literals and convert them into Python value pools."""

from collections import defaultdict
from pathlib import Path

import tree_sitter
import tree_sitter_java

import jpamb
import jvm

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())


def convert_literals(raw_literals: dict[str, list[bytes]]) -> dict[type, list]:
    """Convert the literal forms used in cases/jpamb/cases into Python pools.

    Characters and strings share the str pool. Each integer contributes both
    signs, since unary operators are not part of the collected literals.
    Other literal forms raise NotImplementedError so support can be added
    when a test case needs it.
    """
    literals = defaultdict(list)
    for category, values in raw_literals.items():
        for raw_value in values:
            text = raw_value.decode("utf-8")
            if category == "decimal_integer_literal":
                value = int(text)
            elif category in {"string_literal", "character_literal"}:
                if text.startswith('"""') or "\\" in text:
                    raise NotImplementedError("Escaped literals and text blocks are not supported")
                value = text[1:-1]
            elif category in {"true", "false"}:
                value = category == "true"
            elif category == "null_literal":
                value = None
            else:
                raise NotImplementedError(f"Unsupported literal category: {category}")
            literals[type(value)].append(value)

    integers = set(literals[int])
    literals[int] = sorted(integers | {-value for value in integers})
    return dict(literals)


def parse_java_source(srcfile: Path) -> tree_sitter.Tree:
    parser = tree_sitter.Parser(JAVA_LANGUAGE)
    return parser.parse(srcfile.read_bytes())


def find_class(root: tree_sitter.Node, class_name: str) -> tree_sitter.Node:
    class_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
        (class_declaration
            name: ((identifier) @class-name
                   (#eq? @class-name "{class_name}"))) @class
        """,
    )
    class_matches = tree_sitter.QueryCursor(class_q).captures(root).get("class", [])
    if len(class_matches) != 1:
        raise ValueError(
            f"Expected one class named {class_name}, "
            f"found {len(class_matches)}"
        )
    return class_matches[0]


def find_method(class_node: tree_sitter.Node, methodid: jvm.AbsMethodID) -> tree_sitter.Node:
    """Find a directly declared method by name and arity; reject ambiguous overloads."""
    simple_classname = str(methodid.classname.name)
    class_body = class_node.child_by_field_name("body")
    if class_body is None:
        raise ValueError(f"Class {simple_classname} has no body")

    method_name = methodid.extension.name
    method_matches = []
    for candidate in class_body.named_children:
        if candidate.type != "method_declaration":
            continue
        name_node = candidate.child_by_field_name("name")
        if name_node is None or name_node.text != method_name.encode("utf-8"):
            continue

        parameters = candidate.child_by_field_name("parameters")
        if parameters is None:
            continue
        parameter_count = sum(
            child.type in {"formal_parameter", "spread_parameter"}
            for child in parameters.named_children
        )
        if parameter_count == len(methodid.extension.params):
            method_matches.append(candidate)

    if len(method_matches) != 1:
        raise ValueError(
            f"Expected one method named {method_name} with "
            f"{len(methodid.extension.params)} parameters in {simple_classname}, "
            f"found {len(method_matches)}"
        )
    return method_matches[0]


def collect_literals(root: tree_sitter.Node) -> dict[str, list[bytes]]:
    """Group literal source text by syntax category, preserving traversal order."""
    literals: dict[str, list[bytes]] = defaultdict(list)

    def visit(node: tree_sitter.Node):
        if "literal" in node.type or node.type in {"true", "false"}:
            literals[node.type].append(node.text)

        for child in node.named_children:
            visit(child)

    visit(root)
    return literals


def get_literals_in_method(
    methodid: jvm.AbsMethodID, suite: jpamb.Suite
) -> dict[str, list[bytes]]:
    """Locate the requested method and collect its raw literals for conversion."""
    srcfile = suite.sourcefile(methodid.classname).relative_to(Path.cwd())
    tree = parse_java_source(srcfile)
    class_node = find_class(tree.root_node, str(methodid.classname.name))
    method_node = find_method(class_node, methodid)
    body = method_node.child_by_field_name("body")
    if body is None:
        raise ValueError(f"Method {methodid.extension.name} has no body")
    return collect_literals(body)
