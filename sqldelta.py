#!/usr/bin/env python3
"""sqldelta: diff two SQLite databases, schema and data."""
import argparse
import json
import os
import sqlite3
import sys
import urllib.parse

RED, GREEN, YELLOW, DIM, RESET = "\033[91m", "\033[92m", "\033[93m", "\033[2m", "\033[0m"


def connect(path):
    if not os.path.isfile(path):
        sys.exit(f"error: no such file: {path}")
    uri = "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def tables(con):
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def columns(con, table):
    # PRAGMA table_info rows: cid, name, type, notnull, dflt_value, pk
    return {r[1]: {"type": r[2], "notnull": r[3], "default": r[4], "pk": r[5]}
            for r in con.execute(f"PRAGMA table_info({q(table)})")}


def indexes(con, table):
    return {r[0]: r[1] for r in con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' "
        "AND tbl_name=? AND sql IS NOT NULL", (table,))}


def fmt_col(c):
    return ", ".join(f"{k}={v}" for k, v in c.items())


def schema_diff(a, b):
    ta, tb = set(tables(a)), set(tables(b))
    out = {"tables_added": sorted(tb - ta), "tables_removed": sorted(ta - tb), "changed": {}}
    for t in sorted(ta & tb):
        ca, cb = columns(a, t), columns(b, t)
        ch = []
        for c in sorted(set(cb) - set(ca)):
            ch.append(f"+ column {c} ({cb[c]['type']})")
        for c in sorted(set(ca) - set(cb)):
            ch.append(f"- column {c} ({ca[c]['type']})")
        for c in sorted(set(ca) & set(cb)):
            if ca[c] != cb[c]:
                ch.append(f"~ column {c}: {fmt_col(ca[c])} -> {fmt_col(cb[c])}")
        ia, ib = indexes(a, t), indexes(b, t)
        for i in sorted(set(ib) - set(ia)):
            ch.append(f"+ index {i}")
        for i in sorted(set(ia) - set(ib)):
            ch.append(f"- index {i}")
        for i in sorted(set(ia) & set(ib)):
            if ia[i] != ib[i]:
                ch.append(f"~ index {i} definition changed")
        if ch:
            out["changed"][t] = ch
    return out


def load_rows(con, table, key_cols, val_cols):
    sel = ", ".join([q(c) for c in key_cols] if key_cols else ["rowid"])
    if val_cols:
        sel += ", " + ", ".join(q(c) for c in val_cols)
    nk = len(key_cols) or 1
    rows = {}
    for r in con.execute(f"SELECT {sel} FROM {q(table)}"):
        rows[tuple(r[:nk])] = tuple(r[nk:])
    return rows


def data_diff(a, b, table, samples):
    ca, cb = columns(a, table), columns(b, table)
    common = [c for c in cb if c in ca]
    pk = sorted((c for c in common if ca[c]["pk"] and cb[c]["pk"]),
                key=lambda c: cb[c]["pk"])
    vals = [c for c in common if c not in pk]
    ra, rb = load_rows(a, table, pk, vals), load_rows(b, table, pk, vals)

    def label(k):
        return ", ".join(f"{n}={v}" for n, v in zip(pk or ["rowid"], k))

    added = sorted(set(rb) - set(ra), key=str)
    removed = sorted(set(ra) - set(rb), key=str)
    changed = []
    for k in sorted(set(ra) & set(rb), key=str):
        if ra[k] != rb[k]:
            diffs = [f"{c}: {x!r} -> {y!r}" for c, x, y in zip(vals, ra[k], rb[k]) if x != y]
            changed.append((k, diffs))
    return {
        "key": pk or ["rowid"],
        "added": len(added), "removed": len(removed), "changed": len(changed),
        "samples": {
            "added": [label(k) for k in added[:samples]],
            "removed": [label(k) for k in removed[:samples]],
            "changed": [f"{label(k)}  ({'; '.join(d)})" for k, d in changed[:samples]],
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Diff two SQLite databases.")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--no-data", action="store_true", help="schema only")
    ap.add_argument("--tables", nargs="+", help="limit data diff to these tables")
    ap.add_argument("--samples", type=int, default=5, help="example rows per kind")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    a, b = connect(args.old), connect(args.new)
    schema = schema_diff(a, b)
    data = {}
    if not args.no_data:
        common = sorted(set(tables(a)) & set(tables(b)))
        for t in common:
            if args.tables and t not in args.tables:
                continue
            d = data_diff(a, b, t, args.samples)
            if d["added"] or d["removed"] or d["changed"]:
                data[t] = d

    has_diff = bool(schema["tables_added"] or schema["tables_removed"]
                    or schema["changed"] or data)

    if args.json:
        print(json.dumps({"schema": schema, "data": data}, indent=2, default=str))
    else:
        print(f"{DIM}old: {args.old}\nnew: {args.new}{RESET}\n\nSCHEMA")
        if not (schema["tables_added"] or schema["tables_removed"] or schema["changed"]):
            print(f"  {GREEN}identical{RESET}")
        for t in schema["tables_added"]:
            print(f"  {GREEN}+ table {t}{RESET}")
        for t in schema["tables_removed"]:
            print(f"  {RED}- table {t}{RESET}")
        for t, lines in schema["changed"].items():
            print(f"  {YELLOW}~ table {t}{RESET}")
            for l in lines:
                print(f"      {l}")
        if not args.no_data:
            print("\nDATA")
            if not data:
                print(f"  {GREEN}identical{RESET}")
            for t, d in data.items():
                print(f"  {t}  (key: {', '.join(d['key'])})  "
                      f"{GREEN}+{d['added']}{RESET} {RED}-{d['removed']}{RESET} "
                      f"{YELLOW}~{d['changed']}{RESET}")
                for kind, color in (("added", GREEN), ("removed", RED), ("changed", YELLOW)):
                    for s in d["samples"][kind]:
                        print(f"      {color}{kind:<8}{RESET} {s}")
    sys.exit(1 if has_diff else 0)


if __name__ == "__main__":
    main()
