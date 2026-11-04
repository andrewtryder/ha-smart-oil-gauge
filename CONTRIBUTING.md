# Contributing to Smart Oil Gauge Integration

We welcome contributions to this integration! Please review these guidelines before submitting a pull request.

## Local Development Setup

This repository uses [`uv`](https://docs.astral.sh/uv/) for development dependency management and execution.

To set up a local development environment, you can use Visual Studio Code and Docker to run inside the devcontainer (configured in `.devcontainer/devcontainer.json`). This sets up Python, Home Assistant core libraries, and linters automatically.

Alternatively, you can initialize a local environment directly:

```bash
# Synchronize locked dependencies into virtual environment
uv sync --locked

# Install pre-commit hooks
uv run --locked pre-commit install
```

## Styling and Quality Checks

The portfolio standard validation interface executes the entire local test, linting, and hygiene contract:

```bash
./scripts/validate-local.sh
```

Individual styling checks can also be run manually using `ruff`:

```bash
# Run styling checks
uv run --locked ruff check .

# Check formatting
uv run --locked ruff format --check .

# Auto-format files
uv run --locked ruff format .
```

We also validate custom component structures against core guidelines using `hassfest`:

```bash
docker run --rm -v "$(pwd)/custom_components:/github/workspace/custom_components" ghcr.io/home-assistant/hassfest
```

## Testing

We use `pytest` for unit testing with network isolation. Write test cases for any new functionality and verify they pass with code coverage:

```bash
# Run pytest with offline socket isolation
uv run --locked pytest --disable-socket --allow-unix-socket -p no:cacheprovider
```

## Submitting Pull Requests

1. Fork the repository and create your branch from `main` or `master`.
2. Commit your changes and ensure all `ruff`, `pytest`, and `hassfest` checks pass.
3. Open a Pull Request detailing the changes, motivation, and verification steps.

## Pull request titles

Pull-request titles must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification. When a pull request is merged, its title becomes the squash commit title on `main`. Release Please uses that commit title to determine releases and changelog entries.

- Scopes are optional (for example, `feat(sensor): ...` or `feat: ...`).
- Intermediate branch commits do not need to follow Conventional Commits because pull requests are squash-merged.
- Breaking changes use `!`, such as `feat!: change entity identifiers`.

### Accepted types

* `feat`: user-facing feature
* `fix`: bug fix
* `deps`: dependency update
* `docs`: documentation
* `style`: formatting-only change
* `refactor`: internal restructuring
* `perf`: performance improvement
* `test`: tests
* `build`: build or dependency tooling
* `ci`: CI or automation
* `chore`: maintenance
* `revert`: revert of an earlier change

### Valid examples

```text
feat(sensor): add refill confidence
fix(auth): normalize the account email
docs: clarify HACS installation
test(coordinator): cover corrupt stored data
ci: enforce semantic pull request titles
feat!: change entity unique IDs
```

### Invalid examples

```text
Added a feature
Fix login
Update README
feat: Add refill confidence
```

The final invalid example fails because the subject starts with an uppercase letter.
