-- The published 2012 to 2022 concordance, typed and deduplicated.
-- A handful of 2012 codes appear on more than one row where an industry was
-- split, so the grain is enforced here rather than assumed downstream.

with source as (

    select * from {{ source('raw', 'naics_crosswalk') }}

),

deduplicated as (

    select
        trim(code_2012)  as code_2012,
        trim(title_2012) as title_2012,
        trim(code_2022)  as code_2022,
        trim(title_2022) as title_2022,
        row_number() over (
            partition by trim(code_2012)
            order by trim(code_2022)
        ) as row_num
    from source
    where trim(coalesce(code_2012, '')) <> ''

)

select
    code_2012,
    title_2012,
    code_2022,
    title_2022
from deduplicated
where row_num = 1
