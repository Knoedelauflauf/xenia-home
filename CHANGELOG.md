# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> **Note:** This project did not previously maintain a changelog. This file
> starts from this point forward — for earlier changes, see the
> [commit history](https://github.com/Knoedelauflauf/xenia-home/commits/main)
> and [tags](https://github.com/Knoedelauflauf/xenia-home/tags).

## [Unreleased]

### Added

- `machine_status` sensor exposing the machine's raw status
  (off/on/eco/brewing/draining/unknown), previously only used internally
  for polling-interval selection and switch state.
- `shot_timer` sensor: a live, whole-second shot duration display. Starts
  when brewing begins, freezes at the final value when it ends, and resets
  to 0 after a configurable delay.
- New options: shot timer idle-reset delay (seconds) and an optional
  pump-pressure threshold to delay the timer's start past the
  pre-infusion/ramp-up phase.

### Changed

- The integration now reloads automatically when its options are changed,
  instead of requiring a manual reload of the integration.
