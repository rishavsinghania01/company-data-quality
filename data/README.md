# Data

`naics_crosswalk_2012_2022.csv` is the published Census concordance between the
2012 and 2022 NAICS vintages. 1,069 rows, public domain.

The company records the pipeline reads are not committed. They are produced by
`cdq.generate` on each run from a fixed seed, so two runs on the same seed give
byte identical files. See the "Source data" section of the top level README for
why the records are synthesised and what dirt is deliberately present in them.
