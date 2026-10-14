# mergen 0.2.0 kurulumu

1. [kurulum exe dosyasını indir](https://github.com/tu5j4/mergen/releases/download/v0.2.0/mergen-setup-0.2.0.exe) ve çalıştır.
2. bileşen indirmeleri için uygulamaya özel python seçeneğini açık bırak. istersen masaüstü kısayolunu seç.
3. uygulamanın bileşenler bölümünde önerilen bileşenleri kur. indirme, kurulum ve model testi sonuçları aynı ekranda görünür.
4. dili ve ekran bölgesini seçip çeviriyi başlat.

windows 10 2004 veya üzeri / windows 11 x64, avx destekli işlemci, internet ve birkaç gb boş alan gerekir. exe arayüzü ve python 3.12 çalışma zamanını içerir; model kütüphaneleri ve ağırlıkları ayrıca indirilir.

## çalışma ortamları

| ortam | kullanım |
|---|---|
| cpu | ekran kartından bağımsız çeviri ve ocr |
| nvidia cuda | uygun kart ve sürücüyle çeviri, manga-ocr; paddleocr ayrı ortamda |
| amd rocm | desteklenen radeon kartlarında deneysel, windows 11 gerekir |
| intel xpu | desteklenen intel kartlarında deneysel, windows 11 gerekir |

uygunluk kontrolü tek başına yeterli değildir; çalışma ortamı ve seçili modeller gerçek işlemle doğrulanır. hata durumunda cpu seçeneği kullanılabilir. ekran kartı sürücüleri uygulama tarafından değiştirilmez.

## bileşenler ve veriler

model ve ortamları bileşenler bölümünden kurabilir, onarabilir veya kaldırabilirsin. ayarlardaki seçili ortamları doğrula düğmesi gerçek çeviri ve ocr testi yapar. gerekli modeller indirildikten sonra çeviri internet olmadan çalışır.

ayarlar, modeller ve günlükler uygulama dosyalarından ayrı tutulur. önceki geliştirme sürümlerindeki verileri korumak için veri klasörünün adı `%localappdata%/mergen-next` olarak bırakılmıştır; uygulamanın adı mergen'dir. uygulamayı kaldırmak bu verileri silmez; modelleri bileşenler ekranından kaldırabilirsin.

güncellemeler bölümünde github sürümleri kontrol edilir. kurulum kullanıcı onayıyla yapılır; indirilen paketin imzası ve dosya özeti doğrulanır.

uygulama kodu mit lisanslıdır; nllb modelleri ticari olmayan kullanım içindir. [üçüncü taraf lisansları](../THIRD_PARTY_NOTICES.md).
