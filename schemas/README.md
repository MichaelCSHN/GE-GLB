# Schema Catalog

Schemas are contracts, not an inventory of every JSON file emitted by the repository. Their
lifecycle status is explicit so planned v2 contracts cannot be mistaken for active v1 validators.

| Schema | Status | Producer/model | Consumer/validation |
| --- | --- | --- | --- |
| `manifest.schema.json` | active compatibility | `core.dataset.write_standard_dataset` | `core.dataset.validate_dataset`, schema tests |
| `frame.schema.json` | active compatibility | `core.dataset.write_standard_dataset` (`frames.jsonl` records) | stitch planning, schema tests |
| `products/underbody-image.schema.json` | active contract | `products.UnderbodyImageProduct` | future Task 01 product writer, schema tests |
| `products/panorama-360.schema.json` | active contract | `products.Panorama360Product` | future Task 02 product writer, schema tests |
| `products/lookat-viewset.schema.json` | active contract | `products.LookAtViewSetProduct` | future Task 03 product writer, schema tests |
| `capture/capture-plan-v2.schema.json` | planned, inactive | future neutral `CapturePlan` | no runtime consumer yet |
| `capture/capture-dataset-v2.schema.json` | planned, inactive | future shared run writer | no runtime consumer yet |

`active compatibility` means the schema describes the current `ge-glb.dataset/v1` interface. It
remains supported while the v2 run layout is introduced. `active contract` means the product type
is normative even if its complete writer is not implemented. `planned, inactive` files are design
targets and must not be advertised as runtime-validated outputs.

## Change rules

1. A schema change requires a version decision, producer/model update, fixture or generated
   instance, and validation test.
2. Paths persisted in datasets are POSIX-style paths relative to the dataset root. Runtime
   validation also rejects absolute paths and `..` traversal.
3. Ground-truth-only observations may be represented in capture data but must be rejected from
   reconstruction inputs.
4. Move a planned schema to active only when at least one writer and one instance-validation test
   exist.
