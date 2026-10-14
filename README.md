# mergen-yerel ekran ile türkçe çeviri

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="240">
</p>

mergen, ekranın seçtiğin bölgesini sürekli izler. yazıları **gömülü ocr** ile okur, **yerel çeviri modeli** ile türkçeye çevirir ve çeviriyi konuşma balonunun üzerinde gösterir. çeviri katmanı tıklamalarını engellemez; okumaya ve sayfayı kaydırmaya devam edebilirsin.

japonca, korece, çince ve ingilizce desteklenir. gerekli modeller indirildikten sonra çeviri bilgisayarında çalışır, internet bağlantısı gerekmez.

## kurulum

1. [mergen 0.2.0 kurulumunu indir](https://github.com/tu5j4/mergen/releases/download/v0.2.0/mergen-setup-0.2.0.exe) ve exe dosyasını aç.
2. kurulumdan sonra uygulamadaki `bileşenler` bölümünden `önerilen bileşenleri kur` seçeneğine bas.

windows 10/11 x64 ve avx destekli bir işlemci gerekir. ilk kurulum için internet ve birkaç gb boş alan gerekir. gerekli python çalışma zamanı kurulum paketinde bulunur.

## kullanım

önce okuduğun içeriğin dilini seç. `bölge seç` düğmesiyle çevrilmesini istediğin alanı işaretle veya `tüm ekran` seçeneğini kullan. ardından `çeviriyi başlat` düğmesine bas.

bir yazı çevrilmediyse `şimdi çevir` düğmesiyle tekrar deneyebilirsin. yazı görünümü, çeviri modeli ve diğer seçenekler çark simgesiyle açılan ayarlarda bulunur.

`ctrl+alt+t` ile çeviriyi başlatıp durdurabilir, `ctrl+alt+h` ile gizleyip gösterebilirsin. küçük, eğik veya kesik yazılar bazen atlanabilir; çeviri kalitesi okunan metne bağlıdır.

## sistem kullanımı

gpu, vram ve cpu göstergelerini ayarlardan ayrı ayrı açıp kapatabilirsin. her göstergede ad ve yüzde üstte, ince bir kullanım çubuğu altta görünür. tercihler kaydedilir; tüm göstergeler kapalıysa ölçüm durur. ölçüm alınamadığında sıfır yerine `kullanılamıyor` yazılır.

nvidia üzerinden ölçüm alınamazsa windows'un wddm/pdh sayaçları kullanılır. gpu yüzdesi, seçilen nvidia kartının en yoğun çalışan motorunu gösterir. vram yüzdesi, kullanılan ayrılmış belleğin dxgi ile alınan toplam kapasiteye oranıdır. cpu göstergesi bilgisayarın genel işlemci kullanımını gösterir.

## lisans

uygulama kodu mit lisanslıdır. nllb çeviri modelleri cc-by-nc 4.0 kapsamındadır ve ticari olmayan kullanım içindir.
