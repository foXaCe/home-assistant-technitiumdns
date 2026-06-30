# Contributing

Thank you for contributing to **home-assistant-technitiumdns**, a fork maintained by
[@foXaCe](https://github.com/foXaCe) based on the upstream
[Atlas-Commons](https://github.com/Atlas-Commons/home-assistant-technitiumdns) project.

## Before you start

1. Search [existing issues](https://github.com/foXaCe/home-assistant-technitiumdns/issues) for duplicates.
2. For large changes, open an issue first to discuss the approach.
3. Read our [Code of Conduct](CODE_OF_CONDUCT.md).

## Developer Certificate of Origin (DCO)

**Every commit in a pull request must be signed off.**

Use `-s` when committing:

```bash
git commit -s -m "Describe your change"
```

This adds a `Signed-off-by:` line certifying you wrote the code or have the right to
submit it under the project license. See [developercertificate.org](https://developercertificate.org/).
CI verifies sign-off on every commit (`.github/scripts/verify-dco.sh`).

## Local development

```bash
# Install dev/test dependencies and the pre-commit hooks
scripts/setup            # or: pip install -r requirements_dev.txt

# Install prek (Rust drop-in for pre-commit) and the git hook
pipx install prek        # or: brew install j178/prek/prek
prek install

# Lint, format and type-check
scripts/lint             # ruff check + ruff format --check + mypy

# Run the test suite
scripts/test             # pytest
```

`prek` reads `.pre-commit-config.yaml` and is a drop-in replacement for `pre-commit`.
If you prefer the Python runner: `pipx install pre-commit && pre-commit install`.

## Dependency management

This repository uses a combo: **Renovate** opens regular dependency-update PRs, while
**Dependabot** is limited to security alerts. Renovate's PRs are signed off automatically
for DCO compliance.

## Pull request process

1. Fork the repository and create a branch from `main`.
2. Make focused changes with tests where applicable, each commit signed off (`-s`).
3. Ensure `scripts/lint` and `scripts/test` pass locally before opening the PR.
4. Open a pull request against `main` with a clear description.
5. Address review feedback; the maintainer merges when checks are green.

## Questions

Open a [GitHub Discussion](https://github.com/foXaCe/home-assistant-technitiumdns/discussions)
or an issue.
