# Architektúra procesora LIM M2

<p align="center">
  <img src="Docs/diagram.png" alt="Schéma dátovej cesty LIM M2" width="850">
</p>

<p align="center">
  <b>Vysokovýkonné 16-bitové mikroprogramové jadro s čistým multiplexorovým smerovaním (Zero Tri-State) a lineárnym 24-bitovým adresovaním (16 MB)</b>
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> •
  <a href="README.ua.md"><b>Українська</b></a> •
  <a href="README.ru.md"><b>Русский</b></a> •
  <a href="README.sk.md"><b>Slovenčina</b></a>
</p>

---

## 🌟 Kľúčové architektonické prednosti

* **Čistá multiplexorová dátová cesta (Zero Tri-State / bez Hi-Z):**
  Vnútorná dátová cesta je kompletne zbavená tretieho stavu (`Hi-Z`). Tok dát je riadený výhradne aktívnymi selektormi (`MUX 1`, `DEST-DMUX`, `MUX 2`). Tým sa eliminujú priečne prúdy, zbernicové kolízie a parazitné kapacity. Architektúra je optimálna pre syntézu do moderných FPGA a ASIC.
* **Rozšírené lineárne 24-bitové adresovanie pamäte a zásobníka (až 16 MB):**
  Hardvérová podpora vyhradených 24-bitových registrov:
  * **`PTREG` (Pointer Register):** Priame lineárne adresovanie 16 MB pamäte s voliteľným hardvérovým autoincrementom (`AIP`).
  * **`SREG` (Stack Register):** 24-bitový ukazovateľ zásobníka pre volania podprogramov a hlboké rekurzívne rámce.
* **Dvojitý akumulátorový uzol (`ACCA` a `ACCB`):**
  Vstupné registre pred ALU stabilizujú operandy a izolujú prechodové javy výpočtov od hlavného registrového poľa (`R0–R7`).
* **Priamy premosťovací kanál medzi registrami (Reg-to-Reg Bypass):**
  Priama dátová cesta z `MUX 1` priamo do `MUX 2` zabezpečuje presun dát (`LRR / MOV`) v jedinom takte bez zaťažovania a blokovania ALU.
* **Hardvérové reťazenie dlhej aritmetiky (ALU Auto-Chaining):**
  Aritmetická jednotka integruje vnútorný zvyškový register (`ALU_RESIDUAL`):
  * **Reťazené sčítanie (`ADD`):** Ak súčet $> 2^{16}-1$, prenos (`+1`) sa zachytí a automaticky pripočíta pri nasledujúcom `ADD`.
  * **Reťazené odčítanie (`SUB`):** Ak je rozdiel $< 0$, výpožička (`-1`) sa zapamätá a automaticky odpočíta pri nasledujúcom `SUB`.
  * **Reťazené násobenie (`MUL`):** Spodných 16 bitov sa zapíše do cieľa; horných 16 bitov sa uloží do `ALU_RESIDUAL` a môže byť pripočítaných v nasledujúcich operáciách.
  * **Reťazené delenie (`DIV`):** Podiel sa zapíše do cieľového registra; zvyšok (modulo) sa zachová v `ALU_RESIDUAL`.
  * **Vyprázdnenie reťazca (`NOP`):** Inštrukcia `NOP` vymaže `ALU_RESIDUAL` a resetuje príznaky prenosu/výpožičky pred novými nezávislými výpočtami.
* **Vysoký frekvenčný potenciál:**
  Navrhnuté pre základnú frekvenciu **200~MHz**, so škálovaním na **700~MHz a viac** v moderných kremíkových štruktúrach (ASIC).

---

## 📑 Oficiálna technická dokumentácia

Úplné PDF špecifikácie pripravené na tlač sa nachádzajú v priečinku [`Docs/`](Docs/):

