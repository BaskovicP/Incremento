# Plan internacionalizacije Incrementa i Chrome ekstenzije

## Cilj i odluke

Pripremiti dodatak, PDF/EPUB čitače i Chrome ekstenziju tako da se novi jezik dodaje kroz kataloge prijevoda i provjere, bez traženja i mijenjanja tekstova po kodu. Prvi jezici su engleski (`en`), hrvatski (`hr`) i pojednostavljeni kineski (`zh-Hans`; Chromeova mapa je `zh_CN`). Tradicionalni kineski (`zh-Hant` / `zh_TW`) kasnije je zaseban prijevod, a ne automatska zamjena za pojednostavljeni.

**Ručni odabir u Settings → Language dio je prve verzije**, u Anki dodatku i Chrome ekstenziji. Korisnik može izabrati jezik neovisno o jeziku Ankija ili preglednika. Automatsko praćenje jezika domaćina ostaje jedna opcija. Nepodržani jezik i nedostajući prijevod koriste engleski fallback.

### Korisnički tijek: Settings → Language

| Element | Anki dodatak | Chrome ekstenzija |
| --- | --- | --- |
| Ulaz | Incremento → Settings → Language, zasebna kartica pri početku postavki | Gumb Settings u popupu → kartica Language u prikazu postavki unutar istog popupa |
| Izbornik | Automatski — prati Anki; English; Hrvatski; 简体中文 | Automatski — prati Chrome; English; Hrvatski; 简体中文 |
| Spremanje | Postojeći OK sprema izbor zajedno s ostalim postavkama; Cancel odbacuje izmjenu | Save sprema jezik; Cancel ili zatvaranje bez spremanja odbacuje izmjenu |
| Primjena | Nakon sljedećeg ponovnog pokretanja Ankija; kartica to jasno navodi prije spremanja | Odmah nakon uspješnog spremanja, bez ponovnog pokretanja Chromea |
| Opseg | Postavka dodatka za tu Anki instalaciju, kroz postojeći config service | Postavka ekstenzije za taj Chrome profil, kroz postojeći lokalni storage |

Nazivi jezika uvijek se prikazuju na vlastitom jeziku, kako bi korisnik mogao ispraviti pogrešan odabir. Kartica može nositi oznaku `Jezik / Language` odnosno `语言 / Language`; ta namjerna dvojezična oznaka ostaje prepoznatljiva. Kontrola mora imati label, pristupačan naziv i podršku za tipkovnicu. Ne prikazivati jezik u izborniku kao podržan dok prijevod nije spreman za isporuku.

U dodatku ispod izbornika stoji kratka poruka: „Odabrani jezik primijenit će se nakon ponovnog pokretanja Ankija.” Izbor se sprema odmah na OK, ali aktivni jezik tekuće Anki sesije ostaje isti. Ponovno otvaranje postavki prikazuje spremljeni izbor i poruku ako još čeka primjenu. Time se tijekom učenja ne moraju zatvarati čitači, ponovno stvarati reviewer ili prekidati nespremljeni nacrti. Automatski restart nije dio ove promjene.

Svaka aplikacija ima svoj odabir; ekstenzija radi i kada Anki nije pokrenut. Jedan izbor koji bi sinkronizirao obje aplikacije može se dodati kasnije, ako bude potreban, ali nije uvjet za Settings → Language. Browserovi vlastiti prikazi naziva/opisa ekstenzije i opisa prečaca i dalje slijede Chromeov jezik; popup, bookmark uvoz, overlay i kontekstni meniji ekstenzije slijede korisnikov izbor.

### Postavka i određivanje jezika

