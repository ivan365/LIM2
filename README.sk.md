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
* **`CMP` (4–5):** Výsledok hardvérového komparátora `cmp_flags` (`00`: počiatočný reset / neporovnané / chyba; `01`: operand-1 < operand-2; `10`: operand-1 == operand-2; `11`: operand-1 > operand-2).
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

## 📐 Formát strojových inštrukcií a bitové dekódovanie

Procesor LIM M2 implementuje čistú, ortogonálnu schému kódovania inštrukcií s deterministickým dekódovaním:
* **Univerzálna architektonická syntax:** Najprv cieľový register (kam), a až potom zdrojové operandy (odkiaľ):
  * **Aritmetika (3 operandy):** `ADD Rd, Rs1, Rs2` $\implies \text{Rd} = \text{Rs1} + \text{Rs2}$
  * **Logika (2 operandy):** `AND Rd, Rs` $\implies \text{Rd} = \text{Rd} \ \& \ \text{Rs}$
  * **Unárne (1 bajt, 1 operand):** `NOT Rd`, `INC Rd`, `DEC Rd`
  * **Presun:** `LRR Rd, Rs` $\implies \text{Rd} = \text{Rs}$ (kopírovanie z bodu B do bodu A)
  * **Komparátor:** `CMP Rs1, Rs2` $\implies$ nastavuje `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`, `00`: reset/chyba)
* **Priame kódovanie prvého argumentu a modifikátorov:** 5-bitový opkód v bitoch `[7:3]` oktetu 0, a bity `[2:0]` priamo kódujú prvý registrový argument (`Rd` / `Rs1` / `Rs`) v aritmetike, logike, presunoch, porovnávaní a zásobníkových operáciách, alebo modifikátory adresácie/riadenia (`CFG` / `MOD` / `SZ:Mode`), kde je to aplikovateľné.

### Univerzálna bitová šablóna
```
+------------------------+-------------------+------------------------------------------+
|      OPCODE [7:3]      |   Rd / CFG [2:0]  | Operandy a argumenty (dynamická dĺžka)   |
|        (5 bitov)       |     (3 bity)      |             (0 až 3 oktety)              |
+------------------------+-------------------+------------------------------------------+
  Bit 7                3   Bit 2           0   Bajt 1 ... Bajt 3 (voliteľné)
```

### 10 tried inštrukcií a štruktúra polí

1. **Trieda I: Jednobajtové inštrukcie (1 bajt, 0 dodatočných bajtov)**
   * `NOP`, `HALT`, `CLI`, `STI`, `RET` (`CFG = 000`)
   * `NOT Rd`, `INC Rd`, `DEC Rd` (`Bity [2:0] = Rd` priamo určujú register, druhý bajt zo zbernice pamäte sa nenačítava)
   ```
   Oktet 0: [ OPCODE (5b) | Rd / 000 (3b) ]
   ```

2. **Trieda II: Trojoperandová aritmetika (2 bajty)**
   * `ADD`, `SUB`, `MUL`, `DIV`, `MOD` (`Rd = Rs1 op Rs2`)
   ```
   Oktet 0: [ OPCODE (5b) | Rd [2:0] (Cieľ) ]
   Oktet 1: [ Rs1 [7:5] (Zdroj 1) | Rs2 [4:2] (Zdroj 2) | RSV=00 [1:0] ]
   ```

3. **Trieda III: Dvojoperandová logika (2 bajty)**
   * `AND`, `OR`, `NAND`, `NOR`, `XOR`, `XNOR` (`Rd = Rd op Rs`)
   ```
   Oktet 0: [ OPCODE (5b) | Rd [2:0] (Cieľ/Op1) ]
   Oktet 1: [ Rs [7:5] (Zdroj 2) | RSV=00000 [4:0] ]
   ```

4. **Trieda IV: Medziregistrový presun LRR (2 bajty)**
   * `LRR Rd, Rs`: priame kopírovanie zo zdroja (bod B, `Rs`) do cieľa (bod A, `Rd`) cez premosťovací kanál `MUX 1` $\to$ `MUX 2` (1 cyklus, `FREG` sa nemení).
   ```
   Oktet 0: [ 00111 (5b) | Rd [2:0] (Cieľ) ]
   Oktet 1: [ Rs [7:5] (Zdroj) | RSV=00000 [4:0] ]
   ```

