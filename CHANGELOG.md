# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-08-05

### Added
- Trash (soft delete): deleting a database or project from the web UI no
  longer removes it for good — the item is moved to a trash directory
  (`<data_dir>/trash/`) and can be restored from a new dedicated Trash page
  (drawer entry "Trash"). Restoring into an occupied name asks the user and,
  on "Continue", moves the existing live object into the trash itself so
  nothing is ever permanently deleted. Missing parent projects are recreated
  automatically. Emptying the trash is destructive and guarded by a
  confirmation dialog. Deleting a database also removes its stored API
  password, so a restored database starts without credentials and the admin
  must set a new password. The REST API (`/db/*`, `/admin/*`) is unchanged —
  REST deletes remain permanent. Trashed projects list their contained
  databases on the Trash page.
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
- Dashboard landing page: four stat cards (server online, projects, databases,
  trash with object count), a live traffic monitor showing REST API database
  accesses per minute (rolling 60-second window) plus active UI sessions, and
  a storage overview table with per-project sizes and a trash line. The
  traffic counter only counts authenticated database API calls (query, write,
  tables, import, export) — GUI, admin and metadata endpoints are excluded.
- `webduck user` CLI command group for managing admin users on an existing
  data directory: `webduck user add <name> <password>`, `webduck user list`
  and `webduck user delete <name>`. Deleting the last remaining admin user
  asks for confirmation first (an admin can always be recreated via
  `webduck init`). `user delete` also removes the deleted user's stored
  preferences and query history. There is no role concept yet — every user
  is an admin.
- Startup sweep for stale query history: on server start, history entries
  whose project/database no longer exists — and is not in the trash either —
  are removed. This catches objects deleted before the targeted cleanup
  existed or removed directly on the server. History for live or restorable
  objects is never touched.
- Permanent delete of individual trash entries: each entry in the trash can
  be deleted for good (with confirmation) in addition to emptying the whole
  trash.

### Changed
- Query history is now removed in a targeted way only when a project/database
  is permanently deleted — periodic pruning was removed. Final deletes
  (permanent delete in the trash, emptying the trash, REST hard-delete) clean
  up the affected history entries; deleting a user removes their preferences
  and query history.
- Deleted users are blocked in the Web UI immediately: page guards and action
  handlers re-check that the logged-in user still exists and redirect to the
  login page otherwise. The REST API is unchanged.

### Fixed
- Success toasts on the projects and trash pages were wiped by the
  immediate page reload after the action (create/delete project or database,
  set password, restore, empty trash) and were never visible. The message is
  now queued in the user session and shown once after the reloaded page has
  rendered.
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
