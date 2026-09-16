-- One row per source record with the normalised fields attached.
-- Everything downstream reads this rather than the raw tables, so the cast and
-- the cleaning rules live in exactly one place.

with normalised as (

    select * from {{ source('intermediate', 'normalised_records') }}

),

clustered as (

    select * from {{ source('intermediate', 'entity_clusters') }}

)

select
    normalised.record_id,
    normalised.source_system,
    clustered.cluster_id,
    normalised.name_raw,
    normalised.name_canonical,
    normalised.name_suffix,
    normalised.name_status,
    normalised.phone_e164,
    normalised.phone_extension,
    normalised.phone_status,
    normalised.address_line,
    normalised.address_status,
    normalised.state_code,
    normalised.naics_raw,
    normalised.naics_2022,
    normalised.naics_status,
    normalised.naics_candidates
from normalised
left join clustered
    on normalised.record_id = clustered.record_id
