**Web kartica, Chrome i nastavak učenja — dorada UX prijedloga**

16. rujna 2026. Ovo je prijedlog ponašanja nakon pregleda postojećeg koda, a ne implementirana promjena niti rezultat promatranja korisnika u aktivnom Ankiju. Dopunjuje [istraživanje prijava](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/BROWSER_LOGIN_RESEARCH.hr.md>).

**Izravan odgovor: za postojeću Chrome prijavu stranica bi se gledala u Chromeovu prozoru.** Korisnik ne bi morao tražiti Chrome, kopirati URL ili pamtiti vrijeme. To bi rješavala integracija. Ipak, na jednom zaslonu ostaje stvaran prijelaz aplikacije. Ne treba ga predstavljati kao stranicu koja je i dalje unutar Anki docka.

Prethodna preporuka dobro rješava odvojenost prijava, ali nije dovoljno obradila miješanu sesiju običnih kartica i vanjskih izvora. Glavna dorada je upravljati cijelim prolaskom kroz izvor, uključujući eksplicitan izbor ponavljanja i povratak na odgovarajući prikaz sljedeće kartice.

**Zadano ponašanje: Anki vodi sesiju, a izbor prikaza pamti se po stranici.**

Postojeća obična Web kartica nastavlja se prikazivati u Ankiju dok korisnik ne odabere vanjski prikaz. Za YouTube i servise s prijavom možemo jasno preporučiti Chrome pri prvom izboru. Ne treba nepredvidljivo mijenjati aplikaciju pri svakom nailasku na polje za lozinku niti automatski prebaciti sve postojeće Web kartice.

Prvi izbor može biti ne-modalna ponuda na kartici: **Otvori u mom Chromeu**, uz **Uvijek koristi Chrome za ovu stranicu**. Uparivanje se obavlja samo ako profil još nije povezan. Nakon odabira korisnik zna da se taj izvor otvara izvana. Postavka mora biti lako dostupna i opoziva. Na kasnijim dolascima preskače se isto pitanje i može se izravno aktivirati povezani prozor.

Ako je za domenu već odabran Chrome, ne treba najprije učitati isti sadržaj i u Qt-u. Anki prikazuje naslov trenutne kartice i stanje **Čitaš u Chromeu**, dok jedan preglednik ima odgovornost za reprodukciju i spremanje položaja. Time se izbjegavaju dva playera, dva upita za prijavu i međusobno prepisivanje napretka.

**Ciljani prolazak kroz miješanu sesiju**

| Trenutak | Prikaz i radnja |
|---|---|
| Obična kartica | Normalni Anki prikaz i postojeći izbor odgovora. |
| Slijedi prijavljeni web izvor | Ako je Chrome prethodno odabran, aktivira se postojeći namjenski Chrome prozor s odgovarajućim izvorom i spremljenim mjestom gdje je podržano. |
| Čitanje | Uz stranicu su naziv izvora, potvrđeno stanje spremanja, izdvajanje i oznaka mjesta. Korisnik ostaje u uobičajenom browser računu. |
| Korisnik klikne Završi čitanje | Prikazuju se stvarni izbori odgovora za trenutačnu Anki karticu. Sama radnja još ne ocjenjuje karticu. |
| Korisnik odabere učestalost/ocjenu | Zahtjev se izvršava kroz Anki; tek potvrđen odgovor dopušta prijelaz dalje. |
| Sljedeća je opet web/video kartica za Chrome | Povezani prozor ostaje aktivan i prima novi izvor. Nema povratka u Anki samo radi ocjene. |
| Sljedeća je obična, PDF, EPUB ili druga interna kartica | Aktivira se Anki i pripadajući prikaz. |

To smanjuje nepotrebne povratke kod niza web izvora. Ne uklanja sve prijelaze u sesiji u kojoj se browser i obične kartice izmjenjuju. Ta je granica važna za očekivanja korisnika.

