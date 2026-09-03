# Confuser Obfuser

```text
▄█████  ▄▄▄  ▄▄  ▄▄ ▄▄▄▄▄ ▄▄ ▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄
██     ██▀██ ███▄██ ██▄▄  ██ ██ ███▄▄ ██▄▄  ██▄█▄
▀█████ ▀███▀ ██ ▀██ ██    ▀███▀ ▄▄██▀ ██▄▄▄ ██ ██

▄████▄ ▄▄▄▄  ▄▄▄▄▄ ▄▄ ▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄
██  ██ ██▄██ ██▄▄  ██ ██ ███▄▄ ██▄▄  ██▄█▄
▀████▀ ██▄█▀ ██    ▀███▀ ▄▄██▀ ██▄▄▄ ██ ██

  nothing changed. everything looks different.
  by | emin-eren-kadioglu
```

Confuser Obfuser; Python, C ve Go kaynak kodlarını programın gözlemlenen
davranışını korumaya çalışarak yapısal biçimde dönüştüren, renkli ve
etkileşimli bir terminal aracıdır. Kaynak dili dosya uzantısından otomatik
algılar; fonksiyon, parametre ve yerel değişken adlarını değiştirir, string ve
sayıları dönüştürür, fonksiyon gövdelerine ulaşılamayan sahte kod ekler.

Araç regex tabanlı toplu metin değiştirme yapmaz. Python için standart `ast`, C
için Clang AST, Go için `go/parser`, `go/ast` ve `go/types` kullanır. Böylece
isimler mümkün olduğunca ait oldukları gerçek scope ve declaration üzerinden
eşleştirilir.

> [!IMPORTANT]
> Obfuscation şifreleme değildir ve kaynak kodu geri döndürülemez hâle
> getirmez. Amacı kodun okunmasını ve doğrudan kopyalanmasını zorlaştırmaktır;
> tek başına bir güvenlik sınırı oluşturmaz.

## İçindekiler

