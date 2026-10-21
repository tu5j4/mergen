# mergen kurulumu

## kurulum exe’si

ana readme’deki güncel kurulum exe’sini çalıştır. uygulama kullanıcı hesabına kurulur; yönetici yetkisi ve sistem python kurulumu gerekmez. uygulamaya özel python 3.12 seçeneği bileşen indirmeleri için açık bırakılmalıdır.

uygulamayı açıp `modeller` sayfasından cihaz ortamını, ocr ve çeviri modelini seç. ilk indirme internet bağlantısı ve birkaç gb boş alan gerektirir. modeller hazır olduğunda çeviri yerel çalışır. intel, amd ve nvidia seçenekleri cihaz uyumluluğuna göre değişir.

0.2.0’dan 0.3.0’a geçişte güncelleme anahtarı yenilendiğinden kurulum exe’sini elle çalıştır. eski sürümün imza kontrolü atlanmaz.

## kaynak koddan

1. `kurulum.bat` uygulamaya özel python’u `.data/python`, arayüz ortamını `.venv` altında kurar.
2. `baslat.bat` arayüzü açar.
3. modeller ve cihaz kütüphaneleri uygulamadan indirilir.

kurulum günlüğü `.data/logs/source-setup.log` dosyasındadır. `kurulum.bat -Plan` yalnız kurulacak yolları gösterir. sistem python’u, path ve ekran kartı sürücüleri değiştirilmez.

kaynak sürümde veriler `.data`, kurulu uygulamada `%LOCALAPPDATA%/mergen-next` altında tutulur. exe güncellemesi ayar ve modelleri dağıtım paketinden kopyalamaz. uygulamayı kaldırmak modelleri silmez; modelleri uygulamadaki bileşen yönetiminden kaldırabilirsin.
