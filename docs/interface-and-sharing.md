# Arayüz ve ekran paylaşımı

Ana QML ekranı sol gezinme menüsü, açık/koyu görünüm seçimi ve tek sütunlu
çeviri kontrolleri kullanır. Çeviri önizlemesi eklenmedi. Beş mevcut tema ve
controller sayfa indeksleri korundu. Ana eylem minimum pencere boyutunda görünür.

Ana pencereye artık ekran yakalama engeli uygulanmaz. Yeni `share_translations`
ayarı varsayılan olarak açıktır; mevcut ayar dosyalarında alan yoksa da açılır.
Ayarlar / Okuma altından değiştirilebilir. Çeviri çalışırken değiştirmek için
önce çeviriyi durdurmak gerekir.

Ayar açıkken çeviri katmanına Windows'ta WDA_NONE uygulanır. OCR'nin kendi
Türkçe sonucunu tekrar okumasını önlemek için katman yalnızca uygulamanın ekran
yakalama işlemi sırasında gizlenir. Gizleme onayı gelmezse görüntü okunmaz;
başarısız yakalamalarda da görünürlük geri yüklenir. Bu yol en az 400 ms tarama
aralığı kullanır ve yayında kısa gizleme/titreme görülebilir. Ayar kapalıyken
eski yakalamadan hariç tutma yolu kullanılır; başarılıysa gizleme gerekmez.

Tüm ekran paylaşımı hedeflenir. Yalnızca tarayıcı penceresi paylaşılırsa ayrı
bir pencere olan çeviri katmanının yayına dahil edilmesi paylaşım uygulamasına
bağlıdır. Discord üzerinde gerçek yayın kabul testi henüz yapılmadı.

Microsoft API açıklaması:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity

## Doğrulama

- `python scripts/preview_design.py --check`: gerçek QML, örnek controller ile
  beş tema / dört sayfa ve göstergeler açık/kapalı minimum boyut kontrolü geçti.
  Çıktılar üst klasördeki `tasarimlar/temalar/` altında. Bu mod modelleri başlatmaz, ağ kullanmaz,
  gerçek ayarları yüklemez/kaydetmez. `--check` olmadan tasarım penceresi açılır.
- `tests/test_screen_sharing.py`: 7 test geçti. Bu bilgisayarda OpenCV eksik
  olduğu için yerel test çalıştırıcısında yalnızca cv2 importu mock edildi;
  gerçek görüntü yakalama veya OCR yapılmadı. Katman, görünürlük onayı, zaman
  aşımı ve hata sonrası geri yükleme davranışı test edildi.
- Değişen Python dosyalarının sözdizimi kontrol edildi.
- Tam test kümesi, gerçek OCR/çeviri ve Discord yayını eksik bağımlılıklar
  nedeniyle çalıştırılmadı. Bağımlılık indirme girişimi ağ kısıtlamasına takıldı.
- bu kayıt arayüz geliştirme aşamasındaki kontrolleri anlatır. güncel 0.3.0 paket doğrulaması için `verification.md` dosyasına bak.
