# Config Assets

This folder stores runtime integration assets that should stay with the project.

## Layout

- `config/km/`
  - Keyboard Maestro macro bundle(s), including `Meeting-Automation-Macros.kmmacros`.
- `config/audio_hijack_sessions/`
  - Audio Hijack session exports (`*.ah4session`) used for environment setup and backup.

## Notes

- Import Keyboard Maestro macros from:
  - `config/km/Meeting-Automation-Macros.kmmacros`
- `System+Mic` is optional and disabled by default in app behavior unless:
  - `MEETINGCTL_ENABLE_SYSTEM_PLATFORM=1`
