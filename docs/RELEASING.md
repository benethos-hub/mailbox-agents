# Releasing

A release is its own `release/X.Y.Z` branch and pull request. It carries
one version for the package `benethos-mailbox-agents` on PyPI and for the
image of the same name on ghcr.io. A release, its tag and its publication
are the owner's step, never a default.

The steps in order:

1. **The line of the mailbox service.** A release works against the lines
   in `TESTED` in `sources/mailbox.py` and against no other. A new line of
   the service is a change of its own before the release, by the steps of
   [concept/mailbox-service.md](concept/mailbox-service.md), "The version
   of the service". While the service is at 0.x, each of its minor
   releases needs a release of the agents.
2. **The pins.** `uv lock --upgrade --dry-run`. If it moves anything, run
   `uv lock --upgrade` as a commit of its own, then all gates. Check the
   other pins as well: the base images of the Dockerfile and the images of
   `containers/live/compose.yaml`, a newer tag or a new digest under the
   same tag, and the actions of the workflows. Each update is a commit of
   its own. The issue "Pinned versions have newer releases", which
   `freshness.yml` keeps daily, lists the same, but only as of its last
   run. A raise of the mailbox client or of the image of the mailbox
   service wants a run of the live checks, see
   [concept/testing.md](concept/testing.md).
3. **The version.** Set `version` in `pyproject.toml`, as PEP 440 writes
   it, `0.2.0` or `0.2.0a1`, then `uv lock` and `uv sync`. Set it as well
   as `MAILBOX_AGENTS_VERSION` in `containers/production/.env.example`,
   which a test holds to it.
4. **The changelog.** Close `[Unreleased]` in `CHANGELOG.md` as
   `[X.Y.Z] - <date>`, in the same commit as step 3, and open an empty
   `[Unreleased]` above it. The section names the lines of the mailbox
   service the release works against. At the foot of the file, set the
   link `[Unreleased]` to `compare/vX.Y.Z...HEAD` and add the link
   `[X.Y.Z]`. A test holds the first section and both links to
   `pyproject.toml`. In the same commit, the top row of
   [COMPATIBILITY.md](COMPATIBILITY.md) names the version, its lines and
   the pin of the client, without the note "(not released yet)" a row
   carries before its release. A test holds the row to `pyproject.toml`
   and to `TESTED`.
5. **The migrations.** Freeze the ones new in this release: add the
   fingerprint of each, `MIGRATIONS.step(N).fingerprint()`, to `RELEASED`
   in `tests/test_store.py`. A migration that shipped is never changed.
6. **The release.** After the squash merge: an annotated tag `vX.Y.Z` on
   `main`, pushed, then `gh release create vX.Y.Z --verify-tag --title
   X.Y.Z` with the section of the changelog as the notes, and
   `--prerelease` for a version that PEP 440 reads as a pre-release. The
   published release starts `publish.yml`. It waits for a green CI run of
   that very commit, checks that the tag is the version of
   `pyproject.toml`, uploads sdist and wheel to PyPI and pushes the image
   for linux/amd64 and linux/arm64 to ghcr.io.
7. **What shipped.** Check the package on PyPI with
   `uvx benethos-mailbox-agents@X.Y.Z --version`, and the tags of the
   image: `X.Y.Z` and `X.Y`, and `latest` for a full release, all on the
   same revision. A pre-release gets its exact version only. The run of
   `freshness.yml` that follows each publish installs the release from
   PyPI and asks it for its help.
