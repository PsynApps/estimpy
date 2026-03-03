# 002 — Flat Config Dictionary

## Context

Configuration is authored in YAML for readability (nested structure), but code
needs fast, unambiguous access to individual settings. Nested dictionary access
(`cfg['visualization']['style']['amplitude']['padding']`) is verbose and fragile
when intermediate keys might be missing.

## Decision

Flatten the YAML on load into a single dict with dot-delimited keys:
`es.cfg['visualization.style.amplitude.padding']`. The flat dict is the
canonical runtime representation; the YAML nesting is purely for human
authoring.

## Rationale

- Config access is a single dict lookup — no nested traversal or `.get()` chains
- CLI overrides use a simple `key value` syntax (`-co visualization.style.amplitude.padding 0.2`)
- Config keys are greppable as literal strings across the codebase
- `--config-option-list` can enumerate all valid keys directly from `base_cfg`

Trade-off: derived values (parsed from `*.size` strings, resolved font paths,
blended colors) are injected into the same flat dict during `_on_config_updated()`.
These are documented in `visualization/__init__.py` but are not present in
`default.yaml` or `base_cfg`.
