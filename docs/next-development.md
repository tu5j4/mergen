# yeni sürüm

Bu klasör ayrı bir geliştirme sürümüdür. Eski uygulamanın ayarlarını, modellerini veya ortamını değiştirmez. Kaynak çalıştırmada veriler .data altında; kurulu uygulamada %LOCALAPPDATA%/mergen-next altında tutulur.

## mimari

QML arayüz ve Windows ekran katmanı PySide6 üzerinden çalışır. PaddleOCR, manga-ocr ve NLLB ayrı Python 3.12 ortamlarında JSON satır protokolüyle çağrılır. NVIDIA Paddle ortamı, CUDA paket çakışmalarını önlemek için NVIDIA Torch ortamından ayrıdır.

CPU/NVIDIA çevirisi CTranslate2, AMD/Intel çevirisi Transformers kullanır. AMD için ROCm 7.2.1, Intel için PyTorch XPU paketleri seçilir. PaddleOCR GPU seçenekleri deneysel Transformers yolunu kullanır. Eksik ağırlık veya başarısız donanım testi kurulumu hazır işaretlemez. Önerilen kurulumda OCR CPU'da başlar; GPU OCR ayrıca seçilir.

AMD Radeon için sabit ROCm sürümünün resmi Windows kart listesi kullanılır; listede olmayan kartlara ROCm indirilmez. Intel için Arc adı ilk uygunluk kontrolüdür. Her GPU ortamında gerçek tensör işlemi yapılır. Ayarlardaki model testi seçili cihazda gerçek çeviri/OCR çalıştırır; tüm dillerde kalite garantisi değildir.

## derleme

Python 3.11 + PySide6, numpy, OpenCV, Pillow, psutil, pynput, mss, PyInstaller ve cryptography bulunan bir geliştirme ortamında:

1. scripts/fetch_build_tools.ps1 ile sabit SHA256 özetli Python 3.12 ve Inno Setup indirilir. Betikteki geliştirme Python yolunu kendi ortamına göre değiştir.
2. python scripts/build_executable.py arayüzü dist/Mergen içine derler. Model kütüphaneleri exe içine alınmaz.
3. build-tools/inno/ISCC.exe installer/mergen-next.iss kurulum EXE'sini release içine oluşturur.
4. python -m unittest discover -s tests ve python scripts/smoke_qml.py ile kaynak sürüm doğrulanır.

Kurulum programı yalnızca kullanıcı hesabına kurar. Python çalışma zamanı uygulamaya özeldir; sistem Python'u ve GPU sürücüleri değiştirilmez. Uygulama kaldırıldığında model/ayar verileri korunur. Model kaldırmak için uygulamadaki bileşenler ekranını kullan.

## güncelleme yayımlama

Ed25519 açık anahtarı assets/update-public-key.pem içinde sabitlenir. Özel anahtar bu klasöre veya GitHub'a konmaz. scripts/release_manifest.py ile kurulum dosyası için mergen-update.json imzalanır. Kurulum EXE'si ve bu bildirim, tu5j4/mergen deposunun aynı GitHub Release sürümüne yüklenmelidir. Otomatik güncelleme sürümün yeni olmasını, depo adresini, imzayı, boyutu ve SHA256 özetini kontrol eder.

Mevcut geliştirme için özel anahtar üstteki manga_translator/artifacts/mergen-next-signing klasöründedir. Yedekle; kaybolursa eski uygulamaların güvendiği anahtarla yeni güncellemeleri imzalayamazsın. Bu turda GitHub'a sürüm yayımlanmamıştır.

## doğrulama sınırları

AMD ve Intel donanımı üzerinde uçtan uca test yapılmadıkça bu seçenekler deneysel kalır. Windows 10/11 temiz bilgisayar kurulumu, farklı ekran ölçekleri ve GPU sürümleri için ayrıca kabul testi gerekir. Yazılım çizimi için Mergen.exe --software kullanılabilir.

