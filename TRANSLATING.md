# Translating Incremento

## Najlakši način: izvezi → prevedi u tablici → uvezi

Za vlastiti jezik ne trebate programirati, instalirati alate za razvoj niti mijenjati datoteke dodatka. Incremento izvozi **jednu CSV datoteku** koju možete uređivati u Excelu, Google Sheetsu ili LibreOffice Calcu. CSV sadrži poruke za Anki dodatak, PDF čitač i Chrome companion. Istu datoteku možete uvesti u oba programa; svaki ima svoje postavke jezika.

Ugrađeni jezici su English (`en`), Hrvatski (`hr`) i 简体中文 (`zh-Hans`). Uvoz omogućuje i druge jezike, primjerice Deutsch (`de`), Français (`fr`), Português (`pt-BR`) ili 繁體中文 (`zh-Hant`). Uvezeni jezik prikazuje se pod nazivom koji ste upisali, s oznakom **Uvezeno / Imported**.

### 1. Izvezite predložak ili postojeći prijevod

U Ankiju otvorite **Incremento → Settings / Postavke → Language / Jezik**:

- **Export template… / Izvezi predložak…** izvozi sve engleske izvorne poruke i prazan stupac za prijevode. To je početak za novi jezik.
- **Export selected language… / Izvezi odabrani jezik…** izvozi trenutačno odabrani ugrađeni ili uvezeni jezik zajedno s njegovim prijevodima. Koristite ga za dopune, ispravke ili kao osnovu za novi jezik.

Ista dva gumba nalaze se u **Settings → Language** u popupu Chrome companion extensiona. Izvoz sprema datoteku `incremento-translations.csv`; u Chromeu slijedi uobičajene postavke preuzimanja. Izvoz ne mijenja aktivni jezik. Za novi jezik izveden iz postojećeg promijenite i njegovu oznaku i naziv u sljedećem koraku.

### 2. Otvorite CSV kao tablicu

| Program | Otvaranje | Spremanje za uvoz |
| --- | --- | --- |
| Excel | Data / Podaci → From Text/CSV / Iz teksta/CSV; odaberite UTF-8. Stupce učitajte kao tekst. | Save As / Spremi kao → **CSV UTF-8**; ako se traži, potvrdite spremanje aktivnog lista. |
| Google Sheets | File → Import → Upload; odaberite CSV i isključite pretvaranje teksta u brojeve, datume i formule. | File → Download → **Comma-separated values (.csv)**. |
| LibreOffice Calc | Otvorite CSV; odaberite UTF-8, ispravan razdjelnik i tekstualni tip stupaca. | Save As → **Text CSV**, UTF-8; potvrdite zadržavanje CSV formata. |

Nazivi naredbi mogu se razlikovati po verziji i jeziku programa. Izvoz je UTF-8 s BOM oznakom radi kineskih znakova i hrvatskih slova. Uvoz prihvaća zarez, točku-zarez ili tabulator kao razdjelnik, uz pravilno citirane ćelije. Ne uvozite `.xlsx`, `.ods`, PDF ni poveznicu na Google Sheet: najprije izvezite **CSV UTF-8**. Datoteka može biti i TSV s istim stupcima.

### 3. Mijenjajte samo stupac `translation`

Prvi redak mora zadržati ove nazive i redoslijed:

| component | key | form | source | translation |
| --- | --- | --- | --- | --- |
| meta | version | | File format version; keep 1. | 1 |
| meta | locale | | Language code, for example de, fr or pt-BR. | de |
| meta | name | | Language name in its own language, for example Deutsch. | Deutsch |
| addon | settings_done | | Done | Fertig |

Ovo je skraćeni primjer, ne popis svih poruka. U stvarnoj datoteci zadržite izvezene retke.

U stupcu **translation**:

