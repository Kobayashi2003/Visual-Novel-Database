# Routes

## 1. What exists

- Leave an unimplemented route unregistered.
- Keep every route the edge exposes listed in that prefix's allowlist.

## 2. Input

- Validate before calling downward; let nothing malformed past this layer.
- Clamp an out-of-range value rather than rejecting it.
- Fill in defaults here, so a lower layer always receives a complete argument.

## 3. Output

- Convert the code the layer below reported into an HTTP status here.
- Put the answer, and whatever the caller needs in order to use it, at the top
  level.
- Put anything that only explains how the answer was produced under `meta`.
