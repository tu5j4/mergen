# 0.3.0 doğrulama kaydı

- 162 otomatik test geçti; kurulum yolları, ekran paylaşımı davranışı, bağlam prototipinin geri dönüşleri, imza doğrulama, yanlış anahtarın reddi ve özel veri içeren kaynakların dışa aktarılamaması sınandı.
- gerçek qml açılışı ve iş parçacığı tamamlanma kontrolleri geçti. dil seçimindeki büyük harf görünümü görünüm katmanında düzeltildi.
- python 3.12 ve pyinstaller ile temiz kaynak kopyasından arayüz exe’si; inno setup ile kullanıcı hesabına kurulan kolay kurulum exe’si üretildi. exe sürüm kaynağı 0.3.0’dır.
- üretilen kurulum exe’si sandboxie içinde kuruldu. kurulan exe’nin qml açılış testi ve pakete dahil özel python 3.12.15 x64 testi geçti. arayüz sürecinde torch, paddle, transformers veya ctranslate2 yüklenmedi.
- 3156 paket dosyası ve 16970 gömülü python kod nesnesi tarandı; yerel kullanıcı yolu veya özel anahtar/erişim anahtarı bulgusu çıkmadı. yayın kaynakları izin listesiyle dışa aktarıldı; ayarlar, modeller, günlükler, altyazılar ve yerel test çıktıları dışarıda tutuldu.
- kurulum exe’sinin sha256 özeti yeni ed25519 anahtarıyla imzalandı; manifest imzası ve uygulamadaki açık anahtar eşleşmesi doğrulandı. windows authenticode sertifikası kullanılmadı. önceki özel anahtar kaybolduğundan 0.2.0’dan geçiş elle kurulum gerektirir.
- 12 örneklik gerçek cpu deneyinde qwen 0.6b belirgin anlam kazanımı sağlamadı; bir geçmişli çıktıda eski replikler yeni çeviriye karıştı. prototip normal çeviri akışına eklenmedi. bu küçük deney genel kalite oranı değildir.
- fiziksel intel/amd/nvidia donanım testi, discord yayını ve kurulum exe’sinden tüm ocr/çeviri zinciri bu sürümün yerel doğrulama kapsamı dışındadır.
