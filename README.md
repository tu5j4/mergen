# mergen · hikâyenin diline takılma

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="180">
</p>

mergen; **manga, manhwa, manhua, webtoon ve çizgi romanları türkçe okumayı kolaylaştırmak** için geliştirilen bir masaüstü uygulamasıdır. ekrandaki konuşma balonlarını ve yazıları okur, türkçeye çevirir ve çeviriyi metnin üzerinde gösterir.

okuduğun siteyi veya görüntüleyiciyi değiştirmeden, sayfaları tek tek dışa aktarmadan okumaya devam edebilirsin. çeviri katmanı tıklamalarını engellemez; sayfayı kaydırırken çeviri alanı takip edilir. gerekli modeller indirildikten sonra metin tanıma ve çeviri bilgisayarında çalışır.

## neler sunar?

- japonca manga, korece manhwa ve webtoon, çince manhua ve ingilizce çizgi romanlar için türkçe çeviri.
- seçili bölge veya tüm ekran üzerinden okuma; konuşma balonlarını ve metin gruplarını dikkate alan işleme.
- japonca dikey metinler için okuma düzeni ve manga-ocr desteği.
- çeviri katmanının yazı tipi, boyutu, teması ve saydamlığını ayarlama; ekran paylaşımında görünürlüğünü seçme.
- cihazına göre cpu veya desteklenen ekran kartı ortamını seçme; modelleri uygulama içinden kurma ve kaldırma.

## kullandığımız modeller

mergen iki aşamada çalışır: **önce görseldeki yazıyı okur, ardından okunan metni türkçeye çevirir.** metin tanıma ve çeviri için farklı modeller kullanılır.

| görev | model | uygulamadaki yeri |
|---|---|---|
| türkçe çeviri | [nllb-200 distilled 600m](https://huggingface.co/facebook/nllb-200-distilled-600M) | varsayılan çeviri seçeneği; daha düşük bellek tüketimi için başlangıç modeli. |
| türkçe çeviri | [nllb-200 distilled 1.3b](https://huggingface.co/facebook/nllb-200-distilled-1.3B) | daha büyük çeviri modeli; 600m seçeneğinden daha fazla bellek kullanır. |
| japonca metin tanıma | [manga-ocr-base](https://huggingface.co/kha-white/manga-ocr-base) | japonca manga yazılarını okumak için kullanılan, isteğe bağlı manga-ocr modeli. |
| metin tespiti ve tanıma | [paddleocr · pp-ocrv5 mobil](https://github.com/PaddlePaddle/PaddleOCR) | `pp-ocrv5_mobile_det` ve `pp-ocrv5_mobile_rec`; metnin yerini bulma ve yazıyı okuma. `pp-lcnet_x1_0_textline_ori` satır yönünü belirlemeye yardımcı olur. |
| korece metin tanıma | `korean_pp-ocrv5_mobile_rec` | korece manhwa ve webtoon metinleri için tanıma modeli. |

cpu ve nvidia çevirisinde ctranslate2, amd ve intel çevirisinde transformers/pytorch kullanılır. intel tarafında yerel pytorch xpu yolu bulunur. bunlar modelleri çalıştıran altyapılardır; çeviri modellerimiz nllb’dir. amd ve intel seçenekleri deneyseldir ve desteklenen donanım/sürücü gerektirir.

## kurulum ve kullanım

1. [güncel kurulum paketini releases bölümünden indir](https://github.com/tu5j4/mergen/releases/latest) ve uygulamayı kur.
2. **modeller** sayfasından cihaz ortamını, kullanacağın dillerin metin tanıma modellerini ve nllb çeviri modelini indir. ayrı bir bağımlılık exe’si gerekmez.
3. kaynak dili seç; **bölge seç** ile okuma alanını işaretle veya **tüm ekran** seçeneğini kullan.
4. **çeviriyi başlat** düğmesine bas ve okumaya devam et. gerekirse **şimdi çevir** ile yeniden dene.

`ctrl+alt+t` çeviriyi başlatır/durdurur; `ctrl+alt+h` çeviri katmanını gizler/gösterir.

windows 10/11 x64, avx destekli işlemci ve modeller için birkaç gb boş alan gerekir. ilk kurulum ve model indirmeleri internet bağlantısı gerektirir. hız ve bellek kullanımı seçilen model ve donanıma; çeviri sonucu da metnin doğru okunmasına bağlıdır. küçük, stilize veya düşük çözünürlüklü yazılarda sonuçlar değişebilir.

## kaynak kod ve lisans

kaynak koddan çalıştırmak için `kurulum.bat`, ardından `baslat.bat` dosyasını kullan. uygulama kendi python ortamını oluşturur; sistem python’unu ve ekran kartı sürücülerini değiştirmez. ayrıntılar: [kurulum](docs/kurulum.md) · [derleme](docs/derleme.md).

uygulama kodu mit lisanslıdır. nllb modelleri cc-by-nc 4.0 lisansıyla ticari olmayan kullanım içindir. diğer modeller ve kütüphaneler için [üçüncü taraf bildirimlerine](THIRD_PARTY_NOTICES.md) bakabilirsin.
