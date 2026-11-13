# Incremento licensing audit — 2026-11-13

This review covers the tracked application sources, identified runtime
dependencies, bundled browser assets, Git contributor history, and add-on and
Companion packaging. It supports the transition of Incremento's original code
to **AGPL-3.0-or-later**. Third-party components retain their own licenses.

## Compatibility findings

No incompatible license was identified among the inspected shipped components.
Anki is AGPL-3.0-or-later. PyMuPDF offers AGPLv3 or a separate commercial
license; this project uses the AGPL path. PyQt6 is GPLv3, whose combination
with AGPLv3 is expressly addressed by section 13 of those licenses. These
dependencies are supplied separately, rather than copied into normal
Incremento release archives.

The browser bundles contain React, React DOM and Scheduler (MIT), PDF.js
(Apache-2.0), OpenJPEG and its Mozilla integration (BSD-2-Clause), QuickJS and
its Mozilla integration (MIT), permissively licensed generated runtime code,
and Unicode CLDR-derived plural rules (Unicode License v3). Their notices and
full license texts are in `THIRD_PARTY_NOTICES.txt`.

Other identified external dependencies include Beautiful Soup (MIT),
Python-Markdown and protobuf (BSD-3-Clause), Playwright and Tesseract
(Apache-2.0), DjVuLibre (GPL-2.0-or-later), yt-dlp (Unlicense for its core),
pix2tex (MIT), and Pillow (MIT-CMU). Qt/Chromium and FFmpeg distributions
contain components with additional terms that depend on the installed build.
The normal release excludes these installed dependencies and system programs.
Changing that boundary requires auditing the exact newly bundled artifacts.

## Provenance and corrective work

Git history at the start of the audit contained one external code
contribution: commit `9d3c8a91a3e59b67b6eacb5243624c3f709e5469`, from
[PR #20](https://github.com/BaskovicP/Incremento/pull/20), affecting Windows
file flushing and PDF replacement. The public PR contained no explicit AGPL
relicensing grant. No copyright assignment was inferred from submission or
repository ownership.

For this release, that contribution was removed from a temporary copy of the
current owner-code baseline. A separate implementation task, which did not
read the contributed implementation or its diff/history, addressed the
functional requirements using Python, Microsoft and PyMuPDF documentation.
The resulting replacement preserves writable flush handles and closes PDF
documents before Windows file replacement. Regression tests exercise those
restrictions, backups, metadata preservation, cleanup and failure paths.
Historical commits remain unchanged; this describes the current source tree,
not a relicensing of historical third-party contributions.

The previous PDF.js files had undocumented transformations, stripped headers,
and inconsistent sandbox version metadata. They are replaced by a documented
build from pinned upstream inputs. See `vendor/pdfjs/` and
`scripts/build_pdfjs.mjs` for source provenance, checksums and regeneration.
The full upstream notices are preserved separately from Incremento's license.

## Distribution controls

- `LICENSE` retains Paulo Baskovic's copyright and contains the standard
  AGPL text, including its warranty disclaimer and limitation of liability.
- README, package metadata and the English, Croatian and Simplified Chinese
  About messages identify AGPL-3.0-or-later consistently.
- Add-on and standalone Companion/Firefox packages include the license and
  complete third-party notices. Tests reject missing notices and unsafe inputs.
- Packaging produces a matching source archive from the same build inputs,
  with its filename and SHA-256 digest recorded in the runtime package.
  The project's download workflow publishes that source alongside the binary;
  local packaging does not publish either artifact. Other distribution methods
  allowed by AGPL remain available. See `SOURCE.md`.
- Future contributions must have compatible licensing. Contributors retain
  their copyrights; no assignment is needed merely to charge for compliant
  AGPL distributions.

## Scope limits

Git attribution and source scans are evidence, not a complete reconstruction
of every line's authorship. This review does not cover user documents, media,
decks, optional model training/data rights, or every transitive component in
independently installed tools. No user-profile data was inspected. The
Windows restrictions were exercised in tests on macOS, not on native Windows.

AGPL permits commercial use and resale. Its protections are preservation of
the required source and license rights, copyright notices, and applicable
warranty/liability terms; it does not provide exclusive commercial rights or
guarantee immunity from liability.

## Primary references

- [Anki license](https://github.com/ankitects/anki/blob/main/LICENSE)
- [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html)
- [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
- [Riverbank licensing FAQ](https://www.riverbankcomputing.com/commercial/license-faq)
- [Python fsync](https://docs.python.org/3/library/os.html#os.fsync)
- [Microsoft FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)
- [PyMuPDF document close](https://pymupdf.readthedocs.io/en/latest/document.html#Document.close)
- Exact bundled-component sources and license texts: `THIRD_PARTY_NOTICES.txt`
