# 0.2.0 doğrulama kaydı

- yayımlanan paket için 130 otomatik test geçti; beş tema, açılır menüler ve minimum pencere boyutu kontrol edildi.
- paketlenmiş exe ile nllb cpu çevirisi, paddleocr ve manga-ocr gerçek model testleri geçti.
- arayüz sürecine torch, paddle, transformers veya ctranslate2 yüklenmedi.
- python 3.12 çalışanları, arayüzün python 3.11 uzantılarından ayrıdır. microsoft openmp bağımlılığı kurulum paketine eklenmiştir.
- sistem göstergeleri varsayılan olarak kapalıdır; başlat düğmesi minimum pencere boyutunda görünür kalır.
- amd/intel donanım testi ve canlı sürüm yükseltmesi ayrıca doğrulama gerektirir.

depo düzenlemesinde eski kolay kurulum dağıtımı kaldırılmıştır. uygulamanın çalışan kaynakları `v0.2.0` etiketiyle karşılaştırılır; readme, geliştirme bağımlılıkları ve kaynak dışa aktarma araçları exe dağıtımına göre güncellenir.
