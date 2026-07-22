# Changelog

## [1.5.0](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.4.1...v1.5.0) (2026-07-22)


### Features

* add reauthentication flow, entity descriptions, diagnostics, refill detection, and repair notifications ([ed1905a](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/ed1905aae929f51f9684af38d3186887a794495c))


### Bug Fixes

* **ci:** adjust pytest-homeassistant-custom-component range for Python 3.13 ([51688ef](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/51688ef380553c19a2875536ae5c74631dae0903))
* **ci:** loosen pytest-asyncio range for python 3.13 pip resolution ([12a340b](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/12a340ba27fd0bb4d144deac0ed6bd4558af4a5b))
* **ci:** update workflow action commit SHAs to valid git references ([fc6ee1c](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/fc6ee1c0dbf816d0b0a0cad9477b028507751e87))
* **sensor:** clean up duplicate obsolete sensor classes post-merge ([#31](https://github.com/andrewtryder/ha-smart-oil-gauge/issues/31)) ([3df3b80](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/3df3b80e2c34d2142d1585e4e393f2d2f585fae9))

## [1.4.1](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.4.0...v1.4.1) (2026-07-04)


### Bug Fixes

* install devcontainer venv outside the workspace mount ([8b109fa](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/8b109fac4c76bcfb086d4b83bb80a8dd552567ff))
* remove sensitive cookie and header logging ([3e8ee60](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/3e8ee606fd3f1e049dbb3473a8ac69f7fea9fd49))
* remove sensitive cookie and header logging ([aae80f1](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/aae80f1f7f1cf0f83da48ecb5f1b22c978eabb35))
* remove sensitive cookie and header logging ([2eeb186](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/2eeb186da44169ceef9085842994b6bc5f66a9ce))

## [1.4.0](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.3.0...v1.4.0) (2026-06-16)


### Features

* add dynamic tank naming, configurable check intervals, and new … ([5252a98](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/5252a98770816829c7adbb2dec6de2fadd424849))
* add dynamic tank naming, configurable check intervals, and new sensors ([5cd3656](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/5cd36567558a98265d9bc9abccdc830f024a3d78))

## [1.3.0](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.2.1...v1.3.0) (2026-06-16)


### Features

* add Last Checked timestamp sensor ([9998a7b](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/9998a7bf45f0c09265cd4a6755df209e2b8676b2))

## [1.2.1](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.2.0...v1.2.1) (2026-06-16)


### Bug Fixes

* requirements_test.txt to reduce vulnerabilities ([25c4eac](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/25c4eac4702fb3b5692ceeaf0e250a61e84385ec))

## [1.2.0](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.1.3...v1.2.0) (2026-06-16)


### Features

* add integration brand icon ([ad8c934](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/ad8c9341dfdedf4a7daaa44530170611660de3d3))


### Bug Fixes

* enforce initial login and handle AJAX 401 response status ([7049fcc](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/7049fcc73daa53f2fe3a54b8fd937132a451b96c))
* supply custom User-Agent to ClientSession to avoid 401 WAF blocking ([61e7e0f](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/61e7e0f6d72732827f46af10db1b3692a7021329))

## [1.1.3](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.1.2...v1.1.3) (2026-06-16)


### Bug Fixes

* enforce initial login and handle AJAX 401 response status ([7049fcc](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/7049fcc73daa53f2fe3a54b8fd937132a451b96c))

## [1.1.2](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.1.1...v1.1.2) (2026-06-16)


### Bug Fixes

* enforce initial login and handle AJAX 401 response status ([7049fcc](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/7049fcc73daa53f2fe3a54b8fd937132a451b96c))

## [1.1.1](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.1.0...v1.1.1) (2026-06-16)


### Bug Fixes

* supply custom User-Agent to ClientSession to avoid 401 WAF blocking ([61e7e0f](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/61e7e0f6d72732827f46af10db1b3692a7021329))

## [1.1.0](https://github.com/andrewtryder/ha-smart-oil-gauge/compare/v1.0.0...v1.1.0) (2026-06-16)


### Features

* add integration brand icon ([ad8c934](https://github.com/andrewtryder/ha-smart-oil-gauge/commit/ad8c9341dfdedf4a7daaa44530170611660de3d3))
