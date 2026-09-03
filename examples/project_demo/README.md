# Çok dosyalı mini proje

Harici kütüphane veya indirme gerektirmez. Python, Clang ve Go sistemde kurulu olmalıdır.

- Python: paket importu, başka dosyadaki fonksiyona isimli parametre, JSON veri dosyası.
- C: iki ayrı kaynak, ortak `.h` dosyası, dosyalar arası fonksiyon çağrısı.
- Go: `go.mod`, yerel alt paket, `go:embed` dosyası, `_test.go` testi.

Bu klasörde `python verify.py` üç dili kontrol eder. Tek dil için
`python verify.py python`, `python verify.py c` veya `python verify.py go` kullanın.
Linux/macOS'ta gerekirse `python` yerine `python3` yazın.

Depo kökünde tüm klasörü dönüştürün:

```sh
confuser examples/project_demo --seed 42
```

Çıktı `examples/project_demo-obfuscated` olur. Orada da aynı `python verify.py`
komutu çalışır. Dosyalar yeniden adlandırılmaz; girdi klasörü değişmez.
Mevcut çıktı klasörünün üzerine yazılmaz; yeniden denemek için `-o` ile yeni bir
çıktı klasörü seçin. Doğrulama varsayılan kapalıdır.
