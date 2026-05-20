# legacy/

Code preserved here for traceability is **not part of the
`lp2graph` package**. It is the verbatim first-pass extraction from
[`joernmht/raiLPminerExperimentation`](https://github.com/joernmht/raiLPminerExperimentation)
(MIT). It is excluded from the build, from CI lint and type-check, and
from runtime imports.

The new canonical model in `src/lp2graph/` is the source of truth. Once
the catalog is fully migrated and the legacy code has no diagnostic
value, this directory will be removed.

See `docs/extraction-report.md` for the disposition of every file.
