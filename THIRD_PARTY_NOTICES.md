# üçüncü taraf bileşenler

mergen'in kendi kaynak kodu MIT lisanslıdır. İndirilen kütüphaneler, model
ağırlıkları ve çalışma zamanları kendi lisanslarına tabidir. Kaynak dağıtımı
model ağırlıklarını veya Python paketlerini içermez. 0.4.0 kurulum paketi standart
600m, mergen bağlamlı 1.3b v1 ve OCR ağırlıklarını içerir; çalışma kütüphaneleri
uygulama içinden resmi paket kaynaklarından indirilir.

| bileşen | kaynak / lisans |
|---|---|
| nllb 600m | [Meta model kartı](https://huggingface.co/facebook/nllb-200-distilled-600M), CC-BY-NC-4.0 |
| nllb 1.3b | [Meta model kartı](https://huggingface.co/facebook/nllb-200-distilled-1.3B), CC-BY-NC-4.0 |
| manga-ocr ve modeli | [kod](https://github.com/kha-white/manga-ocr), [model](https://huggingface.co/kha-white/manga-ocr-base), Apache-2.0 |
| paddleocr / paddlepaddle | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [Paddle](https://github.com/PaddlePaddle/Paddle), Apache-2.0 |
| ctranslate2 | [OpenNMT](https://github.com/OpenNMT/CTranslate2), MIT |
| pytorch | [PyTorch lisansı](https://github.com/pytorch/pytorch/blob/main/LICENSE), BSD tarzı ve üçüncü taraf bildirimleri |
| pyside6 / qt | [Qt for Python lisansları](https://doc.qt.io/qtforpython-6/licenses.html), LGPLv3/GPLv3 veya ticari lisans koşulları |
| NVIDIA CUDA / cuDNN | [NVIDIA lisansları](https://docs.nvidia.com/cuda/eula/index.html), ayrı NVIDIA koşulları |

NLLB kaynakları: Meta AI / NLLB Team, “No Language Left Behind: Scaling
Human-Centered Machine Translation”, 2022. paketteki standart 600m modelinin CTranslate2 int8 ve orijinal hf biçimleri korunur.
1.3b modeli mergen tarafından LoRA ile uyarlanmıştır; temel bf16 ağırlıkları,
adapter ve özel dikkat maskesi birlikte kullanılır. Bu dönüşüm modelin CC-BY-NC-4.0
koşullarını değiştirmez. Mergen kodunun MIT olması, NLLB modellerine ticari
kullanım izni vermez. [Lisans metni](https://creativecommons.org/licenses/by-nc/4.0/).

Uygulama logosu proje sahibinin sağladığı `assets/mergen-logo.png` dosyasıdır.
MIT metni uygulama kodu içindir; logo ve üçüncü taraf markaları için ayrıca
marka hakkı veya üçüncü taraf adına izin verilmez.

Kurulu Python paketlerinin kendi LICENSE/NOTICE dosyaları `.venv/Lib/site-packages`
altında bulunur. İkili paket/model içeren yeni dağıtımlar hazırlarken bu dosyaları
ve ilgili yeniden dağıtım koşullarını ayrıca koruyun.

microsoft visual c++ çalışma zamanı ve openmp kitaplığı (vcomp140.dll), microsoft'un yeniden dağıtılabilir çalışma zamanı bileşenleridir; kendi lisans koşullarına tabidir. uygulama bu dosyaları kendi klasöründe kullanır. kaynak: https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files


0.4.0 model ağırlıklarını kayıpsız xz ile paketler. kurulum sonunda özgün dosyalar aynı sha256 özetiyle geri oluşturulur; bu paketleme modeli veya lisansını değiştirmez.
