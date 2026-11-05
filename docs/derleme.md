# derleme ve imzalama

windows x64 ve python 3.12 ile ayrı bir derleme ortamı kullan. `installer/requirements-ui.txt` ile `pyinstaller>=6,<7` paketlerini kur. `python scripts/export_next_source.py <yeni-temiz-klasör> --exclude-tests` genel kaynak izin listesini dışa aktarır. ayarlar, günlükler, ekran görüntüleri, modeller, eğitim verisi ve özel anahtarlar bu pakete girmez. kişisel yolların derlenmiş dosyalara taşınmaması için temiz kopyayı genel bir derleme klasöründe derle.

`python scripts/build_executable.py` arayüzü `dist/Mergen` altında oluşturur. `Mergen.exe`, `Mergen.pkg` ve `Mergen.exe.manifest` birlikte dağıtılır. model çalışma kütüphaneleri arayüz paketine gömülmez; uygulama içinden ayrı ortamlara kurulur. `scripts/fetch_build_tools.ps1` doğrulanan inno setup ve taşınabilir python araçlarını hazırlar.

## uygulama ve model yayınları

uygulama kurulumu model ağırlıklarından ayrı hazırlanır. uygulama sürümü arttığında aynı büyük model dosyalarını yeniden yükleme. `assets/packed-models.json` model arşivlerinin sabit adres, boyut ve sha256 bilgilerini; `assets/bundled-models.json` açılan özgün dosyaların boyut ve özetlerini tutar. kurulum mevcut doğrulanmış modelleri korur; yalnız eksik veya bozuk dosyalar için model sağlama adımı çalışır.

bağlamlı modelin taban ağırlığı ve uyarlaması `tu5j4/nllb-mergen-baglam-v1` deposundaki `v1.0.0` yayınının mevcut dosyalarını ve özetlerini kullanır. diğer sabit model arşivleri `mergen-models-0.5.0` etiketli ortak model yayınında bir kez tutulur. `mergen-model-support-0.5.0.zip` yalnız büyük paketlenmiş ağırlıklar dışındaki sabit destek dosyalarını içerir. model kartları ve lisans dosyaları da destek verilerine dahildir; kişisel yol veya kullanıcı verisi içeremez.

`scripts/pack_model_archives.py` dört büyük ağırlığı bayt şeritleri ve xz ile kayıpsız paketler. hazır arşivleri yeniden üretmek gerekmez. indirme ve açma sonrasında arşivler ve özgün model dosyaları sabit özetlerle doğrulanır. model ağırlıkları kaynak zip'ine veya her uygulama sürümünün kurulum paketine eklenmez. model sürümü değişecekse yeni sabit model yayını oluştur ve manifestleri birlikte güncelle.

`python scripts/build_installer.py --help` güncel uygulama kurulum seçeneklerini gösterir. kurulum başlatıcısı kullanılıyorsa `scripts/build_download_bootstrap.py` yalnız uygulama kurulumunu taşır; model indirmeleri sabit model adreslerinden bağımsız yapılır. başlatıcı paket boyut ve özetlerini doğrulamadan kurulumu çalıştırmaz.

`python scripts/sign_release_local.py --key <özel-anahtar> --installer <kurulum.exe> --output <yayın-klasörü>` ed25519 imzalı güncelleme bildirimi üretir. bu windows authenticode sertifikası değildir. özel anahtar dağıtıma veya repoya eklenmez. kaynak zip'i ve diğer yayın dosyaları için ayrıca sha256 listesi üret.

github commitlerinde author ve committer kimliklerini açıkça github kullanıcı adı ve github noreply adresiyle belirt. kaynak ağacını, yayımlanan dosya boyut/özetlerini, sürüm sabitlerini ve commit kimliklerini yayın sonrasında tekrar doğrula. donmuş python kodları, exe/pkg, taşınabilir python ve model destek dosyalarında kişisel yolların bulunmadığını da denetle.
