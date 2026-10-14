# mergen 0.2.0 geliştirme

## mimari

qt quick arayüzü python 3.11 ve pyside6 ile çalışır. nllb, paddleocr ve manga-ocr, uygulamanın oluşturduğu ayrı python 3.12 ortamlarında çalışır. cpu/nvidia çevirisi ctranslate2, deneysel amd/intel yolu transformers kullanır. nvidia paddle ortamı torch ortamından ayrıdır.

`app/next_main.py` güncel arayüz girişidir; `main.py`, `next_main.py` ve `baslat.bat` bunu açar. `app/ui/control_panel.py` ekran katmanı ve çeviri arka planı için kullanılır. `installer/service.py` uygulama içindeki bileşen yönetimidir. eski komut satırı kurucusunun yardımcı kodu ve testleri uyumluluk için korunur; kullanıcı kurulumu exe üzerinden yapılır.

## geliştirme ortamı

windows x64 ve python 3.11 ile:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts/smoke_qml.py
.\.venv\Scripts\python.exe scripts/test_controller_jobs.py
```

model testleri ayrıca python 3.12 ve uygulamadan kurulmuş bileşenleri gerektirir. kaynak çalıştırmada veriler `.data` altında saklanır. python 3.12, `py -3.12` ile bulunabilmeli veya `.data/python/python.exe` konumunda olmalıdır.

## derleme ve kaynak dağıtımı

1. microsoft visual c++ x64 çalışma zamanı kurulu olmalı; derleme `vcomp140.dll` yoksa durur.
2. `scripts/fetch_build_tools.ps1` sabit sha256 özetleriyle python 3.12 ve inno setup araçlarını hazırlar. proje içindeki `.venv` kullanılır; farklı python için `-PythonExe` verilebilir.
3. `.venv/Scripts/python.exe scripts/build_executable.py` arayüzü `dist/Mergen` içine derler. model kütüphaneleri exe içine alınmaz.
4. `build-tools/inno/ISCC.exe installer/mergen-next.iss` dosyasından `release/mergen-setup-0.2.0.exe` oluşturulur.
5. `python scripts/build_distribution.py --output kaynak-paketi` yalnızca temiz kaynak kodu dışa aktarır. ortamlar, modeller, günlükler ve özel anahtarlar dahil edilmez.

## güncelleme yayımlama

`assets/update-public-key.pem` güvenilen ed25519 açık anahtarıdır. özel anahtar depoya konmaz. `scripts/release_manifest.py` ile kurulum dosyası için imzalı `mergen-update.json` hazırlanır; exe ve bildirim aynı github release içinde yayımlanır. uygulama sürümü, depo adresini, imzayı, boyutu ve sha256 özetini kontrol eder.

amd ve intel seçenekleri ilgili donanımlarda uçtan uca test yapılana kadar deneyseldir. ölçülemeyen sistem değerleri sıfır olarak gösterilmez. tüm kullanım göstergeleri kapalıyken örnekleme durur.
