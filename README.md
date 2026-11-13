<p align="center">
  <img src="assets/banner.svg" alt="sqldelta banner" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-2dd4bf?style=for-the-badge" alt="python">
  <img src="https://img.shields.io/badge/SQLite-diff-6366f1?style=for-the-badge" alt="sqlite">
  <img src="https://img.shields.io/badge/dependencies-zero-a78bfa?style=for-the-badge" alt="zero deps">
  <img src="https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge" alt="MIT">
</p>

**sqldelta** compares two SQLite databases and tells you exactly what changed: tables, columns, indexes and individual rows. Think `git diff` for your database.

## Why

"What did that migration actually do?" "Why does staging differ from production?" "What did the app write during this test?" Snapshot the file before and after, run sqldelta, and read the answer.

## Usage

```bash
python sqldelta.py before.db after.db
python sqldelta.py before.db after.db --no-data          # schema only
python sqldelta.py before.db after.db --tables users     # data for one table
python sqldelta.py before.db after.db --samples 20       # more example rows
python sqldelta.py before.db after.db --json             # for scripts
```

Sample output:

```
SCHEMA
  + table audit_log
  ~ table users
      + column last_login (TEXT)
      ~ column email: type=TEXT, notnull=0 -> type=TEXT, notnull=1

DATA
  users  (key: id)  +2 -1 ~3
      added    id=41
      removed  id=7
      changed  id=3  (email: 'a@x.io' -> 'b@x.io')
```

## What it compares

| Area | Detected |
|------|----------|
| Tables | added, removed |
| Columns | added, removed, type / NOT NULL / default / primary key changes |
| Indexes | added, removed, definition changed |
| Rows | added, removed, changed, matched by primary key (or `rowid` if none) |

## Safe by design

Both files are opened **read-only**. Your databases are never modified.

## Exit codes

`0` identical, `1` differences found. Handy in tests and CI:

```bash
python sqldelta.py expected.db actual.db --no-data || echo "schema drift!"
```

## Notes

- Rows are loaded into memory, so it is meant for small to medium databases.
- Only columns present on both sides are compared for row changes; column additions and removals show up in the schema section.
- Views and triggers are not compared yet.

## License

MIT
