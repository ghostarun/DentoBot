# GitHub Actions plan: publish lab SlicerROS2 image to GHCR

**Status:** PLAN / DESIGN ONLY — **no** `.github/workflows/*.yml` is committed
with this document. Implement later on a narrow `lab/gha-publish` branch → PR
into `main`.

**Audience:** maintainers who cut `lab/*` pins and publish
`ghcr.io/ghostarun/dentobot/slicerros2`.

**Related logbook:** `Workspace/docs/logbook/2026-09-09.md` (afternoon section:
lab update channel, GHCR publish, GHA lessons).

**Official tutorial (cite when implementing):**
https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images

---

## 1. Purpose

Provide a **maintainer CI** path that builds and pushes
`ghcr.io/ghostarun/dentobot/slicerros2` from `Workspace/Dockerfile.slicerros2`
with correct OCI labels and tags aligned to `Workspace/LAB_RELEASE`.

Lab PCs continue to **only pull** via `update-lab-release.bat` /
`update-lab-release.bash` (and the Desktop “Update Dentobot Lab” launcher).
They must never rebuild `Dockerfile.slicerros2` on lab hardware.

## 2. Non-goals

- **No lab PC image rebuilds** — update channel pulls digests only.
- **No auto-merge** of `integration/gui-step6` (or any product branch).
- **No replacement** of `update-lab-release` / desktop update bats.
- **This commit is planning only** — docs under `Workspace/docs`; do not add
  workflow YAML until a dedicated implementation PR.
- Not a general multi-arch matrix or release-please automation in v1.

## 3. Triggers (proposed)

1. **`workflow_dispatch` (primary for v1)**
   - Inputs (proposed):
     - `image_tag_suffix` or explicit `image_tag` (e.g. `jazzy-moveit-sim-YYYYMMDD`)
     - `dry_run` (boolean): build/metadata only, skip push
   - Lets maintainers publish after `LAB_RELEASE` / tag are already correct.

2. **Optional later:** `push` of tags matching `lab/*`
   - Only **after** the pin commit that sets `LAB_RELEASE` `IMAGE` /
     `COMPOSE_IMAGE` already exists on the tagged SHA.
   - Do **not** run on every `main` push — the image is large (~24 GB class);
     burning runner time/disk on unrelated docs or GUI merges is wasteful and
     risky.

## 4. Permissions

Least-privilege **job-level** `permissions` block:

```yaml
permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write
```

- `contents: read` — checkout.
- `packages: write` — push to GHCR with `GITHUB_TOKEN`.
- `attestations: write` + `id-token: write` — only needed if enabling artifact
  attestation (recommended when implementing; can stage behind a flag).

Avoid repo-wide default write. Prefer job block over workflow-wide excess.

## 5. Auth

- **Prefer** `GITHUB_TOKEN` + `docker/login-action`:
  - `registry: ghcr.io`
  - `username: ${{ github.actor }}`
  - `password: ${{ secrets.GITHUB_TOKEN }}`
- Package `ghcr.io/ghostarun/dentobot/slicerros2` must remain **linked to this
  repository** with Actions write access so the job token can push.
- **Avoid long-lived PATs for CI.** The Tarun-X1 manual publish required
  `write:packages` on a human PAT; that was an emergency path, not the
  steady-state methodology.
- Lesson from 2026-09-09: missing `write:packages` produced
  `permission_denied` while **`docker push` still exited 0** — CI must treat
  push/manifest verification as the success gate, not the CLI exit code alone.

## 6. Image naming

Publish to:

```text
ghcr.io/ghostarun/dentobot/slicerros2:<tag>
```

where `<tag>` comes from **`LAB_RELEASE` `IMAGE`** (e.g.
`jazzy-moveit-sim-YYYYMMDD`), **not** from `github.repository` (which is
`ghostarun/DentoBot` and would mint the wrong package path if used as the
image name).

Also push / retain digest references as emitted by `build-push-action` /
`metadata-action`. Keep older tags (e.g. `…20260903`) on GHCR unless an
explicit retention policy says otherwise.

## 7. Build context

- **Context:** `Workspace`
- **Dockerfile:** `Workspace/Dockerfile.slicerros2` (`file: Dockerfile.slicerros2`
  relative to that context)

