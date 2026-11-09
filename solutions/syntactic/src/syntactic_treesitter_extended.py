#!/usr/bin/env python3
"""A very stupid syntactic analysis, that only checks for assertion errors."""

import logging
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_java

import jpamb


def main():
    methodid = jpamb.getmethodid(
        "syntaxer",
        "1.0",
        "Bit Diddlers",
        ["syntactic", "python"],
        for_science=True,
    )

    JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(JAVA_LANGUAGE)

    log = logging
    log.basicConfig(level=logging.DEBUG)

    suite, _ = jpamb.setup()

    srcfile = suite.sourcefile(methodid.classname).relative_to(Path.cwd())

    with open(srcfile, "rb") as f:
        log.debug("parse sourcefile %s", srcfile)
        tree = parser.parse(f.read())

    simple_classname = str(methodid.classname.name)

    log.debug(f"{simple_classname}")

    # To figure out how to write these you can consult the
    # https://tree-sitter.github.io/tree-sitter/playground
    class_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
        (class_declaration 
            name: ((identifier) @class-name 
                   (#eq? @class-name "{simple_classname}"))) @class
    """,
    )

    for node in tree_sitter.QueryCursor(class_q).captures(tree.root_node)["class"]:
        break
    else:
        log.error(f"could not find a class of name {simple_classname} in {srcfile}")

        sys.exit(-1)

    # log.debug("Found class %s", node.range)

    method_name = methodid.extension.name

    method_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
        (method_declaration name: 
          ((identifier) @method-name (#eq? @method-name "{method_name}"))
        ) @method
    """,
    )

    method_node = None
    for snode in tree_sitter.QueryCursor(method_q).captures(node)["method"]:
        if not (p := snode.child_by_field_name("parameters")):
            log.debug(f"Could not find parameteres of {method_name}")
            continue

        params = [c for c in p.children if c.type == "formal_parameter"]

        if len(params) != len(methodid.extension.params):
            continue

        # log.debug(methodid.extension.params)
        # log.debug(params)

        for tn, t in zip(methodid.extension.params, params):
            if (tp := t.child_by_field_name("type")) is None:
                break

            if tp.text is None:
                break

            # todo check for type.
        else:
            method_node = snode
            break
    else:
        log.warning(
            f"could not find a method of name {method_name} in {simple_classname}"
        )
        sys.exit(-1)

    # log.debug("Found method %s %s", method_name, node.range)

    assert method_node is not None
    body = method_node.child_by_field_name("body")
    assert body and body.text
    for t in body.text.splitlines():
        log.debug("line: %s", t.decode())

    def has_capture(query: str, capture: str) -> bool:
        captures = tree_sitter.Query(
            JAVA_LANGUAGE, query
        )
        return bool(
            tree_sitter.QueryCursor(captures).captures(body).get(capture)
        )

    assert_found = has_capture("(assert_statement) @assert", "assert")
    divide_found = has_capture(
        '(binary_expression operator: "/") @divide', "divide"
    )
    infinite_loop_found = has_capture(
        """
        (while_statement
          condition: (parenthesized_expression
            (true)))
        @infinite-loop
        """,
        "infinite-loop",
    )
    null_found = has_capture("(null_literal) @null", "null")

    array_access_query = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (array_access
          index: (_) @index) @array-access
        """,
    )
    array_accesses = tree_sitter.QueryCursor(array_access_query).captures(body)
    out_of_bounds_found = any(
        node.type != "decimal_integer_literal"
        or node.text not in {b"0"}
        for node in array_accesses.get("index", [])
    )

    results = {
        "assertion error": assert_found,
        "divide by zero": divide_found,
        "null pointer": null_found,
        "out of bounds": out_of_bounds_found,
        "*": infinite_loop_found,
    }
    for query in jpamb.QUERIES:
        if query in results:
            print(f"{query};{'found' if results[query] else 'not-found'}")
        else:
            print(f"{query};skip")

    sys.exit(0)