**Gumbi moraju imati jednoznačno značenje.**

- **Spremi i vrati se u Anki** vraća istu karticu, bez ocjene i promjene rasporeda. To je siguran početni tijek i rezervna mogućnost.
- **Završi čitanje** završava rad s izvorom za ovaj posjet i otvara izbor ponavljanja; ništa se ne smije automatski proglasiti uspješno odgovorenim.
- Za topic karticu izbor može glasiti **Češće / Jednako često / Rjeđe**, u skladu s postojećim More/Same/Less pravilima. Druge kartice dobivaju svoje stvarne Anki izbore. Intervali dolaze iz Ankija, ne iz izračuna ekstenzije.
- **Sljedeća kartica** slijedi potvrđen odgovor ili zasebno jasno odabrano preskakanje. Generički Nastavi ne smije potajno značiti Good.
- Ne koristiti **Done/Gotovo** za običan povratak. Postojeći Done u Incrementu ima značenje trajnog završavanja teme kroz suspendiranje i označavanje.

Postojeća kompatibilnost izričito razlikuje odgovor od pukog napredovanja reviewera. Topic izbori imaju svoju semantiku i svi konačno koriste Anki Good. Nova browser kontrola treba pozvati postojeći frontend/backend put, a ne održavati drugi scheduler. [backend/anki_compat.py:166](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/anki_compat.py:166>), [backend/topic_scheduler.py:338](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/topic_scheduler.py:338>), [postojeći Done adapter](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/reviewer_topic_actions.py:100>).

**Jedan namjenski prozor za učenje, s postojećim Chrome računom.**

To je prozor unutar korisnikova odabranog Chrome profila, ne novi anonimni ili zaseban profil koji ponovno traži prijavu. Integracija pamti prozor i tab za aktivni izvor. Ne zamjenjuje korisnikov proizvoljni aktivni tab. Pri prelasku dalje ne zatvara druge osobne tabove. Ako korisnik želi zadržati izvor, može ga odvojiti od sesije prije zamjene sadržaja.

Na malom zaslonu dovoljna je kompaktna Incrementova traka, s izdvajanjima iza proširive kontrole. Na većem zaslonu bočni panel može pokazati više konteksta. Chrome ima službeni Side Panel API, ali njegovo otvaranje ima uvjete korisničke geste u ekstenziji. Ne treba obećati da ga klik iz Ankija uvijek može sam otvoriti. Jednokratni browser korak za otvaranje/povezivanje mora biti uključen u prvi tijek. [Chrome Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel).

