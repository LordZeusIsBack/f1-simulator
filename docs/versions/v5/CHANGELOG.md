# V5 changelog: race control, incidents and penalties

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V4) | `f8840e5` "docs(v4): record version commit hash in changelog" (V4 code is in `22b3668`) |
| V5 version commit | `e22ce77c8c55d70046913c11146a8bbe7f7e220d` (`e22ce77`) |
| Commit message | `feat(v5): add race control, incidents and penalties` |

As in earlier versions, the hash is recorded by a follow-up commit, `docs(v5): record version commit hash in changelog`, which changes only this table.

Line numbers refer to the V5 version commit and may shift later.

## How V5 differs from V4

| V4 | V5 |
|---|---|
| The race always runs under green | Optional `RaceControl`: YELLOW (one segment), VSC, SAFETY_CAR, with legal transitions and defined ends |
| Every car finishes | Scripted incidents can retire cars. Retired cars stop, leave the track and are classified last. |
| Race result = finish time | Result = finish time + penalties (time penalties, converted drive-throughs, two-compound rule) |
| DRS depends only on traffic rules | DRS also needs a GREEN flag and wetness ≤ 0.3 |
| Overtaking only limited by V3 rules | Also forbidden under VSC and SC and inside a yellow zone. Passes in progress are abandoned. |
| Pit stops cost the same in relative terms whenever they happen | Unchanged rules, but slower rivals under VSC or SC make stops relatively cheaper |
| Logs: `pit_events`, `overtakes`, `weather_events` | Plus `race_control.events` |
| — | `race_control=None` (the default) reproduces V4 exactly |

## Files

| File | Origin | V5 status |
|---|---|---|
| `race_control.py` | — | **new** |
| `test_race_control.py` | — | **new** |
| `docs/versions/v5/*.md` | — | **new** |
| `race.py` | V1–V4 | modified |
| `README.md` | V1–V4 | modified |
| `abstract_classes.py`, `cars.py`, `tracks.py`, `physics.py`, `simulation.py`, `tyres.py`, `strategy.py`, `drivers.py`, `traffic.py`, `weather.py`, `main.py`, `test_simulation.py`, `test_race.py`, `test_tyres_fuel_pits.py`, `test_traffic.py`, `test_weather.py`, `pyproject.toml`, `uv.lock`, `docs/versions/v1–v4/*` | | **unchanged** |
| Removed files | | none |

No earlier test needed changing: race control is opt-in.

## Changes per file

### `race_control.py` (new, 142 lines)

| Symbol | Lines | Behaviour |
|---|---|---|
| `Flag` (IntEnum) | 6–11 | GREEN 0, YELLOW 1, VSC 2, SAFETY_CAR 3 (severity order) |
| `TRANSITIONS` | 15–20 | legal moves; every flag can return to GREEN; SAFETY_CAR can only go to GREEN |
| `check_transition(old, new)` | 23–25 | `ValueError` for an illegal move |
| `RaceControlRules` (frozen) | 28–38 | `yellow_slowdown` 0.10, `vsc_factor` 1.40, `sc_factor` 1.60, `sc_catch_up_factor` 1.30, `sc_gap` 10 m, `drive_through_loss` 20 s, `two_compound_penalty` 30 s, `drs_max_wetness` 0.3 |
| `Incident` (frozen) | 41–61 | `time`, `flag`, `duration`, `retire`, `segment`, `reason`, validated |
| `Penalty` (frozen) | 64–79 | `time`, `car`, `kind` ("time" or "drive-through"), `seconds`, `reason`, validated |
| `ControlEvent` (frozen) | 82–88 | `time`, `kind`, `flag`, `cars`, `detail` |
| `RaceControl.__init__` | 94–102 | sorted script, GREEN, empty log |
| `RaceControl.due(time)` | 104–109 | script items that have come due, each handed out once |
| `RaceControl.log` | 111–112 | append an event, stamped with the current flag |
| `RaceControl.call` | 114–124 | escalate (checked transition), or extend the current period |
| `RaceControl.clear` | 126–129 | go to GREEN (checked) |
| `RaceControl.pace_factor` | 131–139 | time factor for a car under the current flag |
| `RaceControl.overtaking_allowed` | 141–142 | GREEN, or YELLOW outside the zone |