5. **Trieda V: Hardvérový komparátor CMP (2 bajty)**
   * `CMP Rs1, Rs2`: nedeštruktívne porovnanie s nastavením `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`, `00`: reset/chyba).
   ```
   Oktet 0: [ 01000 (5b) | Rs1 [2:0] (Operand 1) ]
   Oktet 1: [ Rs2 [7:5] (Operand 2) | RSV=00000 [4:0] ]
   ```

6. **Trieda VI: Hardvérový posun na D-klopných obvodoch (2 bajty, taktovaný cyklus)**
   * `BSL Rd, shift` a `BSR Rd, shift`: iteratívny posuvný register na 16 D-klopných obvodoch ($\approx 300$ tranzistorov namiesto $\approx 30\,000$ pri maticovom posúvači).
   * **Taktované vykonávanie v hardvéri:** posun o 16 bitov trvá o 15 taktov viac než posun o 1 bit (1 takt na 1 bit).
   * Riadené príznakmi `FREG.SMOD` (`1`: rotácia cez `DBIT`, `0`: nulovanie) a `FREG.DBIT` (uchováva posledný vytlačený bit).
   ```
   Oktet 0: [ OPCODE (5b) | Rd [2:0] (Posúvaný register R0--R7) ]
   Oktet 1: [ Počítadlo taktov shift [7:0] (0--16 taktov / bitov) ]
   ```

7. **Trieda VII: Operácie so zásobníkom (2 bajty)**
   * `PUSH Rs` a `POP Rd`: slovný prenos so zásobníkom cez 24-bitový ukazovateľ `SREG`.
   ```
   Oktet 0: [ OPCODE (5b) | Rs / Rd [2:0] (Register R0--R7) ]
   Oktet 1: [ RSV=00000000 [7:0] ]
   ```

8. **Trieda VIII: Manipulácia so špeciálnymi registrami (2 bajty)**
   * `MSP sreg, [op], args`: priame načítanie/zápis alebo funkčná modifikácia `FREG` (00) alebo 24-bitového `PTREG` (01).
   ```
   Oktet 0: [ 11010 (5b) | Mode (1b: 0=Načítanie, 1=Modifikácia) | SREG (2b: 00=FREG, 01=PTREG) ]
   Oktet 1 (Načítanie):    [ Rs [7:5] (FREG) alebo Rs_hi [7:5] | Rs_lo [4:2] (PTREG) | RSV [1:0] ]
   Oktet 1 (Modifikácia):  [ OP [7:6] (FREG: AND/OR/XOR/XNOR; PTREG: ADD/SUB) | Rs [5:3] (Maska/Posun) | RSV [2:0] ]
   ```

9. **Trieda IX: Inštrukcie vetvenia a skokov (2--3 bajty)**
   * `JMP`, `JCR`, `JNZ`, `JZ`:
     * `MOD = 0` (000): 16-bitová priama adresa (spolu 3 bajty).
     * `MOD = 1` (001): Nepriamy registrový skok cez `Rs` (spolu 2 bajty).
     * `MOD = 2` (010): 24-bitový skok cez systémový ukazovateľ `PTREG`.

10. **Trieda X: Inštrukcie výmeny s pamäťou LMR a LRM (2--4 bajty)**
    * `LMR Rd, <SRC_MODE>` a `LRM Rs, <DST_MODE>`:
      * Bit 2 oktetu 0: `SZ` ($0 = 8$ bitov / bajt, $1 = 16$ bitov / slovo).
      * Bits 1–0 oktetu 0: `Mode` (0 = Inline dáta za kódom, 1 = Imm ukazovateľ, 2 = 24-bitový `PTREG` s autoincrementom, 3 = Dvojica registrov 24-bitovej adresy).

---

## ⚡ Inštrukčný súbor procesora (ISA - 32 Inštrukcií)