- Dodatak: `config.json` dobiva `"ui_language": "auto"`; `backend/config_service.py` jedina je granica normalizacije, čitanja i spremanja. `frontend/settings_dialog.py` dobiva ulaznu vrijednost i getter, a `__init__.py:openSettingsFunction()` sprema je samo nakon prihvaćenog dijaloga i uspješnog upisa. Čuvati ostale postavke i nepoznate ključeve. Ne dodavati SQLite tablicu ili datoteku u `user_files/` za jezik sučelja.
- Ekstenzija: `chrome.storage.local` dobiva `ui_language` s istim dopuštenim vrijednostima: `auto`, `en`, `hr`, `zh-Hans`. Koristiti postojeće `getLocalExtensionSetting` / `setLocalExtensionSetting` granice. Neuspješno spremanje ostavlja prethodni aktivni jezik i prikazuje pogrešku.
- Razlikovati spremljeni izbor (`auto` ili kod) i efektivni jezik (`en`, `hr` ili `zh-Hans`). Ručni podržani izbor ima prednost; `auto` čita jezik Anki sučelja odnosno `chrome.i18n.getUILanguage()`. Normalizirati oznake jezika (`hr-HR → hr`, `zh-CN/zh_CN → zh-Hans`), bez automatskog pretvaranja tradicionalnog kineskog u pojednostavljeni. Nedostajuća/nevaljana postavka postaje `auto`; ako automatski odabrani jezik nije podržan, koristiti `en`. Istu tablicu slučajeva provjeravati u Pythonu i JavaScriptu.
- U dodatku efektivni jezik odrediti jednom pri pokretanju, prije izgradnje prevedenih kontrola; izvor za `auto` sakriti iza malog Anki adaptera (lokalni Anki ima `anki.lang.current_lang`). Ne pozivati globalno mijenjanje Anki jezika ili `QLocale.setDefault()` radi ove postavke. Qt standardne gumbe u Incrementovim dijalozima prevesti izričito; Anki vlastiti prozori i sistemski file picker zadržavaju svoj jezik.

Prevoditi samo prikaz: menije, gumbe, poruke, validacijske pogreške, pomoć, naslove, tekstove pristupačnosti, kontekstne menije i trajanja/brojeve/datume. **Ne prevoditi** trajne identifikatore: konfiguracijske i SQLite ključeve, vrijednosti `pdf`/`epub`/`topics`/`items`, Anki nazive polja i note typeova, tagove, action/command ID-ove, bridge naredbe i protokol, CSS/DOM ID-ove, putanje, URL-ove ni korisničke naslove/sadržaj. Tekst koji se sprema u Anki (npr. automatski `Untitled` naslov) zahtijeva zasebnu migracijsku odluku; u ovoj fazi ostaje stabilan.

## Arhitektura

| Površina | Predloženi mehanizam | Izvor jezika | Format i isporuka |
| --- | --- | --- | --- |
| Python/Qt i Python-generirani HTML | Mali `t(id, **values)` / `tn(id, count, **values)` adapter nad standardnim `gettext`; stabilni ID je `msgid`, a engleski katalog eksplicitni fallback | Efektivni jezik iz spremljenog `ui_language`, fiksiran do sljedećeg pokretanja Ankija | `locales/<jezik>/LC_MESSAGES/incremento_*.po` kao izvor i deterministički prevedeni `.mo` u release paketu, uključujući potpuni `en` katalog. ID-evi imaju prevoditeljske komentare s kontekstom. |
| React PDF čitač | Lokalni katalog JSON poruka i mali `t`/`plural` helper; `Intl.PluralRules`, `Intl.NumberFormat`, `Intl.DateTimeFormat` za oblikovanje | Normalizirani jezik poslan iz `frontend/pdf_dock.py` pri otvaranju dokumenta | Katalozi iz `frontend/src/locales/` ulaze u postojeći Vite bundle `web/dist/pdf_viewer.js`; bez mrežnog dohvaćanja. |
| Chrome ekstenzija — vlastito sučelje | Vlastiti mali `t`/`plural` adapter nad lokalno uključenim katalozima; eksplicitni locale i `Intl` za oblikovanje | Efektivni jezik iz `chrome.storage.local.ui_language`; osvježavanje nakon spremanja | Jedan izvor poruka u `_locales/en`, `_locales/hr`, `_locales/zh_CN/messages.json`; build iz istih datoteka izrađuje/uključuje runtime poruke u Vite bundleove. Nema druge ručno održavane kopije prijevoda. |
| Chrome — prikazi iz manifesta | Chromeov nativni `__MSG_key__` i `default_locale: "en"` | Chromeov jezik; ručni izbor ekstenzije ga ne mijenja | Isti `_locales` katalog; naziv/opis/command opisi ostaju u Chromeovu standardnom formatu. |

