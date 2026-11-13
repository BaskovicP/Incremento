# PDF.js vendor source

Incremento uses **PDF.js 4.10.38** from Mozilla. This directory supplies the
unminified inputs, upstream editable source, and provenance for the three
classic scripts shipped under `web/pdfjs/`. PDF.js remains Apache-2.0 licensed;
its embedded components retain the licenses in `THIRD_PARTY_NOTICES.txt`.

## Rebuild the shipped scripts

From the Incremento repository or matching source archive:

```sh
npm ci --prefix frontend
node scripts/build_pdfjs.mjs
node scripts/build_pdfjs.mjs --check
node --test frontend/tests/pdfVendor.test.mjs
```

After `npm ci`, this build is offline. It uses esbuild **0.25.12**, already pinned
in `frontend/package-lock.json`, and verifies every input and source archive
against `manifest.json`. It converts the three unminified upstream ES modules
to minified classic scripts exposing `pdfjsLib`, `pdfjsWorker`, and
`pdfjsSandbox`. The scripts retain the upstream license header and carry a
notice describing Incremento's transformation. No upstream behavior patch is
applied. All three scripts now come from the same upstream release.

The original upstream package URL and SHA-256, each input SHA-256, the upstream
source revisions, and each included source archive SHA-256 are recorded in
`manifest.json`. The `.mjs` inputs are verbatim `package/build/` files from that
package; they are included to make the shipped transformations reproducible
without fetching external code. This replaces the older undocumented builds,
including the sandbox whose historical header had an inconsistent version.

## Modify upstream code

The archives under `sources/` contain preferred editable upstream source and
build files, not only the generated distribution modules:

| Component | Revision | Purpose |
|---|---|---|
| PDF.js | `f9bea397f817100a186d0ced2aa3d4b85813b637` | JavaScript source, build tooling, viewer inputs, and upstream notices for 4.10.38 |
| QuickJS | `3f81070e573e3592728dbbbd04c84c498b20d6dc` | C source for the sandbox engine |
| pdf.js.quickjs | `3ca8f480cd32240378d5e53b759c5e14b76a3549` | Engine patches, integration source, Dockerfile, and build scripts |
| OpenJPEG | `6e92b398dc8e0bf1c2d39dc01f4e9f94b15e75f7` | JPEG 2000 decoder source, version 2.5.3 |
| pdf.js.openjpeg | `154e3b397c5b4f22d4f93e3cd8bacde090d6e453` | Decoder patches, integration source, Dockerfile, and build scripts |

Each archive has one component-named top-level directory. Extract the desired
archives into a working directory and follow their included README/build files.
The PDF.js archive excludes the large upstream PDF test corpus and CI/VCS
metadata. Its source, external build helpers, viewer/translation build inputs,
and root package/build configuration are retained. The other archives exclude
top-level test-data and CI/VCS directories. Archive filtering is recorded in
the manifest; upstream file contents are unchanged.

For a full upstream checkout with tests and Git-derived version metadata, clone
the repository URL recorded in the manifest and check out its exact revision.
The PDF.js upstream build uses Node/npm and `npx gulp generic`; it derives build
metadata from Git history, so an extracted source archive without Git history
may report a development build number. Its three generated modules are under
`build/generic/build/`. The embedded-engine integration repositories contain
their C source revision pins, patches, Dockerfiles, and `node build.js` commands.
Their historical Dockerfiles use `emscripten/emsdk:latest`; bit-for-bit
recompilation of the upstream C artifacts is not claimed. The preferred C
sources and build scripts are included so those components can be modified.

To ship an intentional upstream change, rebuild it using those instructions,
replace the three `.mjs` inputs together, update `manifest.json` and notices to
describe the actual versions/modifications, then run Incremento's offline build
and PDF reader tests. Do not edit `web/pdfjs/*.min.js` directly. Retain all
upstream source notices and distribute the updated source with the release.
