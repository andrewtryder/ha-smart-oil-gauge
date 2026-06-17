# Local Development and Testing

We welcome community contributions. Below are the guidelines for testing, running linters, and verifying your changes.

### 1. Local Python Environment Setup
We use Python virtual environments to manage linter configurations and test suites locally:
```bash
# Initialize virtual environment
python3 -m venv .venv

# Install test and development dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest pytest-homeassistant-custom-component pytest-cov pytest-asyncio aresponses ruff pre-commit
```

### 2. Pre-commit & Ruff Checks
We enforce style checks and import sorting using `ruff`. Run them before submitting code:
```bash
# Install git hooks
.venv/bin/pre-commit install

# Run checks manually on all files
.venv/bin/pre-commit run --all-files
```

### 3. Running Unit Tests
We use `pytest` combined with `pytest-homeassistant-custom-component` to run our test suite:
```bash
.venv/bin/pytest
```
To run tests with code coverage outputs:
```bash
.venv/bin/pytest --cov=custom_components/smart_oil_gauge --cov-report=term-missing
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