### `race.py` (modified, 368 → 506 lines)

| Symbol | Lines | Before (V4) | After (V5) |
|---|---|---|---|
| import | 10 | — | `Flag`, `Incident`, `Penalty`, `RaceControl` |
| `RaceCar` | 26–45 | V4 fields | adds `retired_at`, `penalty_time`, `drive_throughs` |
| `Race.__init__` | 122–185 | | new `race_control=None` setting with validation (fresh, known cars, segments on the track); resets the new car fields |
| `Race.finished` | 222–224 | all cars finished | all cars finished **or retired** |
| `Race.total_time` | 226–228 | — | finish time + penalties |
| `Race.step` | 233–266 | weather refresh, move cars, weather | adds race control at the start of the step, race order whenever race control or traffic is present, skipping retired cars, flag pace and SC queue for the no-traffic path, the SC end check |
| `Race._apply_race_control` | 268–288 | — | applies due incidents (retire, then flag) and penalties; clears YELLOW and VSC when due |
| `Race._penalise` | 290–299 | — | time penalty, drive-through, or ignored for a retired car |
| `_running`, `_in_zone`, `_queue_limit`, `_overtaking_allowed`, `_drs_allowed` | 301–323 | — | helpers (see IMPLEMENTATION.md §7) |
| `Race._drive` | 335–384 | V3/V4 | DRS only if allowed; flag pace; abandon passes under flags; SC queue limit; no attempts when overtaking is forbidden; `held_by` only for traffic holds; DRS detection needs `_drs_allowed()` |
| `Race._on_track` | 417–418 | not finished, not in the pits | also not retired |
| `Race._segment_index` | 420–421 | inline in `_segment` | extracted (the yellow zone needs it) |
| `Race.car_ahead` | 436–439 | | docstring only (retired cars excluded through `_on_track`) |
| `Race._complete_lap` | 447–466 | finish or strategy stop | at the finish calls `_finish_penalties`; otherwise serves a pending drive-through under GREEN or YELLOW |
| `Race._finish_penalties` | 468–482 | — | converts unserved drive-throughs; applies the two-compound rule |
| `Race.standings` | 497–506 | finished by finish time, running by distance | finished by `total_time`, then running, then retired (each by distance) |

**Why:** race control must change pace, overtaking, pit timing and the classification. Every hook sits where V1–V4 already decide those things, so traffic, weather, tyres and strategy needed no change.

### `test_race_control.py` (new)

| Test | Lines | Covers |
|---|---|---|
| `test_transition_table` | 37–46 | all 16 pairs, valid and invalid; every flag can end; no SC downgrade |
| `test_escalation_extension_and_invalid_clear` | 49–59 | GREEN → GREEN invalid; extension keeps the zone; a milder flag cannot replace the SC |
| `test_scripted_items_are_validated` | 62–80 | 7 bad incidents, 3 bad penalties, unknown cars and segments, reused `RaceControl` |
| `test_yellow_slows_only_its_segment_and_clears_after_its_duration` | 83–98 | yellow activation and clearing times; zone-only slow-down and no-pass rule; time lost within bounds |
| `test_vsc_slows_every_car_by_its_factor_and_nobody_passes` | 101–112 | VSC delay = 60 × (1 − 1/1.4) s; order frozen with traffic |
| `test_safety_car_bunches_the_field_freezes_order_and_ends_at_the_line` | 115–129 | spread field bunched to 10 m; order frozen; the SC ends at a line crossing after its minimum |
| `test_retired_car_stops_drops_to_the_bottom_and_the_race_still_ends` | 132–146 | stopped for good; ranked below a car behind it on the road; does not block; race ends |
| `test_pass_in_progress_is_abandoned_when_flags_come_out` | 149–167 | traffic interaction: VSC mid-pass → `"aborted"`; the pass completes only after VSC |
| `test_time_penalty_reorders_the_classification` | 170–175 | the road winner is classified second |
| `test_drive_through_is_served_under_green_or_converted_at_the_flag` | 178–194 | exactly +20 s when served; converted at the finish; not served under SC |
| `test_penalty_for_a_retired_car_is_ignored` | 197–201 | `"ignored"` |
| `test_two_dry_compound_rule` | 204–215 | one compound → +30 s; two → 0; same compound refitted → +30 s; inters → exempt; rule off |
| `test_events_are_logged_in_time_order_with_the_cars_affected` | 218–230 | time order; retirement → flag → penalty at the same moment; cars listed |
| `test_pit_stop_under_vsc_costs_less_than_under_green` | 233–242 | pit-stop interaction (relative loss 21.8 s green, 15.5 s VSC) |
| `test_drs_needs_green_flags_and_a_dry_enough_track` | 245–259 | weather and traffic interaction |
| `test_no_passes_under_safety_car_and_racing_resumes_after` | 262–268 | traffic interaction |
| `test_v4_race_results_unchanged_without_race_control` | 271–288 | regression: V4 results recorded at `22b3668`; a quiet `RaceControl` gives identical results |

