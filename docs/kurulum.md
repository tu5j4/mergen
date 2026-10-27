# mergen 0.4.0 kurulumu

releases bölümündeki `mergen-setup-0.4.0.exe` dosyasını çalıştır. başlatıcı, bu sürüme sabitlenmiş yaklaşık 4,16 gb kurulum verisini github'dan indirir; her parçanın ve birleştirilen kurulumun sha256 özetini doğruladıktan sonra kurulumu açar. parçaları elle aynı klasöre koyman gerekmez. github dosya başına 2 gib sınırı nedeniyle büyük paket 400 mib boyutuna kadar `.data` parçaları olarak yayımlanır. ilk kurulum internet gerektirir.

kurulum standart 600m, bağlamlı 1.3b ve ocr modellerini içerir. modeller kayıpsız arşivlerinden özgün sha256 özetleriyle açılır. python 3.12 uygulamaya özel kurulur; sistem python'u veya ekran kartı sürücüsü değiştirilmez. modeller açıldığında yaklaşık 6,5 gb kaplar. indirme, birleştirme, model açma ve çalışma kütüphaneleri için ayrıca boş alan gerekir.

kurulumun sonundaki uygulamayı açma seçeneği donanımı tarar ve uygun çalışma kütüphanelerini kurar. gpu kurulumu veya gerçek model testi başarısız olursa cpu kullanılır. başlangıçta paddleocr cpu çalışır. bu işlem `modeller` ekranındaki `donanımı tara ve uygun kütüphaneleri kur` düğmesinden de başlatılabilir. hazır ortamlar yeniden indirilmez; eksik kütüphaneler onarılır.

varsayılan model standart 600m'dir. ayarlardan `nllb 1.3b · mergen bağlam v1` seçilebilir. uyarlama ingilizce–türkçe için eğitilmiştir; bağlam önceki en fazla üç kaynak repliği kullanır. kaynak dil çeviri açıkken değiştirilebilir. yeni dilin ocr motoru arka planda hazırlanırken çeviri bir süre bekleyebilir.

uygulamayı kaldırmak model ve ayarları silmez. kaynak zip'i programı kullanmak için gerekli değildir. indirilip doğrulanmış asıl kurulum `%localappdata%/mergen-next/downloads/0.4.0` altında tutulur; yeniden başlatmada yeniden indirilmez.