Do not use the monorepo root as context unless the Dockerfile paths are
rewritten (they are not today).

## 8. Build-args / OCI labels

Map from `Workspace/LAB_RELEASE` + git so the published image identity matches
what `publish-lab-image.bash` expects locally (identity checks remain the
local gate if that script stays in the maintainer path).

Proposed build-args / labels:

| Arg / label | Source |
|---|---|
| `DENTOBOT_IMAGE_REVISION` | Full SHA of the annotated `lab/*` tag (or workflow SHA on pure dispatch if documented) |
| `DENTOBOT_IMAGE_VERSION` | `DENTOBOT_TAG` (`lab/YYYY-MM-DD`) |
| `SLICERROS2_GIT_URL` | From `LAB_RELEASE` |
| `SLICERROS2_SHA` | From `LAB_RELEASE` |

Also set standard OCI labels (`org.opencontainers.image.version`,
`org.opencontainers.image.revision`, source/url as already used on
20260909 re-label) consistently with the lab tag.

**Must** satisfy `publish-lab-image.bash` identity checks if that script
remains the local gate for tagging/pushing.

## 9. Recommended actions (pin by SHA when implementing)

Follow the GitHub tutorial pattern; **pin each action to a full commit SHA**
at implementation time (do not leave floating major tags in production YAML):

1. `actions/checkout`
2. `docker/login-action` — GHCR login with `GITHUB_TOKEN`
3. `docker/metadata-action` — tags/labels for
   `ghcr.io/ghostarun/dentobot/slicerros2`
4. `docker/setup-buildx-action`
5. `docker/build-push-action` — context `Workspace`, file
   `Dockerfile.slicerros2`, build-args from §8, push unless `dry_run`
6. Optional: `actions/attest-build-provenance` (or current attest action from
   the tutorial) when `attestations`/`id-token` permissions are enabled

### Cache strategy note

`LABEL` / `ARG` lines appear **early** in `Dockerfile.slicerros2`, so changing
revision/version build-args **busts Docker layer cache** from that point.
Document and implement:

- Registry cache (`cache-from` / `cache-to` type=registry) keyed by previous
  lab image tag when possible;
- Accept that label-only bumps may still rebuild large layers unless the
  Dockerfile is later reordered (out of scope for v1 plan);
- Tarun-X1’s **thin local re-label** (20260909) was an emergency/RAM
  workaround — CI should prefer a **real Dockerfile build** on hosted runners.

## 10. Ordering with `LAB_RELEASE`

Recommended maintainer sequence:

1. **A.** Change Dockerfile / stack on a branch/PR if the image contents need
   to change.
2. **B.** On `main`: set `LAB_RELEASE` `IMAGE` / `COMPOSE_IMAGE` to the **new**
   tag name; bump `DENTOBOT_TAG` if cutting a new lab pin.
3. **C.** Create annotated `lab/*` tag and push the tag.
4. **D.** Run the workflow (`workflow_dispatch` or tag trigger) to
   **build+push** that `IMAGE` tag with labels matching the tag SHA.
5. **E.** Lab PCs: run **Update Dentobot Lab.bat** (bootstrap helper from
   `origin/main` so frozen tags see new pins).

**Document clearly:** the thin local re-label used for `20260909` on Tarun-X1
was an **emergency / RAM workaround**, not the steady-state path. Steady-state
is CI real builds (§9) after the pin sequence above.

## 11. Verification checklist

After a successful workflow run (or during dry-run/local dry checks):

- [ ] `docker buildx imagetools inspect` (or equivalent) shows the expected
      tag + digest on GHCR
- [ ] `docker pull ghcr.io/ghostarun/dentobot/slicerros2:<tag>` succeeds
- [ ] Label inspect: version = `lab/YYYY-MM-DD`, revision = expected SHA,
      slicer SHA matches `LAB_RELEASE`
- [ ] From a **previous** lab tag checkout, run `update-lab-release` bootstrap
      (from `origin/main`) and confirm pull/skip/colcon behavior
- [ ] On Tarun-X1: CUDA launcher `--check-only` still green after update
- [ ] Do **not** trust `docker push` exit code alone (2026-09-09 false
      negative / exit-0 lesson)

## 12. Risks

