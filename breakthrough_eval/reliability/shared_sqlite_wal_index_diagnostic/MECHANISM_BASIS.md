# SQLite WAL-index mechanism basis

This diagnostic's 32 KiB unit hypothesis comes from primary SQLite technical
documentation, not from the preceding measurements.

- SQLite's official WAL-mode format specifies that the `-shm` WAL-index file is
  memory mapped by clients, consists of one or more hash tables of 32,768 bytes,
  and always has a size that is a multiple of 32,768 bytes:
  <https://sqlite.org/walformat.html>.
- SQLite's official WAL implementation source defines `WALINDEX_PGSZ`, maps
  each required WAL-index page through `sqlite3OsShmMap`, and asserts that the
  page size is 32,768 bytes:
  <https://www3.sqlite.org/matrix/ev/src/wal.html>.
- SQLite's official file-format documentation identifies the memory-mapped file
  as the database filename with the `-shm` suffix:
  <https://www2.sqlite.org/fileformat2.html>.

The prior valid Windows diagnostic independently found that every shared child
gained exactly 48 `Section` objects while controls gained none. Because a
Windows Section is a kernel memory-mapping object, the frozen experiment tests
whether per-process Section growth numerically matches growth in 32 KiB units
of the shared database's `-shm` WAL-index file.
