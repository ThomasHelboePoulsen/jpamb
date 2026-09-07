#!/usr/bin/env python3
"""A very stupid syntactic analysis, that only checks for assertion errors."""

import logging
import re
import sys
from pathlib import Path

import jpamb


def main():
    absmethodid = jpamb.getmethodid(
        "syntaxer",
        "1.0",
        "Bit Diddlers",
        ["syntactic", "python"],
        for_science=True,
    )

    log = logging
    log.basicConfig(level=logging.DEBUG)
    log.debug(Path.cwd())

    suite, _ = jpamb.setup()

    srcfile = suite.sourcefile(absmethodid.classname).relative_to(Path.cwd())

    with open(srcfile, "r") as f:
        log.debug("parse sourcefile %s", srcfile)
        content = f.read()

    res = re.search(rf".* {absmethodid.methodid.name}\(.*\)", content)

    if not res:
        log.error("Could not find method")
        sys.exit(1)

    log.debug(f"found {res}")
    rest = content[res.end(0) : -1]

    assert_or_end = re.search(r"assert|(^\s*})", rest, re.MULTILINE)

    if not assert_or_end:
        log.error("Could not end of method or assert")
        log.error(rest)
        sys.exit(1)

    log.debug(f"found {assert_or_end}")
    assert_found = assert_or_end.group(0) == "assert"

    if assert_found:
        log.debug("Found assertion")
        print("assertion error;found")
    else:
        log.debug("No assertion")
        print("assertion error;not-found")

    divide_or_end = re.search(r"/|(^\s*})", rest, re.MULTILINE)

    if not divide_or_end:
        log.error("Could not find end of method or divide")
        log.error(rest)
        sys.exit(1)

    log.debug(f"found divide {divide_or_end}")
    divide_found = divide_or_end.group(0) == "/"

    if divide_found:
        log.debug("Found divide")
        print("divide by zero;found-div")
    else:
        log.debug("No divide")
        print("divide by zero;not-found-div")


    array_or_end = re.search(r"\w+\[.+?\]|(^\s*})", rest, re.MULTILINE)
    if not array_or_end:
        log.error("Could not find end of method or array")
        log.error(rest)
        sys.exit(1)
    log.debug(f"found array {array_or_end}")

    array_found = "[" in array_or_end.group(0)
    if array_found:
          log.debug("Found array")
          print("out of bounds;found-array")
    else:
          log.debug("No array")
          print("out of bounds;not-found-array")

    null_or_end = re.search(r"\.|null|(^\s*})",rest,re.MULTILINE)
    if not null_or_end:
        log.error ("Could not find end of method or null")
        log.error(rest)
        sys.exit(1)
    log.debug(f"found possible null {null_or_end}")
    null_found = "null" in null_or_end.group(0) or "." in null_or_end.group(0)
    if null_found:
        log.debug("found null")
        print("null pointer;found-null")
    else:
        log.debug("No null")
        print("null pointer;not-found-null")
    
    while_or_end = re.search(r"while|(^\s*})",rest,re.MULTILINE)
    if not while_or_end:
        log.error ("Could not find end of method or while")
        log.error(rest)
        sys.exit(1)
    while_found = "while" in while_or_end.group(0)
    if while_found:
        log.debug ("found while")
        print("*;found-while")
    else:
        log.debug("No while")
        print("*;not-found-while")
    
    for q in jpamb.QUERIES:
        if q not in ["assertion error","divide by zero","out of bounds","null pointer","*"]:
            print(f"{q};skip")