| Kód | Hex | Mnemonic | Trieda | Popis operácie |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Riadenie | Prázdna operácia; vyprázdnenie `ALU_RESIDUAL` a reset reťazenia |
| **00001** | `0x01` | **`ADD`** | Aritmetika | 16-bitové sčítanie s automatickým reťazením prenosu cez `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Aritmetika | 16-bitové odčítanie s automatickým reťazením výpožičky cez `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Aritmetika | Celočíselné násobenie; horných 16 bitov zachytených v `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Aritmetika | Celočíselné delenie; zvyšok (modulo) uložený v `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Pamäť | Načítanie bajtu/slova do registra (zdroj: 0=Imm, 1=Ptr, 2=PTREG, 3=Dvojica registrov 24-bit; veľkosť: 8/16 bit) |
| **00110** | `0x06` | **`LRM`** | Pamäť | Zápis bajtu/slova do pamäte (cieľ: 0=Inline, 1=Ptr, 2=PTREG, 3=Dvojica registrov 24-bit; veľkosť: 8/16 bit) |
| **00111** | `0x07` | **`LRR`** | Presun | Rýchle kopírovanie medzi registrami cez obchádzku `MUX 1` $\to$ `MUX 2` |
| **01000** | `0x08` | **`CMP`** | Porovnanie | Hardvérové porovnanie; aktualizuje `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`), `ZF`, `CF`, `OF` bez zmeny dát |
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
| **11010** | `0x1A` | **`MSP`** | Systém | Manipulácia so špeciálnymi registrami (`FREG`, `PTREG`) |
| **11011** | `0x1B` | **`MOD`** | Aritmetika | Výpočet zvyšku po delení (modulo): `Rd = Rs1 % Rs2` |
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

## 📐 Jednotná filozofia formátu inštrukcií (Destination First)

V architektúre procesora LIM M2 je zavedený striktný a jednotný koncept poradia operandov:

> **Najprv sa vždy uvádza cieľový príjemca (KAM / Destination), a až potom vstupné operandy (ODKIAĽ / Sources).**

* **Aritmetika (3 operandy):** `ADD Rd, Rs1, Rs2` znamená $\text{Rd} = \text{Rs1} + \text{Rs2}$ (napríklad `ADD R0, R1, R2` vypočíta $R0 = R1 + R2$). Rovnako pre: `SUB`, `MUL`, `DIV`.
* **Logika (2 operandy):** `AND Rd, Rs` znamená $\text{Rd} = \text{Rd} \ \& \ \text{Rs}$ (napríklad `AND R0, R1` vypočíta $R0 = R0 \ \& \ R1$). Rovnako pre: `OR`, `NAND`, `NOR`, `XOR`, `XNOR`.
* **Jednobajtové unárne inštrukcie (1 operand):** `INC Rd` ($\text{Rd} = \text{Rd} + 1$), `DEC Rd` ($\text{Rd} = \text{Rd} - 1$) a `NOT Rd` ($\text{Rd} = \sim\text{Rd}$). Modifikujú jediný register `Rd` na mieste. Kódujú sa presne v 1 bajte (`[7:3]` opkód, `[2:0]` Rd), druhý bajt z pamäte sa nenačítava.
* **Medziregistrový presun:** `LRR Rd, Rs` znamená prenos z bodu B (zdroj `Rs`) do bodu A (príjemca `Rd`): $\text{Rd} = \text{Rs}$ (napríklad `LRR R0, R1` vykoná $R0 = R1$).
* **Načítanie z pamäte:** `LMR Rd, ...` ukladá načítané dáta do prvého argumentu `Rd`.

---

## 📥 Architektúra inštrukcie LMR (Load Memory to Register)

Inštrukcia **`LMR`** (`Opcode 00101` / `0x05`) slúži na načítanie dát z externého prostredia a pamäte do interných používateľských registrov procesora (`R0`–`R7`). Vyznačuje sa konfigurovateľným kódovaním a hardvérovou podporou 24-bitového adresovania (až 16 MB).

### 1. Bitový formát inštrukcie
Inštrukcia pozostáva z dvoch základných oktetov (bajtov):

```text
Oktet 0 (Opkód a Režim):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   0   1 |  SRC  |SZ |
+---+---+---+---+---+---+---+---+
 \_____ 5 bitov ___/ \_2b._/ \1b/

Oktet 1 (Registrové argumenty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (R_hi/Dst)  |   Arg2    | 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bity _____/ \_ 3 bity _/ \_2b._/
```

