# Changelog

All notable changes to this integration are recorded here. Versions follow
[semantic versioning](https://semver.org/); the version in `manifest.json` is
what HACS installs, and each release tag must match it.

## 1.0.1

No change to pricing or entities -- this release brings the repository up to
the usual HACS standard.

- **Icon.** The integration now ships its own icon (a 24-hour dial split into
  tariff windows) in `brand/`, which Home Assistant 2026.3+ shows on the
  integration and device pages instead of the generic placeholder.
- **README**: badges, an "Open in HACS" button, an "Add integration" button,
  and manual install steps for anyone not using HACS.
- **Releases always carry notes.** The release workflow now refuses to publish
  a tag with no matching `CHANGELOG.md` section, rather than falling back to an
  empty auto-generated body.
- CI now lints with ruff and runs hassfest + HACS validation alongside the
  tests in one workflow, still weekly as well as on every push. (GitHub had
  switched the old weekly validation off after two quiet months.)

## 1.0.0

First tagged release, and the point at which the integration stopped assuming
you're a GloBird customer.

### Added

- **Releases.** Tagging `v*` builds a HACS zip and publishes it, after checking
  the tag matches `manifest.json` and the test suite passes. HACS now installs
  from the release asset rather than the default branch.
- **The three GloBird programs are individually optional**, and off by default:
  ZeroHero credit, ZeroWastedSolar export boost, and ZeroLimits critical peak
  pricing each have their own toggle. A plain time-of-use plan on any retailer
  is now the default setup path -- the schedule steps are the whole flow, and
  no GloBird entity is created unless asked for.

### Changed

- **`Next price change` reports the next change to the *import* price.** It was
  returning the coordinator's internal recompute time, which also fires on
  export-window edges, ZeroWastedSolar window edges and the midnight counter
  reset. On a plan whose export rate is flat, that showed up as a "next price
  change" at a time when nothing changes. Boundaries between two windows at the
  same rate are skipped too, so an off-peak block split at midnight no longer
  counts as a change. Reports `unknown` for a flat all-day import rate.
- The device is only badged as GloBird when one of their programs is enabled;
  otherwise it's a plain "Time-of-use tariff" named after your plan label.
- Integration display name is now "Time-of-use tariff (GloBird ZEROHERO)". The
  domain (`globird_zerohero`) and all entity IDs are unchanged.

### Migration

Existing config entries are migrated automatically on upgrade (v1 -> v2): the
old single "bonus features" toggle becomes one flag per program, inferred from
what was actually configured. Nothing needs to be re-entered, and no entity IDs
change.