Isti pojmovi i isti stabilni ID-ovi gdje površine dijele radnju (npr. `reader_review_all`, `reader_jump_back`), ali katalog ostaje u nativnom formatu pojedine platforme. Koristiti zajednički podskup znakova dopušten u Chrome ključevima: slova, brojeve i `_`, bez točke. Poruke su cijele rečenice s imenovanim parametrima (logički `count`, `title`), nikad engleski fragmenti, dodani sufiksi `s` ili sastavljanje prevedenih riječi. Python/React adapteri mogu koristiti `{count}`, dok Chromeov `messages.json` koristi `$COUNT$` placeholder povezan sa zamjenom `$1`; build pretvorba i provjera kataloga mapiraju isti logički parametar u runtime format. Bez `eval()` i bez ponovnog tumačenja korisničkih vrijednosti kao predložaka.

Hrvatski treba oblike `one/few/other`, a kineski `other`; izbor radi pluralni mehanizam, ne ručni `count == 1`. Python `tn(id, count)` mora definirati jednoznačan par stabilnih gettext ključeva (`id` / `id_plural`) i odgovarajući `Plural-Forms` u katalogu. JavaScript varijante koriste dosljedne sufikse `_one`, `_few`, `_other`. Brojeve i množinu birati prema efektivnom jeziku kataloga; kada pluralna poruka nedostaje, prebaciti cijelu poruku i pravilo izbora na engleski. Korisnički tekst pri umetanju u HTML ostaje escaped/textContent. Chromeov `getMessage()` ne koristi se za vlastito sučelje s ručnim izborom jer nema argument za željeni jezik.

## Redoslijed provedbe

### 1. Inventar i stabilne granice (PR 1)

- Napraviti automatizirani popis vidljivih stringova u `__init__.py`, `frontend/*.py`, `frontend/src/`, `chrome_extensions/incremento_companion/src/`, statičkom HTML-u i manifestu. Klasificirati prikaz, korisnički podatak i strojni identifikator. Dodati provjeru novih neprevedenih UI literala uz ciljane iznimke za protokol i testne podatke.
- Prije prijevoda ukloniti ovisnost logike o engleskom tekstu. `__init__.py` pri ponovnom vezanju izbornika provjerava `act.text() == "Incremento"`, a pri pronalasku postavki `act.text() == "Settings"`; akcije treba prepoznati stabilnim `objectName`/ID-om. Pregledati i ostale usporedbe s nazivima akcija i izbornika.
- U `frontend/reader_shell.py` sačuvati ID-ove i redoslijed PDF/EPUB kontrola, a oznake, tooltipove i pristupačne opise učiniti prikaznim vrijednostima. Postojeće testove za inventar ID-ova zadržati neovisnima o jeziku.
- Razdvojiti spremljene korisničke oznake preseta od ugrađenih preseta. Trenutačni `config.json` i `backend/custom_schedule.py` imaju engleski `label` (`Daily`, `Every 2 days`), a `preset_label` se sprema i u pravila prilagođenog rasporeda. Postojećim config/SQLite vrijednostima ne mijenjati tekst; budući ugrađeni preset prikazivati preko stabilnog ID-a samo kada je izvor nedvojbeno ugrađen, uz regresijske testove za povijesna pravila i korisnički preimenovane presete.

### 2. Python/Qt temelj i Settings → Language (PR 2)