* **Veľkosť dát (`SZ`, bit 0 oktetu 0):**
  * `0`: Načítanie **1 bajtu** (8 bitov). Spodný bajt cieľového registra prevezme hodnotu, horný bajt sa vynuluje (`{8'b0, data[7:0]}`).
  * `1`: Načítanie **2 bajtov** (16 bitov / strojové slovo).
* **Zdroj dát (`SRC`, bity [2:1] oktetu 0):**
  * `00` (`0`): **Priame dáta (Immediate Data)** — dáta sa nachádzajú v pamäti priamo za kódom inštrukcie (`[PC]`). Čítač inštrukcií `PC` sa automaticky posunie o $1$ alebo $2$ bajty.
  * `01` (`1`): **Priamy ukazovateľ (Immediate Pointer)** — bezprostredne za inštrukciou je uložená absolútna adresa (`[[PC]]`), z ktorej sa vykoná výber dát z pamäte.
  * `10` (`2`): **Ukazovateľ `PTREG`** — čítanie prebieha podľa 24-bitovej systémovej adresy z registra `PTREG`. Pri aktívnom príznaku autoincrementu `FREG.AIP` (bit 12) sa `PTREG` automaticky zvýši o veľkosť výberu (+1 alebo +2), čo umožňuje prúdové načítanie polí.
  * `11` (`3`): **Dvojica používateľských registrov (24-bitové adresovanie cez 32-bitové číslo)** — používateľ zvolí dva 16-bitové registre (`Arg1` a `Arg2`), ktoré spolu vytvárajú 32-bitové zložené číslo, z ktorého sa v praxi adresovania využíva dolných 24 bitov:
    * **`Arg1` (bity [7:5] oktetu 1):** nesie **horné bity adresy**. Tento register je zároveň cieľovým registrom určenia: po výbere dát z pamäte sa horné bity adresy v ňom **prepíšu načítanými dátami**!
    * **`Arg2` (bity [4:2] oktetu 1):** nesie **dolných 16 bitov adresy** a uchováva si svoju pôvodnú hodnotu.
    * Fyzická 24-bitová adresa sa syntetizuje hardvérovo:
      $$\text{EA}[23:0] = ((\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]) \;\&\; \text{0xFFFFFF}$$
    * Načítané dáta sa uložia do `Arg1`.

---

## 📤 Architektúra inštrukcie LRM (Load Register to Memory)

Inštrukcia **`LRM`** (`Opcode 00110` / `0x06`) zabezpečuje symetrické ukladanie dát z registrov procesora do systémovej pamäte alebo externého adresného priestoru. Zničenie (prepísanie) dát alebo kódu na cieľovej adrese je plnou zodpovednosťou programátora!

### 1. Bitový formát inštrukcie
Inštrukcia pozostáva z dvoch základných oktetov (bajtov):

```text
Oktet 0 (Opkód a Režim cieľa):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   1   0 |  DST  |SZ |
+---+---+---+---+---+---+---+---+
 \_____ 5 bitov ___/ \_2b._/ \1b/

Oktet 1 (Registrové argumenty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (Rs/R_hi)   |   Arg2    | 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bity _____/ \_ 3 bity _/ \_2b._/
```

* **Veľkosť ukladaných dát (`SZ`, bit 0 oktetu 0):**
  * `0`: Zápis **1 bajtu** (8 bitov). Do pamäte sa zapíše dolný bajt zdrojového registra (`Rs[7:0]`).
  * `1`: Zápis **2 bajtov** (16 bitov / strojové slovo `Rs[15:0]`).
