# HNG Frontier 0.7.0rc2

This release candidate contains one failure-driven production change. ToolAgentAdapter.execute now
forwards optional temporal validity and access/perspective context when it records tool outcomes.
All added parameters are optional and the SQLite schema is unchanged.

The change follows a preserved 108-episode executing result in which the untouched adapter scored
29.6%, made 18 irreversible mistakes, and performed worse than agent alone because v1 outcomes
remained globally applicable in later API versions. With contextual outcomes, HNG scores 63.9%,
makes zero irreversible mistakes, and exactly ties StrongStructuredBaseline while remaining slower.

Qualifying artifacts are under final_dist and pinned in RELEASE_MANIFEST.json. The first build is
preserved under dist but excluded because its source distribution omitted the changelog and
migration guide.
