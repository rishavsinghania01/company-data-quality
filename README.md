# Company data quality pipeline

[![CI](https://github.com/rishavsinghania01/company-data-quality/actions/workflows/ci.yml/badge.svg)](https://github.com/rishavsinghania01/company-data-quality/actions/workflows/ci.yml)

An Airflow pipeline that takes company records from two source systems, cleans
the fields, works out which records describe the same company, loads the result
into a warehouse with dbt, and publishes a quality scorecard.

It is built around the problem that shows up whenever two systems hold the same
customers: the same company is spelled four ways, the phone number is in six
formats, half the industry codes are on a NAICS vintage that was retired in
2022, and nobody can tell you how many distinct companies you actually have.

```
generate_sources -> load_raw_tables -> normalise_fields -> resolve_entities -> dbt_build -> quality_report
```

## What a run produces

From 3,380 source records across the two systems:

| Metric | Value |
|---|---|
| Distinct companies after resolution | 2,028 |
| Clusters holding more than one record | 1,232 |
| Largest cluster | 3 records |
| NAICS codes remapped from 2012 to 2022 | 471 |
| NAICS codes not found in either vintage | 139 |
| Phone numbers present but too short to be valid | 526 |
| Phone numbers missing entirely | 137 |

Every number in this table is asserted by CI on each push, against the warehouse the pipeline just built — if the code drifts from the README, the build goes red.

Quality scorecard, which is the table a human reads:

| source_system | field | dimension | records_checked | records_passed | pass_rate_pct |
|---|---|---|---|---|---|
| crm_export | name | completeness | 1736 | 1736 | 100.00 |
| crm_export | phone | validity | 1736 | 1394 | 80.30 |
| crm_export | address | completeness | 1736 | 1652 | 95.16 |
| crm_export | naics | validity | 1736 | 1665 | 95.91 |
| registry_extract | name | completeness | 1644 | 1644 | 100.00 |
| registry_extract | phone | validity | 1644 | 1323 | 80.47 |
| registry_extract | address | completeness | 1644 | 1578 | 95.99 |
| registry_extract | naics | validity | 1644 | 1576 | 95.86 |

Whole run takes about eight seconds on a laptop.

## Running it

Needs Python 3.10 or newer. No database server, no cloud account, no API keys.

```bash
pip install -r requirements.txt
make run      # the four Python stages
make dbt      # build and test the warehouse models
make test     # unit tests
```

`make run` writes `warehouse/cdq.duckdb`. To inspect it:

```bash
python3 -c "import duckdb; print(duckdb.connect('warehouse/cdq.duckdb').execute('select * from main_final.rpt_quality_scorecard').fetchdf())"
```

For the DAG itself:

```bash
docker compose up     # Airflow at localhost:8080, admin/admin
```

## How it is put together

**Raw.** Source files land as text with no casting at all. A value that cannot
be parsed should surface as a failed test in staging with the original still
readable, not as a load error that tells you nothing about what arrived.

**Normalisation** (`src/cdq/normalise.py`) is pure Python and every function
returns the cleaned value together with a status. Nothing is silently dropped,
which is what makes the quality report possible: `phone_status = 'too_short'`
is counted, not discarded.

Names are folded by removing accents, punctuation and case, expanding `&` to
`AND`, then stripping legal suffixes longest first so `PRIVATE LIMITED` goes
before `LIMITED`. The suffix that was removed is kept rather than thrown away,
because it is weak evidence when two candidates are otherwise identical.
Stripping a suffix off `Acme Widgets & Co` leaves a dangling `AND`, so trailing
connectors are removed afterwards.

Phone numbers have the extension pulled out before the digits are counted,
otherwise `415.555.0123 ext 42` looks like a 13 digit international number.

**Entity resolution** (`src/cdq/matching.py`) is blocking, then scored
comparison inside each block, then union-find over the accepted pairs.

The blocking key is the first four characters of the canonical name plus the
state. Without blocking, 3,380 records is 5.7 million comparisons; with it the
work is a few thousand. That is a deliberate trade and it costs recall: two
records for the same company whose names diverge in the first four characters
will never be compared. See limitations.

Scoring is weighted, 0.70 on name similarity, 0.20 for an exact phone match and
0.10 for an exact address, accepted at 0.80. Name similarity is Jaccard over
token sets rather than edit distance, because the common failure is word order
and extra words rather than typos. The score is rounded to four places, since
0.70 + 0.10 in binary floating point is 0.7999999999999999 and silently fails a
`>= 0.80` test.

Every accepted pair keeps the reasons that produced it in
`intermediate.match_pairs`, so a questionable merge can be explained rather than
argued about.

**NAICS vintage mapping** (`src/cdq/naics.py`) uses the real Census 2012 to 2022
concordance. Codes come back as `unchanged`, `remapped`, `retired` or `unknown`,
and unknown is reported rather than guessed.

**Warehouse models** are dbt, sources to staging to final.

`dim_company` picks one surviving row per cluster using an explicit rule: the
registry extract wins on legal name because it comes from filings, then the
most complete record wins on contact fields. It is written as a `row_number()`
ordering so that anyone auditing a merge can read the rule instead of guessing
which row the database happened to return.

`stg_naics_2022` exists because of a bug worth keeping in the history. Several
2012 codes collapse into one 2022 code where industries were merged, so joining
`dim_company` to a crosswalk keyed on the 2012 code fanned rows out and broke
the uniqueness test on `company_key`. The fix is a lookup that actually has the
grain the join claims.

Two singular tests guard the parts that unit tests cannot reach:
`assert_no_oversized_clusters` fails the build if a cluster swallows more than
25 records, which is the signature of a transitive merge chaining two real
companies together, and `assert_every_record_has_a_cluster` catches records the
resolution stage dropped rather than merged.

A `check` strategy snapshot tracks how a resolved company changes between runs,
so when a name or industry code moves you can see when it moved.

## Source data

The NAICS crosswalk in `data/` is real, published by the Census Bureau, public
domain.

The company records are synthesised by `src/cdq/generate.py` from a fixed seed,
so two runs produce byte identical files and the tests can assert exact counts.
They are generated rather than downloaded because every open company registry
with NAICS codes attached needs either an API key or a multi gigabyte download,
and a portfolio repository that will not run for whoever clones it is worth
nothing.

The dirt in the generated data is deliberate and each pattern is there because
it is the kind of thing that actually breaks a join:

- the same company written with different legal suffixes, and sometimes none
- names with punctuation, accents, ampersands, stray whitespace and random case
- phone numbers in six formats, some with inline extensions, some too short
- addresses with spelled out street types
- industry codes on two different NAICS vintages
- about one row in eight missing a field entirely
- a slice of duplicated filings in the registry extract

Swapping in a real source means writing a loader for it in `src/cdq/ingest.py`
and pointing `SOURCE_COLUMNS` in `src/cdq/pipeline.py` at the new column names.
Nothing downstream of normalisation knows where the records came from.

## Limitations

Things this does not do, which matter if it were going anywhere near production:

**Blocking costs recall.** Any pair whose canonical names differ in the first
four characters is never compared, so `Acme Widgets` and `ACME-Widgets Holding`
match, but an abbreviation like `Intl Business Machines` against `International
Business Machines` does not. A production version would use several blocking
passes, for example name prefix, phone, and address, and union the candidate
sets.

**Clustering is transitive and that cuts both ways.** A weak link chains two
real companies into one. The oversized cluster test is a blunt guard, not a
solution. Pairwise scores are kept so that a review step could break clusters
at their weakest edge.

**The threshold is a constant, not a trained value.** 0.80 was chosen by
looking at the output. With labelled pairs it should be set from a precision
and recall curve.

**No incremental processing.** Every run rebuilds everything. At this size that
is fine, at real volume the staging models want to be incremental on an updated
timestamp and the resolution stage wants to only reconsider changed blocks.

**Survivorship is a single rule.** A real system needs per field survivorship,
so a good phone number from a system that loses on legal name still wins on
phone.

## Layout

```
dags/company_quality_pipeline.py   the DAG
src/cdq/normalise.py               name, phone and address cleaning
src/cdq/matching.py                blocking, scoring, union-find
src/cdq/naics.py                   2012 to 2022 vintage mapping
src/cdq/pipeline.py                the stages that write to the warehouse
src/cdq/generate.py                seeded source data
dbt/models/staging/                typed, cleaned, one row per record
dbt/models/final/                  dim_company, fct_record_quality, scorecard
dbt/tests/                         singular tests
tests/                             unit tests for the pure functions
data/                              the NAICS crosswalk
```

## Licence

MIT.
