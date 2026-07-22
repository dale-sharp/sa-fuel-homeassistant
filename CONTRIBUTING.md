# Contributing to SA Fuel Pricing

Contributions — bug reports, feature requests, and pull requests — are welcome.

## Quality bar

This integration targets the **Platinum tier of the Home Assistant Integration Quality
Scale**. Contributions are expected to conform to it, not just pass CI:

- [Integration Quality Scale rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)
- [#14](https://github.com/dale-sharp/sa-fuel-homeassistant/issues/14) — this project's
  rule-by-rule Platinum audit, tracking how those rules are interpreted and applied here

If a change touches entity behavior, config flow, or diagnostics, check whether it affects
any rule already addressed there before assuming it's fine.

## Reporting bugs and requesting features

Use the issue templates rather than a blank issue:

- **Bug report** — fill out the [bug report form](https://github.com/dale-sharp/sa-fuel-homeassistant/issues/new?template=bug_report.yml). It asks for System Health details, reproduction steps, and debug logs — these aren't optional extras, they're what makes a bug reproducible.
- **Feature request** — fill out the [feature request form](https://github.com/dale-sharp/sa-fuel-homeassistant/issues/new?template=feature_request.yml).

## Development setup

`uv` manages the environment and all dependencies (dev and runtime) from
`pyproject.toml`/`uv.lock` — there's no separate `pip install -r requirements.txt` step.

```bash
git clone https://github.com/dale-sharp/sa-fuel-homeassistant.git
cd sa-fuel-homeassistant
uv sync
```

**The devcontainer in `.devcontainer/` is the only supported way to run `uv sync`/`pytest`
locally.** Later Home Assistant releases unconditionally import POSIX-only stdlib modules
(`fcntl`, `resource`) that don't exist on Windows, at any Python version — there is no way
to route around this with version pinning, only by developing on Linux. Open the folder in
an editor with Dev Containers support (VS Code's "Reopen in Container", JetBrains Gateway),
or drive it directly with the [devcontainer CLI](https://github.com/devcontainers/cli):

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . -- uv run pytest --cov=custom_components.sa_fuel_pricing --cov-report=term-missing
```

**If your container engine is Podman on Windows** (not Docker Desktop): `docker.exe`'s
default context normally points at Docker Desktop, not Podman — set `DOCKER_CONTEXT=default`
(or use `--docker-path` pointing at your `podman` binary) before any `docker`/`devcontainer`
command. Some Docker CLI builds also have a bug where `docker version --format ...` hangs
indefinitely when talking to a non-Docker-Desktop backend — if `@devcontainers/cli` seems to
hang on startup, pass `--docker-path <path-to-podman>` to bypass the `docker` client entirely.

## Before opening a pull request

Run these locally — they're exactly what CI runs, so a clean local run means a clean CI run:

```bash
uv run pytest --cov=custom_components.sa_fuel_pricing --cov-report=term-missing
uv run ruff format .
uv run ruff check .
uv run ty check
```

- **Coverage:** current baseline is 100% overall, exceeding the Platinum-tier target of
  95%+/no module below ~90%. New code should maintain full coverage; a `# pragma: no cover`
  exclusion (already configured in `pyproject.toml`) is acceptable only for genuinely
  untestable defensive branches, not as a shortcut around writing a real test.
- `ruff format`/`ruff check` and `ty check` are separate jobs in `.github/workflows/lint.yml`.
  Running them locally first catches a CI failure before you push.
- **If `ruff check .` shows only `EXE002` findings inside the devcontainer** on a Windows
  host: this is a known, harmless local artifact — the Windows→WSL2 bind mount reports every
  file as mode `0777`, regardless of git's actually-tracked (correct, non-executable)
  permissions. It never appears in CI (a native Linux checkout, no bind mount). Run
  `uv run ruff check . --config .devcontainer/ruff-devcontainer.toml` locally to filter it
  out — that override file is never used by CI, so it can't mask a real finding there.
- `pytest` isn't run in CI — it's the local gate. Paste its actual output (not just
  pass/fail) into your PR's test plan.
- **PRs that change `custom_components/sa_fuel_pricing/` bump the version** —
  `manifest.json` + `pyproject.toml` + `uv.lock` (via `uv lock`) — and add a `CHANGELOG.md`
  entry. PRs that only touch repo tooling/docs (`.github/`, `.devcontainer/`, `README.md`,
  this file, etc.) don't need one — none of that is included in the release zip HACS
  installs, so bumping would announce a "new release" with unchanged shipped files. State
  explicitly in the PR which case applies rather than leaving it ambiguous.
- Use the [pull request template](https://github.com/dale-sharp/sa-fuel-homeassistant/blob/main/.github/pull_request_template.md)
  — its test plan section expects pasted command output, not a checkbox.

## License

By contributing, you agree that your contributions will be licensed under this project's
license (see [LICENSE](LICENSE)).