- [Öne çıkan özellikler](#öne-çıkan-özellikler)
- [Desteklenen diller ve motorlar](#desteklenen-diller-ve-motorlar)
- [Dönüşümler](#dönüşümler)
- [Hızlı başlangıç](#hızlı-başlangıç)
- [Kurulum](#kurulum)
- [Etkileşimli terminal arayüzü](#etkileşimli-terminal-arayüzü)
- [Komut satırı kullanımı](#komut-satırı-kullanımı)
- [Seed ve rastgelelik](#seed-ve-rastgelelik)
- [Birden fazla obfuscation turu](#birden-fazla-obfuscation-turu)
- [Doğrulama](#doğrulama)
- [Önce ve sonra örnekleri](#önce-ve-sonra-örnekleri)
- [Python API](#python-api)
- [Mimari](#mimari)
- [Dil bazında sınırlar](#dil-bazında-sınırlar)
- [Geliştirme ve test](#geliştirme-ve-test)
- [Sorun giderme](#sorun-giderme)
- [Güvenlik](#güvenlik)

## Öne çıkan özellikler

- `.py`, `.pyw`, `.c` ve `.go` uzantılarından otomatik dil algılama
- Python’da scope-aware AST dönüşümleri
- C’de Clang declaration ID ve source-range tabanlı güvenli isim değiştirme
- Go’da `go/types` nesne eşlemesiyle tip bilgisine dayalı isim değiştirme
- Fonksiyon, parametre ve yerel değişken adlarını yeniden adlandırma
- Python stringlerini parçalı Base64 değişkenleri olarak saklama
- C ve Go stringlerini parçalı hex literal ifadelerine dönüştürme
- Tamsayıları aynı sonucu veren aritmetik ifadelerle oluşturma
- Python, C ve Go fonksiyonlarına ulaşılamayan sahte kod ekleme
- Aynı seed ile tekrar üretilebilir çıktı
- Ayarlanabilir obfuscation tur sayısı; varsayılan `1`
- Orijinal ve dönüştürülmüş programı çalıştırarak davranış karşılaştırması
- Renkli durum mesajları ve yön tuşlarıyla kullanılabilen terminal menüsü
- Windows ve Linux için tek satırla kurulum ve `confuser` komutu
- Harici Python paketi gerektirmeyen çekirdek uygulama

## Desteklenen diller ve motorlar

| Dil | Uzantılar | Yapısal motor | Otomatik çıktı adı |
|---|---|---|---|
| Python | `.py`, `.pyw` | Python `ast` + özel scope/call analizi | `dosya.obf.py` |
| C | `.c` | Clang AST + korumalı lexer | `dosya.obf.c` |
| Go | `.go` | `go/ast` + `go/types` + korumalı lexer | `dosya.obf.go` |

Dosya seçildiğinde terminal menüsü algılanan dili `[Python]`, `[C]` veya `[Go]`
olarak gösterir. Kullanıcının ayrıca dil seçmesine gerek yoktur.

### Sistem gereksinimleri

- Python 3.10 veya üzeri
- C desteği için Clang 14 veya üzeri; C doğrulaması için çalışan derleyici, SDK ve bağlayıcı
- Go desteği için Go 1.22 veya üzeri
- UTF-8 kaynak dosyaları

Python kullanımı için C/Go araçları gerekli değildir. Tek komutluk kurulum
mevcut araçları kullanır; eksik araçları indirmeden önce tek tek onay ister.
Ek Python paketi indirmez. C için yalnızca GCC bulunması AST isim değiştirmeye
yetmez: Clang gerekir. C/Go araçlarının kurulumu isteğe bağlıdır.

## Dönüşümler

Varsayılan yapılandırmada dört dönüşümün tamamı açıktır. Etkileşimli menüden tek
tek kapatılabilir veya CLI üzerinde karşılık gelen `--no-*` seçeneği kullanılabilir.

### 1. İsimleri yeniden adlandırma

Fonksiyonlar, güvenle eşleştirilebilen parametreler ve yerel değişkenler rastgele
üretilen benzersiz adlarla değiştirilir.

Önce:

```python
def calculate_total(price, count):
    total = price * count
    return total
```

Sonra oluşabilecek çıktı:

```python
def _obf_1OhbVrp(_obf_2oiVgRV, _obf_35IfLBc):
    _obf_4bfnoGM = _obf_2oiVgRV * _obf_35IfLBc
    return _obf_4bfnoGM
```

Python motoru doğrudan ve statik olarak çözülebilen keyword çağrılarını da
tanımla birlikte günceller. Callback, alias veya `**mapping` gibi dinamik
durumlarda ilgili parametre adları korunur.

Bu geçişi kapatmak için:

```bash
confuser app.py -o app.obf.py --no-rename
```

### 2. Stringleri parçalama ve kodlama

Python’daki boş olmayan stringler UTF-8/Base64 biçimine çevrilir, 2–6 parçaya
ayrılır ve karışık sırada oluşturulan değişkenlere atanır. Çalışma anında
parçalar doğru sırada birleştirilip çözülür.

Önce:

```python
message = "Hata oluştu"
print(message)
```

Basitleştirilmiş görünüm:

```python
import base64 as _obf_decoder

_obf_part_b = "BvbHX"
_obf_part_a = "SGF0YS"
_obf_part_c = "Fn3R1"
_obf_text = _obf_decoder.b64decode(
    "".join((_obf_part_a, _obf_part_b, _obf_part_c))
).decode("utf-8", "surrogatepass")

print(_obf_text)
```

Gerçek parça sınırları, parça değişkenleri ve atama sırası seed’e göre değişir.
Aynı string dosyada tekrar kullanılıyorsa tek çözülen kopya paylaşılır. Python
docstringleri, annotation ifadeleri, `match` desenleri, boş stringler ve bytes
literal’leri korunur. F-string içindeki sabit metin parçaları dönüştürülür.

C ve Go’da uygun normal string literal’leri parçalı hex ifadelerine dönüştürülür:

```c
printf("\x52" "\x65\x73" "\x75\x6c\x74");
```

```go
fmt.Println("\x52" + "\x65\x73" + "\x75\x6c\x74")
```

C wide-stringleri, Go import yolları, Go struct tag’leri ve güvenli biçimde
dönüştürülemeyen özel literal’ler korunur.

> Base64 bir şifreleme yöntemi değildir. Bu katman yalnızca metnin kaynak
> dosyada doğrudan okunmasını zorlaştırır.

Bu geçişi kapatmak için `--no-strings` kullanılır.

### 3. Sayıları dönüştürme

Tamsayı literal’leri aynı değeri veren aritmetik ifadelere çevrilir.

```python
timeout = 30
```

```python
timeout = 63 - 33
```

C ve Go’da örnek bir dönüşüm:

```c
int timeout = ((4 * 7) + 2);
```

Python motoru boolean değerleri, annotation içindeki sayıları ve `match`
desenlerini korur. C ve Go motoru başında sıfır bulunan ya da hex, octal,
binary, suffix, ondalıklı veya bilimsel gösterim gibi özel biçim taşıyan
sayıları değiştirmez. C'de ara işlemlerin taşmasını önlemek için 2147483647'den
büyük tam sayılar da C/Go sayı geçişinde korunur.

Bu geçişi kapatmak için `--no-numbers` kullanılır.

### 4. Sahte ve işlevsiz kod ekleme

Her üç dilde de fonksiyon gövdelerine derleyicinin veya yorumlayıcının kabul
ettiği, ancak hiçbir zaman çalışmayan zararsız dallar eklenir.

Python:

```python
if 83579 == -1:
    "unreachable"
```

C:

```c
if (0) {
    volatile int _cf_dead_UDIh7yfJs = 6925;
    (void)_cf_dead_UDIh7yfJs;
}
```

Go:

```go
if 0 != 0 {
    _cf_dead_JmTPSIAoC := 5557
    _ = _cf_dead_JmTPSIAoC
}
```

Bu kodlar program sonucunu değiştirmez; yalnızca kaynak yapısına gürültü ekler.
Özellik varsayılan olarak Python, C ve Go için açıktır. Kapatmak için
`--no-dead-code` kullanılır.

## Hızlı başlangıç

Projeyi indirdikten sonra kurulum yapmadan etkileşimli arayüzü açabilirsiniz:

```bash
cd python_obfuscator
python3 confuser_obfuser.py
```

Ya da modül üzerinden:

```bash
python3 -m obfuscator
```

Bir Python dosyasını doğrudan dönüştürmek için:

```bash
python3 -m obfuscator app.py -o app.obf.py --seed 42 --validate
python3 app.obf.py
```

## Kurulum

### Tek komutla kurulum

Projeyi elle indirmeniz veya Git kurmanız gerekmez. Aşağıdaki tek satır
deponun kaynak arşivini indirir, uygulamayı kullanıcı dizinine kopyalar ve
`confuser` komutunu PATH'e ekler. **Python 3.10+ gerekir; eksikse kurulum için onay sorulur.** Uygulamanın
harici Python bağımlılığı yoktur; kurucu pip/venv kurmaz veya güncellemez.

Varsayılan komut eksik Python, Clang ve Go için **ayrı ayrı onay ister**.
`y` / `yes` kurulumu onaylar; `n` veya yalnızca Enter indirmeyi atlar.
Python eksikse ve kurulumu reddedilirse uygulama kurulumu tamamlanamaz.
C/Go araçlarını reddetmek Python kullanımını engellemez. Python örneğinin
doğrulanması zorunludur; C/Go araçları varsa ayrıca denenir, eksik veya bozuksa
uyarı verilir. Başarılı uygulama kurulumu, eksik bir C/Go motorunun da
doğrulandığı anlamına gelmez. Kaynak arşivi için internet gerekir.

**Linux (Bash/Zsh; macOS'ta da kullanılabilir):**

`curl` kurulu olmalıdır.

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/emin-eren-kadioglu/confuser-obfuser/main/install.sh | sh -s -- --from-github) && export PATH="$HOME/.local/bin:$PATH"
```

**Windows 10/11 (PowerShell):**

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/emin-eren-kadioglu/confuser-obfuser/main/install.ps1 -ErrorAction Stop))) -FromGitHub
```

Kurulum bitince aynı terminalde:

```bash
confuser
```

Argümansız çağrı etkileşimli menüyü açar. Doğrudan dosya dönüştürmek için:

```bash
confuser app.py -o app.obf.py --seed 42 --validate
```

> Bu komutlar bu deponun `main` dalındaki mevcut kurulum betiğini çalıştırır.
> Yalnızca güvendiğiniz kaynaklardan kurulum yapın. Kaynak arşivi geçici bir
> klasöre indirilir ve işlem sonunda silinir; projeyi elle indirmeniz gerekmez.

**Onay akışı:** Yukarıdaki komutlara ek seçenek koymanız gerekmez. Örneğin:

```text
Install clang? [y/N]: n
Install go? [y/N]: y
```

Bu örnekte yalnızca Go kurulumu denenir. Kurulu araçlar tekrar indirilmez.
Windows'ta Clang derleme kontrolü başarısızsa C++ Build Tools/SDK için ayrıca
onay sorulur. Araçlar yüzlerce MB; Windows SDK veya Apple geliştirici araçları
birkaç GB indirme gerektirebilir. Kurucu onaydan önce boyut uyarısını gösterir;
kesin boyut sisteme ve eksik bileşenlere bağlıdır. Yönetici/sudo izni veya
yeniden başlatma gerekebilir. Homebrew/WinGet eksikse bunlar için de ayrı onay alınır.

Onaylanan araçlar Linux'ta `apt`, `dnf` veya `pacman`, macOS'ta Homebrew veya
Apple Command Line Tools, Windows'ta WinGet üzerinden kurulur.
Dağıtım paketleri minimum sürümleri sağlamalıdır (Ubuntu 24.04 veya sonrası).
macOS geliştirici araçları grafik kurulum penceresi gerektirebilir; tüm sistem
paketlerinin kullanıcı müdahalesi olmadan kurulacağı garanti edilmez.

Araç sorularını tamamen atlamak için Linux/macOS komutundaki `--from-github`
sonrasına `--no-tools`, Windows komutunun sonuna `-SkipTools` ekleyin.
Etkileşimli terminal yoksa veya `CI=true` ise araç indirilmez. Eski
`--install-tools` / `-InstallTools` seçenekleri uyumluluk için kabul edilir,
ancak artık gerekli değildir ve onayı atlamaz. `confuser` uygulamasını açmak
araç kurulumu başlatmaz; eksik araç soruları kurucuyu tekrar çalıştırınca gelir.
Kurucu mesajları ve uygulamanın kendi hata mesajları İngilizcedir; menü
etiketleri Türkçe kalır. İşletim sistemi/harici araç mesajlarının dili değişebilir.

Güncellemek için varsayılan kurulum satırını tekrar çalıştırın. Yeni uygulama
kopyası kontrol edildikten sonra başlatıcı değiştirilir; eski uygulama
kopyaları otomatik silinmez. Python mevcutsa yerel kaynak klasöründen
`sh install.sh --no-tools` veya `powershell -File .\install.ps1 -SkipTools`
ile kurulum internetsiz çalışır. Go AST analizi ve Go derlemesinde otomatik toolchain/modül
indirmeleri kapalıdır; proje bağımlılıklarını önceden kendiniz hazırlamalısınız.

### İndirilmiş kaynak klasöründen kurulum

Aynı kurulumu proje klasöründen de başlatabilirsiniz:

macOS/Linux:

```bash
sh install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Her iki yöntem de `confuser` ve uyumluluk için `confuser-obfuser` komutlarını
oluşturur. Linux/macOS'ta varsayılan uygulama dizini
`~/.local/share/confuser-obfuser`, komut dizini `~/.local/bin` olur.
Windows'ta uygulama `%LOCALAPPDATA%\ConfuserObfuser` altına kurulur.

### Pip ile kurulum

Kaynak klasörden normal kurulum:

```bash
python3 -m pip install .
```

Geliştirme kurulumu:

```bash
python3 -m pip install -e '.[dev]'
```

Paket kurulumu üç eşdeğer komut oluşturur; eski adlar uyumluluk için korunur:

```bash
confuser
confuser-obfuser
py-obfuscate
```

Argümansız çağrı etkileşimli menüyü, argümanlı çağrı CLI modunu açar.

## Etkileşimli terminal arayüzü

Arayüzü açmak için:

```bash
confuser
```

Ana menüden şu ayarlar yapılabilir:

1. Kaynak dosya seçme
2. Çıktı dosyası belirleme
3. Dört dönüşümü ayrı ayrı açma veya kapatma
4. Sabit seed girme ya da rastgele seed kullanma
5. Doğrulamayı açma veya kapatma
6. Obfuscation tur sayısını belirleme
7. Dönüşümü başlatma

Menüde sol/yukarı tuşları önceki, sağ/aşağı tuşları sonraki seçeneğe gider.
`Enter` seçili satırı çalıştırır; sayı tuşlarıyla doğrudan seçim de yapılabilir.
Bu davranış Unix terminallerinde ve Windows konsolunda ayrı klavye okuma
mekanizmalarıyla desteklenir.

Dosya yolu elle yazılabilir veya terminale sürüklenebilir. Çıktı yolu belirtilmezse:

```text
program.py  → program.obf.py
program.c   → program.obf.c
program.go  → program.obf.go
```

Arayüzde başarı mesajları yeşil, hatalar kırmızı gösterilir. `AÇIK` yeşil,
`KAPALI` kırmızıdır. Dekoratif menü renkleri bu durum renklerinden bağımsızdır.
`NO_COLOR` tanımlıysa, terminal `dumb` modundaysa veya çıktı bir TTY değilse ANSI
renkleri otomatik olarak kapatılır.

## Komut satırı kullanımı

Genel biçim:

```text
confuser INPUT [-o OUTPUT] [SEÇENEKLER]
```

Tüm seçenekler:

| Seçenek | Açıklama | Varsayılan |
|---|---|---|
| `INPUT` | `.py`, `.pyw`, `.c` veya `.go` kaynak dosyası | Zorunlu |
| `-o`, `--output PATH` | Çıktı dosyası; verilmezse stdout’a yazılır | stdout |
| `--seed INTEGER` | Tekrar üretilebilir rastgelelik tohumu | Sistem rastgeleliği |
| `--iterations N` | Dönüşümün kaç tur uygulanacağı | `1` |
| `--no-rename` | İsim değiştirme geçişini kapatır | Açık |
| `--no-strings` | String dönüştürme geçişini kapatır | Açık |
| `--no-numbers` | Sayı dönüştürme geçişini kapatır | Açık |
| `--no-dead-code` | Sahte kod ekleme geçişini kapatır | Açık |
| `--validate` | İki programı çalıştırıp davranışını karşılaştırır | Kapalı |
| `--timeout SECONDS` | Doğrulama alt işlemleri için zaman aşımı | `5.0` |

Python örneği:

```bash
confuser examples/demo.py -o demo.obf.py --seed 42 --validate
```

C örneği:

```bash
confuser examples/demo.c -o demo.obf.c --seed 42 --validate
cc demo.obf.c -o demo && ./demo
```

Go örneği:

```bash
confuser examples/demo.go -o demo.obf.go --seed 42 --validate
go run demo.obf.go
```

Yalnızca isim ve sayı dönüşümü kullanmak için:

```bash
confuser app.py -o app.obf.py --no-strings --no-dead-code
```

Çıktıyı dosya yerine terminale yazmak için `-o` kullanılmaz:

```bash
confuser app.py --seed 42
```

### Özel C derleme seçenekleri

Ek include dizinleri, define veya dil standardı gerekiyorsa
`CONFUSER_CLANG_ARGS` kullanılabilir:

```bash
CONFUSER_CLANG_ARGS='-std=c11 -I./include -DFEATURE=1' \
confuser app.c -o app.obf.c --validate
```

Alternatif Clang çalıştırıcısı `CLANG`, doğrulama derleyicisi `CC` ile seçilebilir:

```bash
CLANG=/opt/llvm/bin/clang CC=clang \
confuser app.c -o app.obf.c --validate
```

## Seed ve rastgelelik

Seed, sahte rastgele sayı üretecinin başlangıç değeridir. Aynı kaynak kod,
aynı araç sürümü, aynı seçenekler ve aynı seed kullanıldığında aynı çıktı
üretilir.

```bash
confuser app.py -o first.py --seed 42
confuser app.py -o second.py --seed 42
```

Seed değişirse şunlar değişebilir:

- Üretilen fonksiyon ve değişken adları
- Base64 parça sınırları
- Parça değişkenlerinin isimleri ve atama sırası
- Sayılarda kullanılan aritmetik değerler
- Sahte kod değişkenleri ve içlerindeki sayılar

Seed verilmezse sistem rastgeleliğiyle başlatılan bir üreteç kullanılır ve
sonraki çalıştırmada farklı çıktı oluşabilir. Seed bir parola değildir ve
kriptografik koruma sağlamaz.

## Birden fazla obfuscation turu

Varsayılan tur sayısı `1`’dir. `--iterations` ile önceki turun çıktısı yeniden
girdi olarak işlenebilir:

```bash
confuser app.py -o app.obf.py --seed 42 --iterations 3 --validate
```

Her turda aynı seed ile yeni bir dönüşüm zinciri başlatılır. Yalnızca son çıktı
yazılır; ara tur dosyaları saklanmaz. Çok sayıda tur özellikle Python Base64
string havuzu nedeniyle dosya boyutunu hızla büyütebilir. Genellikle 1–3 tur
yeterlidir. Bir ara çıktı 2 MiB’ı aşarsa sonraki tur başlatılmaz.

Birden fazla tur daha güçlü bir güvenlik garantisi vermez; yalnızca kaynak
karmaşıklığını ve çalışma maliyetini artırabilir.

## Doğrulama

`--validate`, orijinal ve son obfuscate edilmiş programı ayrı geçici dosyalarda
çalıştırır. Aşağıdaki gözlemler birebir karşılaştırılır:

- Derleme başarısı — C ve Go için
- Süreç çıkış kodu
- Standart çıktı (`stdout`)
- Standart hata (`stderr`)

Python mevcut yorumlayıcıyla çalıştırılır. C dosyaları `CC` ile belirtilen
derleyici, bulunamazsa `cc` veya `clang` ile; Go dosyaları `go build` ile
derlenir. Çok turlu kullanımda yalnızca orijinal kaynak ile son tur arasında
bir kez doğrulama yapılır.

> [!WARNING]
> Doğrulayıcı bir sandbox değildir. Her iki programı gerçekten çalıştırır ve
> dosya, ağ, süreç veya sistem değişikliklerini engellemez. `--validate`
> seçeneğini yalnızca tamamen güvendiğiniz kaynaklarda kullanın.

Doğrulayıcı yalnızca gözlemlenen süreç sonucunu karşılaştırır. Dosya yazma, ağ
isteği, zamanlama, bellek kullanımı veya başka yan etkilerin eşdeğer olduğunu
kanıtlamaz. Stdin kapalı olduğu için kullanıcı girdisi bekleyen uygulamalar
doğrulamaya uygun olmayabilir.

## Önce ve sonra örnekleri

Hazır karşılaştırmalar [`examples/README.md`](examples/README.md) dosyasında
bulunur:

| Dil | Normal kaynak | Obfuscate edilmiş kaynak |
|---|---|---|
| Python | [`examples/demo.py`](examples/demo.py) | [`examples/obfuscated/demo.py`](examples/obfuscated/demo.py) |
| C | [`examples/demo.c`](examples/demo.c) | [`examples/obfuscated/demo.c`](examples/obfuscated/demo.c) |
| Go | [`examples/demo.go`](examples/demo.go) | [`examples/obfuscated/demo.go`](examples/obfuscated/demo.go) |

Hazır çıktılar bütün dönüşümler açıkken, tek tur ve `seed=42` ile aracın kendisi
tarafından oluşturulmuştur.

## Python API

Araç Python kodundan doğrudan kullanılabilir:

```python
from obfuscator import ObfuscationConfig, Obfuscator

source = '''
def greet(name):
    message = f"Merhaba, {name}!"
    return message

print(greet("Ada"))
'''

config = ObfuscationConfig(
    seed=42,
    rename_identifiers=True,
    encode_strings=True,
    transform_numbers=True,
    insert_dead_code=True,
    iterations=1,
)

result = Obfuscator(config).obfuscate(source, "example.py")
print(result)
```

C ve Go için dilin anlaşılabilmesi amacıyla dosya adı verilmelidir:

```python
obfuscator = Obfuscator(ObfuscationConfig(seed=42))

c_result = obfuscator.obfuscate(
    'int main(void) { return 0; }',
    'main.c',
)

go_result = obfuscator.obfuscate(
    'package main\nfunc main() {}\n',
    'main.go',
)
```

Dosya adı verilmeden kullanılan bellek içi API, geriye dönük uyumluluk için
Python kabul eder.

## Mimari

```text
Kaynak dosya
    │
    ├── Dosya uzantısından dil algılama
    │
    ├── Python ──► ast.parse ──► scope/call analizi ──► AST pass'leri
    │
    ├── C ───────► Clang AST ──► declaration eşleme ──► lexer pass'leri
    │
    └── Go ──────► go/ast + go/types ──► object eşleme ──► lexer pass'leri
                                                        │
                                                        ▼
                                              Yeni kaynak kod üretimi
                                                        │
                                              İsteğe bağlı doğrulama
```

Her dönüşüm bağımsız bir pass olarak yapılandırılır. Python tarafında AST
düğümleri değiştirilip yeni kaynak üretilir ve her tur sonunda sözdizimi tekrar
derlenerek kontrol edilir. C ve Go tarafında isimler yapısal motorla
eşlendikten sonra yorum, whitespace, direktif ve literal sınırlarını koruyan
lexer üzerinde string, sayı ve sahte kod işlemleri uygulanır.

Başlıca modüller:

```text
python_obfuscator/
├── confuser_obfuser.py          # Etkileşimli arayüz başlangıcı
├── install.sh                   # macOS/Linux kurulumu
├── install.ps1                  # Windows kurulumu
├── obfuscator/
│   ├── cli.py                   # Komut satırı
│   ├── terminal_ui.py           # Renkli terminal menüsü
│   ├── languages.py             # Uzantı ve dil algılama
│   ├── pipeline.py              # Yapılandırma ve tur orkestrasyonu
│   ├── scope_analyzer.py        # Python scope bağları
│   ├── call_analyzer.py         # Python çağrı/keyword analizi
│   ├── c_ast.py                 # Clang AST köprüsü
│   ├── go_ast.py                # Go yardımcı motor köprüsü
│   ├── go_ast_helper/main.go    # go/ast ve go/types motoru
│   ├── native.py                # C/Go korumalı lexer geçişleri
│   ├── validator.py             # Davranış karşılaştırması
│   └── passes/                  # Python AST dönüşümleri
├── examples/                    # Önce/sonra örnekleri
└── tests/                       # Otomatik testler
```

## Dil bazında sınırlar

### Python

- Normal ve iç içe fonksiyonlar, lambda parametreleri, comprehension bağları,
  exception değişkenleri ve desteklenen pattern binding’leri scope bilgisiyle
  işlenir.
- Recursive ve async fonksiyon çağrıları desteklenir.
- Metot/attribute adları, import bağları ve dunder adlar korunur.
- `__all__` tanımlayan modüllerde üst düzey fonksiyon API’leri korunur.
- `eval`, `exec`, `locals`, `globals`, `vars`, `getattr` ve benzeri dinamik
  namespace erişimleri tespit edilirse isim değiştirme dosya için atlanabilir.
- Metadata erişimi ve henüz desteklenmeyen type-parameter scope’ları
  konservatif korumayı tetikler.
- Araç tek dosya dönüştürür; başka modüllerdeki import ifadelerini güncellemez.

### C

- Clang declaration ID’leri aynı isimli fakat farklı scope’taki değişkenleri
  birbirinden ayırmak için kullanılır.
- Kaynak içindeki serbest fonksiyonlar, parametreler ve yerel değişkenler
  yeniden adlandırılır; `main` korunur.
- Struct alanları, typedef’ler ve callback referansları yazılış benzerliğine
  bakılarak yanlışlıkla değiştirilmez.
- Dönüşüm tek translation unit odaklıdır. Başka `.c` dosyalarının kullandığı
  dış semboller otomatik olarak görülemez.
- Makrolarla üretilen veya include dosyalarından gelen declaration’lar
  konservatif biçimde işlenir ya da korunur.

### Go

- Identifier’lar `go/types.Object` nesneleri üzerinden eşleştirilir.
- Serbest fonksiyonlar, parametreler ve yerel değişkenler değiştirilir;
  `main`, `init`, metot adları, struct alanları ve selector’lar korunur.
- Aynı klasör ve paketteki kardeş `.go` dosyaları incelenir; kardeş dosyaların
  kullandığı semboller korunur.
- Başka paketlerin kullandığı exported API’ler tek dosya analizinden kesin
  olarak bilinemeyebilir.
- Import yolları ve struct tag’leri string geçişinin dışında tutulur.

Dışarıya açık C veya Go kütüphane API’lerinde isimleri korumak için
`--no-rename` kullanılması önerilir.

## Geliştirme ve test

Geliştirme ortamını kurun:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

Testleri çalıştırın:

```bash
python3 -m pytest -q
python3 -m unittest discover -s tests -q
```

Dağıtım paketlerini oluşturun:

```bash
python3 -m build
```

CI; Linux üzerinde Python 3.10, 3.12 ve 3.14 matrisini, Windows kurulumunu ve
dağıtım paketi oluşturmayı ayrı görevlerde kontrol eder. C veya Go toolchain’i
bulunmayan yerel ortamlarda ilgili derleme testleri atlanabilir.

## Sorun giderme

### `clang` bulunamadı

C isim değiştirme motoru Clang ister. Kurulum betiğini çalıştırın veya Clang’i
PATH’e ekleyin:

```bash
clang --version
```

### `go` bulunamadı

Go isim değiştirme motoru ve Go doğrulaması toolchain ister:

```bash
go version
```

Kurulumdan sonra terminali yeniden açmak PATH değişikliğini uygulayabilir.

### Doğrulama zaman aşımına uğruyor

Program kullanıcı girdisi bekliyor veya uzun sürüyor olabilir. CLI’da süre
artırılabilir:

```bash
confuser app.py -o app.obf.py --validate --timeout 30
```

Etkileşimli menünün doğrulama süresi 5 saniyedir. Girdi bekleyen programlarda
doğrulamayı kapatıp çıktı kodunu ayrı test etmek daha uygundur.

### `.obf.py` farklı bir uzantı mı?

Hayır. `program.obf.py` dosyasının gerçek uzantısı hâlâ `.py`’dır; `obf` yalnızca
dosya adının parçasıdır. Normal Python dosyası gibi çalıştırılır:

```bash
python3 program.obf.py
```

Aynı durum `program.obf.c` ve `program.obf.go` için de geçerlidir.

### Çıktı dosyası çok büyüyor

Tur sayısını azaltın veya string dönüşümünü kapatın:

```bash
confuser app.py -o app.obf.py --iterations 1 --no-strings
```

### Dinamik kod isim değiştirmeden sonra bozulabilir mi?

Reflection ve string tabanlı isim erişimi statik analiz için doğal bir sınırdır.
Motor birçok riskli kullanımı algıladığında isim değiştirmeyi atlar; yine de
dinamik framework veya dış API kullanan dosyalarda `--no-rename` ve kapsamlı
uygulama testleri tercih edilmelidir.

## Güvenlik

Kaynak dönüşümü varsayılan olarak kodu çalıştırmaz. `--validate` seçildiğinde
güven sınırı değişir ve hem orijinal hem dönüştürülmüş kod çalıştırılır.
Ayrıntılar ve güvenlik açığı bildirim yöntemi için [SECURITY.md](SECURITY.md)
dosyasına bakın.

Bu araç yalnızca size ait veya değiştirme yetkiniz bulunan kaynak kodlarda
kullanılmalıdır.

## Lisans

Proje [MIT Lisansı](LICENSE) ile dağıtılır.

```text
by | emin-eren-kadioglu
```
