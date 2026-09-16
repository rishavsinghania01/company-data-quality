-- The published 2012 to 2022 concordance, typed, at its real grain.
--
-- The concordance is not one row per 2012 code. Where an industry was split,
-- one 2012 code appears on several rows with a different 2022 code on each,
-- and nothing in the record says which one applies. An earlier version of
-- this model kept the first row and dropped the rest, which turned an
-- ambiguous mapping into a confidently wrong one. The grain is now one row per
-- (2012 code, 2022 code) pair, and every row carries how many targets its 2012
-- code has, so a consumer can see when a code is not safe to map.

with source as (

    select * from {{ source('raw', 'naics_crosswalk') }}

),

typed as (

    select distinct
        trim(code_2012)  as code_2012,
        trim(title_2012) as title_2012,
        trim(code_2022)  as code_2022,
        trim(title_2022) as title_2022
    from source
    where trim(coalesce(code_2012, '')) <> ''

)

select
    code_2012 || '->' || coalesce(code_2022, '')   as mapping_key,
    code_2012,
    title_2012,
    code_2022,
    title_2022,
    count(code_2022) over (partition by code_2012)   as target_count,
    count(code_2022) over (partition by code_2012) > 1 as is_split
from typed
