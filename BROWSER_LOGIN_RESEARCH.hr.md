**Istraživanje: prijave u Incrementovu web prikazu i povezivanje s Chrome profilom**

Datum provjere: 16. rujna 2026. Opseg: pregled implementacije u ovom repozitoriju i primarnih izvora Qt-a, Chromiuma, Googlea, Microsofta i IETF-a. Ovo je tehnički prijedlog; ponašanje dodatka nije promijenjeno. Osobni Chrome profili, spremljene lozinke, kolačići i sadržaj mape user_files nisu pregledavani. Konkretan gubitak prijave nije reproduciran u aktivnom Ankiju, pa su u nastavku odvojeni potvrđeni nalazi i hipoteze.

**Nakon detaljnijeg pregleda UX-a preporučujem sesiju koju vodi Anki, uz zapamćen izbor Chromea za pojedine stranice.** Chrome ostaje tehnički izbor za postojeće browser prijave, ali samo vanjsko otvaranje nije dovršen korisnički tijek. Dolazak, izdvajanje, završetak čitanja, izbor ponavljanja i prijelaz na sljedeću karticu moraju biti povezani. [Dopuna: konkretan UX i odluke o prijelazima](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/BROWSER_LOGIN_UX.hr.md>) precizira i nadopunjuje niže opisanu tehničku arhitekturu. Ugrađeni prikaz ostaje za sadržaj koji u njemu dobro radi.

Najbolji dugoročni doživljaj bio bi: korisnik jednom poveže željeni Chrome profil i odabere stranice za vanjski prikaz. Incremento aktivira namjenski prozor za učenje na spremljenom mjestu. Uz sadržaj prikazuje status i omogućuje eksplicitan izbor ponavljanja kroz Anki. Nakon potvrđene ocjene sljedeći web izvor koristi isti prozor, a obična kartica vraća Anki. Bočni panel sam ne ostvaruje taj tijek: potrebni su podržani reviewer pozivi, upravljanje fokusom i životnim ciklusom. To zahtijeva razvoj; postojeća ekstenzija već pokriva značajan dio uvoza i praćenja.

**Što je već potvrđeno u kodu**

| Nalaz | Dokaz u repozitoriju | Značenje |
|---|---|---|
| Web prikaz stvara imenovani QWebEngineProfile, postavlja vlastitu trajnu pohranu i ForcePersistentCookies. | [frontend/web_dock.py:1111](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1111>) | Spremanje kolačića već je uključeno. Nije dovoljno ponovno uključiti istu zastavicu. |
| Video prikaz radi isto, ali s drugim profilom i drugom mapom. | [frontend/video_dock.py:245](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/video_dock.py:245>) | Prijava u Web prikazu ne prijavljuje automatski Video prikaz. Nijedan ne koristi osobni Chrome profil. |
| Oba prikaza ručno postavljaju identitet Chrome/124 na macOS-u. | Ista dva mjesta inicijalizacije profila. | Taj tekst ne predstavlja nužno stvarni engine ni operacijski sustav korisnika. To je mjesto za provjeru kompatibilnosti, a ne dokazan uzrok odjavljivanja. |
| Web prikaz isključuje JavascriptCanOpenWindows; nema vlastiti createWindow/newWindowRequested tijek. | [frontend/web_dock.py:1126](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1126>), [klasa stranice:1976](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1976>) | Prijave koje ovise o dodatnom prozoru mogu zapeti. To je zasebno od spremanja prijave. |
| Profili se resetiraju pri otvaranju Anki profila; koristi se odgođeno uklanjanje dockova. | [__init__.py:2847](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:2847>), [web reset:3380](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:3380>), [video reset:1288](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/video_dock.py:1288>) | Redoslijed uklanjanja stranice/profila i dovršetak zapisivanja na izlazu zaslužuju kontrolirani test. Kod sam ne dokazuje gubitak kolačića. |
| U inicijalizaciji nije eksplicitno postavljen cachePath; storageName je konstantan za svaki tip prikaza. | Inicijalizacija web/video profila. | Treba provjeriti i osigurati izolaciju predmemorije između Anki profila. To nije dokaz da se kolačići spremaju u pogrešnu mapu. |
| Web kartice imaju Open in Window i praćenje ekstenzijom. | [frontend/web_dock.py:1492](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/web_dock.py:1492>) | Osnovni put prema stvarnom pregledniku već postoji. |
| Video kartice otvaraju preglednik sa spremljenim vremenom. | [frontend/video_dock.py:2211](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/video_dock.py:2211>) | Ne treba iznova razvijati osnovni prijenos pozicije. |
| Vanjsko otvaranje koristi QDesktopServices.openUrl. | Prethodna dva mjesta. | Trenutno nema pouzdanog izbora konkretnog Chrome profila kroz taj poziv. |
| Companion podržava uvoz, izdvajanje teksta/snimki, praćenje Web kartice i videa. | [README ekstenzije](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/README.md>) | Temelj integracije već postoji, ali nije potpuna zamjena za sve funkcije ugrađenog čitača. |
| Automatsko ažuriranje YouTube/Vimeo vremena koristi AnkiConnect na 8765. Web praćenje i uvoz koriste Incrementov bridge na 8766. | [background/main.js:718](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/background/main.js:718>), README ekstenzije. | Korisnik danas može uspješno uvoziti sadržaj, a da mu video sinkronizacija ne radi zbog dodatne ovisnosti. |
| Video preuzimanje pokušava koristiti kolačiće Incrementova video profila. | [backend/video_manager.py:577](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/video_manager.py:577>) | Prijava u vanjskom Chromeu sama po sebi neće popraviti prijavu za yt-dlp i dohvat titlova. |

