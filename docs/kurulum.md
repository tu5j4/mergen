# mergen 0.5.2 kurulumu

releases bölümündeki `mergen-setup-0.5.2.exe` dosyasını çalıştır. uygulama kurulumu ile model verileri ayrı dağıtılır: uygulama sürümü değiştiğinde büyük modeller yeniden paketlenmez. ilk model hazırlığında gereken sabit arşivler merkezi model yayınından indirilir; indirme boyutları ve sha256 özetleri doğrulanır, açılan dosyalar da özgün özetleriyle kontrol edilir.

standart 600m, bağlamlı 1.3b ve ocr modelleri hazırlandığında yaklaşık 6,5 gb kaplar. indirme önbelleği, arşiv açma ve çalışma kütüphaneleri için ayrıca boş alan gerekir. ilk hazırlık internet gerektirir. mevcut model dosyalarının boyutları ve özetleri beklenen değerlerle eşleşiyorsa sonraki uygulama kurulumlarında yeniden indirilmez veya değiştirilmez. model sürümü uygulama sürümünden bağımsızdır; değişken hub `main` ağırlıkları kullanılmaz.

python 3.12 uygulamaya özel kurulur; sistem python'u veya ekran kartı sürücüsü değiştirilmez. kurulumun sonundaki uygulamayı açma seçeneği donanımı tarar ve uygun çalışma kütüphanelerini kurar. gpu kurulumu veya gerçek model testi başarısız olursa cpu kullanılır. bu işlem `modeller` ekranındaki `donanımı tara ve uygun kütüphaneleri kur` düğmesinden de başlatılabilir. hazır çalışma ortamları yeniden indirilmez; eksik kütüphaneler onarılır.

varsayılan çeviri modeli standart 600m'dir. ayarlardan `nllb 1.3b · mergen bağlam v1` seçilebilir. uyarlama ingilizce–türkçe için eğitilmiştir; bağlam önceki en fazla üç kaynak repliği kullanır. kaynak dil çeviri açıkken değiştirilebilir. yeni dilin ocr motoru hazırlanırken çeviri bir süre bekleyebilir.

uygulamayı kaldırmak modelleri ve ayarları silmez. kurulu uygulamanın verileri `%localappdata%/mergen-next` altında tutulur. kaynak zip'i programı kullanmak için gerekli değildir.

## kaynak zip veya github checkout kurulumu

`kurulum.bat` dosyasını çalıştır, tamamlandığında `baslat.bat` ile aç. kaynak arayüzü kendi `.venv` ortamını, model ve çalışma verileri proje içindeki `.data` klasörünü kullanır.

kaynak kurulumu önce `.data` içindeki modellerin boyut ve sha256 özetlerini denetler. eksik dosyalar varsa kurulu uygulamadaki doğrulanmış kopyalardan yararlanabilir; kalan eksikler uygulama kurulumundan bağımsız sabit model yayınından sağlanır. doğru modeller varsa büyük ağırlıklar yeniden indirilmez. kaynak ve kurulu uygulamanın ayrı veri klasörlerinde bulunan model kopyaları ayrı yer kaplar.

model adresleri, arşiv boyutları ve sha256 özetleri `assets/packed-models.json` içinde sabittir; açılan dosyalar `assets/bundled-models.json` ile doğrulanır. bağlamlı modelin taban ağırlığı ve uyarlaması mevcut `nllb-mergen-baglam-v1` model yayınının aynı dosyalarını kullanır. diğer sabit model arşivleri ve destek dosyaları ortak model yayınından gelir. her uygulama sürümü için aynı büyük nllb dosyaları tekrar yayımlanmaz.

sonrasında **modeller** sayfasından cpu veya ekran kartına uygun çalışma kütüphanelerini kur. kaynak kurulum günlüğü `.data/logs/source-setup.log` dosyasındadır. `powershell -File installer/setup_source.ps1 -Plan` yalnız yapılacak işleri gösterir; indirme veya klasör oluşturma yapmaz.
