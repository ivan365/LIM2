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
 15    14    13    12   11   10    9    8    7    6    5    4    3    2    1    0
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|INTR |SMOD |DBIT |AIP |M24 |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
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
* **`AIP` (12):** Autoincrement ukazovateľa `PTREG` pri prístupe k pamäti.
* **`DBIT` (13):** Záchytný register pre bit vysunutý pri posune.
* **`SMOD` (14):** Režim posunu (`0`: nulovanie; `1`: cyklický priechod cez `DBIT`).
* **`INTR` (15):** Príznak vykonávania prerušenia (`1`: procesor obsluhuje prerušenie; ďalšie prerušenia zablokované).

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
| **11000** | `0x18` | **`BSL`** | Posuny | Barelový posun doľava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11001** | `0x19` | **`BSR`** | Posuny | Barelový posun doprava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11010** | `0x1A` | **`CSRM`** | Systém | Prístup k systémovým registrom (`FREG`, `PTREG`, `SREG`) |
| **11011** | `0x1B` | **`RSV27`** | Rezerva | Slot pre vektorové inštrukcie (SIMD) |
| **11100** | `0x1C` | **`RSV28`** | Rezerva | Slot pre rozšírené adresovanie |
| **11101** | `0x1D` | **`RSV29`** | Rezerva | Slot koprocesora s pohyblivou rádovou čiarkou (FPU) |
| **11110** | `0x1E` | **`RSV30`** | Rezerva | Slot pre kryptografický akcelerátor |
| **11111** | `0x1F` | **`RSV31`** | Rezerva | Slot pre budúce rozšírenia architektúry |

---

## 🔌 Fyzické rozhranie a 34-pinové zapuzdrenie

Procesor LIM M2 je zapuzdrený v štandardnom 34-pinovom dvojradovom puzdre, ktoré je navrhnuté pre maximálnu integritu signálov, odolnosť proti šumu a deterministické časovanie:

| Pin | Označenie | Smer | Funkčný popis |
| :---: | :--- | :---: | :--- |
| **1–8** | `A0`–`A7` | Výstup | Spodných 8 bitov 16-bitovej multiplexovanej adresovej zbernice |
| **9–16** | `A8`–`A15` | Výstup | Horných 8 bitov 16-bitovej multiplexovanej adresovej zbernice |
| **17** | `CLK1` | Vstup | Fáza 1 systémových hodín |
| **18** | `CLK2` | Vstup | Fáza 2 systémových hodín (bez vzájomného prekrytia) |
| **19** | `RDI` | Vstup | Raw Direct Interrupt: prioritná linka žiadosti o hardvérové prerušenie |
| **20** | `AL` | Výstup | Address Latch: riadiaci impulz záchytu adresy v externom registri |
| **21** | `RF` | Vstup | Ready Flag: potvrdenie pripravenosti podriadeného pamäťového/periférneho obvodu |
| **22** | `WD` | Výstup | Riadiaci impulz zápisu na zbernici (Write Enable) |
| **23** | `RD` | Výstup | Riadiaci impulz čítania zo zbernice (Read Enable) |
| **24** | `GND` | Napájanie | Spoločné systémové uzemnenie (0 V) |
| **25** | `VCC` | Napájanie | Napájacie napätie logiky jadra a vstupov/výstupov (+5 V nominálne) |
| **26** | **`IA`** | **Výstup** | **Interruption Accepted / Interrupt Acknowledge: potvrdenie prijatia prerušenia; jadro prepne `D0–D7` na vstup a očakáva číslo vektora** |
| **27–34** | `D7`–`D0` | Obojsmerný | 8-bitová obojsmerná zbernica pre prenos dát s pamäťou a perifériami |

---

## ⚡ Architektúra podsystému prerušení a vektorové spracovanie (16 vektorov)

Podsystém prerušení procesora LIM M2 zabezpečuje minimálnu latenciu odozvy reálneho času, subcyklovú arbitráciu a absolútnu ochranu pred zbernicovými kolíziami. Architektúra integruje externé požiadavky a interné softvérové pasce do jednotnej 16-vektorovej hierarchie:

### 1. Zjednotený 16-vektorový systémový priestor

| Vektor | Kód | Zdroj / Spúšťač | Architektonická úloha |
| :---: | :---: | :--- | :--- |
| **`VEC 0`** | `0x00` | Hardvérový / Reset | Power-on Reset: studená inicializácia registrov a zreťazenia jadra |
| **`VEC 1`** | `0x01` | Hardvérový (NMI) | Nemaskovateľné prerušenie: výpadok napájania, kritická hardvérová chyba |
| **`VEC 2`** | `0x02` | Softvérová pasca | Aritmetická výnimka (delenie nulou, príznak `FREG.EM`) |
| **`VEC 3`** | `0x03` | Softvérová pasca | Systémové volanie jadra OS (dispečer `Syscall / Trap`) |
| **`VEC 4`** | `0x04` | Hardvérový / Periféria | Takt systémového intervalového časovača |
| **`VEC 5`** | `0x05` | Hardvérový / Periféria | Sériové rozhranie UART (pripravenosť RX/TX) |
| **`VEC 6`** | `0x06` | Hardvérový / Periféria | Radič DMA (dokončenie blokového prenosu dát) |
| **`VEC 7`** | `0x07` | Hardvérový / Periféria | Externý radič prerušení / Zbernicový most |
| **`VEC 8–15`** | `0x08–0x0F` | Zdieľané (HW / SW) | Používateľské linky periférií a programové obslužné rutiny |

### 2. Cyklovo presný hardvérový handshake (`RDI` $\to$ `IA` $\to$ `D0–D7`)

Spracovanie externého prerušenia prebieha v deterministickom 5-krokovom hardvérovom cykle:
1. **Fáza žiadosti (`RDI`):** Periférne zariadenie nastaví aktívnu úroveň logickej 1 na vstupe `RDI`. Jadro testuje linku na hraniciach mikroinštrukcií.
2. **Vyhodnotenie masky a blokovania:** Pri povolených prerušeniach (`FREG.MIE == 1`) a ak procesor ešte nespracúva iné prerušenie (`FREG.INTR == 0`), procesor požiadavku potvrdí a dokončí aktuálnu mikrooperáciu. Ak `INTR == 1`, nové prerušenia sú zablokované.
3. **Strob potvrdenia (`IA`):** Jadro vygeneruje logickú 1 na vývode `IA` (pin 26), čím signalizuje perifériám pripravenosť prijať identifikátor vektora.
4. **Načítanie vektora (`D0–D7`):** Jadro prepne zbernicu `D0–D7` do stavu vysokej impedancie (vstup) a aktivuje signál `RD`. Zariadenie vystaví 8-bitový identifikátor vektora (spodné 4 bity adresujú vektory 0–15).
5. **Záchyt a prechod na vektor:** Procesor zachytí číslo vektora, deaktivuje `IA` a prejde k uloženiu kontextu.

### 3. Uloženie kontextu v 24-bitovom zásobníku (`SREG`)

Pri vstupe do obslužnej rutiny prerušenia:
1. **Uloženie návratového čítača (PC):**
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory}[\text{SREG}] \leftarrow \text{PC}_{15:0}$$
2. **Uloženie registra stavu a príznakov (`FREG`):** Uloží sa s pôvodným $\text{INTR} = 0$:
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory}[\text{SREG}] \leftarrow \text{FREG}$$
3. **Hardvérové blokovanie:** Nastaví sa `FREG.INTR` na `1` (bit 15) a `FREG.MIE` sa vynuluje na `0` pre zamedzenie kolízií vnorených prerušení.
4. **Skok:** Bázová adresa vektora sa zapíše do čítača inštrukcií `PC`.

### 4. Návrat z prerušenia

Ukončenie obsluhy obnoví pôvodný kontext procesora zo zásobníka:
1. $\text{FREG} \leftarrow \text{Memory}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$ (automaticky vynuluje `INTR` späť na `0` a obnoví `MIE`).
2. $\text{PC} \leftarrow \text{Memory}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$.
Vykonávanie prerušeného toku inštrukcií plynule pokračuje v nasledujúcom takte bez akejkoľvek straty údajov.

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