| Jazyk | Zdrojový kód LaTeX | Skompilovaná PDF špecifikácia |
| :--- | :--- | :--- |
| **Slovenčina** | [`Docs/LIM_M2_Datasheet_SK.tex`](Docs/LIM_M2_Datasheet_SK.tex) | [**Stiahnuť PDF (SK)**](Docs/LIM_M2_Datasheet_SK.pdf) |
| **English** | [`Docs/LIM_M2_Datasheet_EN.tex`](Docs/LIM_M2_Datasheet_EN.tex) | [**Stiahnuť PDF (EN)**](Docs/LIM_M2_Datasheet_EN.pdf) |
| **Українська** | [`Docs/LIM_M2_Datasheet_UA.tex`](Docs/LIM_M2_Datasheet_UA.tex) | [**Stiahnuť PDF (UA)**](Docs/LIM_M2_Datasheet_UA.pdf) |
| **Русский** | [`Docs/LIM_M2_Datasheet_RU.tex`](Docs/LIM_M2_Datasheet_RU.tex) | [**Stiahnuť PDF (RU)**](Docs/LIM_M2_Datasheet_RU.pdf) |

---

## 🗃️ Architektonický registrový súbor

| Register | Šírka | Architektonický účel |
| :--- | :---: | :--- |
| **`R0` – `R7`** | 16 bitov | Registre všeobecného určenia (GPR). Rýchle čítanie cez `MUX 1`, riadený zápis cez `WB_DATA`. |
| **`SREG`** | **24 bitov** | Systémový zásobníkový register. Lineárne 24-bitové adresovanie zásobníka až do 16 MB. |
| **`PTREG`** | **24 bitov** | Rozšírený ukazovateľový register. Lineárne adresovanie pamäte až do 16 MB s autoincrementom (`AIP`). |
| **`FREG`** | 16 bitov | Stavový a riadiaci register procesora. Združuje aritmetické príznaky a systémové režimy. |
| **`ACCA` / `ACCB`** | 16 bitov | Pomocné akumulátory ALU. Predradené vstupy pre operandy A a B. |

### Bitová mapa príznakového registra (`FREG`)

```text
 15   14   13   12   11   10    9    8    7    6    5    4    3    2    1    0
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|AIP |SBIT|SMOD|DBIT|M24 |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
```

* **`ZF` (0):** Príznak nuly (Zero Flag).
* **`CF` (1):** Príznak prenosu / výpožičky (Carry Flag).
* **`OF` (2):** Príznak pretečenia (Overflow Flag).
* **`EM` (3):** Hardvérová chyba matematických operácií (Error Math: delenie nulou).
* **`CMP` (4–5):** Výsledok 2-bitového hardvérového komparátora (`<`, `=`, `>`).
* **`CLK` (6–7):** Režim deličky hodinovej frekvencie.
* **`PIE` (8):** Povolenie programových prerušení.
* **`MIE` (9):** Povolenie maskovateľných prerušení.
* **`DWR` (10):** Vynútený prenos bez čakania na zbernicu.
* **`M24` (11):** Povolenie 24-bitového rozšíreného adresného režimu.
* **`DBIT` (12):** Vyrovnávacia pamäť posledného vysunutého bitu.
* **`SMOD` / `SBIT` (13–14):** Konfigurácia vkladania bitov pri posunoch.
* **`AIP` (15):** Autoincrement ukazovateľa `PTREG` pri prístupe k pamäti.

---

## ⚡ Inštrukčný súbor procesora (ISA - 32 Inštrukcií)

