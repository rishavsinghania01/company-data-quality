-- A lookup keyed on the 2022 vintage.
--
-- stg_naics_crosswalk is keyed on the 2012 code, and several 2012 codes
-- collapse into one 2022 code where industries were merged. Joining a fact to
-- that model on code_2022 therefore fans rows out. This model exists so the
-- join has the grain it claims to have.

with crosswalk as (

    select * from {{ ref('stg_naics_crosswalk') }}
    where code_2022 is not null

)

select distinct
    code_2022,
    title_2022
from crosswalk
