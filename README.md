# Company data quality pipeline

[![CI](https://github.com/rishavsinghania01/company-data-quality/actions/workflows/ci.yml/badge.svg)](https://github.com/rishavsinghania01/company-data-quality/actions/workflows/ci.yml)

An Airflow pipeline for company records held in two source systems. It cleans
the fields and works out which records describe the same company. It then
scores that matching against labelled truth, loads the result into a warehouse
with dbt and publishes a quality scorecard.

The source records are synthetic (see [Source data](#source-data)). They
reproduce what happens whenever two systems hold the same customers: the same
company is spelled four ways, the phone number is in six formats, half the
industry codes are on a NAICS vintage retired in 2022, and nobody can say how
many distinct companies there are.

```
generate_sources -> load_raw_tables -> normalise_fields -> resolve_entities -> evaluate_resolution -> dbt_build -> quality_report
```

## What a run produces

From 3,380 source records that describe 2,000 real companies:

| Entity resolution | Value |
|---|---|
| Distinct companies after resolution | 2,028 (truth: 2,000) |
| Clusters holding more than one record | 1,232 |
| Largest cluster | 3 records |
| Pairwise precision | 1.0000 |
| Pairwise recall | 0.9787 |
| F1 | 0.9892 |
| False merges (two companies in one cluster) | 0 |
| Missed pairs (one company across two clusters) | 32, across 28 companies |

| Field quality | Value |
|---|---|
| NAICS codes remapped from 2012 to 2022 | 459 |
| NAICS codes on a 2012 industry that was split, so not mappable from the record alone | 12 |
| NAICS codes not found in either vintage | 139 |
| Phone numbers present but too short to be valid | 526 |
| Phone numbers missing entirely | 137 |

CI checks every number in these tables on each push, against the warehouse the
pipeline has just built. If the code drifts from the README, the build goes
red.

The quality scorecard is the table a person reads:

| source_system | field | dimension | records_checked | records_passed | pass_rate_pct |
|---|---|---|---|---|---|
| crm_export | name | completeness | 1736 | 1736 | 100.00 |
| crm_export | phone | validity | 1736 | 1394 | 80.30 |
| crm_export | address | completeness | 1736 | 1652 | 95.16 |
| crm_export | naics | validity | 1736 | 1659 | 95.56 |
| registry_extract | name | completeness | 1644 | 1644 | 100.00 |
| registry_extract | phone | validity | 1644 | 1323 | 80.47 |
| registry_extract | address | completeness | 1644 | 1578 | 95.99 |
| registry_extract | naics | validity | 1644 | 1570 | 95.50 |

A full run takes about half a minute on a laptop, most of it the threshold
sweep described below.

## How accuracy is measured

Entity resolution is scored on pairs of records. Two records that belong to the
same real company are a true pair, and two records the resolver put in one
cluster are a predicted pair. Precision is the share of predicted pairs that
are real and recall is the share of real pairs the resolver found. A false
merge creates predicted pairs that are not real and costs precision. A company
split across clusters leaves real pairs unpredicted and costs recall.

The labels come from the generator. It writes `ground_truth.csv` next to the
two source extracts, mapping every record id to the company it was generated
from, duplicates included. The resolver never reads that file, and a real
source can supply its own labelled pairs in the same shape. The arithmetic is
in `src/cdq/evaluate.py`, a pure function unit tested on five records.
`evaluate_resolution` in `src/cdq/pipeline.py` writes three tables:
`quality.resolution_accuracy` (the figures above), `quality.resolution_errors`
(every wrong pair with both raw names and its score, so each miss can be read)
and `quality.resolution_threshold_sweep`:

| threshold | clusters | precision | recall | F1 | false merges | missed pairs |
|---|---|---|---|---|---|---|
| 0.60 | 2000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| 0.65 | 2000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| 0.70 | 2000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| 0.75 | 2028 | 1.0000 | 0.9787 | 0.9892 | 0 | 32 |
| **0.80** | **2028** | **1.0000** | **0.9787** | **0.9892** | **0** | **32** |
| 0.85 | 2471 | 1.0000 | 0.6602 | 0.7954 | 0 | 511 |
| 0.90 | 2471 | 1.0000 | 0.6602 | 0.7954 | 0 | 511 |
| 0.95 | 2551 | 1.0000 | 0.5984 | 0.7488 | 0 | 604 |

### The 32 misses

Every one of them scores exactly 0.70. The names are identical after
normalisation, one record's phone number failed validation (too short, or
missing) and one record's address is missing. The name is the only evidence
left, and 0.70 does not clear 0.80. Blocking is not the cause: at 0.70 recall
is 1.0, so every real pair is compared, and lowering the threshold to 0.70
would find all 32.

### Why the threshold stays at 0.80

Precision is 1.0 at every threshold down to 0.60, and that says more about the
generated data than about the resolver. The generator builds company names from
a region, a base name and a segment, so two different companies in the same
state never share a full name and a name-only match of 0.70 is always right
here.

Real data has "Acme Widgets" with two phone numbers and two addresses in the
same state, which is exactly the pair that should not be merged on the name
alone. With no hard negatives in the data the sweep cannot tune the threshold,
so 0.80 is kept because it demands one piece of corroborating evidence. Adding
near-duplicate distinct companies to the generator is the first item under
limitations.

## A bug the measurement found

The first version of this README reported 2,292 distinct companies as a result.
Scoring against the ground truth showed 292 too many: precision was 1.0, recall
was 0.78, and 292 real companies had been split across two clusters.

The cause was one line in `normalise_name`. Punctuation is stripped before
legal suffixes are matched, so `Acme Widgets L.L.C.` became `ACME WIDGETS L L
C`, which matched nothing in the suffix list. The same company written with
`LLC` and with `L.L.C.` ended up with two canonical names. Runs of
single-letter tokens are now joined back before suffix stripping, a regression
test covers it, and recall went from 0.7812 to 0.9787 with precision unchanged.

A cluster count alone could not have shown this. The evaluate stage is there so
that the next bug of this kind fails CI before it reaches a README.

## Running it

Needs Python 3.10 or newer. No database server, cloud account or API keys.

```bash
pip install -r requirements.txt
make run      # the six Python stages: generate, load-raw, normalise, resolve, evaluate, quality
make dbt      # build and test the warehouse models
make test     # unit tests
```

`make run` writes `warehouse/cdq.duckdb`. To inspect it:

```bash
python3 -c "import duckdb; print(duckdb.connect('warehouse/cdq.duckdb').execute('select * from main_final.rpt_quality_scorecard').fetchdf())"
python3 -c "import duckdb; print(duckdb.connect('warehouse/cdq.duckdb').execute('select * from quality.resolution_errors').fetchdf())"
```

For the DAG itself:

```bash
docker compose up     # Airflow at localhost:8080, admin/admin
```

That brings up Postgres for Airflow's metadata, runs the migrations once, then
starts the webserver and scheduler on `LocalExecutor`. The project's Python
dependencies are baked into a small image that extends the official Airflow one
(`Dockerfile`), so a broken dependency fails the image build before the
scheduler ever starts.

That caught a conflict straight away. dbt-core 1.12 needs `protobuf >= 6` and
Airflow 2.10's OpenTelemetry exporter needs `protobuf < 5`, so they cannot
share an environment. dbt lives in its own virtualenv inside the image, and the
DAG's `BashOperator` calls that binary (`CDQ_DBT_BIN`); that is one reason the
dbt step is a plain shell command. CI builds the image, runs `dbt --version`
from that virtualenv, and runs `tests/test_dag.py` inside the image to check
that the DAG parses and chains the seven stages in order.

## How it is put together

### Raw

Source files land as text with no casting. A value that cannot be parsed then
shows up as a failed test in staging with the original still readable. A load
error would say nothing about what arrived.

### Normalisation

`src/cdq/normalise.py` is pure Python, and every function returns the cleaned
value together with a status. Nothing is silently dropped, which is what makes
the quality report possible: a `phone_status = 'too_short'` row is counted and
kept.

Names are folded by removing accents, punctuation and case and expanding `&` to
`AND`. Dotted abbreviations are joined back into one token (`L.L.C.` to `LLC`,
`I.B.M.` to `IBM`), then legal suffixes are stripped longest first, so `PRIVATE
LIMITED` goes before `LIMITED`. The removed suffix is kept, because it is weak
evidence when two candidates are otherwise identical. Stripping a suffix off
`Acme Widgets & Co` leaves a dangling `AND`, so trailing connectors are removed
afterwards.

Phone numbers have the extension pulled out before the digits are counted.
Otherwise `415.555.0123 ext 42` looks like a 13 digit international number.

### Entity resolution

`src/cdq/matching.py` blocks the records, scores comparisons inside each block,
then runs union-find over the accepted pairs.

The blocking key is the first four characters of the canonical name plus the
state. Without blocking, 3,380 records need 5.7 million comparisons. With it
there are 168 blocks and 40,790 comparisons, and the largest block holds 41
records. The trade usually costs recall, because two records whose names differ
in the first four characters are never compared. On this data the measured cost
is zero (recall reaches 1.0 in the sweep, so no real pair is blocked apart),
but that comes from the generator and would not hold on real data. See
limitations.

Scoring is weighted: 0.70 for name similarity, 0.20 for an exact phone match
and 0.10 for an exact address, accepted at 0.80. Name similarity is Jaccard
over token sets, because the usual failure is word order and extra words. Typos
are rarer. The score is rounded to four places, since 0.70 + 0.10 in binary
floating point is 0.7999999999999999 and silently fails a `>= 0.80` test.

Every accepted pair keeps the reasons that produced it in
`intermediate.match_pairs`, so anyone questioning a merge can see why it
happened.

### Evaluation

`src/cdq/evaluate.py` and `evaluate_resolution` in `src/cdq/pipeline.py` are
described above. The stage skips cleanly when there is no `raw.ground_truth`
table, because a real source only has labels if someone sat down and made them.

### NAICS vintage mapping

`src/cdq/naics.py` uses the real Census 2012 to 2022 concordance. Codes come
back as `unchanged`, `remapped`, `ambiguous_split`, `retired` or `unknown`, and
the last two are never guessed.

`ambiguous_split` exists because the concordance maps some codes to more than
one target. Four 2012 industries were split into two 2022 codes each (211111,
452112, 541711, 541712), and a record carrying one of those codes does not say
which half it belongs to. An earlier version loaded the crosswalk into a dict
keyed on the 2012 code, so the last row won, and twelve records were reported
as confidently remapped to whichever 2022 code came last in the file. They are
now reported as ambiguous, with the candidate codes in `naics_candidates` for a
reviewer to choose from and no `naics_2022` for the model to treat as fact.

### Warehouse models

The dbt models run from sources to staging to final.

`dim_company` picks one surviving row per cluster with an explicit rule: the
registry extract wins on legal name because it comes from filings, then the
most complete record wins on contact fields. It is written as a `row_number()`
ordering, so anyone auditing a merge can read the rule and see which row was
kept.

The crosswalk has two grain problems, in opposite directions, and each has a
model. `stg_naics_crosswalk` keeps the concordance at its real grain, one row
per (2012 code, 2022 code) pair, with `target_count` and `is_split` on every
row. Deduplicating it with `row_number() = 1` would repeat the Python loader's
bug in SQL, quietly keeping one target per code. `stg_naics_2022` handles the
other direction. Where industries were merged, several 2012 codes collapse into
one 2022 code, so joining `dim_company` to a crosswalk keyed on the 2012 code
fanned rows out and broke the uniqueness test on `company_key`.
`stg_naics_2022` is a lookup with the grain that join needs.

Two singular tests guard what unit tests cannot reach.
`assert_no_oversized_clusters` fails the build if a cluster holds more than 25
records, the signature of a transitive merge that chains two real companies
together. `assert_every_record_has_a_cluster` catches records the resolution
stage dropped.

A `check` strategy snapshot tracks how a resolved company changes between runs,
so when a name or industry code moves you can see when it moved.

## Source data

The NAICS crosswalk in `data/` is real, published by the Census Bureau and in
the public domain.

The company records are synthesised by `src/cdq/generate.py` from a fixed seed,
so two runs produce byte identical files and the tests can assert exact counts.
Every open company registry with NAICS codes attached needs an API key or a
download of several gigabytes, and a portfolio repository should run for
whoever clones it.

Each kind of mess in the generated data is there because it breaks joins in
real data:

- the same company written with different legal suffixes, dotted and not, and sometimes none
- names with punctuation, accents, ampersands, stray whitespace and random case
- phone numbers in six formats, some with inline extensions, some too short
- addresses with spelled out street types
- industry codes on two different NAICS vintages, including the split ones
- about one row in eight missing a field entirely
- a slice of duplicated filings in the registry extract (149 rows)

Swapping in a real source means writing a loader for it in `src/cdq/ingest.py`
and pointing `SOURCE_COLUMNS` in `src/cdq/pipeline.py` at the new column names.
Nothing downstream of normalisation knows where the records came from. Without
a `ground_truth.csv` the evaluate stage skips and the rest runs unchanged.

## Limitations

These would matter before this went anywhere near production.

The generated data has no hard negatives. No two distinct companies share a
full name in the same state, so precision is 1.0 at every threshold and the
sweep cannot show where false merges would start. The next generator change is
a slice of near-duplicate distinct companies: same name and state with a
different phone and address, and franchises that share a name across cities.
Until then the accuracy figures are an upper bound and the threshold is a
judgement call.

Blocking costs recall on real data. A pair whose canonical names differ in the
first four characters is never compared, so `Intl Business Machines` cannot
match `International Business Machines`. The measured cost here is zero only
because the generator never abbreviates. A production version would run several
blocking passes (name prefix, phone, address) and union the candidate sets, and
the evaluate stage would then show what each pass adds.

Clustering is transitive, so one weak link chains two real companies into one.
The oversized cluster test only catches the extreme cases. Pairwise scores are
kept so that a review step could break clusters at their weakest edge.

There is no incremental processing; every run rebuilds everything. That is fine
at this size. At real volume the staging models should be incremental on an
updated timestamp and the resolution stage should reconsider only changed
blocks.

Survivorship is a single rule. A real system needs survivorship per field, so a
good phone number from a system that loses on legal name still wins on phone.

## Layout

```
dags/company_quality_pipeline.py   the DAG
src/cdq/normalise.py               name, phone and address cleaning
src/cdq/matching.py                blocking, scoring, union-find
src/cdq/evaluate.py                pairwise precision, recall, F1 against labels
src/cdq/naics.py                   2012 to 2022 vintage mapping
src/cdq/pipeline.py                the stages that write to the warehouse
src/cdq/generate.py                seeded source data plus ground truth
dbt/models/staging/                typed, cleaned, one row per record
dbt/models/final/                  dim_company, fct_record_quality, scorecard
dbt/tests/                         singular tests
tests/                             unit tests for the pure functions, DAG import test
data/                              the NAICS crosswalk
Dockerfile, docker-compose.yml     Airflow on Postgres with the project installed
```

## Licence

MIT.