1. Uz `meta / version` ostavite `1`.
2. Uz `meta / locale` upišite jezičnu oznaku, npr. `de`, `hr`, `en-GB`, `pt-BR` ili `zh-Hant`. Upotrebljavajte standardnu oznaku jezika, ne naziv jezika ili putanju.
3. Uz `meta / name` upišite naziv koji korisnik treba vidjeti u izborniku, npr. `Deutsch`.
4. U ostalim redovima upisujte prijevod engleskog teksta iz stupca `source`.

Prazno polje znači **koristi engleski tekst**. Možete krenuti s nekoliko poruka i postupno dopunjavati jezik. Nije potrebno prevesti sve prije prvog uvoza. Ako uvozite paket s istom oznakom jezika, on **zamjenjuje** prethodni paket; prazna polja ne zadržavaju stare prijevode. Zato za dopune najprije izvezite postojeći jezik.

Možete filtrirati cijelu tablicu po stupcu `component`: `addon` su Anki/Qt dijalozi i izbornici, `reader` je ugrađeni PDF čitač, a `extension` su poruke Chrome companion extensiona. Pri sortiranju uvijek sortirajte cijele retke. Ne preimenujte stupce, ključeve, obrasce množine ni engleski izvorni tekst. Ne dodajte vlastite nepoznate ključeve. Datoteka s promijenjenim `source` tekstom odbija se kako prijevod ne bi završio uz pogrešnu poruku.

### 4. Sačuvajte oznake unutar teksta

- `{count}`, `{title}`, `{filename}`, `{value:.2f}` i slične oznake ostaju potpuno iste, uključujući naziv, velika/mala slova i format. Možete promijeniti njihov položaj u rečenici. Primjer: `Page {page}` → `Stranica {page}`.
- Chrome poruke mogu imati `$COUNT$`, `$TITLE$` i druge oznake s dolarima. Zadržite točan zapis; nemojte ih zamijeniti Python oznakama s vitičastim zagradama.
- Ako izvor ima HTML, npr. `<b>…</b>`, prevedite tekst između oznaka, a oznake, atribute i njihov redoslijed ostavite iste. Uvoz ne dopušta dodavanje skripti ili novih HTML oznaka/atributa.
- Stupac `form` kod nekih poruka sadrži `zero`, `one`, `two`, `few`, `many`, `other`. To su kategorije množine, ne upute za prijevod tih riječi. Ne mijenjajte ih. Za hrvatski su potrebni `one` (1, 21…), `few` (2–4, 22–24…) i `other` (0, 5–20…); engleski koristi `one` i `other`, a kineski `other`. Za druge jezike koristite njihove kategorije. Predložak sadrži svih šest kako isti format ne bi ovisio o jeziku. Ako potreban oblik nije preveden, cijela poruka za taj broj koristi engleski.
- Ne prevodite nazive datoteka, SQL primjere, potvrdu `UNLOCK`, spremljene oznake/tags, podatke kartica ili druge programske identifikatore unutar poruke. Prevodi se korisničko sučelje, ne korisnikov sadržaj.

Ćelije su običan tekst. Izvoz štiti početke nalik formulama (`=`, `+`, `-`, `@`) apostrofom; uvoz prepoznaje taj zaštitni zapis. Ne uklanjajte ga ručno. Stupac s prijevodima držite u tekstualnom formatu i ne koristite formule. Zarezi, navodnici i prijelomi redaka unutar poruke dopušteni su; program za tablice treba ih pravilno citirati pri spremanju CSV-a.

### 5. Uvezite i spremite

**Anki:** u istom tabu kliknite **Import translations… / Uvezi prijevode…**, odaberite CSV i provjerite prikazani naziv i broj prevedenih unosa. Novi jezik automatski se odabire. Kliknite **OK** za spremanje paketa i odabira, a zatim **ponovno pokrenite Anki** za primjenu. **Cancel / Odustani** odbacuje uvoz i promjenu odabira. Ponovni uvoz prije potvrde zamjenjuje prethodni pripremljeni uvoz u tom dijalogu. Neuspješan uvoz ostavlja prethodni izbor i pripremljeni paket. Otvoreni čitači i nespremljeni sadržaj ne mijenjaju jezik tijekom uređivanja postavki.