### `README.md` (modified)

Updated for V5: current version, race-control configuration, how to reproduce V4, the race-control example with expected output, test commands, layout and doc links.

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Command | When | Result |
|---|---|---|
| All five existing test files | before V5 changes | `ok` |
| V4 weather, traffic and stops race | before V5 changes | values recorded in `test_v4_race_results_unchanged_without_race_control` |
| `python3 test_simulation.py` | after V5 | `ok` (2 tests, 0.2 s) |
| `python3 test_race.py` | after V5 | `ok` (12 tests, V1 regression, 0.9 s) |
| `python3 test_tyres_fuel_pits.py` | after V5 | `ok` (13 tests, V2 regression, 1.2 s) |
| `python3 test_traffic.py` | after V5 | `ok` (15 tests, V3 regression, 1.3 s) |
| `python3 test_weather.py` | after V5 | `ok` (12 tests, 1.5 s) |
| `python3 test_race_control.py` | after V5 | `ok` (17 tests, V4 regression, 2.9 s) |
| README race-control example | after V5 | output exactly as shown in the README, 3.2 s |
| README V2, V3 and V4 examples, `python3 main.py` | after V5 | unchanged (no race control) |

**Mutation check (manual, not committed).** In a scratch copy, 21 deliberate bugs were introduced one at a time:

- an SC downgrade allowed;
- any flag change allowed;
- no SC catch-up;
- VSC with no effect;
- yellow with no effect;
- overtaking always allowed;
- no extension;
- no SC queue;
- the SC ending without a line crossing;
- YELLOW and VSC never ending;
- retirements not applied;
- retired cars ranked among running ones;
- time penalties dropped;
- drive-throughs served under SC;
- drive-throughs not converted;
- no wet-tyre exemption;
- DRS always allowed;
- passes not abandoned under flags;
- retired cars still on track;
- no car-number validation;
- passing attempts allowed under flags.

The first run missed three of them (the retired-car ranking, abandoning passes, and retired cars treated as on track). The retirement test was strengthened and `test_pass_in_progress_is_abandoned_when_flags_come_out` was added; all 21 are now caught.

No test was skipped. pytest is not used.

## Commands

```bash
python3 test_simulation.py && python3 test_race.py && python3 test_tyres_fuel_pits.py \
  && python3 test_traffic.py && python3 test_weather.py && python3 test_race_control.py
python3 main.py              # V3-style race, no race control (unchanged)
```

The README "Race control example" runs a race with incidents and penalties.

## Deliberately absent in V5

| Feature | Status |
|---|---|
| Calibration of flag effects and penalties | V6 |
| RL interface, learned strategies | V7–V8 |
| Red flags, investigations and stewarding, blue flags, unlapping, the chequered-flag rule for lapped cars, a safety-car vehicle, restart procedures, random or physics-based incidents | not implemented (see IMPLEMENTATION.md §13) |

## Known limitations

See IMPLEMENTATION.md §13. In short:

- the SC is not a car;
- restarts are instant;
- one yellow zone at a time;
- VSC is a uniform slow-down;
- incidents are scripted only;
- time penalties are added at the end;
- the two-compound sanction is a model choice;
- there is no lapped-car handling;
- fuel and wear are unchanged on slow laps;
- event times are quantised to `dt`;
- all values are placeholders;
- `main.py` does not use race control.
