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
        "The Rice Theorem Cookers",
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
    
    # Check for assertion errors 

    assert_or_end = re.search(r"assert|>|(^\s*})", rest, re.MULTILINE)

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
        
    # Check for divide by zero errors

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
        
    
    # find null pointer errors
    
    null_or_end = re.search(r"null|(^\s*})", rest, re.MULTILINE)
    
    if not null_or_end:
        log.error("Could not find end of method or null")
        log.error(rest)
        sys.exit(1)

    log.debug(f"found null {null_or_end}")
    null_found = null_or_end.group(0) == "null"

    if null_found:
        log.debug("Found null")
        print("null pointer;found-null")
    else:
        log.debug("No null")
        print("null pointer;not-found-null")
        
    # loop true check
    
    loop_or_end = re.search(r"loop|for|(^\s*})", rest, re.MULTILINE)
    
    if not loop_or_end:
        log.error("Could not find end of method or loop true")
        log.error(rest)
        sys.exit(1)
        
    log.debug(f"found loop {loop_or_end}")
    loop_found = loop_or_end.group(0) == "loop true"
    
    if loop_found:
        log.debug("Found loop true")
        print("*;found-loop")
    else:
        log.debug("No loop true")
        print("*;not-found-loop")
        
    # check for out of bounds (essentially check for array)
    
    array_or_end = re.search(r"\[|\]|for|(^\s*})", rest, re.MULTILINE)
    
    if not array_or_end:
        log.error("Could not find end of method or array")
        log.error(rest)
        sys.exit(1)
    
    log.debug(f"found array {array_or_end}")
    array_found = array_or_end.group(0) == "[" or array_or_end.group(0) == "]"
    
    if array_found:
        log.debug("Found array")
        print("out of bounds;found-array")
    else:
        log.debug("No array")
        print("out of bounds;not-found-array")
        
    
    # MUST BE LAST PIECE OF CODE
    
    for q in jpamb.QUERIES:
        if q != "assertion error" and q != "divide by zero" and q != "null pointer" and q != "*" and q != "out of bounds":
            print(f"{q};skip")
            
    