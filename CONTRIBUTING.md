# Contributing to smspi

Thank you for considering a contribution. This project is public and maintained at [https://github.com/drhdev/smspi](https://github.com/drhdev/smspi).

## How to contribute

1. Fork the repository on GitHub.
2. Clone your fork: `git clone git@github.com:<you>/smspi.git`
3. Create a branch: `git checkout -b fix/description` or `feature/description`
4. Make focused changes; match existing Python style and logging patterns.
5. Run tests locally when possible:
   ```bash
   PYTHONPATH=src python -c "from tests.test_telegram_format import *; ..."
   ```
6. On a Raspberry Pi with hardware, run:
   ```bash
   ./scripts/smoke-test.sh
   ```
7. Open a pull request against `main` with a clear description and test notes.

## What we appreciate

- Bug fixes for ModemManager / `mmcli` integration
- Documentation improvements (README, troubleshooting)
- Safe defaults for Pi deployments
- Tests that do not require physical modems

## What to avoid

- Committing secrets (`.env`, real `config/config.yaml`, databases)
- Breaking host-only ModemManager assumption in Docker deployments
- Large unrelated refactors in a single PR

## License

By contributing, you agree that your contributions are licensed under the same **GPL-3.0-or-later** license as the project.
