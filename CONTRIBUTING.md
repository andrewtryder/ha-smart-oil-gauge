# Contributing to Smart Oil Gauge Integration

We welcome contributions to this integration! Please review these guidelines before submitting a pull request.

## Local Development Setup

To set up a local development environment, you can use Visual Studio Code and Docker to run inside the devcontainer (configured in `.devcontainer/devcontainer.json`). This sets up Python, Home Assistant core libraries, and linters automatically.

Alternatively, you can initialize a local environment:

```bash
# Set up virtual environment
python3 -m venv .venv

# Install dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements_test.txt

# Install pre-commit hooks
.venv/bin/pre-commit install
```

## Styling and Quality Checks

We use `ruff` to enforce code styles and format rules. Run these checks locally before committing changes:

```bash
# Run styling checks
.venv/bin/ruff check custom_components/ tests/

# Auto-format files
.venv/bin/ruff format custom_components/ tests/
```

We also validate custom component structures against core guidelines using `hassfest`:

```bash
docker run --rm -v "$(pwd)/custom_components:/github/workspace/custom_components" ghcr.io/home-assistant/hassfest
```

## Testing

We use `pytest` for unit testing. Write test cases for any new functionality and verify they pass with code coverage:

```bash
# Run pytest
PYTHONPATH=. .venv/bin/pytest --cov=custom_components/smart_oil_gauge --cov-report=term-missing
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