* **Režim cieľa (`DST`, bity [2:1] oktetu 0):**
  * `00` (`0`): **Priamo do pamäte / kódu za inštrukciou (Inline Memory)** — dáta sa zapisujú priamo do oblasti pamäte nasledujúcej bezprostredne za opkódom inštrukcie (`[PC]`). Čítač inštrukcií `PC` sa automaticky posunie o $1$ alebo $2$ bajty. Slúži na samomodifikujúci sa kód a inicializáciu vložených vyrovnávacích pamätí. Prepísanie inštrukcií je na zodpovednosti programátora.
  * `01` (`1`): **Priamy ukazovateľ (Immediate Pointer)** — hneď za inštrukciou sa nachádza 16-bitová absolútna adresa (`[[PC]]`), na ktorú sa zapíše hodnota z `Arg1` (`Rs`).
  * `10` (`2`): **Ukazovateľ `PTREG`** — zápis prebieha podľa 24-bitovej fyzickej adresy z registra `PTREG`. Pri aktívnom príznaku autoinkrementu `FREG.AIP` (bit 12) sa `PTREG` automaticky zvýši o veľkosť dát (+1 alebo +2), čo zabezpečuje prúdový zápis polí.
  * `11` (`3`): **Dvojica používateľských registrov (24-bitové adresovanie cez 32-bitové číslo)**:
    * **`Arg1` (bity [7:5] oktetu 1):** nesie **horné bity adresy** a súčasne je **zdrojom dát** (`Rs`), ktoré sa zapisujú do pamäte.
    * **`Arg2` (bity [4:2] oktetu 1):** nesie **dolných 16 bitov adresy** (`Rs_lo`).
    * Fyzická 24-bitová adresa cieľa sa generuje hardvérovo:
      $$\text{EA}[23:0] = ((\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]) \;\&\; \text{0xFFFFFF}$$
    * Zápis hodnoty `Arg1` sa vykoná na adresu $\text{EA}$. Prepísanie cieľovej pamäte plne riadi programátor.

---

## 🔄 Architektúra inštrukcie LRR (Load Register to Register)

Inštrukcia **`LRR`** (`Opcode 00111` / `0x07`) predstavuje základnú bleskovú inštrukciu medziregistrového presunu dát medzi registrami všeobecného určenia (`R0`–`R7`) z bodu B (zdroj `Rs`) do bodu A (príjemca `Rd`).

### 1. Bitový formát inštrukcie
Inštrukcia pozostáva z dvoch oktetov (16 bitov):

```text
Oktet 0 (Opkód a Rezerva):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   1   1 | 0   0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 5 bitov ___/ \_ 3 bity _/

Oktet 1 (Registrové argumenty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (Rd, KAM)   | Arg2 (Rs, ODKIAĽ)| 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bity _____/ \_ 3 bity ______/ \_2b._/
```

* **Cieľový register (`Arg1` / `Rd`, bity [7:5] oktetu 1):** bod A (kam sa zapisujú dáta).
* **Zdrojový register (`Arg2` / `Rs`, bity [4:2] oktetu 1):** bod B (odkiaľ sa čítajú dáta).
* **Sémantika operácie:**
  $$\text{Rd} \leftarrow \text{Rs}$$
  Napríklad: `LRR R0, R1` $\implies R0 = R1$ (obsah registra `R1` sa skopíruje do `R0`).
* **Hardvérová implementácia:** Dáta prechádzajú cez priamu premosťovaciu multiplexorovú cestu `MUX 1` $\to$ `MUX 2` priamo do `DEST-DMUX` za 1 takt bez zaťaženia ALU. Príznaky registra `FREG` zostávajú nedotknuté.

---

## 💻 Referenčná príručka inštrukcií pre programátora (ISA Reference)

Architektúra LIM M2 dodržiava prísnu sémantiku **«Cieľ na prvom mieste» (Destination First)**. Vo všetkých viacooperandových inštrukciách je prvým argumentom (`arg0`) vždy cieľový register, do ktorého sa ukladá výsledok operácie.

V assembleri a v budúcom kompilátore sú univerzálne registre označené ako `R0`, `R1`, `R2`, `R3`, `R4`, `R5`, `R6`, `R7`.

### 1. Presun dát a pamäť
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`LRR`** | `LRR arg0(REG), arg1(REG) : arg0 = arg1` | `LRR R0, R1 ; R0 = R1` | Rýchle kopírovanie medzi registrami (bez zmeny príznakov). |
| **`LMR`** | `LMR arg0(REG), arg1(SRC_MODE) : arg0 = MEM[...]` | `LMR R0, R1, R2 ; R0 = MEM[{R0, R2}]` | Načítanie z pamäte do registra (Immediate, Pointer, PTREG alebo 24-bit pár registrov). |
| **`LRM`** | `LRM arg0(REG), arg1(DST_MODE) : MEM[...] = arg0` | `LRM R0, R1 ; MEM[{R0, R1}] = R0` | Uloženie hodnoty registra do pamäte (Inline, Pointer, PTREG alebo pár registrov). |
| **`PUSH`** | `PUSH arg0(REG) : SREG -= 2, MEM[SREG] = arg0` | `PUSH R0 ; Uloženie R0 do zásobníka` | Dekrement ukazovateľa zásobníka SREG o 2 a zápis slova. |
| **`POP`** | `POP arg0(REG) : arg0 = MEM[SREG], SREG += 2` | `POP R0 ; Výber slova zo zásobníka do R0` | Čítanie slova zo zásobníka do registra a inkrement SREG o 2. |

