# GloBird ZEROHERO for Home Assistant

Live import/export price sensors for [GloBird Energy](https://www.globirdenergy.com.au/)'s **ZEROHERO** plan, built to plug directly into Home Assistant's Energy dashboard cost tracking.

## Why this exists

ZEROHERO's base rate is a **fixed daily time-of-use schedule** (e.g. free import 11am-2pm, peak 3-9pm), not a live wholesale-linked price like Amber Electric. That means the current price can be computed purely from the time of day and your configured rate schedule -- no polling GloBird, no portal login, no scraping. This integration does exactly that, plus tracks ZEROHERO's bonus mechanics (ZeroHero credit, ZeroWastedSolar boost, ZeroLimits critical peak events) as informational sensors.

Two existing projects were checked before building this and neither covers this gap: [globird-ha](https://github.com/bolagnaise/globird-ha) exposes account/usage/cost history via portal login but explicitly doesn't expose rate/pricing sensors; [ha-pricehawk](https://github.com/Artic0din/ha-pricehawk) lets you configure GloBird rates but only produces accumulated cost totals, not a live per-kWh price entity.

## What you get

- **Current import price** and **current export price** sensors (`device_class: monetary`, `AUD/kWh`, updates exactly at each price-window boundary) -- point HA's Energy dashboard **Configure grid connection** at these:
  - Grid consumption cost -> "Use an entity with the current price" -> *Current import price*
  - Return to grid compensation -> "Use an entity with the current price" -> *Current export price*
- Price tier label (Free / Off-peak / Peak / ZeroWastedSolar boost / Critical peak)
- Next price change (timestamp) -- the next time the **import** price actually changes. Export-window edges and window splits that keep the same rate (an off-peak block divided at midnight, say) aren't price changes, so they're not reported here. `unknown` if your import schedule is a single flat rate.
- Daily supply charge (informational)
- If you enable bonus tracking during setup:
  - ZeroHero credit status for today (pending / earned / missed)
  - ZeroWastedSolar kWh remaining today
  - A switch to manually flag a ZeroLimits critical peak event (or point the integration at an `input_boolean`/`binary_sensor` you already use for this)

## Installation (HACS custom repository)

This isn't in the default HACS store. In HACS: **⋮ menu -> Custom repositories**, add `https://github.com/andrewgould/ha-globird-zerohero` as an **Integration**, then install "GloBird ZEROHERO" and restart Home Assistant. Then **Settings -> Devices & services -> Add integration -> GloBird ZEROHERO**.

## Setup

You'll need your current ZEROHERO rates from your bill or GloBird's published price fact sheet for your distribution area -- the config flow pre-fills the current published Jemena defaults as a starting point, but **you enter and own the numbers**; nothing is scraped or auto-updated, so re-check them if GloBird changes rates.

1. Plan label, daily supply charge, and whether to track the bonus mechanics.
2. Import (grid consumption) price schedule -- up to 6 time windows, must cover the full 24 hours with no gaps or overlaps.
3. Export (feed-in) price schedule -- same shape.
4. *(if bonus tracking enabled)* ZeroHero credit threshold/window/amount and your grid-import sensor.
5. *(if bonus tracking enabled)* ZeroWastedSolar rate/cap/window and your solar-export sensor.
6. *(if bonus tracking enabled)* ZeroLimits critical-peak rates and toggle source.

Everything is editable later without removing the integration: **Settings -> Devices & services -> GloBird ZEROHERO -> Configure**.

### Flagging a ZeroLimits critical peak event

GloBird announces these ad-hoc via its app with no public API to detect them automatically. When you get the notification, turn on the **ZeroLimits critical peak active** switch (or your linked helper entity) for the duration of the event; turn it off when it ends. While active, the current export price switches to the critical-peak rate and the current import price includes the surcharge.

## Documented assumptions

- **Critical peak overrides ZeroWastedSolar, rather than stacking.** GloBird doesn't publish how the two interact when both would apply; this integration uses the higher-precedence critical-peak rate outright.
- **ZeroHero threshold detection works best against a power (W/kW) sensor.** If you only have a cumulative energy sensor linked, eligibility is approximated from a rolling delta sampled during the evening window, which can be less precise for very brief spikes.
- **The rate schedule uses a bounded number of time windows** (6 max per direction), matching ZEROHERO's actual ~4-5 windows. If GloBird restructures the plan with more windows, or you're on a materially different variant, this may need extending.
- **Public holiday / day-type variation is not modelled** -- out of scope for v1.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

`schedule.py` and `pricing.py` are the core pricing algorithm and are framework-free (no Home Assistant imports), so most of the test suite runs as plain pytest with no `hass` fixture. `coordinator.py`, `config_flow.py`, `sensor.py`, and `switch.py` are the Home Assistant integration glue.

## License

MIT
