# mergen kurulumu

## ilk kurulum

dağıtımda `kolay-kurulum` kullanıcı paketi, yanındaki `github` temiz kaynak kod
kopyasıdır. geliştirme sürümünün ortam ve ayarlarından bağımsızdır. aşağıdaki
adımları `kolay-kurulum` klasöründe uygulayın; github'dan indirdiyseniz depo
klasörünün kendisinde aynı dosyalar bulunur.

1. klasörü yazma izniniz olan kalıcı bir konuma çıkarın. `program files` kullanmayın.
2. `kurulum.bat` dosyasını açın. python 3.11 x64 yoksa kurulması için izin istenir.
3. donanım taramasını inceleyin; cpu veya uygun nvidia gpu altyapısını seçin.
4. korece modeli, japonca manga-ocr ve çeviri modelini seçin. emin değilseniz standart 600m ile başlayın.
5. gösterilen tüm bağımlılık planını onaylayın. vc++ çalışma zamanı eksikse ayrıca izin istenir.
6. sağlık kontrolü geçtikten sonra `baslat.bat` dosyasını açın.

ilk kurulum ve seçilen modellerin indirilmesi internet gerektirir; bu işlem bağlantıya göre uzun sürebilir. hazır modellerle çeviri yerel çalışır. atlanan dil/model daha sonra ilk kullanımda indirme gerektirebilir. çeviri modeli atlandıysa uygulama henüz çeviri yapamaz.

## uyumluluk

| donanım | bu dağıtımın yolu |
|---|---|
| nvidia, doğrulanan sürücü ve cuda yeteneği | paddle cuda; isteğe bağlı izole manga-ocr cuda |
| amd / intel | cpu; bu dağıtım rocm/directml içermez |
| bilinmeyen veya doğrulanamayan gpu | cpu |

windows 10 2004 veya üzeri / windows 11 x64, avx destekli işlemci ve python 3.11 x64 gerekir. kurulum gerekli boş alanı denetler. amd/intel cpu yolu daha yavaş olabilir.

nvidia ön kontrolü cuda cihazı 0 için sürücü 576.02 veya üzerini ve 7.5–12.0 cuda işlem yeteneğini kabul eder. bu muhafazakâr paket profilidir; her nvidia kartın desteklendiği anlamına gelmez. sürücü kurulumunu/değiştirmeyi otomatik yapmaz. ön kontrol tek başına yeterli değildir: kurulan altyapı gerçek tensör işlemiyle, çeviri örnek cümleyle doğrulanır. hata olursa `bagliliklar.bat` üzerinden cpu seçilebilir. bellek yetersizse 600m ve/veya cpu manga-ocr kullanın; minimum vram garantisi verilmez.

kaynaklar: [paddle windows kurulumu](https://www.paddlepaddle.org.cn/documentation/docs/install/pip/windows-pip_en.html), [cuda 12.9 sürücü gereksinimleri](https://docs.nvidia.com/cuda/archive/12.9.0/cuda-toolkit-release-notes/index.html), [ctranslate2 donanım desteği](https://opennmt.net/CTranslate2/hardware_support.html).

## sonradan kurma, onarma ve kaldırma

uygulamayı kapatıp `bagliliklar.bat` dosyasını açın:

- `1`: paket ve model dosyalarını tara; `mevcut` çalışabilirlik garantisi değildir.
- `2`: numaralarını seçtiğiniz bileşenleri kur/onar. gereken alt bağımlılıklar onaydan önce gösterilir.
- `3`: seçilen bileşenleri onayla ve kaldır. dosyalar kalıcı silinir; tekrar indirilebilir.
- `4`: paket tutarlılığı ve çalışma testleri.

paddle cpu ve gpu aynı anda kurulmaz; birini seçmek diğerinin yerini alır. manga-ocr gpu ayrı `.manga-venv` ortamındadır. ortak alt paketler kaldırma sırasında başka özellikleri bozmamak için tutulur. temel ortamı kaldırmak uygulamanın çalışmasını durdurur; kaynak kod ve ayarlar korunur.

yeni kurulumlar model önbelleğini bu klasördeki `.cache` altında tutar. başka uygulamaların önbelleği, sistem python'u ve ekran kartı sürücüsü silinmez. eski geliştirme kopyasındaki ortak önbelleğin kaldırılması reddedilir. uygulamayı veya iki kurulum penceresini aynı anda çalıştırmayın.

başarısız kurulumda tamamlanan bileşenler korunur. aynı bileşeni yeniden kurarak onarın; hata mesajını saklayın. tüm klasörü taşırsanız sanal ortamları yeni konumda yeniden kurun.

## github ve lisanslar

test otomasyonu için açık onaylı kurulum örneği:
`kurulum.bat -Components paddle-cpu,korean,manga-cpu,600m -AcceptInstall`.
bu seçenek listelenen bileşenleri, gerekli alt bağımlılıkları ve eksikse python /
vc++ önkoşullarını onaylar. normal kullanımda yalnızca çift tıklayın;
`-AcceptInstall` verilmedikçe sorular atlanmaz. otomatik kurulum sırasında uygulama kapalı olmalıdır.

`github` klasörünün **içeriğini** deponuza yükleyin. ortamları, `.cache`, `models`, `settings.json` ve günlükleri eklemeyin; `.gitignore` bunları hariç tutar. ilk dağıtım model ağırlığı içermez.

uygulama kodu MIT lisanslıdır. nllb modelleri ayrıca **cc-by-nc-4.0** lisanslıdır; MIT seçimi bu kısıtlamayı kaldırmaz. diğer bileşenler için [üçüncü taraf bildirimleri](../THIRD_PARTY_NOTICES.md) geçerlidir.
