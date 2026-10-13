# mergen — yerel ekran ocr ve türkçe çeviri

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="240">
</p>

**Hızlı başlangıç:** [kolay kurulum ZIP paketini indir](mergen-kolay-kurulum.zip), tamamını çıkarıp `kolay-kurulum/kurulum.bat` dosyasını aç. Kurulumdan sonra aynı klasördeki `baslat.bat` ile başlat. [Kolay kurulum dosyaları](kolay-kurulum) da depoda bulunur.

Ekranın seçtiğin bölgesini sürekli izler, yazıları **gömülü OCR** ile okur, **yerel çeviri modeli** ile Türkçeye çevirir
ve sonucu orijinal konuşma balonunun üstüne **şeffaf, tıklama geçirgen bir katman** olarak çizer.
Model bir kez indirildikten sonra internet gerekmez.

Windows'ta `baslat.bat`, uygulamayı konsol penceresi açık bırakmadan başlatır.
Görev çubuğu ve pencere simgesi `assets/mergen.ico` içindeki çoklu boyutlu
mergen logosudur. Başlatma hatası olursa ekranda uyarı çıkar ve ayrıntılar
`logs/baslatma-hatasi.log` dosyasına yazılır.

Ana menüde kaynak dil ve OCR seçimleri, bölge seçimi, eşit aralıklı araç
baloncukları (şimdi çevir, çeviriyi gizle ve yalnızca çarkla açılan ayarlar),
altında tam genişlikte başlat düğmesi bulunur. Panel temaları yeşil, beyaz,
lacivert, siyah ve sepyadır; çeviri kutusu teması ayrı seçilir. Tikler ve
opaklık sürgüsü panelin zıt vurgu rengini kullanır. Açılır seçimler fare
tekerleğiyle yanlışlıkla değişmez; ayarlar penceresi kaydırılabilir. Menü
metinleri küçük harflidir; kaynak metinlerin ve çevirilerin harf düzeni
bu görünüm tercihinden etkilenmez.

Sistem kullanımında ad ve yüzde üstte, ince kullanım barı altta gösterilir.
GPU, VRAM ve CPU göstergeleri ayrı ayrı açılabilir. NVIDIA ölçümü başarısız
olursa Windows üzerinde WDDM/PDH sayaçlarına geçilir; GPU için seçilen
NVIDIA adaptörünün en yoğun motoru, VRAM için DXGI kapasitesine göre
kullanılan ayrılmış bellek ölçülür. CPU tüm sistem kullanımını gösterir.
Tercihler kaydedilir; tüm barlar kapalıyken periyodik ölçüm durur.
Ölçülemeyen değerler sıfır yerine kullanılabilir olmadığı belirtilerek gösterilir.

| Bileşen | Kullanılan |
|---|---|
| Arayüz / overlay | PySide6 (Qt 6) |
| Ekran yakalama | mss |
| OCR | **PaddleOCR** (tüm diller) + izole **manga-ocr** (Japonca, CPU/GPU) |
| Çeviri | Meta **NLLB-200** (CTranslate2, GPU FP16 / CPU int8) → Türkçe |

## Kurulum

Windows 10 2004+/11 x64, AVX destekli işlemci ve Python **3.11 x64** gerekir.

1. `kurulum.bat` dosyasını aç.
2. Donanım taramasını incele; kurulmasını istediğin OCR ve çeviri modellerini seçip onayla.
3. Sağlık kontrolü geçince `baslat.bat` ile aç.

Python yoksa kurulumu için ayrıca izin istenir. NVIDIA CUDA ön kontrolü ve gerçek
işlem testi yapılır; AMD/Intel kartlarda bu dağıtım CPU kullanır. İlk indirmeler
internet gerektirir. Ayrıntılar: [geliştirici kurulum notları](docs/kurulum.md).

Bu depo geliştiriciler içindir. Kullanıcılara `kolay-kurulum` paketini verin;
onda yalnızca üç başlatma dosyası, kısa bir rehber ve `program` klasörü vardır.
Dağıtımı üretmek için `python scripts/build_distribution.py --output YENI_KLASOR`
çalıştırılır. Testler: `python -m unittest discover -s tests -v`.

## Bağımlılık yöneticisi

