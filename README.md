# mergen-yerel ekran ile türkçe çeviri

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="240">
</p>

mergen, ekranın seçtiğin bölgesini sürekli izler. yazıları **gömülü ocr** ile okur, **yerel çeviri modeli** ile türkçeye çevirir ve çeviriyi konuşma balonunun üzerinde gösterir. çeviri katmanı tıklamalarını engellemez; okumaya ve sayfayı kaydırmaya devam edebilirsin.

japonca, korece, çince ve ingilizce desteklenir. gerekli modeller indirildikten sonra çeviri bilgisayarında çalışır, internet bağlantısı gerekmez.

## kurulum

1. [kurulum paketini indir](https://github.com/tu5j4/mergen/raw/refs/heads/main/mergen-kolay-kurulum.zip) ve zip dosyasını bir klasöre çıkar.
2. `kolay-kurulum` klasöründeki `kurulum.bat` dosyasını aç. kurmak istediğin bileşenleri seçip onayla.
3. kurulum tamamlandıktan sonra aynı klasördeki `baslat.bat` dosyasını aç.

windows 10/11 x64 ve avx destekli bir işlemci gerekir. ilk kurulum için internet bağlantısı ve birkaç gb boş alan gerekir. python 3.11 bilgisayarında yoksa kurulum sırasında yükleyebilirsin.

## kullanım

önce okuduğun içeriğin dilini seç. `bölge seç` düğmesiyle çevrilmesini istediğin alanı işaretle veya `tüm ekran` seçeneğini kullan. ardından `başlat` düğmesine bas.

bir yazı çevrilmediyse `şimdi çevir` düğmesiyle tekrar deneyebilirsin. yazı görünümü, çeviri modeli ve diğer seçenekler çark simgesiyle açılan ayarlarda bulunur.

`ctrl+alt+t` ile çeviriyi başlatıp durdurabilir, `ctrl+alt+h` ile gizleyip gösterebilirsin. küçük, eğik veya kesik yazılar bazen atlanabilir; çeviri kalitesi okunan metne bağlıdır.

## sistem kullanımı

gpu, vram ve cpu göstergelerini ayarlardan ayrı ayrı açıp kapatabilirsin. her göstergede ad ve yüzde üstte, ince bir kullanım çubuğu altta görünür. tercihler kaydedilir; tüm göstergeler kapalıysa ölçüm durur. ölçüm alınamadığında sıfır yerine `kullanılamıyor` yazılır.

nvidia üzerinden ölçüm alınamazsa windows'un wddm/pdh sayaçları kullanılır. gpu yüzdesi, seçilen nvidia kartının en yoğun çalışan motorunu gösterir. vram yüzdesi, kullanılan ayrılmış belleğin dxgi ile alınan toplam kapasiteye oranıdır. cpu göstergesi bilgisayarın genel işlemci kullanımını gösterir.

## lisans

uygulama kodu mit lisanslıdır. nllb çeviri modelleri cc-by-nc 4.0 kapsamındadır ve ticari olmayan kullanım içindir.
