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