- Dodati centralni prevoditeljski adapter koji se inicijalizira u `__init__.py`, bez čitanja globalnog profila duboko u backendu. Poslovni sloj neka, gdje je moguće, vraća kod/stanje i parametre; korisničku poruku sastavlja Qt/UI granica. Potpuni engleski katalog rezervna je vrijednost i za ključ koji nedostaje u djelomičnom prijevodu; ne prikazivati sirovi ID. Zadržati engleski fallback i provjeriti puni put `hr-HR → hr`, `zh-CN/zh-Hans → zh-Hans`. Ugraditi kompilaciju `.po` → `.mo` i provjeru kataloga u CI/release te dodati top-level `locales/` u eksplicitno pakiranje i arhivne testove.
- Uskladiti `config.json`, `backend/config_service.py`, `frontend/settings_dialog.py`, `__init__.py`, `tests/test_config_service.py`, `tests/test_settings_dialog.py` i `MANUAL.md` za novi `ui_language`. Zasebna Language kartica i prihvaćanje/odustajanje rade prema prethodno opisanom tijeku. Spremanje jezika ne ulazi u postojeće live-refresh pozive za reviewer/dockove.
- Pretvoriti jednu cjelovitu vertikalu: glavni Incremento meni, Settings i osnovni Learning dijalog, uključujući title, tooltip, validation i accessible text. Zatim po istom obrascu migrirati onboarding, command palette, statistiku, reader dockove, reviewere i preostale dijaloge. To su implementacijski koraci; djelomično preveden jezik ne oglašavati kao završen u release izborniku.
- U command palette pretraživanje neka razumije prevedeni naziv i engleski alias, dok se pozivanje i dalje temelji na registriranoj QAction/ID putanji. U brojevima, datumima i vremenima koristiti odgovarajući locale, ali trajne vrijednosti i datotečni formati ostaju neovisni o lokalizaciji. `frontend/epub_dock.py` trenutno računa toolbar oznake pri uvozu modula; prevedene oznake treba sastaviti tek nakon inicijalizacije jezika, pri otvaranju docka, dok inventar ID-ova ostaje nepromjenjiv.

### 3. PDF/EPUB i ugrađeni web prikaz (PR 3)

- Prevesti `frontend/src/PdfViewer.jsx`, `HighlightLayer.jsx` i `usePdfRender.js`: vidljive oznake, aria/title/placeholder, potvrde, prazna stanja, pogreške, brojanje i plural. Održati PDF/EPUB terminologiju i inventar kontrola usklađenim s `frontend/reader_shell.py`.
- `frontend/pdf_dock.py` već šalje pending-start objekt i pozicijski `incrementoPdfStart(...)`; locale dodati u oba puta, uz provjeru odgovarajućeg React potrošača. `web/pdf_dock.html` neka ima statični `<html lang="en">` fallback, a React postavlja stvarni `document.documentElement.lang` nakon primitka jezika. Python-generirani EPUB dokument također treba ispravan `lang`; njegovi UI tekstovi koriste isti Python adapter, a vrijednosti koje idu u JavaScript prenose se kroz postojeću sigurnu JSON granicu.
- Za `limitStatus.enforcement_label` i slične backendom sastavljene engleske tekstove prenositi stabilni mode/kod i parametre, pa prevoditi na mjestu prikaza. Pogreške u `usePdfRender.js` mapirati na lokaliziranu korisničku poruku, bez sastavljanja engleskog prefiksa i sirovog teksta JavaScript iznimke. U `frontend/src/pdfLinks.mjs` fallback `Go to page N` također premjestiti na prikazni sloj i prilagoditi njegove Node testove.
- Odvojeno provjeriti kineski **sadržaj** u PDF-u: spajanje odabranih redaka ne smije umetati neprikladne ASCII razmake u CJK tekst; pretraga ne smije pretpostaviti razmake između riječi; rezanje teksta ne smije razdvojiti Unicode znak. To je funkcionalna provjera čitača, ne samo prijevod UI-ja.

### 4. Chrome ekstenzija (PR 4)

