# Remote Outputs Interlock Group Schema Fix

## Overview

A bug was identified where boneIO would fail to start if `interlock_group` was configured as a string under a `remote_outputs` section. 
The application CLI crashed with the following validation error:
```
Failed to load config. Configuration validation failed:
- remote_outputs: [{0: [{'interlock_group': ['must be of list type']}]}]
```

## Details

While the codebase (`boneio/core/manager/outputs.py` and `boneio/core/manager/manager.py`) is designed to handle both strings and lists for `interlock_group`, the Cerberus schema definition for `remote_outputs` strictly required a `list`.

For local `outputs`, `interlock_group` was defined in `boneio/schema/schema.yaml` as:
```yaml
      interlock_group:
        type:
          - string
          - list
```

In contrast, `remote_outputs` had:
```yaml
    interlock_group:
      type: list
```

## Solution

We aligned the schema in [remote_outputs.yaml](file:///home/poznan.tbhydro.net/admin/ProjektyPrywatne/bone/app_black/boneio/schema/remote_outputs.yaml) with the local outputs schema to accept both `string` and `list` types:

```yaml
    interlock_group:
      type:
        - string
        - list
```

We also added new test cases in [test_config_validation.py](file:///home/poznan.tbhydro.net/admin/ProjektyPrywatne/bone/app_black/tests/unit/core/test_config_validation.py) to ensure configuration validation works with both formats.

## Files Changed

| File | Change |
|---|---|
| [remote_outputs.yaml](file:///home/poznan.tbhydro.net/admin/ProjektyPrywatne/bone/app_black/boneio/schema/remote_outputs.yaml) | Changed `interlock_group` type to accept both `string` and `list`. |
| [test_config_validation.py](file:///home/poznan.tbhydro.net/admin/ProjektyPrywatne/bone/app_black/tests/unit/core/test_config_validation.py) | **New** — Added test cases for verifying schema validation logic. |
