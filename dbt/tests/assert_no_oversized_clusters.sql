-- A cluster that swallows an implausible number of source records is the
-- signature of a bad transitive merge, where one weak link chained two real
-- companies together. Fails the build so it cannot ship unnoticed.

select
    company_key,
    source_record_count
from {{ ref('dim_company') }}
where source_record_count > 25
