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
- Icon buttons in the projects view replace text buttons (tooltips retained).

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
