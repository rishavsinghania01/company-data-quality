{% snapshot company_snapshot %}
{{
    config(
        target_schema='snapshots',
        unique_key='company_key',
        strategy='check',
        check_cols=['company_name', 'phone_e164', 'address_line', 'naics_2022']
    )
}}

-- Tracks how a resolved company changes between runs. Useful when a source
-- system is reloaded and a name or industry code moves, because the history
-- shows when it changed rather than only that it is different now.

select
    company_key,
    company_name,
    state_code,
    phone_e164,
    address_line,
    naics_2022
from {{ ref('dim_company') }}

{% endsnapshot %}
