# 0.2.1 doğrulama kaydı

- 127 otomatik test geçti.
- iş parçacığı tamamlanması, reddedilen kurulum, kullanım göstergeleri ve başarısız doğrulamanın yanlışlıkla başarı sayılmaması kontrol edildi.
- beş tema, dört sekme ve beş açılır menü görünümü qml üzerinde kontrol edildi. bütün kullanım göstergeleri kapalıyken kartın kaybolduğu ve pencerenin küçülebildiği doğrulandı.
- paketlenmiş 0.2.1 exe üzerinden python 3.12 alt süreçleriyle üç gerçek cpu model testi geçti: nllb japoncadan türkçeye çevirdi, paddleocr "hello world" metnini okudu, manga-ocr "こんにちは" sonucunu verdi.
- arayüz sürecinde torch, paddle, transformers veya ctranslate2 yüklenmedi.
- model süreçlerinin kaynak klasörü arayüzün python 3.11 uzantılarından ayrıldı. paketlenmiş exe testinde önce görülen python311.dll sürüm çakışması giderildi.
- kurulum paketi inno setup ile derlenir. amd/intel donanım testi ve canlı github sürüm yükseltmesi bu değişiklikte yapılmadı.
- yeni kurulum paketi kullanıcının kontrol etmesi için windows sandbox içinde açılır; model kütüphaneleri ve ağırlıkları uygulamanın bileşenler ekranından indirilir.
