#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.width = 10**9
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.default_flow_style = False

SCHEMA_ORDER = [
    "title",
    "summary",
    "description",
    "$ref",
    "type",
    "format",
    "required",
    "properties",
    "enum",
    "minimum",
    "minLength",
    "maximum",
    "maxLength",
    "pattern",
    "example",
    "examples",
]


def is_map(x: Any) -> bool:
    return isinstance(x, CommentedMap)


def reorder_map(src: CommentedMap, keys_in_order: list[str]) -> CommentedMap:
    out = CommentedMap()
    for k in keys_in_order:
        if k in src:
            out[k] = src[k]
            try:
                out.ca.items[k] = src.ca.items.get(k)
            except Exception:
                pass
    for k in src:
        if k not in out:
            out[k] = src[k]
            try:
                out.ca.items[k] = src.ca.items.get(k)
            except Exception:
                pass
    try:
        out.ca.comment = src.ca.comment
        out.ca.end = src.ca.end
    except Exception:
        pass
    return out


def looks_like_schema(obj: Any) -> bool:
    if not is_map(obj):
        return False
    schema_keys = {"$ref", "type", "properties", "required", "enum", "allOf", "oneOf", "anyOf", "items", "additionalProperties"}
    return any(k in obj for k in schema_keys)


def sort_required_list(req: Any) -> Any:
    if isinstance(req, list):
        return sorted(req)
    return req


def reorder_properties(props: Any, required: list[str] | None) -> Any:
    if not is_map(props):
        return props
    required = required or []
    required_set = set(required)

    req_keys = sorted([k for k in props.keys() if k in required_set])
    opt_keys = sorted([k for k in props.keys() if k not in required_set])

    return reorder_map(props, req_keys + opt_keys)


def sort_schema_obj(schema: CommentedMap) -> CommentedMap:
    # $ref-only Schema nicht umbauen
    if "$ref" in schema and len(schema.keys()) == 1:
        return schema

    out = reorder_map(schema, SCHEMA_ORDER)

    # required sortieren
    if "required" in out:
        out["required"] = sort_required_list(out["required"])

    # properties: required-first
    req_list = out.get("required")
    req_list = req_list if isinstance(req_list, list) else []
    if "properties" in out:
        out["properties"] = reorder_properties(out["properties"], req_list)

    return out


def walk(node: Any) -> Any:
    if is_map(node):
        if "components" in node and is_map(node["components"]):
            comps = node["components"]
            if "schemas" in comps and is_map(comps["schemas"]):
                for k, v in list(comps["schemas"].items()):
                    if is_map(v):
                        comps["schemas"][k] = sort_schema_obj(v)

        for k, v in list(node.items()):
            if k == "schema" and is_map(v) and looks_like_schema(v):
                node[k] = sort_schema_obj(v)
            else:
                node[k] = walk(v)
        return node

    if isinstance(node, list):
        for i, item in enumerate(node):
            if is_map(item) and looks_like_schema(item):
                node[i] = sort_schema_obj(item)
            else:
                node[i] = walk(item)
        return node

    return node


def load_yaml(p: Path) -> CommentedMap:
    with p.open("r", encoding="utf-8") as f:
        doc = yaml.load(f)
    if not is_map(doc):
        raise SystemExit(f'ERROR: YAML root must be a mapping/object in "{p}".')
    return doc


def save_yaml(p: Path, doc: CommentedMap) -> None:
    with p.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"Usage: {argv[0]} <spec.yaml> [more.yaml ...]", file=sys.stderr)
        return 1

    rc = 0
    for fn in argv[1:]:
        p = Path(fn)
        try:
            doc = load_yaml(p)
            doc = walk(doc)
            save_yaml(p, doc)
            print(f"Schemas sorted: {p}")
        except Exception as e:
            rc = 2
            print(f"ERR {p}: {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