### 2. Aritmetika a porovnanie
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`ADD`** | `ADD arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 + arg2` | `ADD R0, R1, R2 ; R0 = R1 + R2` | Sčítanie dvoch 16-bitových čísel s aktualizáciou príznakov ZF, CF, OF. |
| **`SUB`** | `SUB arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 - arg2` | `SUB R0, R1, R2 ; R0 = R1 - R2` | Odčítanie operandov s nastavením príznakov výpožičky/nuly. |
| **`MUL`** | `MUL arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 * arg2` | `MUL R0, R1, R2 ; R0 = R1 * R2` | Bezznamienkové násobenie 16x16 bitov (vyššie bity vo FREG/DBIT). |
| **`DIV`** | `DIV arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 / arg2` | `DIV R0, R1, R2 ; R0 = R1 / R2` | Celočíselné delenie (delenie nulou vyvolá výnimku VEC 0). |
| **`INC`** | `INC arg0(REG) : arg0 = arg0 + 1` | `INC R0 ; R0 = R0 + 1` | 1-bajtová inštrukcia (`[7:3]` opkód, `[2:0]` Rd): inkrement registra o jednotku. |
| **`DEC`** | `DEC arg0(REG) : arg0 = arg0 - 1` | `DEC R0 ; R0 = R0 - 1` | 1-bajtová inštrukcia (`[7:3]` opkód, `[2:0]` Rd): dekrement registra o jednotku. |
| **`CMP`** | `CMP arg0(REG), arg1(REG) : compare(arg0, arg1)` | `CMP R0, R1 ; Porovnanie R0 a R1` | Hardvérové porovnanie bez zmeny dát. Nastavuje `FREG.CMP` (`01`: R0<R1, `10`: R0==R1, `11`: R0>R1; `00`: reset/chyba) a príznaky ZF, CF. |

### 3. Bitová logika
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`AND`** | `AND arg0(REG), arg1(REG) : arg0 = arg0 & arg1` | `AND R0, R1 ; R0 = R0 & R1` | Bitový logický súčin (2 operandy). |
| **`OR`** | `OR arg0(REG), arg1(REG) : arg0 = arg0 \| arg1` | `OR R0, R1 ; R0 = R0 \| R1` | Bitový logický súčet (2 operandy). |
| **`XOR`** | `XOR arg0(REG), arg1(REG) : arg0 = arg0 ^ arg1` | `XOR R0, R1 ; R0 = R0 ^ R1` | Bitová non-ekvivalencia (2 operandy, nulovanie pri R0==R1). |
| **`NOT`** | `NOT arg0(REG) : arg0 = ~arg0` | `NOT R0 ; R0 = ~R0` | 1-bajtová inštrukcia (`[7:3]` opkód, `[2:0]` Rd): bitová inverzia. |
| **`NAND`** | `NAND arg0(REG), arg1(REG) : arg0 = ~(arg0 & arg1)` | `NAND R0, R1 ; R0 = ~(R0 & R1)` | Bitový zápor súčinu NAND (2 operandy). |
| **`NOR`** | `NOR arg0(REG), arg1(REG) : arg0 = ~(arg0 \| arg1)` | `NOR R0, R1 ; R0 = ~(R0 \| R1)` | Bitový zápor súčtu NOR (2 operandy). |
| **`XNOR`** | `XNOR arg0(REG), arg1(REG) : arg0 = ~(arg0 ^ arg1)` | `XNOR R0, R1 ; R0 = ~(R0 ^ R1)` | Bitová ekvivalencia (2 operandy). |

