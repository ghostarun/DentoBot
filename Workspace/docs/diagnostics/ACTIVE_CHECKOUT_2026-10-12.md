# Sole active checkout and preserved legacy inventory — 12 October 2026

Tarun explicitly selects one working development tree and main publication. Active: `/home/tarun/dentobot/ros2_ws/src/DentoBot` on `main`. Controlled docs now live at this active checkout; the advisor checkout is legacy. All other registered worktrees below are legacy snapshots, not active development targets. Keep their branches/HEADs/files, dirty edits and retained runtime source pins unchanged. Temporary explicitly authorized implementation auxiliaries retain distinct worktree/branch isolation and become legacy after integration; they do not create a second long-term active checkout.

Inventory before publication: **65 registered worktrees total: one active plus64 legacy**. No worktree is removed or relocated. This is checkout routing metadata, not a pending-work queue or evidence of application acceptance. One historical tree is dirty; its edits are excluded from publication and preserved in place.

| Legacy checkout | Preserved HEAD | Branch/state | Dirty at inventory |
|---|---|---|---|
| `/home/tarun/dentobot-handoffs/20261007T152028Z-d094adb88175472ea109f58850ebb476/repo` | `851d9639c5ac` | `handoff/20261007T152028Z-d094adb88175472ea109f58850ebb476` | No |
| `/home/tarun/dentobot-worktrees/ab-parity` | `709419de9005` | `p0/ab-parity-2026-10-09` | No |
| `/home/tarun/dentobot-worktrees/ab-parity-gpu-gate` | `e931405522cf` | `p0/ab-parity-gpu-gate-2026-10-09` | No |
| `/home/tarun/dentobot-worktrees/advisor-batch-fix` | `0b614de70cbe` | `p0/advisor-ui-batch` | No |
| `/home/tarun/dentobot-worktrees/advisor-f1-fix` | `74348719aa2c` | `p0/advisor-f1-base-revision-restore` | No |
| `/home/tarun/dentobot-worktrees/advisor-f5-fix` | `e1b5e6709710` | `p0/advisor-f5-landmarks-optional` | No |
| `/home/tarun/dentobot-worktrees/advisor-gui-2026-10-08` | `35600cd0fabf` | `p0/advisor-gui-2026-10-08` | No |
| `/home/tarun/dentobot-worktrees/advisor-gui-state-audit` | `9e9d90ffcb95` | `p0/s6-gui-state-audit` | No |
| `/home/tarun/dentobot-worktrees/advisor-home-acceptance-binding-20261012` | `35600cd0fabf` | `repair/advisor-home-acceptance-binding-20261012` | No |
| `/home/tarun/dentobot-worktrees/advisor-input-uinput` | `931efc819b30` | `p0/s6-input-uinput` | No |
| `/home/tarun/dentobot-worktrees/advisor-luna-invariants-20261008` | `ddbad8e3dc7b` | `p0/advisor-session-routing-l1-20261009` | No |
| `/home/tarun/dentobot-worktrees/advisor-luna-review-20261008` | `2ee8345ee393` | `detached` | No |
| `/home/tarun/dentobot-worktrees/advisor-luna-review-final-20261008` | `63d93ac2a688` | `detached` | No |
| `/home/tarun/dentobot-worktrees/advisor-luna-video-20261008` | `731148efe051` | `p0/advisor-luna-video-20261008` | No |
| `/home/tarun/dentobot-worktrees/advisor-review-provenance-20261008` | `01eb376adc52` | `detached` | No |
| `/home/tarun/dentobot-worktrees/advisor-w1-review` | `8cb69763a789` | `detached` | No |
| `/home/tarun/dentobot-worktrees/advisor-w3-gui-tests` | `a2dcbbf66b48` | `p0/advisor-w3-gui-tests` | No |
| `/home/tarun/dentobot-worktrees/advisor-w4-home-unit` | `e32d2641bf4a` | `p0/advisor-w4-home-unit` | No |
| `/home/tarun/dentobot-worktrees/branch-restore-fix` | `93f77cf93bc7` | `p0/s6-branch-restore-fix` | No |
| `/home/tarun/dentobot-worktrees/dcp-partial-case-complete-astra-20261011` | `35600cd0fabf` | `repair/dcp-partial-case-complete-astra-20261011` | No |
| `/home/tarun/dentobot-worktrees/dcp-partial-load-20261010` | `00db1a8eb21e` | `repair/dcp-partial-load-20261010` | No |
| `/home/tarun/dentobot-worktrees/frame-sync-l2-fix` | `38424d14a8c2` | `p0/frame-sync-l2-fix` | No |
| `/home/tarun/dentobot-worktrees/stale-step-a-fixes` | `a631f47863ed` | `p0/stale-step-a-fixes` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-handoff-20261007T213258Z-ebf146c5fa0944a3a2603b51114c4652` | `765c240b4f84` | `handoff/20261007T213258Z-ebf146c5fa0944a3a2603b51114c4652` | Yes; preserved |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-0000b4e4cd40` | `0000b4e4cd40` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-068ca378557d` | `068ca378557d` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-0971051150a0` | `0971051150a0` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-0cc888bfb366` | `0cc888bfb366` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-0d1e9b565464` | `0d1e9b565464` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-13649e66dfa8` | `13649e66dfa8` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-144874e56782` | `144874e56782` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-25f64bb46144` | `25f64bb46144` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-2b49251de5f0` | `2b49251de5f0` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-34f5a7a6aa6b` | `34f5a7a6aa6b` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-3562de5dab91` | `3562de5dab91` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-3958e2ce275d` | `3958e2ce275d` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-3961b6ce0b4e` | `3961b6ce0b4e` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-4153c794633d` | `4153c794633d` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-473680725b90` | `473680725b90` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-474f1d83c8fe` | `474f1d83c8fe` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-51f2a017cf11` | `51f2a017cf11` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-5ed8b386855d` | `5ed8b386855d` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-6468f6edab11` | `6468f6edab11` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-6c3c0da6c4c8` | `6c3c0da6c4c8` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-829426e1354e` | `829426e1354e` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-82e1cf13a2e3` | `82e1cf13a2e3` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-86caabad4424` | `86caabad4424` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-89b4ec54a8dd` | `89b4ec54a8dd` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-8adeb9d4ae47` | `8adeb9d4ae47` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-8e7e0b2662f9` | `8e7e0b2662f9` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-912fa3801a0b` | `912fa3801a0b` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-a46a0a2ec63d` | `a46a0a2ec63d` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-a4f9aa19bf16` | `a4f9aa19bf16` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-ac030b44e4fa` | `ac030b44e4fa` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-bb0169f7a6bf` | `bb0169f7a6bf` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-bd261482c273` | `bd261482c273` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-bfb6b98ebf78` | `bfb6b98ebf78` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-cab6c74` | `cab6c7483365` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-cab6c7483365` | `cab6c7483365` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-d5194450f4ff` | `d5194450f4ff` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-ddbad8e3dc7b` | `ddbad8e3dc7b` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-e146bb9abc0f` | `e146bb9abc0f` | `detached` | No |
| `/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-fe0af4a77f03` | `fe0af4a77f03` | `detached` | No |
| `/home/tarun/dentobot/tmp/goal2-visible-case` | `e9d246c44dfc` | `test/plat-u-07-goal2-visible-case` | No |

Publication evidence: `data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-MAIN-PUBLICATION-20261012T032331Z/`. Original inventory records are outside Git. Main receives the clean integrated source plus controlled routing records; no runtime/model/data payloads or unreviewed dirty legacy edits are added.
