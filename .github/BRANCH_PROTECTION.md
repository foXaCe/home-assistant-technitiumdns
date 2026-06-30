# Branch protection for `main`

Merging to `main` requires passing CI and a pull request. Configuration lives in this
repository (`.github/rulesets/main.json`) so it can be reviewed and re-applied consistently.

## What runs on every PR and push to `main`

Workflow: [`.github/workflows/ci.github.yml`](workflows/ci.github.yml)

The final job is always named **Required checks**. Branch rulesets require that status to
be green before merge.

## DCO (Developer Certificate of Origin)

Install the [DCO GitHub App](https://github.com/apps/dco) on the `foXaCe` account.

Every commit must include sign-off:

```bash
git commit -s -m "Your message"
```

## Apply the ruleset (one-time)

GitHub rulesets are configured on the repository, not via git push. The script auto-detects
the owner/repo from the `origin` remote (here: `foXaCe/home-assistant-technitiumdns`):

```bash
chmod +x .github/scripts/apply-main-ruleset.sh
./.github/scripts/apply-main-ruleset.sh
```

### Important: check name must exist first

GitHub only lets you select status checks that have run at least once. Open a PR against
`main` (or push once) **before** applying the ruleset.