Pregled razvojne okoline pokazao je PyQt6/Qt 6.10.1, PyQt6-WebEngine 6.10.0 i QtWebEngine 6.10.1 u lokalnom .venv-u, uz anki/aqt 25.9.2. Metapodatak instalirane Anki aplikacije navodi 26.9. Razvojni .venv nije dokaz verzije Qt-a učitane u aktivnoj Anki aplikaciji; stvarne runtime mogućnosti treba zasebno provjeriti.

**Prijava, pamćenje lozinke i prepoznavanje preglednika tri su različita problema.**

Prijavu uglavnom održava sesija koju stranica prepoznaje. Spremljena lozinka služi za ponovnu autentikaciju kad sesija više nije važeća. Chrome profil uključuje mnogo više od jedne datoteke s kolačićima. Zbog toga omogućavanje trajne pohrane u Qt-u ne znači da korisnik dobiva Chromeov spremljeni račun ili automatsko popunjavanje.

Qt dokumentira da imenovani profil može spremati stanje te da ForcePersistentCookies čuva i sesijske kolačiće. Također traži uništenje diskovnog profila prije ili tijekom izlaza kako bi se podaci potpuno zapisali. Zadana lokacija predmemorije izvodi se zasebno iz cache lokacije i naziva profila. To daje konkretne smjernice za testiranje životnog ciklusa. [Qt: QWebEngineProfile](https://doc.qt.io/qt-6/qwebengineprofile.html).

| Simptom | Što prvo provjeriti |
|---|---|
| U Chromeu sam prijavljen, u Anki Web prikazu nisam. | Očekivana odvojenost profila; koristiti Chrome sesiju kroz vanjsko otvaranje. |
| U Web prikazu sam prijavljen, u Video prikazu nisam. | Trenutno su to dva različita Incrementova profila. |
| Prijava nestane nakon urednog izlaza iz Ankija. | Isti Anki profil i put pohrane, trajnost testne sesije, redoslijed gašenja i serverovo istjecanje sesije. |
| Google odbija prijavu porukom o nepodržanom/nesigurnom pregledniku. | Ograničenja ugrađenog preglednika; pokušaj u stvarnom Chromeu. |
| Klik na prijavu ne otvori ništa. | Popup/novi prozor i redirect tijek. |
| Video ne radi, iako sam prijavljen. | Točan tip stranice, dozvole gledanja, način reprodukcije, codec/DRM ili greška playera. |

Za provjeru trajnosti predlažem malu lokalnu testnu stranicu s izmišljenim session/persistent kolačićima i localStorage vrijednošću. Testira se zatvaranje docka, uredan restart Ankija i promjena Anki profila. Takav test može dokazati kvar pohrane bez čitanja osobnih prijava. Nakon toga slijedi ručna provjera konkretnog servisa. U ovom istraživanju taj runtime test nije izvršen.

**Google/YouTube imaju dodatna ograničenja koja promjena profila unutar Qt-a ne uklanja.**

Googleova OAuth pravila ne dopuštaju usmjeravanje autorizacije u ugrađeni user-agent pod kontrolom aplikacije. Google posebno upućuje aplikacije temeljene na ugrađenim frameworkovima, uključujući CEF, na browser-based OAuth te traži istinito predstavljanje preglednika. To ne dokazuje točan razlog svake YouTube greške, ali objašnjava zašto prijava kroz WebView nije pouzdana osnova proizvoda. [OAuth pravila](https://developers.google.com/identity/protocols/oauth2/policies), [Googleove upute za ugrađene preglednike](https://developers.googleblog.com/guidance-to-developers-affected-by-our-effort-to-block-less-secure-browsers-and-applications/).

Zamjena teksta Chrome/124 novijim brojem ne ažurira engine. Preporučujem provjeru stvarne runtime verzije i ciljano testiranje uklanjanja hardkodiranog identiteta, uz jasno vanjsko otvaranje za nepodržane stranice. To ne treba predstavljati kao zajamčen popravak prijave.

Trenutni YouTube put u Video docku učitava običnu watch stranicu. Zato greška iframe playera nije automatski objašnjenje ovog problema. Ako se greška javlja u videu ugrađenom unutar druge web stranice, relevantne su zasebne kategorije: 101/150 znače zabranu ugrađenog prikaza, a 153 nedostatak Referer zaglavlja ili odgovarajuće identifikacije klijenta. [Izrada watch URL-a](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/video_providers.py:185>), [YouTube IFrame API](https://developers.google.com/youtube/iframe_api_reference).

Qt također ima uvjete za podršku pojedinim medijskim formatima i Widevineu. Bez konkretnog koda pogreške ne treba pripisati svaki neuspjeh reprodukcije prijavi. [Qt WebEngine media features](https://doc.qt.io/qt-6/qtwebengine-features.html).

**Usporedba mogućih integracija**

Sljedeće ocjene su arhitekturna procjena za Incremento, a ne rezultat benchmarka.

| Pristup | Koristi postojeću Chrome prijavu? | Doživljaj korisnika | Procjena |
|---|---|---|---|
| Popraviti trajnost postojećeg Qt profila | Ne | I dalje zasebna početna prijava | Potrebno za kvalitetu ugrađenog prikaza, nedovoljno za puni cilj. |
| Dijeliti jedan Qt profil između Web i remote Video prikaza | Ne | Manje ponavljanja prijave unutar istog Anki profila | Moguće, uz pažljivu migraciju i razdvajanje lokalnog sadržaja. |
| Otvarati zadani sistemski preglednik | Da, ako se otvori željeni Chrome profil | Vrlo jednostavno | Najbrže poboljšanje; već postoji osnovna funkcija. |
| Otvarati konkretan povezani Chrome profil i koristiti Companion | Da | Jednokratno povezivanje, zatim rad sa spremljenim stanjem | Preporučeni proizvodni smjer. |
| Chrome s Incrementovim bočnim panelom | Da | Stranica i alati za učenje u istom prozoru | Najbolja sljedeća faza za integriran rad. |
| Chrome prozor tipa popup ili app | Da, uz ispravno odabran profil | Odvojen kompaktan prozor | Opcionalni prikaz; nije Qt dock i treba provjeriti dostupnost kontrola. |
| Izravno dati Chromeovu mapu profila Qt-u | Nema pouzdanog ugovora | Naizgled bez postavljanja | Ne preporučujem; formati, zaštita podataka i istodobni pristup. |
| Kopirati kolačiće iz Chromea | Ponekad dio sesije | Povremeno ponovno povezivanje i nove dozvole | Nije pouzdan opći proizvodni put. |
| Remote debugging/CDP nad osobnim Chromeom | U određenim novijim načinima da | Razvojne postavke i upiti za pristup | Korisno za razvoj; nepotrebno složeno za redovno učenje. |
| Zamijeniti Qt s CEF/WebView2 | Ne automatski | Velika promjena bez jamstva prijava | Slab odnos koristi i opsega za ovaj problem. |
| Dodati OAuth prijavu u sam Incremento | Samo autorizacija vlastitog klijenta | Korisno za konkretan API | Ne prijavljuje proizvoljne web stranice unutar Qt-a. |

**Zašto izravno dijeljenje Chromeove mape nije preporučeni put**

Postaviti Qt-ov persistentStoragePath na Chromeov Default ili Profile 1 nije dokumentirani postupak uvoza Chrome računa. Chromium navodi da dva istodobna Chrome procesa ne mogu dijeliti isti user data directory; Qt dodatno nije isti proizvod ni nužno ista verzija Chromiuma. Moj zaključak je da tu mapu ne treba koristiti kao zajedničku radnu pohranu. [Chromium: user data directory](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md).

Chrome štiti osjetljive podatke platformskim mehanizmima: na macOS-u Keychainom, na Linuxu sistemskim spremištem, a na Windowsu je od Chromea 127 uvedeno dodatno App-Bound šifriranje kolačića. Samo kopiranje datoteke zato nije prenosiv integracijski ugovor. [Google: zaštita Chrome kolačića](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html).

Postoji službeni chrome.cookies API, pa nije točno da je svaki izvoz kolačića tehnički nemoguć. Međutim, on traži odgovarajuće dozvole, treba očuvati atribute i particije te ne predstavlja prijenos cijelog profila. U našem manifestu dozvola cookies trenutačno ne postoji. [Chrome Cookies API](https://developer.chrome.com/docs/extensions/reference/api/cookies), [manifest ekstenzije](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/manifest.json>).

Noviji Device Bound Session Credentials dodatno pokazuju smjer razvoja: za servise koji ga koriste obnavljanje kratkotrajne sesije može ovisiti o ključu koji preglednik čuva. Google je javnu dostupnost opisao za Chrome 146 na Windowsu, uz najavljeno proširenje na macOS. To nije tvrdnja da svaki današnji kolačić na svakoj platformi ima tu zaštitu. [Google: DBSC](https://blog.google/security/protecting-cookies-with-device-bound-session-credentials/).

**Dvije novosti zbog kojih stariji savjeti mogu zavarati**

Prvo, od Chromea 136 klasični --remote-debugging-port i --remote-debugging-pipe ne rade nad zadanim Chrome data direktorijem; za taj način traži se zaseban direktorij. Time se ne dobiva automatski korisnikova postojeća sesija. [Chrome 136 promjena](https://developer.chrome.com/blog/remote-debugging-port).

Ali od Chromea 144 postoji i korisnički odobrena veza na već pokrenuti Chrome preko novog remote-debugging tijeka. Googleov opis navodi prethodno uključivanje opcije i dijalog dopuštenja za novu debugging sesiju. Zato tvrdnja da je povezivanje na postojeći Chrome danas potpuno nemoguće nije točna. Moj prigovor je prikladnost: redovno učenje ne treba ovisiti o debugging postavkama i dodatnim potvrdama. Ni ovaj način sam po sebi ne ugrađuje Chrome u QWebEngineView. [Chrome: povezivanje s postojećom sesijom](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).

Drugo, Qt 6.10 ima QWebEngineExtensionManager s podrškom za učitavanje Manifest V3 ekstenzija. Starija tvrdnja da Qt uopće ne podržava ekstenzije više nije općenito točna. Ipak, učitavanje ekstenzije u Qt-ov profil ne preuzima stanje iste ekstenzije ili računa iz Chromea. Upravitelje lozinki trebalo bi zasebno provjeriti prema stvarnom Anki runtimeu i potrebnim extension API-jima. To je moguć eksperiment za ugrađeni prikaz, ne zamjena za postojeći Chrome profil. [Qt: extension manager](https://doc.qt.io/qt-6.10/qwebengineextensionmanager.html).

WebView2 također ima vlastitu pohranu aplikacije i vlastite profile. Zamjena renderera zato ne znači automatsko nasljeđivanje osobnog Chrome profila. [Microsoft: WebView2 user data folders](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder).

OAuth kroz sistemski preglednik jest standardni obrazac za autorizaciju vlastite native aplikacije. Dobiveni pristup određenom API-ju nije opći način da se youtube.com, Gmail ili proizvoljan portal prijave u drugom rendereru. Taj zaključak slijedi iz odvojenosti aplikacije i browser sesije u opisanom modelu. [IETF RFC 8252](https://www.rfc-editor.org/rfc/rfc8252).

**Kako bi preporučeno rješenje izgledalo korisniku**

1. U postavkama odabere način otvaranja: Automatski, U Ankiju ili U povezanom pregledniku. Automatski slijedi korisnikove zapamćene izbore po stranici. Za YouTube i stranice s problematičnom prijavom može preporučiti Chrome pri prvom izboru; ne prebacuje sve Web kartice niti postojeće korisnike bez prethodne odluke.
2. Jednom otvori Companion u željenom Chrome profilu i odabere Poveži ovaj preglednik. Vidljivo ime, primjerice Osobni ili Posao, može unijeti sam. Ne treba čitati njegovu e-mail adresu ni tražiti Google lozinku.
3. Otvaranje Anki kartice usmjeri ga na pripadajuću karticu preglednika, s prethodnim URL-om i pozicijom gdje je podržana. Već otvorena povezana kartica ponovno se koristi.
4. Anki pokaže Povezano, Spremljeno na 12:34 ili Preglednik nije povezan. Poruka mora predstavljati potvrđeno stanje, a ne samo uspješan pokušaj pokretanja URL-a.
5. Izdvajanje teksta ili snimke koristi postojeću ekstenziju. Kasniji bočni panel može dodati oznake, povezane kartice i povratak učenju. Raspoređivanje kartica i dalje ostaje Anki-jeva odgovornost.

U ovoj arhitekturi prijava ostaje u Chromeu. Stranica se prikazuje kao normalna kartica, a Incremento prima potrebni sadržaj i stanje učenja kroz postojeće ili ciljano proširene operacije. Kad sam servis zatraži novu prijavu, korisnik i dalje dobiva svoj uobičajeni browser tijek; obećanje proizvoda treba biti manje nepotrebnih prijava, a ne da više nikad neće biti prijave.

**Odabir pravog profila važniji je od samog pokretanja Chromea.**

Zadani sistemski preglednik i željeni Chrome profil nisu ista postavka. QDesktopServices prepušta otvaranje operacijskom sustavu. Povratna vrijednost true potvrđuje zahtjev za otvaranje, ne učitanu stranicu niti uspješnu vezu s ekstenzijom. [Qt: QDesktopServices](https://doc.qt.io/qt-6/qdesktopservices.html).

Za brzo rješenje može se dodati ciljani pokretač Chromea s eksplicitnim profilom. Chromium definira --profile-directory. To znači pokrenuti pravi Chrome s odabranim profilom, a ne čitati njegov profil iz Qt-a. Naziv direktorija ne mora odgovarati nazivu prikazanom korisniku. Pokretač treba centralizirati uz postojeće platformske adaptere, koristiti listu argumenata i provjeriti ponašanje na macOS-u, Windowsu i Linuxu, s već pokrenutim i zatvorenim Chromeom. [Chromiumova definicija prekidača](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.h), [postojeći platformski adapter](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/file_shell.py>).

Pouzdaniji dugoročni izbor je uparena instanca Companiona: ona otvara ili aktivira tab u svojem browser kontekstu. Tabs API omogućuje rad s karticama i prozorima, ali nije API za prebacivanje na proizvoljni drugi korisnički profil. Povezivanje zato mora krenuti iz željenog profila. Za osnovno stvaranje kartice nije potrebna opća tabs dozvola. [Chrome Tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs).

**Što treba doraditi u postojećoj integraciji**

| Područje | Konkretna dorada |
|---|---|
| Pravilo otvaranja | Jedan zajednički servis za Web i remote Video; globalni izbor i korisnikove iznimke po domeni. Lokalni dokumenti i video zadržavaju svoje čitače. |
| Identitet browser instance | Ne oslanjati se samo na extension ID: ista ekstenzija može postojati u više profila. Koristiti odabranu lokalnu instancu i jasnu vezu s Anki profilom. Trajni identifikator nije sam po sebi autentikacija. |
| Identitet aktivne Anki sesije | Handshake treba moći razlikovati generaciju aktivnog profila. Stara tab/card veza nakon promjene profila mora prestati vrijediti, čak i kad je ekstenzija dobila novi transportni token. |
| Video napredak | Dodati podržanu Incrementovu operaciju za video poziciju na bridgeu i ukloniti obvezni AnkiConnect za osnovni tijek. Provjeravati točan card/media odnos, ne masovno ažurirati sve bilješke istog videa. |
| Povratak iz preglednika | Uskladiti automatsku potvrdu spremljenog vremena s postojećim ručnim dijalogom; ne pitati ponovno za vrijeme koje je već pouzdano spremljeno. |
| Pozicija web teksta | Ekstenzija dokumentira URL i media resume. Potpuno vraćanje tekstualnog scrolla/oznake iz Qt-a u Chrome treba zasebno implementirati i provjeriti. |
| Aktivno vrijeme učenja | Definirati računa li se vidljivo/aktivno pregledavanje ili stvarna reprodukcija. Ne pretpostaviti da postojeći Anki timer automatski pravilno broji vrijeme izvan Ankija. |
| URL oznake | Osnovni vanjski Web/Video linkovi još nose card ID u query parametrima. Novi prijenos treba maknuti identitet kartice iz serveru vidljivog URL-a, uz čitanje starijih linkova. Fragment također može čitati skripta stranice, pa u njega ne staviti bridge token. |
| Status i oporavak | Prikazati neaktivnu ekstenziju, nedostajuću dozvolu, drugi browser profil i prekid Ankija; ponavljanje slanja mora biti ograničeno i bez dupliciranja uvoza. |

Dokazi za relevantne granice su [handshake:1667](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/browser_bridge.py:1667>), [bridgeAuth.js](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/shared/bridgeAuth.js>), [Web URL builder:629](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/web_manager.py:629>) i [ručni povratak iz preglednika:2639](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/video_dock.py:2639>). Ovdje je riječ o zahtjevima za novu integraciju; rizik pogrešnog profila nije potvrđen runtime reprodukcijom.

Postojeći bridge prima HTTP zahtjeve ekstenzije. Nije već gotov kanal kojim Anki trenutno može proizvoljno narediti odabranom browser profilu otvaranje kartice. Za to je potreban dodatan mehanizam i potvrda izvršenja. Prva faza može koristiti eksplicitni pokretač preglednika, a uparena integracija treba mali dvosmjerni transportni prototip.

Za aktivnu sesiju kandidati su lokalni WebSocket ili Chrome Native Messaging. Prvi se bolje uklapa u postojeći lokalni servis, ali zahtijeva zasebno definiranu autentikaciju i ograničenja; nije dovoljno otvoriti socket i vjerovati pošiljatelju. Ne smije se staviti postojeći token u URL niti običnoj stranici dati pristup bridgeu. Postojeći HTTP pozivi ostaju kroz bridgeAuth.js. Native Messaging ima službeni kanal sa strogo navedenim ekstenzijama, ali traži instalaciju i održavanje native hosta na svakoj platformi. Moj je izbor prvo prototipirati lokalni kanal bez dodatnog instalacijskog paketa, a native host uvoditi samo ako pouzdanost ili distribucija to opravdaju. [Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging).

Manifest V3 service worker može biti ugašen između događaja. Chrome od verzije 116 podržava održavanje aktivne WebSocket veze razmjenom poruka unutar vremenskog prozora aktivnosti. To nije razlog za neograničeno pozadinsko praćenje: veza treba imati oporavak, ograničeno ponovno spajanje i životni ciklus vezan uz korisnikov rad. [Chrome: WebSockets u extension workeru](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets).

**Dozvole i bočni panel trebaju biti razumljivi, uz što manje postavljanja.**

Otvaranje URL-a iz Ankija samo po sebi ne daje ekstenziji activeTab pristup. On nastaje korisnikovom radnjom u ekstenziji i prestaje prelaskom na drugi origin. Za automatski rad na dodatnim domenama treba jasno ponuđena dozvola; postojeći Automatic site access već rješava dio toga. Budući dizajn može nuditi uži izbor po stranici. Podržani player u tuđem iframeu može tražiti dodatni host pristup. [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).

Bočni panel omogućuje prikaz Incrementovih alata pokraj normalne stranice. Chrome podržava sidePanel od verzije 114, a programsko otvaranje nakon odgovarajuće korisničke radnje od 116. Klik u Anki prozoru ne treba unaprijed smatrati valjanom Chrome extension gestom za automatsko otvaranje panela. Početni tijek treba predvidjeti klik na ikonu ekstenzije; podršku u Braveu i drugim preglednicima zasebno provjeriti. [Chrome Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel).

Kompaktan Chrome popup može biti dodatna opcija, uz testove dostupnosti menija, prijava i kontrola. Forsirano ugrađivanje vanjskog Chrome prozora u Qt dock ne preporučujem za više platformi: ni Tabs ni Windows API ne daju ugovor za takvu integraciju u Anki widget. [Chrome Windows API](https://developer.chrome.com/docs/extensions/reference/api/windows).

Trenutačna instalacija Companiona traži Developer mode i Load unpacked. Za obične korisnike objava kroz Chrome Web Store bila bi veliki dobitak: jednostavnija instalacija i standardni kanal distribucije. To je zaseban korak s registracijom, paketom, podacima za objavu i pregledom; ovaj izvještaj ništa ne objavljuje niti pretpostavlja da je ekstenzija već u trgovini. [Postupak objave](https://developer.chrome.com/docs/webstore/publish).

**Ugrađeni prikaz vrijedi poboljšati, uz realna očekivanja.**

Predlažem zajednički upravitelj životnog ciklusa profila, eksplicitno profilne storage/cache lokacije i provjerljivo gašenje stranica prije uklanjanja profila. Najprije treba potvrditi kvar kontroliranim testom. Već uključenu trajnu pohranu treba sačuvati, a ne pretpostaviti da nedostaje.

Jedan zajednički profil za udaljeni Web i Video sadržaj mogao bi smanjiti dvostruke prijave unutar Ankija. Međutim, Video profil danas dopušta pristup lokalnim datotekama, dok ga Web profil ograničava. Ne treba ih samo spojiti i preuzeti permisivnije postavke. Lokalni video, PDF/EPUB čitači i inertni snapshotovi moraju zadržati odgovarajuće odvojene granice. Postojeće dvije pohrane ne treba nekritički spajati: korisnik može biti prijavljen s različitim računima.

Popup tijek za stranice koje ga trebaju mora biti namjeran i imati vlasnika prozora te isti profil. Qt izričito opisuje potrebnu obradu novih prozora. Globalno uključivanje popupa ne bi riješilo Googleova ograničenja ugrađene autorizacije. [Qt: QWebEnginePage](https://doc.qt.io/qt-6/qwebenginepage.html).

Izolirani renderer za HTML/PDF snapshot namjerno nema trajne kolačiće i nije interaktivni browser. Njegovo dijeljenje s osobnom sesijom nije popravak ovog problema. [frontend/webpage_dialog.py:101](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/webpage_dialog.py:101>).

**Predloženi redoslijed izvedbe**

| Faza | Isporuka | Kada je dovršena |
|---|---|---|
| 1. Razjasniti i smanjiti problem | Kontrolirani test trajnosti; jasniji gumb Otvori u pregledniku; postavka vanjskog otvaranja za odabrane tipove/domene. | Korisnik može do postojećeg browser računa bez prolaska kroz prijavu u Qt-u. |
| 2. Učiniti integraciju pouzdanom | Odabir profila, povezivanje Companiona, potvrda otvorene kartice, jedna kartica po aktivnom izvoru, video pozicija kroz Incrementov bridge. | Točan profil i napredak ostaju ispravni kroz ponovno pokretanje i promjene Anki profila. |
| 3. Poboljšati rad u jednom prozoru | Chrome bočni panel, usklađeno izdvajanje i oznake, potvrđeno brojanje aktivnosti, jednostavna distribucija. | Uobičajeni tijek učenja ne zahtijeva stalno prebacivanje između dva prozora. |
| 4. Doraditi interni browser | Životni ciklus, cache izolacija, ciljano rukovanje prozorima, mogući zajednički profil samo za udaljeni sadržaj. | Testovi potvrđuju trajnost i izolaciju bez obećanja potpune Chrome kompatibilnosti. |

To je procjena redoslijeda, ne rok izrade. Najbrže poboljšanje koristi već postojeći vanjski put; potpuna integracija s uparivanjem i panelom opsegom je veća od promjene jedne postavke.

**Provjere prije isporuke trebaju pratiti stvarne korisničke situacije.**

| Scenarij | Očekivani rezultat |
|---|---|
| Dva Chrome profila s različitim računima | Otvara se eksplicitno povezani profil. |
| Dva Anki profila s istim brojem kartice | Stari browser tab ne može slati napredak u novi Anki profil. |
| Restart Ankija i uspavan/restartan extension worker | Ponovno povezivanje jasno je; stara veza ne postaje važeća samo osvježenjem tokena. |
| Chrome nije zadani preglednik | Ciljano povezani Chrome ostaje cilj; generički vanjski način poštuje OS postavku. |
| Chrome je zatvoren ili ekstenzija isključena | Prikazuje se točno stanje bez tvrdnje da se napredak sprema. |
| Otvaranje iste kartice više puta | Ponovno se koristi odgovarajući tab, bez poplave novih prozora. |
| YouTube pause, seek, SPA navigacija, zatvaranje taba | Pozicija ostaje vezana uz točnu karticu i video, uz ograničenu frekvenciju zapisa. |
| Više Anki kartica istog videa | Promjena jedne ne ažurira automatski sve druge. |
| Web stranica promijeni domenu ili player koristi drugi iframe origin | Dozvole i stanje veze imaju predvidljivo objašnjenje. |
| Ekstrakcija, oznake, tekstualni scroll, vrijeme učenja | Provjerene su funkcije koje se obećavaju; nepodržane jasno označene. |
| Prijava u Chromeu radi, preuzimanje/titlovi ne rade | Poruka razlikuje gledanje u pregledniku od zasebnog download tijeka. |
| Uredan izlaz i promjena Anki profila | Qt testna sesija traje gdje treba, a stanje ne prelazi između profila. |

Implementacija treba uskladiti config.json, config_service, Settings, root wiring, prijevode i MANUAL za nove postavke. Promjene Companiona trebaju izvorne testove i regenerirane dist datoteke; nove operacije bridgea provjere autentikacije, veličina, profila i životnog ciklusa. Ovo istraživanje nije mijenjalo implementaciju, pa build i runtime testovi nisu pokretani.

Za trenutno korištenje već dostupnog puta dovoljno je u željenom Chrome profilu imati Companion, otvoriti Web karticu preko Open in Window i uključiti Track via Chrome extension. Za automatski rad na običnim stranicama treba odgovarajući Automatic site access ili radnja na trenutnom tabu; za postojeću automatsku YouTube/Vimeo sinkronizaciju vremena trenutačno je potreban i AnkiConnect. Ako OS otvori drugi preglednik ili drugi profil, ta putanja još ne ostvaruje željeni rezultat — upravo zato su odabir profila i vidljiv status prvi prioriteti predložene integracije.
