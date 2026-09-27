# hexmap-web conventions

The portable standard governs this repo. Read it before working here:

    https://github.com/sear-labs/code-standard    canonical - same from any machine

# Part 11 - This project specifically

**Archetype C, library.** It was split out of `tarrant-landvalue-gis` so other map projects can
install it rather than copy it (Part 2: split when someone consumes one half without the other).
It gets real coverage, SemVer and a changelog, and its public API is `hexmap_web.__all__`.

**The templates stay generic.** Every word on a page comes from the project's `MapSpec`. A test
fails if a project's name appears in `templates/`. Formatting happens in Python (`fmt`), never
in the page.

**Library versions in the pages are pinned** (`page.py`): a page must render the same next year.
Change one only by bumping it, checking both pages in a browser and noting it in `CHANGELOG.md`.

**No data here.** The example and the tests use synthetic data. Nothing a project maps enters
this repo.

The four starting questions (Part 2c):
- Sensitivity: code only.
- Active: yes.
- Syncing folder: no; it is under dev/repo.
- Writers: one machine (IE-132612).

Public since v0.1.0 (Dr. Jones, 2026-09-27): generic code, no data. Every change goes through a pull
request, and Dr. Jones merges.
