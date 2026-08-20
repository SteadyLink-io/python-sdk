# Contributing

## Setup

```bash
python -m pip install build pytest twine
pytest
```

## Pull requests

- Keep changes focused and add tests for public behavior.
- Preserve backward compatibility unless the change is planned for a major release.
- Update the README and changelog when the public API changes.
- Run `pytest`, `python -m build`, and `python -m twine check dist/*` before opening a pull request.

## Releases

1. Update the version in `pyproject.toml` and `steadylink/__init__.py`.
2. Move release notes into a new section in `CHANGELOG.md`.
3. Merge the release commit to `main`.
4. Publish a matching GitHub release, such as `v0.2.0`.

The release workflow publishes through PyPI Trusted Publishing. Maintainers should not add long-lived PyPI tokens to the repository.