- U `manifest.json` dodati `default_locale: "en"` i `__MSG_key__` za naziv, opis, `action.default_title` i opise svih naredbi. Dodati potpune `_locales/en`, `_locales/hr`, `_locales/zh_CN` kataloge s opisima i provjerenim placeholderima.
- Dodati Settings prikaz u postojeći `src/popup/App.jsx`, s Language karticom i kontroliranim nacrtom odabira. Samo Save upisuje `ui_language`. Zadržati stanje import obrasca pri ulasku/izlasku iz Settings prikaza; za ovaj mali dodatak nije potrebna nova options stranica ni novi Vite entry point.
- Dodati `src/shared/i18n.js` za eksplicitni locale, lokalni cache i fallback. Uključiti sve podržane runtime kataloge u postojeće lokalne bundleove. Inicijalizirati locale prije prvog prikaza u popupu/bookmark stranici i prije korisničkih radnji nakon buđenja service workera; registraciju njegovih event listenera ne odgađati do završetka async čitanja. Pri instalaciji, pokretanju Chromea i ponovnom pokretanju workera učitati spremljeni locale prije inicijalnog postavljanja kontekstnog menija i action tooltipa; `storage.onChanged` sam ne pokriva hladni start. Ne dohvaćati prijevode s mreže niti tražiti dostupnost Ankija.
- Nakon uspješnog spremanja osvježiti React tekstove bez remountanja formulara, odabranih bookmarka ili pokrenutog importa. `chrome.storage.onChanged` osvježava već postojeće content overleye i background tekstove; proširiti postojeći guard za `LINK_SAVE_SETTINGS_KEY` i na `ui_language`. `syncLinkSaveContextMenu()` mora ažurirati postojeće ID-ove bez duplikata, a `chrome.action.setTitle()` korisnički tooltip. Samo promjena jezika ne smije injektirati content skripte u nove stranice ni mijenjati browser permissions. Dinamične statuse čuvati kao kod/parametre kada ih treba ponovno prevesti.
- U `src/popup/`, `src/bookmarks/`, `src/content/main.js` i `src/background/main.js` zamijeniti vidljive literale: status/pogreške, badge/toast, capture overlay, kontekstne menije i bookmark import. `src/shared/` neka vraća stabilne kodove pogrešaka gdje se tekst može prikazati na više mjesta. `src/shared/bridge.js` sada prikazuje backendov `data.error`, a `formatBridgeError` uspoređuje engleski `Origin not allowed.`; u bridge odgovor dodati stabilni `error_code` i parametre uz postojeći `error` radi kompatibilnosti, u ekstenziji prevesti kod, a staru poruku koristiti samo kao prijelazni fallback. `popup.html`, `bookmarks.html` i `offscreen.html` trebaju lokaliziran naslov i `html lang` preko lokalnog entry pointa.
- Množine bookmarka i kartica birati preko `Intl.PluralRules` s izabranim efektivnim localeom; koristiti potpune varijante poruka. Provjera kataloga mora provjeriti Chromeov `$NAME$`/`$1` mapping, runtime pretvorbu i manifest reference. Pri sortiranju bookmark naslova proslijediti efektivni locale umjesto neodređenog `localeCompare()`, uz očuvanje označenih redaka po stabilnim ID-ovima.
- `scripts/package_addon.py` trenutačno iz ekstenzije pakira samo `icons` i `dist` podmape; izričito dodati `_locales` i test da sva tri `messages.json` završe u release arhivi. Ne dirati permissions/CSP zbog i18n-a.

### 5. Provjere i uvjet završetka (uz svaki PR, završni PR za cijeli tijek)

