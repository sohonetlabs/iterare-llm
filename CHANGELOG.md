# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] - 2026-06-16

### Added

- Layered configuration: settings now resolve across three layers of increasing
  precedence — built-in defaults, a global config at `~/.iterare/config.toml`,
  then the project config at `.iterare/config.toml`. A key set in a higher layer
  fully overrides the same key in a lower one (lists are replaced wholesale, not
  merged).
- Global config management: `iterare install` and `iterare init` now create the
  global config at `~/.iterare/config.toml` when it is missing. An existing
  global config is never overwritten, so user edits are preserved.
- Configurable bind mounts: a new `[mounts]` section lets you bind-mount extra
  host paths into every container using Docker-compose short syntax
  (`"SOURCE:TARGET[:MODE]"`). Sources support `~` and `$VAR` expansion, and the
  essential iterare mounts always take precedence on conflict.

### Changed

- Both the global and project config files are now optional. When neither
  exists, built-in defaults are used instead of raising an error.
- `iterare init` now writes a minimal, inheritance-only project config that
  documents how to override the global defaults, rather than a full standalone
  config.

[0.2.3]: https://github.com/sohonetlabs/iterare-llm/releases/tag/0.2.3
