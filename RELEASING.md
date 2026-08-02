# Releasing PyCForge

PyCForge publishes immutable, reproducible distributions from an exact version
tag. The normal `pip install pycforge` contract includes the PyQt5 desktop
application; there is no workspace extra.

## One-time PyPI setup

Create a pending Trusted Publisher for a new PyPI project with these exact
values:

- PyPI project name: `pycforge`
- GitHub owner: `lastforkbender`
- GitHub repository: `pycforge`
- workflow: `release.yml`
- environment: `pypi`

Create the matching protected GitHub environment named `pypi`. No long-lived
PyPI API token belongs in GitHub secrets.

## Release procedure

1. Require a green `CI` workflow on `main`.
2. Confirm `pyproject.toml`, `pycforge/_version.py`, and the tag all use the
   same version.
3. Create and push the exact annotated tag, for example `v0.15.2`.
4. Monitor the `Release` workflow.

The tag workflow runs the complete test suite, builds a wheel and sdist,
normalizes them for reproducibility, runs strict Twine and closed-set artifact
verification, clean-installs the wheel with its mandatory PyQt5 dependency,
constructs the real desktop window offscreen, and creates a draft GitHub
release. It then publishes to PyPI using OIDC and only makes the GitHub release
public after PyPI succeeds.

Release assets are never overwritten. A rerun may reuse an existing draft only
when all three draft assets are byte-identical to the newly verified wheel,
sdist, and conversion-reference PDF.

