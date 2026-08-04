# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-08-02

### Added
- Database compression ("compact") in the Web UI: each database can be
  compacted via a dedicated button, reclaiming space DuckDB leaves behind
  after updates/deletes. Handles foreign keys correctly by copying tables in
  FK dependency order (duckdb#16785/#24215) and self-referential foreign keys
  row-by-row (duckdb#7168); shows a hint when nothing could be reclaimed.
- Icon buttons replace the text buttons in the projects view for deleting a
  database or project and for creating a project or database (tooltips
  retained).
- Query history: the SQL editor stores the last 20 successful queries per
  user, project and database. Recall them with Alt+Up/Alt+Down (shell-style)
  or via the history panel below the editor; duplicates move to the top
  instead of piling up, and running queries with Alt+Enter is supported.
- Database size display in the projects view: the file size is shown next to
  each database name, formatted with decimal units so it matches file
  managers like the macOS Finder and Windows Explorer.
- Compress recommendation: the compress icon next to a database lights up
  amber when fragmentation (free/total blocks) reaches 20 % in databases of
  at least 10 MB, with a tooltip hinting that compression is recommended; the
  icon turns grey again after a successful compact.
- SQL editor shortcut hint as a tooltip on the "SQL" label (Alt+Enter to run
  the query, Alt+Up/Alt+Down to browse the history).

### License
- Starting with version 1.4.0, WebDuck is licensed under the GNU Affero General
  Public License v3.0 (AGPLv3, "or any later version").

## [1.3.0] - 2026-08-01

### Added
- Parallel reads over the REST API: read-only connections to the same
  database now run concurrently (per-file reader-writer lock with writer
  preference).

### Changed
- REST API endpoints (`/db/*`, `/admin/*`) offload blocking engine calls to
  a threadpool via `asyncio.to_thread`, keeping the event loop free.
- Writes remain serialized (DuckDB single-writer model); the exclusive lock
  guarantees a read-only and a read-write connection never overlap.