`bagliliklar.bat` dosyası, kurulu Python paketlerini ve yerel OCR/çeviri modellerini
tarar. Menüden yalnızca eksik veya ihtiyaç duyduğun bileşeni seçerek kurabilirsin.
Menüde tara, kur/onar, kaldır ve sağlık kontrolü bulunur. manga-ocr gpu bileşeni
ayrı `.manga-venv` ortamını kurar. Ana ortamın Paddle/Torch paketlerini değiştirmez.
Kurulum birkaç GB disk/indirme gerektirebilir. Kaldırma yalnızca bu kopyanın
seçili bileşenlerini etkiler; sistem Python'u ve sürücüler kaldırılmaz.

### Manga-ocr GPU / CPU

EasyOCR artık kullanılmaz. Paddle tüm dillerde tespit/okuma yapar; Japoncada
`manga-ocr` seçimi veya `Otomatik` + Japonca manga-ocr onayı, Paddle'ın bulduğu
balonları manga-ocr ile yeniden okur. Ayarlardaki `manga-ocr cihazı` seçimi:

- **Otomatik:** izole ortam varsa GPU'yu dener; başarısızsa CPU, manga modeli
  yüklenemezse Paddle sonucu korunur.
- **GPU:** ayrı CUDA ortamını kullanır. Başlatma hatası durum satırında uyarı
  olarak gösterilir ve Paddle çalışmaya devam eder.
- **CPU:** manga-ocr RAM/işlemci kullanır; onun GPU model belleği ayrılmaz.

Yardımcı işlem açık kalır, her balonda yeniden model yüklemez. Dil/motor
değişince ve uygulama kapanınca sonlandırılır. `manga_batch` 1–4 aralığında
sınırlandırılır; küçük batch, manga-ocr tepe VRAM'ini sınırlamaya yardımcı olur.
Çeviri modeli seçiminiz korunur. `use_gpu: "no"` çeviriyi de CPU'ya alır.

VRAM kullanımı seçilen modellere ve görüntü boyutuna bağlıdır; tüm cihazlar için
sabit bir minimum/maksimum bellek garantisi yoktur.

## Kullanım

1. İçerik dilini seç (Japonca manga, Korece manhwa, Çince manhua, İngilizce çizgi roman).
2. **Bölge seç** → okuyucunun / tarayıcının sayfa alanını sürükleyerek işaretle (ya da **Tüm ekran**).
3. **Başlat**. Sayfayı kaydırdığında eski çeviri anında silinir, kaydırma durunca yeni sayfa okunur.
4. Overlay tıklamaları alttaki pencereye geçirir; okumaya ve kaydırmaya normal şekilde devam edersin.

Kısayollar: `Ctrl+Alt+T` başlat/durdur, `Ctrl+Alt+R` bölge seç, `Ctrl+Alt+H` orijinali gör, `Ctrl+Alt+Y` şimdi çevir.

### Panel düzeni ve kesik balonlar

Mobil model İngilizce/Çince/Japonca için ortak PP-OCRv5 tanıyıcıyı, Korece için
ayrı `korean_PP-OCRv5_mobile_rec` modelini kullanır. GPU'lu Paddle kuruluysa ve
GPU kapatılmadıysa `GPU:0` üzerinde çalışır. Paddle yoksa bağımlılık hatası
gösterilir; artık EasyOCR'a dönüş yapılmaz.

Panel düzeni otomatik uygulanır; ek model veya indirme gerektirmez. Beyaz panel
aralıkları CPU üzerinde incelenir, bulunan bölgelerdeki balonlar ayrı tutulur.
Japonca/Çince içerik sağdan sola, İngilizce/Korece içerik soldan sağa sıralanır.
İngilizce dışındaki dillerde model çağrıları panel sınırlarını korur. İngilizcede
hız için farklı panellerin bağımsız balonları aynı toplu model çağrısına
alınabilir (`translate_chunk`); okuma sırası ve balon başına sonuç korunur.
Her balon NLLB'ye bağımsız cümle olarak gider: bu özellik bağlam anlayan yeni
bir çeviri modeli değildir ve hatalı OCR karakterlerini tek başına düzeltmez.

Panel kısmen görünse bile tam görünen balon çevrilir. OCR metni veya güvenilir
balon adayı ekran sınırında kesiliyorsa sonuç bekletilir; dikey kaydırmayla
tamamlanan bölge tekrar okunabilir. Algılanamayan balon sınırları için bu koruma
kesin değildir. Çerçevesiz, eğik veya aralarında başlık/efekt bulunan paneller
ayrılamazsa tek bölge korunur; metin zorla parçalanmaz.

