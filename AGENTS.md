# uygulamada görünen metinler

Kullanıcı aksini söylemedikçe uygulama arayüzünde görünen bütün yazılar küçük
harfle gösterilmelidir. Başlıklar, düğmeler, menüler, durumlar, model ve cihaz
etiketleri de bu kurala dahildir. Kod adları, API adları, dosya yolları ve
teknik sabitlerin kaynak kod içindeki yazımı değiştirilmeyebilir; kullanıcıya
gösterilen biçim küçük harf olmalıdır. Bu tercih sonraki güncellemelerde de
korunmalıdır. Yalnızca harf boyutu için dosya yollarını veya model kimliklerini
değiştirmeyin; görünüm katmanında uygulayın.

# çeviri içeriği istisnası

çeviri içeriğinin büyük/küçük harf biçimini modelin ürettiği gibi koruyun.
arayüz başlıkları, düğmeler, menüler, durumlar ve cihaz/model etiketleri küçük
harf kalır. çeviri içeriğine görünüm katmanında da zorunlu lowercase uygulamayın.

## riskli değişikliklerde önce başarısız test

yol haritasındaki 1.3 (ekran geometrisi), 2.1 (partial birleştirme) ve 3.1
(kaydırma takibi) için üretim davranışını değiştirmeden önce hatayı mevcut
kodda yeniden üreten başarısız bir test yazın ve çalıştırın. ardından aynı
testi düzeltmeyle geçirin; önce/sonra sonucunu kaydedin. yalnızca gözle yapılan
deneme bu üç alan için yeterli değildir. bu kural sonraki güncellemelerde de korunur.

