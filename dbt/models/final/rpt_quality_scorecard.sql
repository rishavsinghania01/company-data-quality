-- The table a human actually looks at. One row per source and dimension with
-- a pass rate, which is what makes a regression visible between runs.

with facts as (

    select * from {{ ref('fct_record_quality') }}

)

select
    source_system,
    field,
    dimension,
    count(*)                                              as records_checked,
    sum(passed)                                           as records_passed,
    round(100.0 * sum(passed) / nullif(count(*), 0), 2)   as pass_rate_pct
from facts
group by 1, 2, 3
order by 1, 2
