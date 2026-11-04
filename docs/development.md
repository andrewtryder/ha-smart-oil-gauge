# Local Development and Testing

We welcome community contributions. Below are the guidelines for testing, running linters, and verifying your changes.

### 1. Local Python Environment Setup
This repository uses [`uv`](https://docs.astral.sh/uv/) for development dependency management and execution. It targets Python 3.14 (Home Assistant 2026.3+).
```bash
# Synchronize locked dependencies into virtual environment
uv sync --locked
```

### 2. Pre-commit & Ruff Checks
We enforce style checks and format rules using `ruff`. Run them before submitting code:
```bash
# Install git hooks
uv run --locked pre-commit install

# Run checks manually on all files
uv run --locked pre-commit run --all-files

# Or run ruff directly
uv run --locked ruff check .
uv run --locked ruff format --check .
```

### 3. Running Unit Tests
We use `pytest` combined with `pytest-homeassistant-custom-component` and network isolation:
```bash
# Run pytest with offline socket isolation
uv run --locked pytest --disable-socket --allow-unix-socket -p no:cacheprovider
```
To run tests with code coverage outputs:
```bash
uv run --locked pytest --cov=custom_components/smart_oil_gauge --cov-report=term-missing --disable-socket --allow-unix-socket -p no:cacheprovider
```

### 4. Integration Core Verification (`hassfest`)
We validate the custom component's structural sanity against Home Assistant core requirements using `hassfest` via Docker:
```bash
docker run --rm -v "$(pwd):/github/workspace" ghcr.io/home-assistant/hassfest
```

### 5. Running Home Assistant Locally (Sandbox Testing)
You can test the custom component in a real Home Assistant container on your Mac:
```bash
docker run -d \
  --name homeassistant-test \
  --privileged \
  -v "$(pwd)/custom_components:/config/custom_components" \
  -p 8123:8123 \
  ghcr.io/home-assistant/home-assistant:stable
```
Once launched, open `http://localhost:8123` in your browser, perform the onboarding steps, and add the **Smart Oil Gauge** integration.
