-- Record level quality facts, one row per source record and check.
-- Unpivoted deliberately so that adding a new check is a new union branch and
-- not a schema change for every consumer.

with records as (

    select * from {{ ref('stg_records') }}

)

select record_id, source_system, 'name' as field, 'completeness' as dimension,
       case when name_status = 'ok' then 1 else 0 end as passed,
       name_status as detail
from records

union all

select record_id, source_system, 'phone', 'validity',
       case when phone_status = 'ok' then 1 else 0 end,
       phone_status
from records

union all

select record_id, source_system, 'address', 'completeness',
       case when address_status = 'ok' then 1 else 0 end,
       address_status
from records

union all

select record_id, source_system, 'naics', 'validity',
       case when naics_status in ('unchanged', 'remapped') then 1 else 0 end,
       naics_status
from records
