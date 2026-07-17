# Development Discipline

## Definition of done

A change is done when implementation, contract/schema, tests, example or fixture, documentation,
and compatibility impact agree. GUI or hardware behavior that was not exercised must be listed as
an outstanding target-machine check.

## Testing layers

1. Pure geometry and schema unit tests.
2. Dataset and workflow integration tests with tiny deterministic fixtures.
3. Backend artifact parsing tests, such as KML/XML and Blender-job JSON.
4. Target-machine smoke tests for Blender, Earth Pro, and future hardware.

## Reproducibility

Plans use stable ordering and IDs. Generated products record task configuration, source dataset,
algorithm/version, limitations, and coverage. Randomized algorithms require an explicit seed.

## Safety and data ownership

Do not commit private imagery, licensed GLB assets, credentials, or captured datasets. Google Earth
products must preserve required attribution. Real-capture interfaces must not assume a vehicle or
drone command authority merely because data import is authorized.