### 4. Bitové posuny (s podporou SMOD a DBIT)
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`BSL`** | `BSL arg0(REG), arg1(IMM) : arg0 = arg0 << arg1` | `BSL R0, 4 ; Posun R0 doľava o 4 bity` | Iteratívny hardvérový posun doľava na mieste. Realizovaný cez hardvérový cyklus posuvného registra (1 takt na 1 bit, $\approx 300$ tranzistorov namiesto $\approx 30\,000$). Posun o 16 bitov trvá o 15 taktov viac než posun o 1 bit. Bajt 0: `[7:3]` opkód 11000, `[2:0]` Rd. Bajt 1: `[7:0]` shift (0--16). Cyklická rotácia pri `SMOD=1` (bit 15 sa vráti na bit 0); výplň aktuálnym `DBIT` (0 alebo 1) pri `SMOD=0`. Posledný vytlačený bit sa uloží do `FREG.DBIT`. |
| **`BSR`** | `BSR arg0(REG), arg1(IMM) : arg0 = arg0 >> arg1` | `BSR R0, 4 ; Posun R0 doprava o 4 bity` | Iteratívny hardvérový posun doprava na mieste. Realizovaný cez hardvérový cyklus posuvného registra (1 takt na 1 bit, $\approx 300$ tranzistorov namiesto $\approx 30\,000$). Posun o 16 bitov trvá o 15 taktov viac než posun o 1 bit. Bajt 0: `[7:3]` opkód 11001, `[2:0]` Rd. Bajt 1: `[7:0]` shift (0--16). Cyklická rotácia pri `SMOD=1` (bit 0 sa vráti na bit 15); výplň aktuálnym `DBIT` (0 alebo 1) pri `SMOD=0`. Posledný vytlačený bit sa uloží do `FREG.DBIT`. |

### 5. Skoky a podprogramy
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`JMP`** | `JMP target(IMM\|REG) : PC = target` | `JMP R0 ; Bezpodmienečný skok` | Bezpodmienečný skok na adresu v registri alebo konštante. |
| **`JZ`** | `JZ target(IMM\|REG) : if FREG.ZF == 1 then PC = target` | `JZ loop_end ; Skok ak ZF == 1` | Podmienený skok pri nulovom výsledku predchádzajúcej operácie. |
| **`CALL`** | `CALL target(IMM\|REG) : SREG -= 2, MEM[SREG] = PC, PC = target` | `CALL func ; Volanie podprogramu` | Uloženie návratovej adresy do zásobníka a skok na procedúru. |
| **`RET`** | `RET : PC = MEM[SREG], SREG += 2` | `RET ; Návrat z procedúry` | Vybratie návratovej adresy zo zásobníka do PC. |

### 6. Riadenie, prerušenia a systémové registre
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`NOP`** | `NOP : No Operation` | `NOP ; Vynechanie taktu` | Prázdny takt procesora. |
| **`HALT`** | `HALT : Zastavenie jadra do prerušenia` | `HALT ; Čakanie na hardvérovú udalosť` | Prechod jadra do úsporného režimu čakania na prerušenie. |
| **`CLI`** | `CLI : FREG.MIE = 0` | `CLI ; Zákaz prerušení` | Atomické nulovanie príznaku povolenia prerušení (kritická sekcia). |
| **`STI`** | `STI : FREG.MIE = 1` | `STI ; Povolenie prerušení` | Atomické nastavenie príznaku povolenia prerušení. |
| **`INTR`** | `INTR vec(IMM) : Hardvérové/softvérové prerušenie` | `INTR 4 ; Softvérové prerušenie VEC 4` | Vyvolanie vektora prerušenia s uložením PC a FREG do zásobníka. |
| **`RETI`** | `RETI : FREG = MEM[SREG], PC = MEM[SREG+2], SREG += 4` | `RETI ; Návrat z obsluhy` | Atomické obnovenie FREG (vynulovanie INTR na 0) a PC zo zásobníka. |
| **`MSP`** | `MSP sreg, [op], args : práca so špeciálnymi registrami` | `MSP FREG, OR, R0 ; FREG = FREG \| R0` | Priamy zápis FREG/PTREG, bitové masky FREG (AND/OR/XOR/XNOR) alebo lokálny posun PTREG (ADD/SUB). |

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
