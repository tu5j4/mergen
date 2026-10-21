# derleme ve imzalama

windows x64 üzerinde python 3.12 ile ayrı bir sanal ortam oluştur. `installer/requirements-ui.txt` ve `pyinstaller>=6,<7` paketlerini kur. `python scripts/build_executable.py` arayüzü `dist/Mergen` altında üretir; modeller exe içine gömülmez.

`powershell -ExecutionPolicy Bypass -File scripts/fetch_build_tools.ps1 -PythonExe <python-yolu>` doğrulanan python ve inno setup araçlarını hazırlar. `python scripts/build_installer.py` kolay kurulum exe’sini `release` altında oluşturur. kişisel kullanıcı yollarını ikili dosyalara taşımamak için temiz kaynak dışa aktarımını genel bir derleme klasöründe derle.

kaynak paketi: `python scripts/export_next_source.py <yeni-hedef>`. izin listesinin dışında kalan ayarlar, ortamlar, modeller, günlükler, ekran görüntüleri ve özel anahtarlar dışa aktarılmaz. paket manifesti sha256 içerir.

imzalama: `python scripts/sign_release_local.py --key <özel-anahtar-yolu>`. araç, özel anahtarın uygulamadaki açık anahtarla eşleştiğini kontrol eder; kurulum exe’si için imzalı `mergen-update.json` ve `SHA256SUMS.txt` üretir. bu ed25519 güncelleme imzasıdır; windows authenticode sertifikası değildir. özel anahtar repoya veya dağıtıma eklenmez.

0.3.0’da, eski özel anahtarın kaybolması nedeniyle yeni anahtar kullanılır. 0.2.0 kullanıcıları 0.3.0 kurulum exe’sini elle çalıştırmalıdır. imza doğrulamasını devre dışı bırakan bir geçiş uygulanmaz.

qwen 0.6b bağlam yardımcısı deneysel kaynak olarak korunur ve ana çeviri akışında çalıştırılmaz. altyazılar ve yerel deney sonuçları kaynak paketine dahil değildir.
