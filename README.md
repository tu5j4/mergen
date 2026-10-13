# mergen

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="240">
</p>

mergen, ekrandaki manga, manhwa, webtoon ve çizgi roman metinlerini ocr ile okuyup türkçeye çeviren yerel bir windows uygulamasıdır. çevirileri, okuduğunuz içeriğin üzerinde tıklamaları engellemeyen bir katmanda gösterir. japonca, korece, çince ve ingilizce kaynakları destekler.

ocr için paddleocr, japonca içeriklerde isteğe bağlı olarak manga-ocr; çeviri için nllb-200 kullanılır. gerekli modeller indirildikten sonra çeviri yerel olarak çalışır. ilk kurulum ve eksik modellerin indirilmesi internet gerektirir.

## hızlı başlangıç

windows 10 (2004 veya sonrası) ya da windows 11 x64 ve avx destekli bir işlemci gerekir. kurulum python 3.11 x64 eksikse yüklemek için ayrıca izin ister. modeller birkaç gb alan ve indirme gerektirebilir.

1. son kullanıcı paketi olan [`kolay-kurulum`](kolay-kurulum) klasörünü tüm içeriğiyle bilgisayarınıza alın.
2. bu klasördeki `kurulum.bat` dosyasını çalıştırın; donanım kontrolünü inceleyip kurulacak bileşenleri onaylayın.
3. kurulum tamamlanınca aynı klasördeki `baslat.bat` dosyasıyla uygulamayı açın.
4. kaynak dili ve çevrilecek ekran bölgesini seçip `başlat` düğmesine basın.

sonradan model kurmak, onarmak veya kaldırmak için uygulamayı kapatıp `kolay-kurulum/bagliliklar.bat` dosyasını açabilirsiniz. bu paket docker kullanmaz; windows üzerinde yerel çalışır. klasörü taşırken içindeki `program` klasörü de birlikte taşınmalıdır.

depo kökündeki `kurulum.bat`, `baslat.bat` ve `bagliliklar.bat` dosyaları kaynak kod kopyasıyla çalışmak içindir. geliştirme ve test komutları aşağıdadır.

## kullanım

- `bölge seç` ile yalnızca okuyucu alanını işaretleyin veya tüm ekranı seçin.
- `başlat` / `durdur` ile otomatik taramayı yönetin. `şimdi çevir` geçerli görüntüyü yeniden tarar; `çeviriyi gizle` katmanı geçici olarak saklar.
- kaydırma durduğunda yeni görünen metin taranır. ayarlardan ocr, model, hız ve görünüm tercihlerini değiştirebilirsiniz.

kısayollar: `Ctrl+Alt+T` başlat/durdur, `Ctrl+Alt+R` bölge seç, `Ctrl+Alt+H` çeviriyi gizle/göster, `Ctrl+Alt+Y` şimdi çevir.

ocr ve otomatik balon algılama kusursuz değildir. küçük, eğik, çok kalın, düşük kontrastlı veya ekran kenarında kesilmiş yazılar atlanabilir; çeviri kalitesi de okunan metne bağlıdır. böyle bir durumda bölgeyi yeniden seçmek veya `şimdi çevir` ile tekrar taramak yardımcı olabilir.

## donanım ve modeller

| donanım | bu dağıtımdaki çalışma yolu |
| --- | --- |
| uyumlu nvidia gpu | kurulum doğrularsa paddleocr ve çeviri için cuda; manga-ocr için isteğe bağlı ayrı gpu ortamı |
| amd veya intel gpu | cpu yolu; bu dağıtım rocm veya directml içermez |
| desteklenmeyen ya da doğrulanamayan gpu | cpu yolu |

çeviri modeli olarak daha hafif **nllb 600m** veya daha büyük **nllb 1.3b** seçilebilir. vram kullanımı seçilen modellere ve görüntü boyutuna bağlıdır; her cihaz için sabit bir bellek gereksinimi garanti edilmez. gpu kullanılamadığında cpu yolu daha yavaş olabilir. japonca için manga-ocr cpu veya uygun nvidia gpu üzerinde çalıştırılabilir; diğer dillerde paddleocr kullanılır.

## kaynak kod ve lisans

kaynak kodu çalıştırmak veya geliştirmek için depo kökündeki `kurulum.bat` dosyasını kullanabilirsiniz. testler: `python -m unittest discover -s tests -v`.

uygulama kodu [mit lisanslıdır](LICENSE). ocr ve çeviri modellerinin kendi lisansları geçerlidir; nllb modelleri **cc-by-nc 4.0** lisansına tabidir. model ağırlıkları bu depoda bulunmaz, kurulum sırasında kullanıcının onayıyla indirilir. ayrıntılar için [üçüncü taraf bildirimlerine](THIRD_PARTY_NOTICES.md) bakın.
