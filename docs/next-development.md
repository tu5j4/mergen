# mimari

qml arayüz ve ekran katmanı pyside6 ile çalışır. paddleocr, manga-ocr ve nllb ayrı python 3.12 ortamlarında json satır protokolüyle çağrılır. arayüz açılışında model kütüphaneleri yüklenmez.

cpu/nvidia çevirisi ctranslate2, amd/intel çevirisi transformers kullanır. intel için yerel pytorch xpu paketleri seçilir. cihaz desteği ve gerçek tensör işlemleri doğrulanmadan ortam hazır işaretlenmez; amd ve intel fiziksel donanım testleri bu sürümün yerel doğrulama kapsamı dışındadır.

kaynak çalıştırmada veriler `.data`, kurulu uygulamada `%LOCALAPPDATA%/mergen-next` altında tutulur. alt süreçlerin kaynakları `runtime-source` ile arayüzün ikili kütüphanelerinden ayrılır.

kurulum ve derleme için [derleme belgesine](derleme.md), sürümde yapılan kontroller için [doğrulama kaydına](verification.md) bak.

qwen bağlam yardımcısı deneysel kaynak olarak bulunur; uygulamanın normal çeviri akışında çalışmaz. ana çeviri motoru nllb olarak kalır.
