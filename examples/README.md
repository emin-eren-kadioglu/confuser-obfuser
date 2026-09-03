# Önce / sonra örnekleri

Çok dosyalı klasör modu için ayrıca [`project_demo`](project_demo/README.md)
örneği bulunur: Python paketleri, C başlığı ve birden fazla kaynak dosyası,
Go yerel modülü ve testi birlikte denenebilir.

Bu klasördeki üç küçük program, Confuser Obfuser'ın desteklediği diller için
okunabilir kaynak örnekleridir. `obfuscated/` klasöründeki karşılıkları bütün
dönüşümler açıkken, tek tur ve `seed=42` kullanılarak araç tarafından üretildi.

| Dil | Obfuscate edilmemiş | Obfuscate edilmiş |
|---|---|---|
| Python | [`demo.py`](demo.py) | [`obfuscated/demo.py`](obfuscated/demo.py) |
| C | [`demo.c`](demo.c) | [`obfuscated/demo.c`](obfuscated/demo.c) |
| Go | [`demo.go`](demo.go) | [`obfuscated/demo.go`](obfuscated/demo.go) |

Çıktılarda fonksiyon, parametre ve yerel değişken adlarının değiştiğini;
stringlerin parçalara ayrıldığını, sayıların eşdeğer ifadelere çevrildiğini ve
ulaşılamayan zararsız dalların eklendiğini görebilirsiniz.

## Yeniden üretme

Proje kökünde aşağıdaki komutları çalıştırın:

```bash
python3 -m obfuscator examples/demo.py -o examples/obfuscated/demo.py --seed 42 --validate
python3 -m obfuscator examples/demo.c -o examples/obfuscated/demo.c --seed 42 --validate
python3 -m obfuscator examples/demo.go -o examples/obfuscated/demo.go --seed 42 --validate
```

Sabit seed nedeniyle aynı araç sürümü ve aynı seçenekler aynı çıktıyı üretir.
`--validate`, kaynak ve dönüştürülmüş programın gözlemlenen davranışını
karşılaştırır; yalnızca güvendiğiniz kodlarda kullanılmalıdır.