- Testirati da ručni izbor nadjačava jezik domaćina: npr. Anki na engleskom + Hrvatski → hrvatsko Incremento sučelje nakon restarta; Chrome na hrvatskom + 简体中文 → kinesko sučelje ekstenzije odmah nakon Save. Testirati povratak na `auto`, fallback nepodržanog jezika i razlikovanje `zh-Hans`/`zh-Hant`.
- Testirati OK/Save, Cancel, zatvaranje bez spremanja, grešku upisa, ponovno otvaranje postavki i ponovno pokretanje aplikacija. Anki u tekućoj sesiji zadržava stari efektivni jezik; iduća sesija koristi spremljeni. U ekstenziji provjeriti više otvorenih konteksta, buđenje service workera, menu/tooltip nakon hladnog starta sa spremljenim `hr`/`zh-Hans` te utrku početnog čitanja s novim spremanjem. Promjena jezika ne gubi draft, bookmark odabir ni napredak importa.
- Testirati nedostajući ključ, paritet ključeva i placeholdera, hrvatske množine (`0/1/2/5/11/12/21/22/25`), kineski bez množinskih nastavaka te format brojeva/datuma. Primjer ispune s `$`, `{}`, `<` i kineskim znakovima mora ostati običan tekst. Provjeriti da izbor jezika mijenja samo pripadajuću postavku i prikaz, bez preimenovanja ostalih config/SQLite/bridge vrijednosti ili postojećih Anki bilježaka.
- Qt i React/extension UI pregledati na `en`, `hr`, `zh-Hans`/`zh_CN`: dugi hrvatski natpisi, kineski fontovi, uski popup, PDF/EPUB sažeti toolbar, tipkovnički fokus i tekst čitača ekrana. Testirati CJK odabir, pretragu, highlight i bookmark posebno.
- Za promjenu Python UI-ja pokrenuti relevantne `pytest` skupove; za React `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build`; za ekstenziju `npm --prefix chrome_extensions/incremento_companion test` i `npm --prefix frontend run build:extension`; za isporuku test pakiranja i release gate. Izvor i generirane `web/dist` odnosno extension `dist` datoteke ostaju u istom PR-u. Testove vezane uz engleski tekst zamijeniti provjerama konkretnih poruka po localeu i stabilnih ID-ova, bez slabljenja ponašajnih tvrdnji.

Plan je implementiran kada korisnik kroz **Settings → Language → izbor → OK/Save** može trajno postaviti sva tri jezika u obje aplikacije, uz jasno opisanu primjenu i očuvano radno stanje. Svaki oglašeni jezik mora pokrivati cijelo Incrementovo sučelje, uključujući pomoćne i pristupačne tekstove.

Novi jezik dodaje se kroz mali registar jezika (kod, vlastiti naziv, Chrome mapa), kataloge i provjere, bez izmjene poslovne logike. Izbornik se gradi iz registra, bez novih `if language == ...` grana u dijalozima. Dokumentirati jedan razvojni postupak: dodaj kataloge → provjeri ključeve/plurale → kompiliraj Python kataloge → izgradi oba Vite izlaza → testiraj i provjeri arhivu. Upute za prevoditelje trebaju uključiti rječnik zajedničkih pojmova, kontekst poruke i objašnjenje parametara. Ažurirati `MANUAL.md` i extension `README.md` s ulazom u Language postavke i ponašanjem pri spremanju.

## Referentna dokumentacija

