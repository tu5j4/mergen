# mergen · ekranı türkçeye çevir

<p align="center">
  <img src="assets/mergen-logo.png" alt="mergen logosu" width="160">
</p>

mergen; manga, çizgi roman ve ekrandaki yazıları okuyup türkçe çeviriyi metnin üzerinde gösterir. japonca, korece, çince ve ingilizce desteklenir. modeller indirildikten sonra çeviri yerel çalışır.

## kolay kurulum

[mergen 0.3.0 kurulum exe’sini indir](https://github.com/tu5j4/mergen/releases/download/v0.3.0/mergen-setup-0.3.0.exe), kur ve uygulamayı aç. gerekli ocr, çeviri modelleri ve cihaz kütüphaneleri uygulamanın **modeller** sayfasından indirilir; ayrı bir bağımlılık exe’si gerekmez.

windows 10/11 x64, avx destekli işlemci ve modeller için birkaç gb boş alan gerekir. cpu, nvidia, intel ve amd seçeneklerinin kullanılabilirliği donanıma bağlıdır.

0.2.0’dan geçerken yeni güncelleme anahtarı nedeniyle kurulum exe’sini bir kez elle çalıştır.

## kullanım

kaynak dili seç → **bölge seç** veya **tüm ekran** → **çeviriyi başlat**. `ctrl+alt+t` başlatır/durdurur; `ctrl+alt+h` çeviriyi gizler/gösterir. ekran paylaşımında çevirilerin görünmesini ayarlardan seçebilirsin.

## 0.3.0’da

- yenilenen sade arayüz, küçük harfli metinler ve yeni logo.
- ekran paylaşımı görünürlüğü ve uygulamanın kendi görüntüsünü yakalamaması için düzenlemeler.
- intel tarafında yerel pytorch xpu desteği; sadeleştirilen başlatma ve uygulamaya özel python kurulumu.

kaynak koddan çalıştırmak için `kurulum.bat`, ardından `baslat.bat`. kurulum sistem python’unu ve sürücüleri değiştirmez. geliştirme ve derleme bilgileri [docs/derleme.md](docs/derleme.md) içindedir.

uygulama kodu mit lisanslıdır. nllb modelleri cc-by-nc 4.0 lisansıyla ticari olmayan kullanım içindir; diğer bileşenler için [lisans bildirimlerine](THIRD_PARTY_NOTICES.md) bak.