Kaynaklar:
- https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html
- https://docs.pytorch.org/docs/main/notes/get_start_xpu.html
- https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html


## 0.2.1 düzenlemeleri

Model süreçlerinin kaynakları exe içindeki runtime-source klasörüne ayrıldı. Python 3.12 süreçleri arayüzün Python 3.11 numpy/cv2/Pillow dosyalarını artık import etmez. Alt süreç başlatılırken frozen uygulamanın DLL arama yolu kaldırılıp sonra geri yüklenir. Uygulamaya özel MSVC DLL'leri model ortamına kopyalanır; sistem çalışma zamanı değiştirilmez.

Bileşenler ekranı canlı işlem aşamasını, günlüğü ve model testi sonuçlarını üstte gösterir. Önerilen kurulumdan sonra seçili modeller otomatik test edilir. Eksik modeller ayrı belirtilir; başarısız test başarı olarak gösterilmez. İşlem günlüğü logs/components.log altında saklanır.

Arayüzde sistem kullanımının görünürlüğü üç göstergeye bağlıdır. Bütün göstergeler kapalıysa kart kaldırılır ve pencere küçülebilir. Tema ve kullanım göstergeleri çeviriyi durdurmadan değiştirilebilir.

Görünüm düzeninde Apple'ın malzeme, hiyerarşi ve okunabilirlik yönergeleri esas alınmıştır; Windows sürümünde native Apple Liquid Glass kullanılmaz:
https://developer.apple.com/design/human-interface-guidelines/materials
https://developer.apple.com/design/human-interface-guidelines/accessibility

## 0.2.2 paddle cpu kurulumu

paddle'ın oneDNN bağımlılığı için gereken x64 vcomp140.dll kurulum paketine, uygulamaya özel python klasörüne ve model ortamının scripts klasörüne eklenir. sistem klasörlerine dosya yazılmaz. derleme için microsoft visual c++ x64 çalışma zamanının kurulu olması gerekir; dosya yoksa derleme durur. cpu ortamı hazır işaretlenmeden önce torch ve paddle ile gerçek tensör işlemi yapılır.


## 0.2.3 görünüm

referans görsele göre yuvarlak cam yüzeyleri, ton geçişleri ve ölçeklenen vektör simgeler kullanıldı. beş tema korundu; yeni kullanıcılar için lacivert seçildi. sistem kullanımı kullanıcı ayarlardan bir gösterge seçene kadar kapalıdır; açık tercihler kaydedilir. eski varsayılan gpu seçimini taşımamak için usage_preferences_set alanı kullanılır. başlat butonu kaydırılabilir bölümün dışında tutulur ve minimum pencere yüksekliği kontrol grubuna göre hesaplanır. sistem kullanım alanı gerekirse ayrıca kaydırılır. sayı seçicisi de temaya uyar; çoktan seçmeli alanlar mouse tekerleği ile değişmez.

130 birim testi, iş parçacığı kontrolü ve beş temanın qml görsel kontrolleri geçti. en küçük pencere boyutunda, göstergeler açık ve kapalıyken başlat butonu için görünürlük ve geometri kontrolü eklendi.


## 0.2.4 sade görünüm

ana ekranın iç içe çerçeveleri kaldırıldı. sekmeler ince bir çizgiyle seçilir; kontroller düz yüzeyler, küçük köşe yuvarlamaları ve kısa renk geçişleri kullanır. beş tema daha nötr renklerle güncellendi. yeni kurulumlarda beyaz tema açılır; mevcut tema tercihi korunur. ayarlar, bileşenler ve güncellemeler aynı kontrol bileşenlerini kullanır. çeviri akışı, cihaz seçimi, model kurulumları ve kısayollar değiştirilmedi. minimum boyut ve isteğe bağlı sistem kullanımı davranışı korundu.

130 test, arka plan iş kontrolü ve beş tema için görsel kontroller geçti.