Kesilmenin üst, alt, sol veya sağ kenarda olması ayrı izlenir. Soldan/sağdan
kesilen balon, altındaki sağlam balonları bekletmez. Yeni metin şeridinin sınırı
gerçek ekran kenarından ayrılır; şerit sınırında kesilme görülürse yalnızca bir
kez tam görünüm yeniden taranır. Kapalı kontur bulunamazsa, ekran kenarında
devam eden açık renkli ve kıvrımlı balon içi temkinli bir ek işaret olarak
kullanılır; düz panel ve beyaz sayfa bu işaretle balon sayılmaz.

### Eksik İngilizce balonları yeniden okuma

Tam görünen açık renkli bir balonda düşük güvenli OCR satırı veya okunmamış
harf benzeri alan varsa yerel kırpımda bir ek okuma denenir. Tarama başına
en fazla iki balon yeniden okunur. Güvenilir mevcut satırlar korunur;
kesik balonlar bu kurtarma yoluna alınmaz. Kaydırma sonrasında aynı İngilizce
metin alanı daha tam okunursa eski kelimeleri büyük ölçüde aynı sırada
koruyan sonuç eski eksik çeviriyi güncelleyebilir. Farklı paneller ve birden
fazla komşu metin alanını birleştiren sonuçlar bu yolla değiştirilmez.
Şüpheli balonlardaki ek okuma gecikmeyi artırabilir; her eksik OCR sonucunun
kurtarılacağı garanti edilmez.

### Oturumluk isim ve terim tutarlılığı

Ayarlardaki `oturumluk isim ve terim tutarlılığı` varsayılan olarak açıktır.
Son 24 farklı, tamamlanmış konuşma ve en fazla 128 isim/kısaltma eşleşmesi
yalnızca RAM'de tutulur; diyaloglar dosyaya kaydedilmez. Kaydırma ve yeniden
tarama aynı metni hafızaya tekrar doldurmaz. Dil veya çeviri alanı değişince,
uygulama kapanınca veya `konuşma hafızasını temizle` düğmesine basınca temizlenir.
Yeni bölüm/hikâyeye geçerken bu düğme kullanılabilir. Normal sayfa geçişlerinde
isim hafızası korunur. Kapatma/açma seçeneği ve temizleme model indirmez.

NLLB'ye önceki konuşmalar eklenmez; her balon bağımsız kalır. Doğrulanmış isim
yazımları model girdisinde korunur, çıkan isimler denetlenir ve yalnızca şüpheli
balonlarda mevcut sınırlı yeniden çeviri yolu kullanılır. Çözülmeyen sonuç `[?]`
olarak işaretlenir ve hafızaya öğretilmez. İptal edilmiş taramalar da kalıcı
oturum hafızasına eklenmez. Mevcut aile/meslek/sayı sözlüğü kontrolü korunur.

Doğrulanmış yazımlar [session_terms.json](app/data/session_terms.json) içindedir;
başlangıç listesi Yuji Itadori'nin desteklenen dillerdeki tam adını kapsar.
`contextual_sources` altındaki kısa/şüpheli yazımlar ancak tam ad aynı toplu
çağrıda veya daha önce güvenilir biçimde görülmüşse etkinleşir. Bu dosya aynen
korunacak isim/kısaltma yazımları içindir; genel sözcükleri gelişigüzel eklemek
çeviri anlamını bozabilir. Düzenledikten sonra uygulamayı yeniden başlatın.
İngilizcede açık isim tanıtımları (`my name is …`, `Dr. …`) ve CJK metnindeki
açık Latin kısaltmalarından da temkinli biçimde yazım öğrenilir. Bilinmeyen
Çince/Japonca/Korece isimler otomatik tahmin edilmez.

Bu hafif aşama NLLB'ye hikâye anlama, konuşanı belirleme veya zamir çözme
yeteneği kazandırmaz. Yeni GPU modeli yüklemez; şüpheli isimlerde yeniden
çeviri gerektiğinde model gecikmesi artabilir. `session_context: false`
ile önceki çeviri yolu kullanılabilir.

## Platform notları

Hazır kurulum yalnızca Windows içindir; aşağıdaki diğer platform notları kaynak
koddan geliştirme içindir ve bu kurulum tarafından doğrulanmaz.

- **Windows 10 (2004+) / 11:** En iyi deneyim. Overlay ekran yakalamadan hariç tutulur, titreme olmaz.
- **macOS:** Sistem Ayarları → Gizlilik → *Ekran Kaydı* ve *Erişilebilirlik* (kısayollar için) izni ver.
- **Linux (X11):** Overlay yakalamadan hariç tutulamadığı için tarama anında çok kısa gizlenir (hafif titreme).
  Wayland'da global ekran yakalama kısıtlıdır, X11 oturumu kullan.