| Kód | Hex | Mnemonic | Trieda | Popis operácie |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Riadenie | Prázdna operácia; vyprázdnenie `ALU_RESIDUAL` a reset reťazenia |
| **00001** | `0x01` | **`ADD`** | Aritmetika | 16-bitové sčítanie s automatickým reťazením prenosu cez `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Aritmetika | 16-bitové odčítanie s automatickým reťazením výpožičky cez `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Aritmetika | Celočíselné násobenie; horných 16 bitov zachytených v `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Aritmetika | Celočíselné delenie; zvyšok (modulo) uložený v `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Pamäť | Načítanie slova z pamäte do registra (podpora 24-bitového `PTREG`) |
| **00110** | `0x06` | **`LRM`** | Pamäť | Zápis slova registra do systémovej pamäte |
| **00111** | `0x07` | **`LRR`** | Presun | Rýchle kopírovanie medzi registrami cez obchádzku `MUX 1` $\to$ `MUX 2` |
| **01000** | `0x08` | **`CMP`** | Porovnanie | Hardvérové porovnanie; aktualizuje `FREG.CMP`, `ZF`, `CF`, `OF` bez zmeny dát |
| **01001** | `0x09` | **`JMP`** | Skok | Nepodmienený skok (16-bitový lokálny alebo 24-bitový cez `PTREG`) |
| **01010** | `0x0A` | **`JCR`** | Skok | Podmienený skok pri príznaku prenosu (`CF == 1`) |
| **01011** | `0x0B` | **`JNZ`** | Skok | Podmienený skok pri nenulovom stave (`ZF == 0`) |
| **01100** | `0x0C` | **`JZ`** | Skok | Podmienený skok pri nulovom stave (`ZF == 1`) |
| **01101** | `0x0D` | **`AND`** | Logika | Bitový logický súčin (AND) |
| **01110** | `0x0E` | **`OR`** | Logika | Bitový logický súčet (OR) |
| **01111** | `0x0F` | **`NAND`** | Logika | Bitová negácia logického súčinu (NAND) |
| **10000** | `0x10` | **`NOR`** | Logika | Bitová negácia logického súčtu (NOR) |
| **10001** | `0x11` | **`NOT`** | Logika | Bitová inverzia operandu (jednotkový doplnok) |
| **10010** | `0x12` | **`XOR`** | Logika | Bitová neverzia (XOR) |
| **10011** | `0x13` | **`XNOR`** | Logika | Bitová ekvivalencia |
| **10100** | `0x14` | **`INC`** | Aritmetika | Hardvérová inkrementácia o 1 |
| **10101** | `0x15` | **`DEC`** | Aritmetika | Hardvérová dekrementácia o 1 |
| **10110** | `0x16` | **`PUSH`** | Zásobník | Uloženie slova do 24-bitového zásobníka (`SREG <- SREG - 2`) |
| **10111** | `0x17` | **`POP`** | Zásobník | Výber slova z 24-bitového zásobníka (`SREG <- SREG + 2`) |
| **11000** | `0x18` | **`BSL`** | Posuny | Barelový posun doľava s ukladaním do `FREG.DBIT` |
| **11001** | `0x19` | **`BSR`** | Posuny | Barelový posun doprava s ukladaním do `FREG.DBIT` |
| **11010** | `0x1A` | **`CSRM`** | Systém | Prístup k systémovým registrom (`FREG`, `PTREG`, `SREG`) |
| **11011** | `0x1B` | **`RSV27`** | Rezerva | Slot pre vektorové inštrukcie (SIMD) |
| **11100** | `0x1C` | **`RSV28`** | Rezerva | Slot pre rozšírené adresovanie |
| **11101** | `0x1D` | **`RSV29`** | Rezerva | Slot koprocesora s pohyblivou rádovou čiarkou (FPU) |
| **11110** | `0x1E` | **`RSV30`** | Rezerva | Slot pre kryptografický akcelerátor |
| **11111** | `0x1F` | **`RSV31`** | Rezerva | Slot pre budúce rozšírenia architektúry |

---

## 🚀 Rýchly štart a simulácia

### 1. Spustenie simulátora

```bash
# Interaktívny terminálový monitor
python3 sim/sim.py sim/demo.hex -i
```

### 2. Kompilácia PDF špecifikácií

```bash
cd Docs
chmod +x compile_datasheets.sh
./compile_datasheets.sh
```

---

## 📜 Autori a stav projektu

* **Autor architektúry:** Ivan Hniedash
* **Stav:** Oficiálny architektonický štandard jadra LIM M2 (Revízia 0.2)