| Risk | Mitigation |
|---|---|
| Runner disk/time for ~24 GB-class image | Prefer `workflow_dispatch` / tag triggers; not every `main` push; monitor runner disk; consider larger runners if GitHub offers them for the org |
| GHCR visibility private | Keep package private; ensure lab tokens/`gh` auth can pull; document lab login |
| Token scope mistakes | Prefer `GITHUB_TOKEN` + package linked to repo; avoid under-scoped PATs |
| `docker push` exit 0 false negative | Manifest inspect + pull gate in CI |
| Merge conflict with `integration/gui-step6` | Keep workflow under `.github/` and docs under `Workspace/docs/` only; implement YAML via narrow PR |

## 13. Conflict avoidance with active development

- Branch **`integration/gui-step6`** owns Step 6 GUI product work.
- This plan and the accompanying logbook touch **only** `Workspace/docs`
  (and, later, `.github/workflows`).
- **Never** edit Slicer module / Step 6 panels in the same commit as lab CI
  docs.
- When implementing YAML later: open a **narrow PR** from `lab/gha-publish`
  into `main` — do not bundle GUI product commits with workflow landing.

## 14. Draft YAML sketch

> **NOT COMMITTED / NOT ACTIVE — sketch only for review.**
> Copy into `.github/workflows/publish-lab-slicerros2.yml` only in a future
> implementation PR. Action SHAs below are **placeholders** — replace with
> current full commit SHAs at implementation time.

```yaml
# NOT COMMITTED / NOT ACTIVE — sketch only for review
name: Publish lab SlicerROS2 image

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "IMAGE tag from LAB_RELEASE (e.g. jazzy-moveit-sim-YYYYMMDD)"
        required: true
        type: string
      dry_run:
        description: "Build and print metadata but do not push"
        required: false
        type: boolean
        default: false
  # Optional later — enable only after pin+tag ordering is documented for ops:
  # push:
  #   tags:
  #     - "lab/*"

permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@0000000000000000000000000000000000000000  # pin SHA

      - name: Log in to GHCR
        uses: docker/login-action@0000000000000000000000000000000000000000  # pin SHA
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@0000000000000000000000000000000000000000  # pin SHA
        with:
          images: ghcr.io/ghostarun/dentobot/slicerros2
          tags: |
            type=raw,value=${{ inputs.image_tag }}

      - name: Set up Buildx
        uses: docker/setup-buildx-action@0000000000000000000000000000000000000000  # pin SHA

      - name: Read LAB_RELEASE identity
        id: lab
        run: |
          # Parse Workspace/LAB_RELEASE for DENTOBOT_TAG, SLICERROS2_*, IMAGE
          # Export DENTOBOT_IMAGE_VERSION / REVISION / SLICERROS2_* for build-args
          echo "Implement parser in real workflow; keep identity checks aligned with publish-lab-image.bash"

      - name: Build and push
        uses: docker/build-push-action@0000000000000000000000000000000000000000  # pin SHA
        with:
          context: Workspace
          file: Workspace/Dockerfile.slicerros2
          push: ${{ inputs.dry_run == false }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            DENTOBOT_IMAGE_REVISION=${{ github.sha }}
            DENTOBOT_IMAGE_VERSION=${{ steps.lab.outputs.dentobot_tag }}
            SLICERROS2_GIT_URL=${{ steps.lab.outputs.slicerros2_git_url }}
            SLICERROS2_SHA=${{ steps.lab.outputs.slicerros2_sha }}
          # cache-from / cache-to: registry cache keyed by previous lab tag

      - name: Verify manifest (fail closed)
        if: ${{ inputs.dry_run == false }}
        run: |
          docker buildx imagetools inspect \
            "ghcr.io/ghostarun/dentobot/slicerros2:${{ inputs.image_tag }}"

      # Optional: attest build provenance per GitHub tutorial
```

---

## Implementation follow-ups (out of scope for this docs commit)

1. Create branch `lab/gha-publish` from current `main`.
2. Add `.github/workflows/publish-lab-slicerros2.yml` from the sketch with
   real action SHAs and a real `LAB_RELEASE` parser step.
3. Open a narrow PR into `main`; do not combine with `integration/gui-step6`.
4. After merge: dry-run dispatch, then a real publish for the next lab pin.