## Çeviri modeli ve dağıtım

Kurulumda iki yerel model seçeneği vardır: **standart** (NLLB 600M) daha az
donanım ister; **kaliteli** (NLLB 1.3B) daha büyüktür. Çeviri kalitesi OCR'a ve
içeriğe bağlıdır. Kod **MIT** lisanslıdır; modellerin lisansları değişmez.
NLLB modelleri **CC-BY-NC 4.0** lisansına tabidir. Dağıtım kaynak kod içerir,
ağırlıklar kullanıcının onayıyla indirilir. [Üçüncü taraf bildirimleri](THIRD_PARTY_NOTICES.md).

## Ayar ipuçları (`settings.json`)

- `speed_preset`: `fast` / `balanced` / `quality` (panelden de seçilir).
- `settle_ms`: kaydırma durduktan sonra OCR'a başlamadan önceki bekleme.
- `poll_ms`: kaydırma takibi sıklığı (60 = ~15 fps).
- `scroll_tracking`: webtoon'da çeviriyi içerikle kaydırır, sadece yeni kısmı okur.
- `change_threshold`: animasyonlu reklamlar sürekli yeniden okumaya sebep oluyorsa artır.
- `group_gap_ratio`: farklı balonlar birleşiyorsa düşür, tek balon bölünüyorsa artır.
- `ocr_mag_ratio`: küçük yazılarda 2.0 yap (daha yavaş).
- `beam_size`: 1 = en hızlı, 4–5 = daha iyi çeviri.

## Eksik balonlar için tanı

Japoncada gri dokuların veya beyaz harf konturlarının balon sanılmasını azaltmak
için aday sınırının OCR sütununun en az %75'ini kapsaması aranır; konturun içi de
örneklenir. Balonsuz yakın dikey sütunlar mevcut hizalama kurallarıyla sağdan sola
birleştirilir. Japonca çeviri kutularının genişletilmesi komşu kutuların merkezleri
arasında sınırlandırılır; önceden örtüşen sütunlar da ayrı yatay alanlarda kalır.
Yalnızca aynı doğrulanmış balondaki Japonca dikey sütunlarda kısa/uzun sütun
yükseklik sınırı esnetilir; punto, hizalama, mesafe ve panel sınırı kontrolleri
korunur. Balon dışındaki yazılar için yükseklik koruması devam eder.
Bu kontroller ek model veya OCR geçişi kullanmaz.

Korece webtoonlarda yatay Hangul satırlarının yanlışlıkla 180° döndürülmesini
önlemek için satır yön sınıflandırıcısı kapalıdır. Aynı bilinen balondaki hizalı
satırlar daha geniş satır aralığında da birlikte çevrilir. Kaydırma taramasının
sınırı algılanan balonu keserse şerit balonun tamamını kapsayacak kadar büyütülür;
ek bir OCR geçişi yapılmaz. Bu davranışlar diğer dilleri değiştirmez. Gerçekten
baş aşağı duran Korece yazıları önce görüntüleyicide düz çevirmek gerekir.

Son taramanın aşaması, görüntü boyutu, OCR kutuları, kesik balon işaretleri ve
çeviri sayısı `logs/son_tarama.json` dosyasında tutulur. Ekran görüntüsü ve
diyalog metinleri kaydedilmez. OCR/çeviri hatasında bölge tamamlanmış sayılmaz;
birer saniye bekleyerek en fazla iki otomatik tekrar yapılır. Devam eden hatada
`Tek çevir` ile yeniden deneyebilirsiniz.

## Mimari (mobil port için)
```
app/core/   -> UI'dan bağımsız: yakalama, değişim algılama, OCR, gruplama, çeviri
app/ui/     -> Masaüstüne özel Qt arayüzü (overlay, bölge seçici, panel)
```
Android portunda: `MediaProjection` (ekran yakalama) + `SYSTEM_ALERT_WINDOW` (overlay),
OCR için ML Kit / ONNX, çeviri için NLLB'nin ONNX/CTranslate2 sürümü kullanılabilir;
`textgroup.py` ve `pipeline.py` içindeki mantık birebir taşınır.

> Not: NLLB-200 modeli CC-BY-NC 4.0 lisanslıdır (ticari olmayan kullanım).
