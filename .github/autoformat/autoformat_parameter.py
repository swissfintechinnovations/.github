#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.width = 170
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.default_flow_style = False

PARAM_ORDER = ["in", "name", "description", "required", "schema"]


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


def looks_like_parameter(obj: Any) -> bool:
    if not is_map(obj):
        return False
    return ("$ref" in obj) or (("in" in obj or "name" in obj) and ("schema" in obj or "required" in obj or "description" in obj))


def sort_parameter_obj(param: CommentedMap) -> CommentedMap:
    if "$ref" in param and len(param.keys()) == 1:
        return param
    return reorder_map(param, PARAM_ORDER)


def walk(node: Any) -> Any:
    if is_map(node):
        # components.parameters.*
        if "components" in node and is_map(node["components"]):
            comps = node["components"]
            if "parameters" in comps and is_map(comps["parameters"]):
                for k, v in list(comps["parameters"].items()):
                    if is_map(v):
                        comps["parameters"][k] = sort_parameter_obj(v)

        for k, v in list(node.items()):
            if k == "parameters" and isinstance(v, list):
                new_list = []
                changed = False
                for item in v:
                    if is_map(item) and looks_like_parameter(item):
                        new_list.append(sort_parameter_obj(item))
                        changed = True
                    else:
                        new_list.append(walk(item))
                if changed:
                    node[k] = new_list
            else:
                node[k] = walk(v)
        return node

    if isinstance(node, list):
        for i, item in enumerate(node):
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
            print(f"Parameters sorted: {p}")
        except Exception as e:
            rc = 2
            print(f"ERR {p}: {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
