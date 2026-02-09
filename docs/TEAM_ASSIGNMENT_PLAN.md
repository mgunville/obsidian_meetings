# Team Assignment Plan

Use these lanes so coders can work mostly independently.

## Lane A: Core CLI and Config
- Stories: E1-S1, E1-S2, E1-S3, E7-S1
- Output: stable command contracts and doctor checks

## Lane B: Calendar Backend
- Stories: E2-S1, E2-S2, E2-S3, E2-S4
- Output: now-or-next event JSON contract
- Dependency handoff: provide fixture JSON for Lane C/D tests

## Lane C: Notes and Patching
- Stories: E3-S1, E3-S2, E3-S3, E3-S4
- Output: deterministic note creation + safe updates

## Lane D: Recording and Runtime State
- Stories: E4-S1, E4-S2, E4-S3, E4-S4, E4-S5
- Output: start/stop/status contract for UX

## Lane E: Processing Pipeline
- Stories: E5-S1, E5-S2, E5-S3, E5-S4, E5-S5
- Output: transcript/summary/audio conversion flow

## Lane F: UX Macros and Packaging
- Stories: E6-S1, E6-S2, E6-S3, E6-S4, E6-S5, E7-S2, E7-S3
- Output: KM macro package + quickstart docs + smoke checks

## Integration Milestones
1. Milestone M1: E1 + E2 + E3 done (note creation from calendar)
2. Milestone M2: E4 done (recording loop stable)
3. Milestone M3: E5 done (processing pipeline complete)
4. Milestone M4: E6 + E7 done (team-ready UX and setup)

## Recommended Team Cadence
- Daily: 15-minute contract sync across lanes.
- Merge policy: story PRs must include tests.
- Contract changes: update consuming lane in same day.
