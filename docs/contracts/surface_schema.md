# Surface Schema

Canonical surface table:

- `surface_cells` (`surface_mapper.contracts.surface.SURFACE_TABLE_DEFAULT`)

One row represents one metric value for one spatial cell (optionally within a time slice).

## `surface_cells`

| Column | Type | Required | Notes |
|---|---|---|---|
| `dataset` | `VARCHAR` | yes | Source dataset key |
| `grid` | `VARCHAR` | yes | Grid backend (`h3` currently) |
| `resolution` | `INTEGER` | yes | Grid resolution value |
| `cell_id` | `VARCHAR` | yes | Spatial cell identifier |
| `metric` | `VARCHAR` | yes | Metric name (`attention`, `richness`, etc.) |
| `value` | `DOUBLE` | yes | Metric value |
| `support` | `DOUBLE` | no | Support size / confidence proxy |
| `time_slice` | `VARCHAR` | no | Time grouping label |
| `start_date` | `DATE` | no | Start of time window |
| `end_date` | `DATE` | no | End of time window |

Renderers and exporters consume this table as a stable interface.
