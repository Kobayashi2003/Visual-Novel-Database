# Application

## 1. Calls between layers

- Call downward only, to the adjacent layer.

## 2. Helper location

Put a helper where its callers are:

| Location | Callers |
| --- | --- |
| the module itself | that module only |
| the layer's `common.py` | more than one module in that layer |
| `utils/` | more than one layer |

## 3. Module names

- Name the same job the same in every application.
