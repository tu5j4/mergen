# derleme ve imzalama

windows x64 ve python 3.12 ile ayrı bir derleme ortamı kullan. `installer/requirements-ui.txt` ile `pyinstaller>=6,<7` paketlerini kur. `python scripts/export_next_source.py <yeni-temiz-klasör>` yalnızca kaynak izin listesini dışa aktarır. ayarlar, günlükler, ekran görüntüleri, modeller, eğitim verisi ve özel anahtarlar bu pakete girmez. kişisel yolların derlenmiş dosyalara taşınmaması için temiz kopyayı genel bir derleme klasöründe derle.

`python scripts/build_executable.py` arayüzü `dist/Mergen` altında oluşturur. model kütüphaneleri bu arayüz paketine gömülmez; uygulama içinden ayrı ortamlara kurulur.

`scripts/fetch_build_tools.ps1` doğrulanan inno setup ve taşınabilir python araçlarını hazırlar. sabit model paketi için `scripts/prepare_model_payload.py` kullanılır. dağıtımdaki bütün metin ve model kartlarında kişisel yol bulunmadığını denetle; model dosyalarının boyut ve sha256 bilgilerini `assets/bundled-models.json` içine kaydet. model ağırlıkları kaynak zip'ine konulmaz.

`scripts/pack_model_archives.py` dört büyük ağırlığı bayt şeritleri ve xz ile kayıpsız paketler. `assets/packed-models.json` özgün dosya ve arşiv özetlerini tutar. hazır arşivleri tekrar üretmek gerekmez. `python scripts/build_installer.py --model-payload <sabit-paket> --packed-payload <kayıpsız-arşivler>` tek dosyalık tam kurulumu üretir. kurulumda model dosyaları özgün özetleriyle geri açılır. tam exe, windows kurulum boyutu sınırını aşmamalıdır.

github sürüm dosyası başına 2 gib sınırı için `python scripts/build_download_bootstrap.py --installer <tam-kurulum.exe> --output <yayın-klasörü>` çalıştır. araç tam kurulumu 2000 mib altındaki `.data` parçalarına böler; bütün sha256 özetlerini içine sabitleyen küçük bir windows forms başlatıcısı derler. başlatıcı her parçayı ve birleşen exe'yi doğrulamadan kurulumu çalıştırmaz. kullanıcı yalnızca başlatıcı exe'yi açar. `.data` parçaları aynı sabit tam kurulumun baytlarıdır.

`python scripts/sign_release_local.py --key <özel-anahtar> --installer <başlatıcı.exe> --output <yayın-klasörü>` başlatıcı için ed25519 imzalı güncelleme bildirimi üretir. bu windows authenticode sertifikası değildir. özel anahtar dağıtıma veya repoya eklenmez. kaynak zip'i, paket parçaları ve diğer belgeler için ayrıca sha256 listesi üret.

github commitlerinde author ve committer kimliklerini açıkça github kullanıcı adı ve github noreply adresiyle belirt. kaynak ağacını, yayımlanan dosya boyut/özetlerini, sürüm sabitlerini ve commit kimliklerini yayın sonrasında tekrar doğrula.
