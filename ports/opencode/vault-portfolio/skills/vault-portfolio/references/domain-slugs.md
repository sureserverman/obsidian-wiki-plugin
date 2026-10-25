# Domain Slugs: mapping a project's stack to its decision registers

The per-domain half of the decisions register lives at
`<vault>/Portfolio/decisions/<domain>.md`, one file per architecture or platform
domain. To ask "what binds this project?" you first have to know *which domain
registers apply* — this table is that mapping.

It is the decision-register counterpart to the planning plugin's stack-routing
table, which maps the same stack signals to subagents. The two vocabularies are
deliberately paired: a task routed to a Rust specialist is a task whose decisions
live in `rust.md`. When you add a row to one table, check whether the other needs
one too.

## The vocabulary is open, not closed

**A stack with no register yet is not an error.** Domain registers are created on
first `promote`, so a project working in a domain nobody has recorded a decision
in yet will get "no matching register" — and that is a complete, correct answer,
not a failure to look. The failure mode this table prevents is the opposite one:
guessing a slug, finding nothing, and concluding nothing constrains the work.

`/vault-portfolio decisions --list-domains` shows which registers actually exist
right now; this table says which ones *would* apply.

## Stack → domain

The **Files** column is read by `domain-decisions.py`'s `infer_domains(repo)`:
each backticked pattern is a shell glob, matched against a file or directory's
name when it holds no `/`, and against its path from the repo root when it does.
Any match adds the row's slugs. Dependency and build trees (`.git`,
`node_modules`, `target`, `build`, `dist`, `vendor`, virtualenvs) and test-data
trees (`tests`, `test`, `fixtures`, `testdata`, `__tests__`) are not the repo's
own stack and are skipped. A row whose Files cell is `—` names a signal
no file shows reliably: it is never inferred, only chosen by reading the work.

| Stack signal | Files | Domain slug(s) |
|---|---|---|
| Rust crates, clippy/cargo-audit work | `Cargo.toml`, `*.rs` | `rust` |
| Kotlin / Gradle / Compose / Espresso on Android | `settings.gradle`, `settings.gradle.kts`, `AndroidManifest.xml` | `android` |
| Hardened Android builds, per-app VPN, Play-services sandboxing | — | `android` |
| Swift / SwiftUI / AppKit on desktop | `*.xcodeproj`, `Package.swift` | `macos` |
| Swift / SwiftUI / UIKit on phone or tablet | — | `ios` |
| launchd plists, `.pkg` installers, notarization, Quick Actions | — | `macos` |
| systemd units, `.deb` packaging, postinst scripts, AppArmor, Wayland compositors | `debian/control`, `*.service` | `ubuntu` |
| Isolation-focused Debian derivatives | — | `ubuntu`, `tor` |
| Tor daemon, onion services, control port, socat / stunnel / haproxy / autossh | `torrc`, `*.torrc` | `tor` |
| DNS resolvers fronting Tor, circuit isolation | — | `tor` |
| WebExtensions, `manifest.json`, add-on store review constraints | `manifest.json` | `browser-extensions` |
| GTK4 / libadwaita / GNOME desktop UI | — | `gnome` |
| WinUI / WPF | `*.xaml` | `windows` |
| Garmin Connect IQ / Monkey C | `monkey.jungle` | `garmin` |
| Web frontend, WCAG / a11y constraints | — | `web` |
| GitHub Actions workflows, release pipelines, multi-repo packaging | `.github/workflows/*.yml`, `.github/workflows/*.yaml` | `ci` |
| Anything sourced from a **security review** finding | — | `security` (see below) |
| Portfolio tooling itself — registry, vault layout, plan/backlog formats | — | `portfolio-tooling` |

## `security` is scoped by the finding, not the project

Set `Domains:` from what the constraint is *about*, not from the stack the
project happens to be written in. A finding about a Tor control-port assumption
is `tor` even when it surfaces inside an Android app — that is what lets every
Tor-adjacent project inherit it on promotion. A finding is additionally `security`
when the constraint exists *because* of an exposure rather than a platform limit.

A decision sourced from a security-review report cites the report by filename
and date only and restates the substance in its own words; the report body never
enters the vault.

## Inference is a starting point, not an authority

The digest a caller gets back is only as good as the slugs it was given. When the
stack is ambiguous (a Rust CLI that ships as a `.deb` and talks to Tor is
`rust` + `ubuntu` + `tor`), **pass all of them** — an extra register costs one
read and a few lines of digest, while a missed one costs a violated constraint
nobody notices until review. `infer_domains()` finds only what files show; add
the slugs the work itself shows.
