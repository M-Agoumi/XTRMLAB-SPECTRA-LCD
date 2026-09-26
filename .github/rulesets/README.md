# Branch and tag rulesets

These are GitHub [repository rulesets](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
kept in the repo so the protection settings are reviewable and easy to
restore. Files in this folder do nothing by themselves; a maintainer
imports them once:

**Settings → Rules → Rulesets → New ruleset → Import a ruleset**, then
pick the JSON file.

| File | Protects | What it enforces |
| --- | --- | --- |
| `develop.json` | `develop` | No direct pushes, force-pushes or deletion. Changes land through a PR with 1 code-owner approval, resolved threads, and green `test` + `frontend` checks. |
| `main.json` | `main` | Same as develop, merge commits only (release PRs from develop). |
| `release-tags.json` | `v*` tags | Release tags can't be moved or deleted, except by an admin. |

Repository admins are bypass actors in **pull request mode**: an admin
can merge their own PR without a second approval, but still can't push
straight to the branch. The `beta-latest` tag is not covered, since CI
moves it on every develop push.

The required checks `test` and `frontend` are job names in
`.github/workflows/build.yml`. If you rename a job, update the rulesets
too, or every PR will wait forever on a check that never reports.