- [Chrome: internacionalizacija ekstenzije](https://developer.chrome.com/docs/extensions/develop/ui/i18n)
- [Chrome: `chrome.i18n` i fallback](https://developer.chrome.com/docs/extensions/reference/api/i18n)
- [Chrome: format poruka i placeholderi](https://developer.chrome.com/docs/extensions/how-to/ui/localization-message-formats)
- [Chrome: trajne postavke i promjene kroz storage API](https://developer.chrome.com/docs/extensions/reference/api/storage)
- [Python: gettext katalog, plural i fallback](https://docs.python.org/3/library/gettext.html)

## Status provedbe

Provedeno u ovoj radnoj grani: Settings → Language u dodatku i ekstenziji, odvojeno spremanje izbora, sedam Python gettext domena, lokalni JSON katalozi čitača i izvorni Chrome katalozi za engleski, hrvatski i pojednostavljeni kineski. Dodavanje jezika opisano je u `TRANSLATING.md`.

Python kataloge, parametre poruka i nove izravne UI literale provjeravaju `scripts/compile_i18n.py --check` i `scripts/i18n_inventory.py --check`. JavaScript testovi provjeravaju kataloge, množine, hladni start ekstenzije i fallback. Release postupak gradi oba browser bundlea i uključuje samo izričito dopuštene runtime kataloge.

Implementacija je podijeljena između modela GPT-5.6 Sol (čitači i ekstenzija) i GPT-5.6 Terra (Qt dijalozi), uz neovisnu provjeru modela GPT-6 Astra. Pronađene regresije u package importu, izoliranoj Chrome injekciji, prikazu oznake praćenja i učitavanju jezika hladnog workera ispravljene su uz ciljane testove.

Završni release postupak prošao je 13. rujna 2026.: 2122 Python testa, 32 testa PDF preglednika i 87 testova ekstenzije, Ruff, mypy, ESLint, Python kompilacija i sva četiri ciljana mutacijska testa. Zasebni deterministički repair eval prošao je svih sedam slučajeva. Katalozi i izravni UI literali prolaze obje i18n provjere, a oba Vite izlaza ponovno su izgrađena iz završnog izvora.

Python provjera izvedena je lokalno na Pythonu 3.14.5 i prijavila je 23 upozorenja: nesklad package metapodataka u testnim importima, nezatvorene SQLite veze u testnom procesu i namjerno dupliciran ZIP zapis u negativnom testu. Nijedan test nije pao niti bio preskočen; podržane CI verzije 3.12/3.13 nisu zasebno pokretane lokalno.

Arhiva `dist/incremento-addon-20260913-170151.ankiaddon` provjerena je nakon izrade: sadrži svih 21 Python runtime kataloga i tri Chrome kataloga, bundleovi odgovaraju radnom stablu, a korisnički podaci, lokalni `meta.json` i razvojni katalozi `.po` isključeni su. Qt Settings i reprezentativni dijalozi vizualno su pregledani u izoliranom prikazu na hrvatskom i kineskom. Stvarne korisničke sesije Ankija i Chromea nisu ponovno pokretane; interaktivna provjera u stvarnom Chromeu nije provedena.

## Dorada nakon prijavljenih snimki zaslona

Preklapanje objašnjenja smjera prioriteta reproducirano je u izvornom macOS Qt stilu. Premještanje u zaseban red pune širine ispravlja izračun potrebne visine. Novi test stvarnog Qt rasporeda provjerava prelamane oznake svih kartica postavki na tri jezika, pri više širina i veličina fonta, uz Fusion i dostupni macOS stil. Ispravljene postavke i izbornik gumba vizualno su pregledani na hrvatskom i kineskom.

Dopunjeni su prijevodi izbornika gumba ponavljanja, reviewer HTML/JavaScript oznaka i opisa, dinamičnih opisa gumba za izdvajanje, pregleda kartica, knjižnih oznaka, pristupačnih sažetaka, generiranih naziva odjeljaka i citata te korisničkih poruka o neuspješnim uvozima i snimkama. Vrste sadržaja u statusima ekstenzije prikazuju lokalizirane nazive, a njihovi stabilni identifikatori ostaju očuvani. Provjera inventara sada obuhvaća `addMenu`, `addAction`, jednostavne lokalne dodjele i oznake iz tuple/list petlji; HTML i JavaScript dodatno su pokriveni testovima stvarnog generiranog izlaza.

Završni release postupak dorade prošao je: **2177 Python testova, 32 PDF testa i 90 testova ekstenzije**, bez padova. Python je prijavio 23 upozorenja. Prošli su kompilacija, Ruff, mypy, ESLint, četiri ciljana mutacijska testa, provjera svih 21 kataloga i prošireni inventar. Oba browser bundlea ponovno su izgrađena. Provjerena nova arhiva je `dist/incremento-addon-20260913-174412.ankiaddon`; ona zamjenjuje prethodnu arhivu za ovu doradu.

Izvorne Anki radnje poput Replay Own Voice i Auto Advance prate Anki jezik. Postojeći korisnički sadržaj, nazivi polja, oznake i tehničke pojedinosti vanjskih alata ne prevode se kao Incrementove UI poruke. Nijedna korisnička sesija nije ponovno pokrenuta tijekom dorade.