Uvezeni paketi spremaju se **u trenutačni Anki profil**. Jezična postavka dodatka odnosi se na ovu instalaciju Ankija; ako odabrani paket nije instaliran u drugom profilu, sučelje u tom profilu koristi engleski. Isti CSV možete uvesti zasebno u svaki željeni profil. Promjena profila ne smije prenijeti njegov privatni paket u drugi profil.

**Chrome companion:** otvorite **Settings → Language**, uvezite isti CSV i kliknite **Save**. Jezik se primjenjuje odmah, bez ponovnog pokretanja Chromea; otvorene stranice extensiona čuvaju svoj rad. **Cancel** ili zatvaranje postavki bez spremanja odbacuje promjene. Paket se čuva u lokalnoj pohrani tog Chrome profila. Odabir u Ankiju ne mijenja odabir u Chromeu i obratno.

Sve se učitava lokalno, bez internetske usluge za prevođenje. Promjena jezika ne prevodi Anki-jeve vlastite dijaloge i radnje (npr. Replay Own Voice / Auto Advance), sistemske dijaloge ni nazive/opise extensiona kojima upravlja Chrome. Njihov jezik postavite u Ankiju, sustavu ili Chromeu.

### Dopune, dijeljenje i rješavanje pogrešaka

- Za ispravak izvezite **odabrani jezik**, promijenite prijevode i ponovno ga uvezite pod istom oznakom. Uvezeni `hr` ili `en` zaseban je paket; ne zamjenjuje ugrađeni Hrvatski ili English.
- Za dijeljenje pošaljite CSV drugoj osobi. Ona ga uvozi kroz Settings; ne treba uređivati kod ni kopirati `.po`, `.mo` ili JSON datoteke. Izvoz sadrži poruke sučelja i naziv/oznaku paketa, bez kartica, bilježaka ili imena profila.
- Nakon nadogradnje dodatka izvezite **spremljeni odabrani jezik** ponovno. Izvoz dodaje nove izvorne retke s praznim prijevodom, a zadržava kompatibilne postojeće prijevode. Zastarjeli ključevi i prijevodi s nevažećim oznakama preskaču se pri učitavanju spremljenog paketa. Stari CSV s promijenjenim izvornim tekstom treba dopuniti iz novog izvoza prije uvoza.
- Pogreška pri uvozu navodi razlog i, kada je dostupno, broj zapisa. Ako ćelija sadrži prijelom retka, broj zapisa ne mora odgovarati broju fizičkog retka u uređivaču teksta. Provjerite zaglavlje, tri `meta` retka, duplikate, `source`, oznake parametara i HTML. Popravite CSV pa ponovite uvoz.
- Granice: 2 MiB po datoteci/paketu, 20.000 zapisa, 16 KiB po ćeliji, naziv jezika do 80 znakova i najviše 20 spremljenih paketa. Chromeova raspoloživa lokalna pohrana može nametnuti dodatnu granicu; neuspjelo spremanje prikazuje pogrešku i čuva aktivni jezik.
- Za povratak odaberite ugrađeni **English** ili **Hrvatski** pa spremite. U Ankiju zatim ponovno pokrenite aplikaciju.

## Technical contract for maintainers

Custom packs are validated text data, never executable code. `backend/language_packs.py` and the extension's `src/shared/languagePacks.js` implement the same version-1 CSV contract. Normalized storage contains `version`, `locale`, `name` and `translations` maps for `addon`, `reader`, `extension`. Plural entries use `key::form`; preferences use `custom:<locale>` so imports cannot replace built-in catalog identity. Python stores bounded atomic JSON under `backend/paths.py`'s profile `language_packs/` directory. Chrome uses `chrome.storage.local.ui_language_packs`; Save writes the pending registry and preference together.

