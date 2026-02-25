---
type: meeting
meeting_id: "{{ meeting_id }}"
title: "{{ title }}"
start: "{{ start_iso }}"
end: "{{ end_iso }}"
calendar: "{{ calendar_name }}"
platform: "{{ platform }}"
join_url: "{{ join_url }}"
recording_wav: "{{ recording_wav_rel }}"
recording_mp3: ""
transcript_txt: ""
transcript_srt: ""
transcript_json: ""
transcript_status: "pending"
summary_status: "pending"
ai_summary_model: ""
created_via: "meetingctl"
tags:
  - work/meeting
  - ahead
  - meetingctl
---

# {{ title }}

## Context
- When: {{ start_human }} - {{ end_human }}
- Platform: {{ platform }}
- Join: {{ join_url }}

## Notes

## Minutes
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->

## Decisions
<!-- DECISIONS_START -->
> _Pending_
<!-- DECISIONS_END -->

## Action items
<!-- ACTION_ITEMS_START -->
> _Pending_
<!-- ACTION_ITEMS_END -->

## Transcript
<!-- TRANSCRIPT_START -->
> _Pending_
<!-- TRANSCRIPT_END -->

## References
<!-- REFERENCES_START -->
> _Pending_
<!-- REFERENCES_END -->
