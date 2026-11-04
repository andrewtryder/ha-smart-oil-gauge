# Agent Instructions for Home Assistant Smart Oil Gauge Integration

This file provides context and instructions for AI agents (like Jules, Cursor, Antigravity) working on this repository.

## General Context
This repository contains a Home Assistant custom component integration for the "Smart Oil Gauge". It interacts with the cloud API via web scraping/HTML parsing (using `beautifulsoup4`) since there is no official API.
The core integration logic is located in `custom_components/smart_oil_gauge/`.

## File Structure
- `custom_components/smart_oil_gauge/`: The main integration code.
  - `client.py`: Handles communication with the Smart Oil Gauge portal.
  - `sensor.py`, `binary_sensor.py`, `switch.py`: Home Assistant entity platforms.
  - `config_flow.py`: Handles the UI configuration setup for Home Assistant.
  - `coordinator.py`: Data update coordinator handling the polling.
- `tests/`: Unit tests using `pytest` and `pytest-homeassistant-custom-component`.
- `pyproject.toml`: Configuration for `ruff` and `pytest`.

## Release and Commit Conventions
**CRITICAL:** This project uses `release-please` for automated changelog generation and version bumping.
You **must** follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification for all commit messages.

*   `feat: <description>`: For new features (bumps minor version).
*   `fix: <description>`: For bug fixes (bumps patch version).
*   `docs: <description>`, `chore: <description>`, `test: <description>`, `refactor: <description>`: For non-code changes (does not bump version).
*   Add `!` after the type/scope for breaking changes (e.g., `feat!: <description>`), which will bump the major version.

## Local Development and Tooling

### Python Environment
This project targets Python 3.14 (Home Assistant 2026.3+) and uses `uv` for development dependency management:
```bash
uv sync --locked
```

### Formatting and Linting (Ruff)
This project enforces code styles and format rules using `ruff`. Run these checks locally before committing changes:
```bash
# Run styling checks
uv run --locked ruff check .

# Auto-format files
uv run --locked ruff format .
```

### Pre-commit Hooks
The project uses `pre-commit`. Always ensure you run pre-commit or ensure hooks pass:
```bash
uv run --locked pre-commit run --all-files
```

### Testing (Pytest)
Tests are written with `pytest`. Run the test suite with offline network isolation to verify your changes and check coverage:
```bash
uv run --locked pytest --disable-socket --allow-unix-socket -p no:cacheprovider
```

### Hassfest Validation
When modifying the structure of the custom component, validate it using `hassfest` via Docker:
```bash
docker run --rm -v "$(pwd):/github/workspace" ghcr.io/home-assistant/hassfest
```