`locales/translation_catalog.json` is the generated English schema; `locales/builtin_translation_packs.json` supplies editable bundled translations. Both are regenerated with `.venv/bin/python scripts/build_translation_catalog.py`, then checked with `--check` in CI and release. The extension imports the larger built-in snapshots only when the user requests an export. Python uses bundled Unicode CLDR cardinal rules (`locales/cardinal_rules.json`, with `UNICODE_LICENSE.txt`) for custom plural selection; JavaScript uses `Intl.PluralRules`. See [Unicode's plural rule documentation](https://unicode.org/reports/tr35/tr35-numbers.html#Language_Plural_Rules). No uploaded plural expressions are evaluated. Custom Python number/date display currently uses the existing English defaults outside the bundled locales; JavaScript uses browser locale formatting where available. Importing an RTL language translates text but does not introduce a separate mirrored layout.

Strict imports reject unknown keys, changed English sources, duplicate rows, invalid locale metadata, missing/changed placeholders, unsafe markup and oversized data. Stored packs use compatible-row filtering after structural/bounds validation so application updates can fall back safely. Adding a custom language does not require any registry, packaging, dependency or build change. The following developer sections apply when changing source strings or adding an **officially bundled** language.

## Catalog ownership

| Interface | Editable sources | Runtime output |
| --- | --- | --- |
| Python/Qt | `locales/<language>/LC_MESSAGES/incremento_*.po` | Matching committed `.mo` files |
| PDF viewer | `frontend/src/locales/<language>.json` | `web/dist/pdf_viewer.js` |
| Chrome companion | `chrome_extensions/incremento_companion/_locales/<chrome-language>/messages.json` | Native manifest messages and extension `dist/` bundles |

Python catalogs are split into `core` (Settings), `root` (menus/application adapters), `backend` (shared presentation helpers), `qt` (learning/general dialogs), `readers` (document/media UI), `admin` (backup/database/shared utility dialogs), and `imports` (import and companion-style Qt dialogs). Every message ID has one owner. Other modules can reuse its `t()` key without copying it into their own domain. All domains load together; the full English catalog chain is the fallback.

Use stable IDs (`reader_review_all`) and whole messages with named parameters (`{title}`, `{count}`). Do not assemble sentences from translated fragments or derive logic from the displayed label. Keep actions, selected rows, presets and combo selections keyed by stable IDs/item data. Translate at display time; avoid building translated constants during module import.

Python `t(id, **values)` formats a message. `tn(id, count, **values)` uses the pair `id` / `id_plural` in gettext and supplies `{count}`. Croatian needs three forms; Simplified Chinese needs one. The PO `Plural-Forms` header controls this. JavaScript plural keys use `_one`, `_few`, `_other`, selected through `Intl.PluralRules`.

Preserve all parameter names, conversions, and format specifications. A literal brace in Python message text must be doubled (`{{` or `}}`). User values containing braces, dollar signs or Chinese characters remain plain values and are not interpreted as templates. Escape dynamic values at HTML boundaries; use textContent/React text rendering for ordinary labels. Keep SQL examples, confirmation token `UNLOCK`, and preset editor units `days`, `weeks`, `months` unchanged.

## Updating translations

1. Edit the appropriate source catalog in every supported language. For Python, `msgid` is the stable identifier and `msgstr` contains the translated text, including English text in `en`.
2. Run `.venv/bin/python scripts/compile_i18n.py`, then `.venv/bin/python scripts/build_translation_catalog.py`. The second command regenerates the shared CSV schema and editable snapshots of all bundled languages. It must run before either JavaScript build. The compiler checks domain/key parity, named placeholders, duplicate IDs, source references and required interpolation arguments, and then compiles the MO files. It requires GNU gettext's `msgfmt`; Anki users need no translation dependency.
3. Run the relevant Python tests, `npm --prefix frontend test`, and `npm --prefix chrome_extensions/incremento_companion test`.
4. Build the PDF viewer with `npm --prefix frontend run build`, then the extension with `npm --prefix frontend run build:extension`. Keep each generated file with its source changes.
5. Run `.venv/bin/python scripts/compile_i18n.py --check` and inspect the UI in each language, including a narrow popup and long Croatian labels. The release gate checks compilation drift and verifies that runtime catalogs are packaged.

The Chrome catalog is the single source for both its native manifest and custom language-switchable UI. Placeholder definitions map `$NAME$` to `$1`, `$2`, etc.; the custom runtime reads the same messages locally. Use the existing helper rather than `chrome.i18n.getMessage()` for interface text because the latter follows Chrome's language instead of the manual preference.

`scripts/i18n_inventory.py` lists Python UI literals for review, including menu actions and labels passed through simple local assignments or tuple/list loops. It deliberately reports possible user-data examples and dynamic formatting too; classify these before editing. CI and release run `scripts/i18n_inventory.py --check`; exact source/text exceptions and their reasons live in `scripts/i18n_literal_exceptions.json`. New inspected UI literals fail the gate unless translated or explicitly reviewed as identifiers/user data. The compiler checks literal `t()`/`tn()` references and required parameters against the catalogs. Neither tool substitutes for reviewing HTML, generated UI, error paths and dynamic labels.

Check the actual rendered output, including reviewer HTML/JavaScript, refreshed tooltips, preview tables, bookmark panels, generated citation labels and accessibility summaries. Display translated names for internal content kinds while preserving their protocol/storage values. Extension status messages that survive a language change should retain message descriptors, including nested kind labels, until rendering.

Run `tests/test_settings_layout.py` for wrapped Settings text at multiple widths and font sizes. It uses real Qt offscreen, including the native macOS style when available; mocked widgets and the Fusion style alone did not catch the nested form-field height regression. Long guidance belongs in a full-width form row when native field sizing clips it.

## Adding an officially bundled language (developers)

1. Add the locale code, native display name and aliases to the small language registry/normalizer in `backend/i18n.py`; add its number/date presentation rules there. Do not add language branches to individual dialogs.
2. Copy all English PO domains to the new locale folder, set the proper Language/Plural-Forms headers, and translate every message. Compile them.
3. Add the reader JSON catalog and register it in `frontend/src/i18n.mjs`.
4. Add Chrome `messages.json`, then register its locale/native name/catalog in `src/shared/i18n.js`. Keep the Python and JavaScript normalization cases aligned, including fallback from unsupported regional variants.
5. Add the locale to the explicit Python/Chrome catalog allowlists in `scripts/package_addon.py` and extend archive/language tests. A new catalog domain similarly needs all locales plus one allowlist entry.
6. Run tests, rebuild both bundles, inspect the UI, and run `.venv/bin/python scripts/package_addon.py --release --clean-staging`. Do not expose an unfinished language as supported.

## Shared terminology

| English | Hrvatski | 简体中文 |
| --- | --- | --- |
| Settings | Postavke | 设置 |
| Language | Jezik | 语言 |
| Topic | Tema | 主题 |
| Item | Stavka | 条目 |
| Extract | Izdvoji | 提取 |
| Review | Ponavljanje | 复习 |
| Bookmark | Knjižna oznaka | 书签 |
| Knowledge Tree | Stablo znanja | 知识树 |
| Priority | Prioritet | 优先级 |
| Preset | Predložak | 预设 |
| Cancel | Odustani | 取消 |

Native language names remain **English**, **Hrvatski**, **简体中文** in every locale. Anki's own dialogs/system file pickers and Chrome-owned manifest labels follow the host application. Changing Incremento's language does not alter them or rename existing user content.
