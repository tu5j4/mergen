# 0.3.0 doğrulama kaydı

- 162 otomatik test geçti; kurulum yolları, ekran paylaşımı davranışı, bağlam prototipinin geri dönüşleri, imza doğrulama, yanlış anahtarın reddi ve özel veri içeren kaynakların dışa aktarılamaması sınandı.
- gerçek qml açılışı ve iş parçacığı tamamlanma kontrolleri geçti. dil seçimindeki büyük harf görünümü görünüm katmanında düzeltildi.
- python 3.12 ve pyinstaller ile temiz kaynak kopyasından arayüz exe’si; inno setup ile kullanıcı hesabına kurulan kolay kurulum exe’si üretildi. exe sürüm kaynağı 0.3.0’dır.
- üretilen kurulum exe’si sandboxie içinde kuruldu. kurulan exe’nin qml açılış testi ve pakete dahil özel python 3.12.15 x64 testi geçti. arayüz sürecinde torch, paddle, transformers veya ctranslate2 yüklenmedi.
- 3156 paket dosyası ve 16970 gömülü python kod nesnesi tarandı; yerel kullanıcı yolu veya özel anahtar/erişim anahtarı bulgusu çıkmadı. yayın kaynakları izin listesiyle dışa aktarıldı; ayarlar, modeller, günlükler, altyazılar ve yerel test çıktıları dışarıda tutuldu.
- kurulum exe’sinin sha256 özeti yeni ed25519 anahtarıyla imzalandı; manifest imzası ve uygulamadaki açık anahtar eşleşmesi doğrulandı. windows authenticode sertifikası kullanılmadı. önceki özel anahtar kaybolduğundan 0.2.0’dan geçiş elle kurulum gerektirir.
- 12 örneklik gerçek cpu deneyinde qwen 0.6b belirgin anlam kazanımı sağlamadı; bir geçmişli çıktıda eski replikler yeni çeviriye karıştı. prototip normal çeviri akışına eklenmedi. bu küçük deney genel kalite oranı değildir.
- fiziksel intel/amd/nvidia donanım testi, discord yayını ve kurulum exe’sinden tüm ocr/çeviri zinciri bu sürümün yerel doğrulama kapsamı dışındadır.

## 0.3.1 yerel düzeltme paketi

- 171 otomatik test, qml açılışı ve model testi sayfa yönlendirmesi kontrolü geçti.
- kurulum sırasında vazgeçme ve pencereyi kapatma akışı eklendi. sessiz bir alt süreç ve onun açtığı süreçle gerçek iptal denemesi geçti; iptal edilen işin başarı eylemi çalışmadı. model başlangıcındaki bekleme ve önerilen bileşenler zinciri de iptale yanıt verir.
- uygulamadaki güncellemeler sayfasına ve başlat menüsüne kaldırıcı erişimi eklendi. kaldırıcı modelleri ve ayarları silmez.
- güncel paket sandboxie içinde kuruldu; paketlenmiş qml açılışı ve gerçek kaldırma testi geçti. uygulama dosyaları kaldırıldı; test model ve ayar dosyaları korundu. 3158 paket dosyası ve 16985 gömülü kod nesnesi taramasında kişisel dosya, kullanıcı yolu veya özel anahtar bulgusu çıkmadı.
- kurulu 0.3.0 uygulamanın eski kaydında cpu ocr başlangıcı zaman aşımına düşmüştü. hata yeniden üretilemedi: aynı paketle tekrarda nvidia çevirisi ve cpu ocr geçti. ilk hatanın kesin nedeni belirlenmiş sayılmıyor.
- model testinin yanlışlıkla ayarlar sayfasına geçmesi düzeltildi. model yükleme aşamaları gösteriliyor; başlangıç bekleme süresi istek süresinden ayrıldı ve başlangıç için beş dakika sınır kondu. tanı mesajları uygulamanın yerel günlüklerine yazılıyor.
- tamamlanmayan model indirmeleri bileşene özel geçici klasörde korunur ve sonraki denemede aynı klasör kullanılır. model doğrulanmadan hazır işaretlenmez. indirme, diske kurulum ve nllb dönüştürmesi ayrı aşamalar olarak gösterilir.
- ayrı gerçek indirme denemesinde yaklaşık 29 mb ocr dosyası 7,6 saniyede indirildi. önceki günlükte nllb kaynak dosyaları yaklaşık 72 saniyede alınmış; cpu paketlerinde yaklaşık 23–25 mb/sn, büyük nvidia paketinde 17 mb/sn indirme hızı kaydedilmiş. bunlar belirli bağlantıdaki ölçümlerdir; sunucunun her zaman aynı hızda çalıştığı anlamına gelmez.
- 0.3.1 kurulum paketi derlendi, güncelleme imzası doğrulandı ve bu bilgisayardaki uygulamaya kuruldu. kurulum sırasında ayar dosyası değişmedi. kurulu exe üzerinden nvidia çevirisi “merhaba, nasılsın?” ve cpu ocr “hello world” testleri geçti; mevcut modeller yeniden indirilmedi.
- bu paket yerel test paketidir; github release’i bu işlemde güncellenmedi. kişisel günlükler, test dosyaları ve model ağırlıkları kaynak dışa aktarımında bulunmaz.
