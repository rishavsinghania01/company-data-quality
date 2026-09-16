-- Every record with a usable name must land in exactly one cluster. A null
-- here means the resolution stage dropped a record rather than merging it.

select record_id
from {{ ref('stg_records') }}
where name_status = 'ok'
  and cluster_id is null
