# qwen 0.6b bağlam deneyi

bu prototip ana uygulamanın otomatik çevirisini değiştirmez. gerçek nllb 600m
cpu çevirisini qwen3-0.6b q8 önerileriyle karşılaştırır. amaç türkçe anlam
kalitesini, gecikmeyi ve bellek maliyetini görerek sonraki entegrasyona karar vermektir.

## çalışma şekli

- llama.cpp cpu sunucusu yalnız 127.0.0.1 üzerinde rastgele port ve oturuma özel
  anahtarla açılır. diyaloğu buluta göndermez. model kurulumu internet kullanır.
- qwen düşünme modu kapalı, bağlam penceresi 2048 token, çıktı sınırı 256 tokendır.
- yakın geçmiş en fazla altı replik ve sınırlı metin bütçesi içerir.
- her örnekte nllb, geçmişsiz qwen ve geçmişli qwen çıktısı ayrı tutulur.
- önceki türkçe metinler nllb çıktılarıdır. insan referansları modele gönderilmez.
- çıktı öneridir; biçim doğrulaması anlam doğruluğunu kanıtlamaz.
- eksik model, zaman aşımı veya hatalı çıktıda nllb taslağı döner ve durum
  `fallback` olarak raporlanır; hata başarı gibi gösterilmez.
- bu aşamada otomatik seri özeti, kalıcı seri hafızası veya ana ekranda bağlam
  açma düğmesi eklenmedi. bunlar karşılaştırma sonucundan sonraki entegrasyondur.

## sandbox

`scripts/prepare_sandbox_context.py` yerel inceleme veritabanından 11–12.
bölümlere ait 12 örnek seçer ve yeni bir test klasörü oluşturur. kaynakların
izinli dosya listesiyle anlık kopyası salt okunur paylaşılır. ayrı sonuç klasörü
yazılabilir. mikrofon, kamera, pano ve sanal gpu kapalı; ağ açık; bellek 8 gb.

üretilen `baslat.wsb` açılınca sandbox içinde taşınabilir python, arayüz ve
ayrı cpu karşılaştırma ortamı kurulur. güncel uygulama açılır ve test başlar.
ilk çalıştırmada torch, nllb ve qwen için birkaç gb indirme gerekebilir.
kurulum ve model önbellekleri sandbox içinde kalır; kapanınca silinir. sonuçlar
ana bilgisayarda korunur. sandbox'ı sonuçlar yazılmadan kapatmayın.

- `status.json`: çalışan aşama / hata / tamamlanma durumu.
- `sandbox.log`, `gui-error.log`, `qwen-server.log`: işlem günlükleri.
- `results.json`, `results.csv`, `rapor.html`: gerçek model sonuçları ve süreler.
- qwen dosyasının sha256 özeti sabitlenmiştir. llama cpu sürümü resmi github
  sürümlerinden sha256 bilgisi olan ilk uygun paket olarak seçilir; çözülen
  sürüm ve özetler rapora yazılır. test yeniden üretilirken sürüm değişebilir.

bu test ekran yakalama/ocr veya fiziksel ekran kartı doğrulaması değildir.
ana uygulamanın normal model bileşenleri modeller sayfasından ayrıca kurulur.

resmi kaynaklar:
- https://huggingface.co/Qwen/Qwen3-0.6B-GGUF
- https://github.com/ggml-org/llama.cpp
- https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file

## 0.3.0 kararı

sandboxie içinde cpu ile yapılan 12 örneklik denemede geçmişsiz 0.6b düzenlemesi anlam kazanımı sağlamadı; geçmişli yöntem bir örnekte önceki replikleri yeni çeviriye ekledi. küçük örnekleme dayanan bu inceleme genel başarı oranı değildir. prototip normal çeviri akışına eklenmedi; yerel altyazı dosyaları ve deney çıktıları dağıtılmıyor.