Na dva monitora korisnik može smjestiti Anki i Chrome jedan pokraj drugoga. Integracija treba zapamtiti njegov raspored, umjesto da ga stalno mijenja. Programsku aktivaciju prozora treba provjeriti na podržanim sustavima, uključujući macOS fullscreen i Spaces. Chrome Windows API upravlja Chromeovim prozorima; povratak u Anki zahtijeva native dio integracije. [Chrome Windows API](https://developer.chrome.com/docs/extensions/reference/api/windows), [Qt QWindow](https://doc.qt.io/qt-6/qwindow.html).

**Zašto sadašnji Open in Window nije dovoljan**

| Nalaz iz koda | Potrebna dorada UX-a |
|---|---|
| Question hook automatski pokazuje Web dock. | Prije učitavanja odlučiti pripada li izvor internom ili povezanom browser prikazu. |
| Vanjski gumb uglavnom samo poziva otvaranje URL-a. | Uvesti točan povezani profil/prozor, potvrdu otvaranja i vidljivi put povratka. |
| Vanjske promjene URL-a učitavaju isti URL i u internom prikazu. | U vanjskom načinu ažurirati stanje bez ponovne reprodukcije/navigacije u Qt-u. |
| Povratak iz videa otvara ručni dijalog vremena zaustavljanja. | Nakon potvrđenog automatskog spremanja vratiti se bez dijaloga. Ručni unos ostaje iznimka pri neuspjehu. |
| Postojeći timeri nisu dokaz aktivnosti na povezanoj stranici. | Razlikovati video poziciju, proteklo vrijeme sesije i aktivno vrijeme učenja. |
| Reviewer ima vlastiti odgođeni povrat fokusa. | Dok Chrome vodi čitanje, naknadni Anki callback ne smije preoteti tipkovnicu. |

Dokazi: [Web question lifecycle:1816](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1816>), [vanjsko otvaranje:1492](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1492>), [sinkronizacija internog prikaza:1764](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1764>), [povratak iz videa:2627](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/video_dock.py:2627>), [mjerenje sesije:1562](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/session.py:1562>), [reviewer focus:39](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/reviewer_focus.py:39>).

**Prekidi i rubni slučajevi dio su glavnog tijeka.**

Ako ekstenzija nije dostupna, Anki ostaje na kartici i nudi ponovno povezivanje ili obično vanjsko otvaranje s jasnom porukom da automatsko spremanje nije potvrđeno. Otkazivanje povezivanja ne preskače karticu. Neuspjelo spremanje ne treba zaključati korisnika u Chromeu: povratak ostaje moguć uz točno prikazano stanje.

Ako je korisnik ručno prešao na drugu Anki karticu, stari browser panel više ne smije ocjenjivati. Isto vrijedi nakon promjene Anki profila, završetka sesije, Undo ili dvostrukog klika. Potrebni su identitet trenutačne kartice/profila i generacija sesije te potvrda jedne provedene radnje. Povratak iz starog taba ne smije potajno vratiti staru karticu preko korisnikova novog izbora.

Prelazak na nepovezani osobni tab nije nastavak učenja trenutnog izvora. Klik na YouTube preporuku ne smije zamijeniti identitet izvornog videa. Praćenje navigacije unutar Web kartice već postoji, ali granica između nastavka čitanja, login preusmjeravanja i odlaska na drugi izvor mora biti vidljiva i definirana. Tipke stranice, poput razmaknice za video, ostaju stranici; browser ne šalje skrivene Anki ocjene.

**Ako je zahtjev nula prijelaza između aplikacija, postoje dvije druge odluke.**

Potpuno ostajanje u Ankiju zadržava najjednostavniji prostorni UX, uz poboljšanje njegova vlastitog WebView profila. To samo po sebi ne daje postojeću Chrome sesiju niti uklanja ograničenja pojedinih prijava.

Druga mogućnost je cijelo učenje u Chromeu, uključujući obične kartice. Tada treba razviti browser reviewer s Anki predlošcima, medijima, odgovorima, prečacima, Undo i životnim ciklusom. Sam bočni panel ne rješava sve to. Taj smjer ima smisla samo kao zasebno odabrana veća nadogradnja, a ne skriveni dodatak popravku prijave.

**Redoslijed koji preporučujem:** prvo provjeriti i popraviti trajnost postojećih prijava unutar Ankija, da vanjsko otvaranje ne bude zamjena za rješiv kvar. Za izvore kojima i dalje treba Chrome prototipirati kompletan prolazak na jednom zaslonu; zatim implementirati povezivanje, zapamćeni izbor prikaza, potvrđeno spremanje i povratak na istu karticu. Eksplicitno ocjenjivanje uz browser sadržaj i prijelaz prema tipu sljedeće kartice trebaju biti uvjet da se vanjski način nazove potpuno integriranim učenjem. Tek potom proširivati panel i rasporede prozora.

Provjera treba odraditi niz obična kartica → prijavljeni Web → drugi Web → obična kartica → YouTube, uz ugašenu ekstenziju, zatvoren Chrome, promjenu profila i neuspjelo spremanje. Promatra se broj nepotrebnih radnji, predvidljivost fokusa, očuvanost mjesta čitanja i točan trenutak ocjenjivanja. Ovaj dokument definira očekivanja; takvo testiranje s korisnikom još nije provedeno.
