# Source code and rebuilding

Incremento's source repository is
[BaskovicP/Incremento](https://github.com/BaskovicP/Incremento).
The repository contains the editable Anki add-on, PDF viewer, Companion,
translation catalogs, tests, and build scripts.

## Source for a packaged release

Every `.ankiaddon` built by `scripts/package_addon.py` has a sibling
`-source.zip` archive. `SOURCE_ARTIFACT.json` inside the add-on and its bundled
Companion records that archive's filename and SHA-256 digest. The source
archive is assembled from the working tree during the same packaging run as
the runtime package; it does not substitute the latest Git commit or branch.
Use `--release` to rebuild and verify generated assets before distribution,
and avoid editing source files while packaging is running. Ordinary packaging
without `--release` includes existing generated assets and does not verify
that they match their editable sources.

For this download-based release workflow, publish the matching source archive
alongside the binary download, with equivalent access and no additional
charge for source. Keep
the source archive available for as long as the associated binary is offered.
Do not substitute a link to a moving branch for the matching release source.
Standalone Companion/Firefox distributions must provide access to the same
source archive and preserve the source guide and release metadata.

A source checkout has no generated `SOURCE_ARTIFACT.json`: the editable
source is already present. Preserve the exact commit or source archive when
sharing a build. User data, installed dependencies, caches, local Anki
metadata, and credentials are not source-package inputs.

## Build from source

Use a supported Python version from `pyproject.toml`/the CI workflow, Node.js,
npm, and GNU gettext (`msgfmt`). From the extracted source root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
.venv/bin/python scripts/compile_i18n.py
.venv/bin/python scripts/build_translation_catalog.py
node scripts/build_pdfjs.mjs
.venv/bin/python scripts/package_addon.py --release --clean-staging
```

The release command builds the PDF viewer and Companion, runs checks and
tests, and produces the add-on and its matching source archive in `dist/`.
Anki installs the `.ankiaddon`; the source ZIP is for inspection, modification,
and rebuilding. See `README.md` for manual installation and development.

The editable PDF.js build inputs and their pinned upstream provenance are
under `vendor/pdfjs/`; `scripts/build_pdfjs.mjs` produces `web/pdfjs/`.
The vendor documentation identifies the upstream PDF.js sources and embedded
decoder/sandbox sources. Their separate licenses remain in
`THIRD_PARTY_NOTICES.txt`. Build tools and separately installed runtime
dependencies retain their own licenses and upstream source distributions.

## Redistribution and support

Keep `LICENSE`, `THIRD_PARTY_NOTICES.txt`, this guide, and any generated
`SOURCE_ARTIFACT.json` with distributions. Preserve copyright notices and
identify your modifications as required by the applicable licenses.
Rebuild generated JavaScript and translation catalogs after changing their
sources. Running the release gate is the project's recommended validation
procedure; it is not an additional condition on the rights granted by AGPL.
This guide describes the project's source-delivery workflow and does not
replace other distribution methods permitted by the license.

The AGPL license applies to covered code, not to user-imported documents,
cards, or media. It does not grant rights to third-party content. See
`EXPORTING.md` for backing up and moving user data.
