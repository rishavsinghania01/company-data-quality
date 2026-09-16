-- One row per resolved company.
--
-- The surviving values are chosen by a documented rule rather than by
-- whichever row the database happened to return: the registry extract wins on
-- legal name because it comes from filings, and the most complete record wins
-- on contact fields. Anyone auditing a merge can read this and know why.

with records as (

    select * from {{ ref('stg_records') }}
    where cluster_id is not null

),

ranked as (

    select
        *,
        row_number() over (
            partition by cluster_id
            order by
                case when source_system = 'registry_extract' then 0 else 1 end,
                case when phone_status = 'ok' then 0 else 1 end,
                case when address_status = 'ok' then 0 else 1 end,
                record_id
        ) as survivor_rank
    from records

),

survivors as (

    select * from ranked where survivor_rank = 1

),

contributions as (

    select
        cluster_id,
        count(*)                                          as source_record_count,
        count(distinct source_system)                     as source_system_count,
        max(case when naics_status = 'remapped' then 1 else 0 end) as had_retired_naics
    from records
    group by 1

)

select
    survivors.cluster_id                as company_key,
    survivors.name_canonical            as company_name,
    survivors.name_raw                  as company_name_as_filed,
    survivors.state_code,
    survivors.phone_e164,
    survivors.address_line,
    survivors.naics_2022,
    crosswalk.title_2022                as naics_title,
    contributions.source_record_count,
    contributions.source_system_count,
    contributions.had_retired_naics
from survivors
left join contributions
    on survivors.cluster_id = contributions.cluster_id
left join {{ ref('stg_naics_2022') }} as crosswalk
    on survivors.naics_2022 = crosswalk.code_2022
