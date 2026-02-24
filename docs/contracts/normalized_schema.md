# Normalized Schema

Canonical normalized tables:

- `normalized_observations` (`surface_mapper.contracts.normalized.NORMALIZED_OBS_TABLE`)
- `normalized_events` (`surface_mapper.contracts.normalized.NORMALIZED_EVENTS_TABLE`)

These are dataset-agnostic contracts used by all ingest adapters.

## `normalized_observations`

One row per observation record.

| Column | Type | Required | Notes |
|---|---|---|---|
| `dataset` | `VARCHAR` | yes | Source dataset key (example: `ebird-ebd`) |
| `event_id` | `VARCHAR` | yes | Event/checklist identifier |
| `observed_at` | `DATE` | yes | Observation or event date |
| `lat` | `DOUBLE` | yes | Latitude, constrained in model to `[-90, 90]` |
| `lon` | `DOUBLE` | yes | Longitude, constrained in model to `[-180, 180]` |
| `taxon` | `VARCHAR` | yes | Taxon/species identifier |
| `count` | `INTEGER` | no | Observed count |
| `is_complete` | `BOOLEAN` | no | Complete checklist/event flag |

## `normalized_events`

One row per sampling event/checklist.

| Column | Type | Required | Notes |
|---|---|---|---|
| `dataset` | `VARCHAR` | yes | Source dataset key |
| `event_id` | `VARCHAR` | yes | Event/checklist identifier |
| `observed_at` | `DATE` | yes | Event date |
| `lat` | `DOUBLE` | yes | Latitude, constrained in model to `[-90, 90]` |
| `lon` | `DOUBLE` | yes | Longitude, constrained in model to `[-180, 180]` |
| `duration_minutes` | `DOUBLE` | no | Effort duration |
| `distance_km` | `DOUBLE` | no | Effort distance |
| `area_ha` | `DOUBLE` | no | Effort area |
| `protocol` | `VARCHAR` | no | Sampling protocol name |
| `num_observers` | `INTEGER` | no | Number of observers |
| `is_complete` | `BOOLEAN` | no | Complete checklist/event flag |
