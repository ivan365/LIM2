# Architektúra procesora LIM M2

<p align="center">
  <img src="LIM2%20Docs/images/lim2.png" alt="Schéma dátovej cesty LIM M2" width="850">
</p>

<p align="center">
  <b>Vysokovýkonné 16-bitové mikroprogramové jadro s čistým multiplexorovým smerovaním (Zero Tri-State) a lineárnym 32-bitovým adresovaním (4 GB)</b>
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
* **Natívne lineárne 32-bitové adresovanie pamäte a zásobníka (až 4 GB):**
  Hardvérová podpora vyhradených 32-bitových registrov:
  * **`PTREG` (Pointer Register):** Priame lineárne adresovanie 4 GB pamäte s voliteľným hardvérovým autoincrementom (`AIP`).
  * **`SREG` (Stack Register):** 32-bitový ukazovateľ zásobníka pre volania podprogramov a hlboké rekurzívne rámce.
  * **32 vektorových 32-bitových registrov:** 16 vektorov prerušení (`$ir0..$ir15`) a 16 registrov hraníc Zón Privilégií (`$pv0..$pv15`).
* **Dvojúrovňový model ochrany privilégií (User a Supervisor):**
  Hardvérové rozlíšenie práv podľa príznaku `PRV` (bit 11 v `FREG`) s hardvérovou kontrolou príslušnosti `PC` k jednej z 8 Zón Privilégií (`[$pv0:$pv1]`..`[$pv14:$pv15]`).
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

Úplná PDF špecifikácia pripravené na tlač sa nachádza v priečinku [`LIM2 Docs/`](LIM2%20Docs/):

| Jazyk | Zdrojový kód LaTeX | Skompilovaná PDF špecifikácia |
| :--- | :--- | :--- |
| **English** | [`LIM2 Docs/lim2_en.tex`](LIM2%20Docs/lim2_en.tex) | [**Stiahnuť PDF (EN)**](LIM2%20Docs/lim2_en.pdf) |

---

## 🗃️ Architektonický registrový súbor

| Register | Šírka | Architektonický účel |
| Register | Šírka | Podporované aliasy | Úloha v architektúre LIM M2 |
| :--- | :---: | :--- | :--- |
| **`R0` – `R7`** | 16 bitov | `$0`..`$7`, `R0`..`R7`, `$r0`..`$r7`, `0`..`7` | Registre všeobecného určenia (GPR). Rýchle čítanie cez `MUX 1`, riadený zápis cez `WB_DATA`. |
| **`SREG`** | **32 bitov** | `$sp`, `sp`, `$sreg`, `sreg` | Systémový zásobníkový register. Lineárne 32-bitové adresovanie zásobníka až do 4 GB. |
| **`PTREG`** | **32 bitov** | `$ptreg`, `ptreg` | Rozšírený ukazovateľový register. Lineárne adresovanie pamäte až do 4 GB s autoincrementom (`AIP`). |
| **`FREG`** | 16 bitov | `$freg`, `freg` | Stavový a riadiaci register procesora (bit 11: `PRV` — režim User/Supervisor). |
| **`ACCA` / `ACCB`** | 16 bitov | *Interné registre* | Pomocné akumulátory ALU. Predradené vstupy pre operandy A a B. |
| **`$ir0`..`$ir15`** | **32 bitov** | `$ir0`..`$ir15`, `ir0`..`ir15`, `$vec0`..`$vec15` | 16 vektorových registrov adries obsluhy prerušení IVT. |
| **`$pv0`..`$pv13`** | **32 bitov** | `$pv0`..`$pv13`, `pv0`..`pv13`, `$vec16`..`$vec29` | 14 vektorových registrov hraníc 7 párov Zón Privilégií (`[$pv0:$pv1]`..`[$pv12:$pv13]`). |
| **`$pv14`** | **32 bitov** | `$pv14`, `$ram_base`, `$ram_start`, `$rom_base`, `$vec30` | Dolná hranica adresného rozsahu pamäte RAM / ROM. |
| **`$pv15`** | **32 bitov** | `$pv15`, `$ram_limit`, `$ram_end`, `$rom_limit`, `$vec31` | Horná hranica adresného rozsahu pamäte RAM / ROM. |

### Bitová mapa príznakového registra (`FREG`)

```text
 15    14    13    12   11   10    9    8    7    6    5    4    3    2    1    0
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|INTR |SMOD |DBIT |AIP |PRV |DWR |MIE |SSRC|CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
```

* **`ZF` (0):** Príznak nuly (Zero Flag).
* **`CF` (1):** Príznak prenosu / výpožičky (Carry Flag).
* **`OF` (2):** Príznak pretečenia (Overflow Flag).
* **`EM` (3):** Hardvérová chyba matematických operácií (Error Math: delenie nulou).
* **`CMP` (4–5):** Výsledok hardvérového komparátora `cmp_flags` (`00`: počiatočný reset / neporovnané / chyba; `01`: operand-1 < operand-2; `10`: operand-1 == operand-2; `11`: operand-1 > operand-2).
* **`CLK` (6–7):** Režim deličky hodinovej frekvencie.
* **`SSRC` (8):** Zdroj bitu pri posune (0: nuly, 1: vyrovnávacia pamäť `DBIT`).
* **`MIE` (9):** Povolenie maskovateľných prerušení.
* **`DWR` (10):** Vynútený prenos bez čakania na zbernicu.
* **`PRV` (11):** Režim privilégií procesora (`0`: User Mode — bežný režim; `1`: Supervisor Mode — režim správcu/jadra). Zapnutý predvolene pri resete jadra (`PRV = 1`).
* **`AIP` (12):** Hardvérový autoincrement ukazovateľa `PTREG` pri prístupe k pamäti. Zapnutý predvolene (`AIP = 1`, pri resete `FREG = 0x1800`). Inkrementuje `PTREG` o **+1** (bajt pri `.b`), **+2** (slovo pri `.w`) a **+4** (32-bitový vektor/ukazovateľ pri `MSP.ld`).
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
   * `PUSH Rs` a `POP Rd`: slovný prenos so zásobníkom cez 32-bitový ukazovateľ `SREG`.
   ```
   Oktet 0: [ OPCODE (5b) | Rs / Rd [2:0] (Register R0--R7) ]
   Oktet 1: [ RSV=00000000 [7:0] ]
   ```

8. **Trieda VIII: Manipulácia so špeciálnymi registrami (2–6 bajtov)**
   * `MSP sreg, [op], args`: priame načítanie/zápis alebo funkčná modifikácia `FREG` (00), 32-bitového `PTREG` (01), 32-bitového ukazovateľa zásobníka `SREG` (10) alebo 32 vektorových 32-bitových registrov `VEC` (11: `$ir0..$ir15` vektorov prerušení a `$pv0..$pv15` chránených zón privilégií).
   ```
   Oktet 0: [ 11010 (5b) | Mode (1b: 0=Načítanie/LD, 1=Modifikácia) | SREG (2b: 00=FREG, 01=PTREG, 10=SREG, 11=VEC) ]
   Oktet 1 (VEC, 11):       [ Vector_ID [7:3] (0..31: ir0-15 / pv0-15) | Source [2:1] (00=Reg, 01=Imm32, 10=[$ptreg], 11=Ptr) | Sub/PtrType [0] ]
   Oktet 2 (VEC Reg/Ptr):   [ Rd_hi [7:5] (vyšších 16 bitov) | Rs_lo [4:2] (nižších 16 bitov) | RSV=00 [1:0] ] (pre Source=00 alebo 11-reg)
   Oktet 1 (FREG Načítanie):[ Rs [7:5] | RSV [4:3] | Source [2:1] | RSV [0] ]
   Oktet 1 (FREG Logika):   [ OP [7:6] (00=AND, 01=OR, 10=XOR, 11=XNOR) | Rs [5:3] / RSV | Source [2:1] | RSV [0] ]
   Oktet 1 (PTREG/SREG LD): [ Rd_hi [7:5] | Rs_lo [4:2] | Source [1:0] ]
   Oktet 1 (PTREG/SREG Ar): [ OP [7] (0=ADD, 1=SUB) | Rs [6:4] | Source [3:2] | RSV [1:0] ]
   ```

9. **Trieda IX: Inštrukcie vetvenia a skokov (2--5 bajtov / fused 7 bajtov)**
   * `JMP`, `JNZ`, `JZ`, `CALL`:
     * `MOD = 0` (000): Priama 32-bitová adresa (spolu 5 bajtov: 1 bajt opkód + 4 bajty adresy Little-Endian).
     * `MOD = 1` (001): Nepriamy registrový skok cez `Rs` (spolu 2 bajty).
     * `MOD = 2` (010): 32-bitový skok cez systémový ukazovateľ `PTREG` (spolu 2 bajty).
     * `MOD = 3` (011): 32-bitový nepriamy skok podľa ukazovateľa v pamäti `[addr32]` (spolu 5 bajtov: 1 bajt opkód + 4 bajty adresy Little-Endian, číta 32-bitovú adresu) alebo páru `[$rd:$rs]` (2 bajty).
   * `JCR` (Jump Compare Result, 5 bajtov):
     * Samostatný `JCR` (5 bajtov): testuje výsledok porovnania `CMP` v bitoch `[7:6]` registra `FREG`. Oktet 0 obsahuje opkód 10 a `CFG [2:0]`, za ním nasledujú 4 bajty cieľovej 32-bitovej adresy `target32` (Little-Endian).
     * Fused makro: `JCR $1 > $2, addr` (`CMP` + `JCR`, spolu 7 bajtov).

10. **Trieda X: Inštrukcie výmeny s pamäťou LMR a LRM (2--6 bajtov)**
    * `LMR Rd, <SRC_MODE>` a `LRM Rs, <DST_MODE>`:
      * Bit 2 oktetu 0: `SZ` ($0 = 8$ bitov / bajt, $1 = 16$ bitov / slovo).
      * Bits 1–0 oktetu 0: `Mode` (0 = Inline dáta za kódom [3–4 bajty], 1 = Priamy 32-bitový ukazovateľ `[addr32]` [6 bajtov: 2 bajty hlavička + 4 bajty adresy Little-Endian], 2 = 32-bitový `PTREG` s autoincrementom [2 bajty], 3 = Dvojica registrov 32-bitovej adresy [2 bajty]).

---

## ⚡ Inštrukčný súbor procesora (ISA - 32 Inštrukcií)

| Kód | Hex | Mnemonic | Trieda | Popis operácie |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Riadenie | Prázdna operácia; vyprázdnenie `ALU_RESIDUAL` a reset reťazenia |
| **00001** | `0x01` | **`ADD`** | Aritmetika | 16-bitové sčítanie s automatickým reťazením prenosu cez `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Aritmetika | 16-bitové odčítanie s automatickým reťazením výpožičky cez `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Aritmetika | Celočíselné násobenie; horných 16 bitov zachytených v `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Aritmetika | Celočíselné delenie; zvyšok (modulo) uložený v `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Pamäť | Načítanie bajtu/slova do registra (zdroj: 0=Imm, 1=Ptr, 2=PTREG, 3=Dvojica registrov 32-bit; veľkosť: 8/16 bit) |
| **00110** | `0x06` | **`LRM`** | Pamäť | Zápis bajtu/slova do pamäte (cieľ: 0=Inline, 1=Ptr, 2=PTREG, 3=Dvojica registrov 32-bit; veľkosť: 8/16 bit) |
| **00111** | `0x07` | **`LRR`** | Presun | Rýchle kopírovanie medzi registrami cez obchádzku `MUX 1` $\to$ `MUX 2` |
| **01000** | `0x08` | **`CMP`** | Porovnanie | Hardvérové porovnanie; aktualizuje `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`), `ZF`, `CF`, `OF` bez zmeny dát |
| **01001** | `0x09` | **`JMP`** | Skok | Bezpodmienečný 32-bitový skok (MOD=0 priamy 5 bajtov; MOD=1 registrový 2 bajty; MOD=2 cez PTREG 2 bajty; MOD=3 nepriamy [addr32] 5 bajtov) |
| **01010** | `0x0A` | **`JCR`** | Skok | 32-bitový podmienený skok podľa výsledku porovnania CMP (`<`, `<=`, `==`, `!=`, `>=`, `>`, 5 bajtov, fused makro: 7 bajtov) |
| **01011** | `0x0B` | **`JNZ`** | Skok | 32-bitový podmienený skok pri nenulovom stave (`ZF == 0`, 5 bajtov / 2 bajty) |
| **01100** | `0x0C` | **`JZ`** | Skok | 32-bitový podmienený skok pri nulovom stave (`ZF == 1`, 5 bajtov / 2 bajty) |
| **01101** | `0x0D` | **`AND`** | Logika | Bitový logický súčin (AND) |
| **01110** | `0x0E` | **`OR`** | Logika | Bitový logický súčet (OR) |
| **01111** | `0x0F` | **`NAND`** | Logika | Bitová negácia logického súčinu (NAND) |
| **10000** | `0x10` | **`NOR`** | Logika | Bitová negácia logického súčtu (NOR) |
| **10001** | `0x11` | **`NOT`** | Logika | Bitová inverzia operandu (jednotkový doplnok) |
| **10010** | `0x12` | **`XOR`** | Logika | Bitová neverzia (XOR) |
| **10011** | `0x13` | **`XNOR`** | Logika | Bitová ekvivalencia |
| **10100** | `0x14` | **`INC`** | Aritmetika | Hardvérová inkrementácia o 1 |
| **10101** | `0x15` | **`DEC`** | Aritmetika | Hardvérová dekrementácia o 1 |
| **10110** | `0x16` | **`PUSH`** | Zásobník | Uloženie slova do 32-bitového zásobníka (`SREG <- SREG - 2`) |
| **10111** | `0x17` | **`POP`** | Zásobník | Výber slova z 32-bitového zásobníka (`SREG <- SREG + 2`) |
| **11000** | `0x18` | **`BSL`** | Posuny | Barelový posun doľava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11001** | `0x19` | **`BSR`** | Posuny | Barelový posun doprava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11010** | `0x1A` | **`MSP`** | Systém | Manipulácia so špeciálnymi registrami (`FREG`, `PTREG`, `SREG`, `VEC`) |
| **11011** | `0x1B` | **`MOD`** | Aritmetika | Výpočet zvyšku po delení (modulo): `Rd = Rs1 % Rs2` |
| **11100** | `0x1C` | **`INTR`** | Systém | Softvérové prerušenie (2 bajty): najnižšie 4 bity 2. bajtu `[3:0]` vyberajú vektor `0..15` (`$ir0..$ir15`) |
| **11101** | `0x1D` | **`CALL`** | Skok | Volanie podprogramu s uložením 32-bitového PC a 16-bitového FREG do zásobníka (`SREG -= 4, MEM32[SREG] = PC; SREG -= 2, MEM16[SREG] = FREG`) |
| **11110** | `0x1E` | **`RET`** | Skok | Návrat z podprogramu s obnovením 16-bitového FREG a 32-bitového PC zo zásobníka (`FREG = MEM16[SREG], SREG += 2; PC = MEM32[SREG], SREG += 4`) |
| **11111** | `0x1F` | **`HALT`** | Riadenie | Hardvérové zastavenie jadra procesora (`HLT`) |

---

## 🔌 Fyzické rozhranie a 50-vývodové puzdro s natívnou 32-bitovou zbernicou adries

Procesor LIM M2 disponuje **natívnou 32-bitovou adresnou zbernicou (`A0–A31`)**, ktorá umožňuje priamy fyzický prístup k celému lineárnemu adresnému priestoru **4 Gigabajty**, a **8-bitovou (jednobajtovou) vonkajšou dátovou zbernicou (`D0–D7`)**.

Procesor sa vyrába v **50-vývodovom puzdre DIP-50 / QFP-52** (po 25 vývodov na každej strane, vytvorené pridaním po 8 pinov z oboch strán k pôvodnému 34-vývodovému puzdru):

| Piny | Označenie | Smer | Funkčný účel |
| :---: | :--- | :---: | :--- |
| **1–16** | `A0`–`A15` | Výstup | Dolných 16 bitov 32-bitovej natívnej zbernice adries |
| **17–24** | `A16`–`A23` | Výstup | Stredných 8 bitov zbernice adries (+8 pinov na ľavej strane) |
| **25** | `CLK1` | Vstup | Fáza 1 hodinovej synchronizácie jadra |
| **26** | `CLK2` | Vstup | Fáza 2 hodinovej synchronizácie jadra (bez vzájomného prekrytia) |
| **27** | `RESET` | Vstup | Hardvérový reset procesora (aktívny nízky) |
| **28** | `RDI` | Vstup | Raw Direct Interrupt: prioritná linka hardvérovej žiadosti o prerušenie |
| **29** | **`IA`** | **Výstup** | **Interrupt Acknowledge: potvrdenie prerušenia procesorom** |
| **30** | `RF` | Vstup | Ready Flag: potvrdenie pripravenosti pamäte/periférie |
| **31** | `WD` | Výstup | Zápisový strob zbernice (Write Enable) |
| **32** | `RD` | Výstup | Čítací strob zbernice (Read Enable) |
| **33** | `VCC` | Napájanie | Digitálne napájanie jadra (+3.3 V / +5 V) |
| **34** | `GND` | Napájanie | Systémové uzemnenie (0 V) |
| **35–42** | `D0`–`D7` | Obojsmerný | **8-bitová (jednobajtová) vonkajšia obojsmerná dátová zbernica pre pamäť a periférie** |
| **43–50** | `A24`–`A31` | Výstup | **Horných 8 bitov zbernice adries (+8 pinov na pravej strane, 4 GB adresovanie)** |

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

### 3. Uloženie kontextu v 32-bitovom zásobníku (`SREG`) a prechod do Supervisor Mode

Pri vstupe do obslužnej rutiny prerušenia:
1. **Uloženie návratového 32-bitového čítača (PC):**
   $$\text{SREG} \leftarrow \text{SREG} - 4, \quad \text{Memory32}[\text{SREG}] \leftarrow \text{PC}_{31:0}$$
2. **Uloženie registra stavu a príznakov (`FREG`):** Uloží sa s pôvodným `PRV` a $\text{INTR} = 0$:
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory16}[\text{SREG}] \leftarrow \text{FREG}$$
3. **Hardvérový prechod do Supervisor Mode:** Nastaví sa `FREG.PRV <- 1` (Supervisor Mode), `FREG.INTR <- 1` (bit 15) a `FREG.MIE <- 0` pre zamedzenie kolízií vnorených prerušení.
4. **Vektorový skok:** 32-bitová adresa obsluhy sa priamo načíta z `$ir0..$ir15` do čítača inštrukcií `PC`.

### 4. Návrat z prerušenia (`RTI`)

Ukončenie obsluhy obnoví pôvodný kontext procesora a režim privilégií:
1. $\text{FREG} \leftarrow \text{Memory16}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$ (automaticky obnoví pôvodný `PRV`, vynuluje `INTR` späť na `0` a obnoví `MIE`).
2. $\text{PC} \leftarrow \text{Memory32}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 4$.
Vykonávanie prerušeného toku inštrukcií plynule pokračuje v nasledujúcom takte bez akejkoľvek straty údajov v pôvodnom režime privilégií.

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

Inštrukcia **`LMR`** (`Opcode 00101` / `0x05`) slúži na načítanie dát z externého prostredia a pamäte do interných používateľských registrov procesora (`R0`–`R7`). Vyznačuje sa konfigurovateľným kódovaním a hardvérovou podporou 32-bitového adresovania (až 4 GB).

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
  * `10` (`2`): **Ukazovateľ `PTREG`** — čítanie prebieha podľa 32-bitovej systémovej adresy z registra `PTREG`. Pri aktívnom príznaku autoincrementu `FREG.AIP` (bit 12) sa `PTREG` automaticky zvýši o veľkosť výberu (+1 alebo +2), čo umožňuje prúdové načítanie polí.
  * `11` (`3`): **Dvojica používateľských registrov (32-bitové adresovanie cez pár registrov)** — používateľ zvolí dva 16-bitové registre (`Arg1` a `Arg2`), ktoré spolu vytvárajú 32-bitovú adresu:
    * **`Arg1` (bity [7:5] oktetu 1):** nesie **horných 16 bitov adresy**. Tento register je zároveň cieľovým registrom určenia: po výbere dát z pamäte sa horné bity adresy v ňom **prepíšu načítanými dátami**!
    * **`Arg2` (bity [4:2] oktetu 1):** nesie **dolných 16 bitov adresy** a uchováva si svoju pôvodnú hodnotu.
    * Fyzická 32-bitová adresa sa syntetizuje hardvérovo:
      $$\text{EA}[31:0] = (\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]$$
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
  * `10` (`2`): **Ukazovateľ `PTREG`** — zápis prebieha podľa 32-bitovej fyzickej adresy z registra `PTREG`. Pri aktívnom príznaku autoinkrementu `FREG.AIP` (bit 12) sa `PTREG` automaticky zvýši o veľkosť dát (+1 alebo +2), čo zabezpečuje prúdový zápis polí.
  * `11` (`3`): **Dvojica používateľských registrov (32-bitové adresovanie cez pár registrov)**:
    * **`Arg1` (bity [7:5] oktetu 1):** nesie **horných 16 bitov adresy** a súčasne je **zdrojom dát** (`Rs`), ktoré sa zapisujú do pamäte.
    * **`Arg2` (bity [4:2] oktetu 1):** nesie **dolných 16 bitov adresy** (`Rs_lo`).
    * Fyzická 32-bitová adresa cieľa sa generuje hardvérovo:
      $$\text{EA}[31:0] = (\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]$$
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
| **`LRR`** | `LRR arg0(REG), arg1(REG) : arg0 = arg1` | `LRR R0, R1 ; R0 = R1` | Rýchle kopírovanie medzi registrami (bez zmeny príznakov). |
| **`LMR`** | `LMR arg0(REG), arg1(SRC_MODE) : arg0 = MEM[...]` | `LMR R0, R1, R2 ; R0 = MEM[{R0, R2}]` | Načítanie z pamäte do registra (Immediate, Pointer, PTREG alebo 32-bit pár registrov). |
| **`LRM`** | `LRM arg0(REG), arg1(DST_MODE) : MEM[...] = arg0` | `LRM R0, R1 ; MEM[{R0, R1}] = R0` | Uloženie hodnoty registra do pamäte (Inline, Pointer, PTREG alebo 32-bit pár registrov). |
| **`PUSH`** | `PUSH arg0(REG) : SREG -= 2, MEM[SREG] = arg0` | `PUSH R0 ; Uloženie R0 do zásobníka` | Dekrement 32-bitového ukazovateľa zásobníka SREG o 2 a zápis slova. |
| **`POP`** | `POP arg0(REG) : arg0 = MEM[SREG], SREG += 2` | `POP R0 ; Výber slova zo zásobníka do R0` | Čítanie slova zo zásobníka do registra a inkrement 32-bitového SREG o 2. |

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
| **`CALL`** | `CALL target(IMM\|REG) : SREG -= 4, MEM32[SREG] = PC, PC = target` | `CALL func ; Volanie podprogramu` | Uloženie návratovej adresy do 32-bitového zásobníka a skok na procedúru. |
| **`RET`** | `RET : PC = MEM32[SREG], SREG += 4` | `RET ; Návrat z procedúry` | Vybratie návratovej adresy z 32-bitového zásobníka do PC. |

### 6. Riadenie, prerušenia a systémové registre
| Mnemotechnika | Signatúra programátora | Príklad kódu | Popis |
|---|---|---|---|
| **`NOP`** | `NOP : No Operation` | `NOP ; Vynechanie taktu` | Prázdny takt procesora. |
| **`HALT`** | `HALT : Zastavenie jadra do prerušenia` | `HALT ; Čakanie na hardvérovú udalosť` | Prechod jadra do úsporného režimu čakania na prerušenie. |
| **`CLI`** | `CLI : FREG.MIE = 0` | `CLI ; Zákaz prerušení` | Atomické nulovanie príznaku povolenia prerušení (kritická sekcia). |
| **`STI`** | `STI : FREG.MIE = 1` | `STI ; Povolenie prerušení` | Atomické nastavenie príznaku povolenia prerušení. |
| **`INTR`** | `INTR vec(IMM) : Hardvérové/softvérové prerušenie` | `INTR 4 ; Softvérové prerušenie VEC 4` | Vyvolanie vektora prerušenia s uložením PC a FREG do zásobníka. |
| **`RETI`** | `RETI : FREG = MEM16[SREG], PC = MEM32[SREG+2], SREG += 6` | `RETI ; Návrat z obsluhy` | Atomické obnovenie FREG (obnovenie PRV, vynulovanie INTR) a PC zo zásobníka. |
| **`MSP`** | `MSP sreg, [op], args : práca so špeciálnymi registrami` | `MSP FREG, OR, R0 ; FREG = FREG \| R0` | Priamy zápis FREG/PTREG/SREG/VEC, bitové masky FREG, lokálny posun PTREG/SREG alebo nastavenie vektorových registrov. |

---

## 🛠️ Jazyk symbolických inštrukcií (Assembler) a kompilátor LIM M2 (`limasm.py`)

Súčasťou SDK je oficiálny dvojprechodový kompilátor assemblera **`limasm.py`**, ktorý kompiluje zdrojové súbory `.asm` súčasne do binárneho obrazu (`.bin`) a anotovaného hexadecimálneho výpisu (`.hex`), pripraveného na nahratie do pamäťových zariadení cez `programmer.py` alebo priamu konfiguráciu zbernice.

### 1. Označovanie registrov a prípony veľkosti (`.b`, `.w`, `.d`)
* **Všeobecné registre (GPR):** zapisujú sa s prefixom `$` a číslom `$0`–`$7` (podporované sú aj klasické aliasy `R0`–`R7` a `$r0`–`$r7`).
* **Špeciálne registre:**
  * `$ptreg` — 32-bitový lineárny adresný ukazovateľ (`PTREG`, 4 GB);
  * `$freg` — 16-bitový register príznakov a stavu (`FREG`, bit 11: `PRV`);
  * `$sreg` (alebo `$sp`) — 32-bitový systémový ukazovateľ vrcholu zásobníka (`SREG`);
  * `$ir0`..`$ir15` — 16 vektorových 32-bitových registrov adries prerušení;
  * `$pv0`..`$pv15` — 16 vektorových 32-bitových registrov hraníc Zón Privilégií (8 rozsahov `[$pv0:$pv1]`..`[$pv14:$pv15]`).
* **Prípony veľkosti operandov:** inštrukcie pamäte `LMR` a `LRM` striktne podporujú dve hardvérové veľkosti (bit `SZ`):
  * `.b` (*byte*, 8 bitov / 1 bajt, `SZ=0`) — napr. `LMR.b $0, 0x42`, `LRM.b $0, [0x1000]`
  * `.w` (*word*, 16 bitov / 2 bajty, `SZ=1`, predvolené) — napr. `LMR.w $0, 0x1234` alebo `LMR $0, 0x1234`
  *(Inštrukcie `LMR` a `LRM` podporujú výhradne `.b` a `.w`; pre 32-bitové hodnoty sa používajú direktívy `dd` a `MSP.ld`).*

### 2. Registrové operácie ALU a unárne inštrukcie
3-operandové inštrukcie ALU (`ADD`, `SUB`, `MUL`, `DIV`, `MOD`) a 1-bajtové unárne inštrukcie (`INC`, `DEC`, `NOT`) pracujú výhradne so všeobecnými registrami:
```asm
ADD $0, $1, $2      ; $0 = $1 + $2 (podporované aj: ADD R0, R1, R1)
SUB $3, $3, $1      ; $3 = $3 - $1
MUL $4, $0, $2      ; $4 = $0 * $2
DIV $5, $4, $1      ; $5 = $4 / $1
INC $0              ; $0 = $0 + 1 (alebo INC R0 — 1-bajtová inštrukcia)
DEC $1              ; $1 = $1 - 1 (alebo DEC R1 — 1-bajtová inštrukcia)
NOT $2              ; $2 = ~$2
```

### 3. Režimy adresovania pamäte (`LMR` a `LRM`)
V inštrukciách presunu dát syntax argumentu priamo určuje hardvérový režim adresovania:
* **Samotné číslo bez zátvoriek** — priama konštanta (*immediate*, `SRC=0` / `DST=0`).
* **Hranaté zátvorky `[...]`** — odkaz na údaje v pamäti (dereferencia adresy alebo ukazovateľa).

| Režim adresovania | Príklad `LMR` (načítanie do registra) | Príklad `LRM` (uloženie do pamäte) | Podrobný popis |
|---|---|---|---|
| **Priama hodnota** (`SRC=0`) | `LMR.w $0, 0x1234`<br>`LMR.b $1, 0x25` | `LRM.w $0, 0x2000` | Číslo bez zátvoriek: v `LMR` uloží konštantu priamo do `$0`; v `LRM` určuje 16-bitovú cieľovú adresu. |
| **Priamy odkaz `[addr]`** (`SRC=1`) | `LMR.w $0, [0x1000]` | `LRM.w $0, [0x1000]` | Hranaté zátvorky pristupujú k bunke pamäte na adrese `0x1000` (`MEM[0x1000]`). |
| **Nepriamy cez `[$ptreg]`** (`SRC=2`) | `LMR.w $0, [$ptreg]` | `LRM.b $4, [$ptreg]` | Prístup k pamäti podľa 32-bitovej fyzickej adresy v registri `PTREG` (`MEM[PTREG]`). |
| **Registrový pár `[$0:$1]`** (`SRC=3`) | `LMR $0, [$0:$1]`<br>*(alebo `LMR, $0, [$0:$1]`)* | `LRM $2, [$0:$1]` | Zložený 32-bitový ukazovateľ z dvojice registrov (`($0 << 16) \| $1`). |

### 4. Natívne 32-bitové adresovanie (4 GB), Chránené Režimy a Architektúra MSP

V architektúre LIM M2 je realizovaný **natívny 32-bitový lineárny adresný priestor** (`A0–A31`, do **4 Gigabajtov** fyzickej pamäte) bez multiplexovania pinov a prepínania bánk. Procesor integruje hardvérový systém ochrany privilégií a 32 vektorových 32-bitových registrov.

#### 4.1. Dvojúrovňový model privilégií (User a Supervisor)
Procesor podporuje dva hardvérové režimy vykonávania určené bitom **11 (`PRV`)** v stavovom registri `FREG`:
* **Supervisor Mode (`PRV = 1`)** — režim správcu/jadra (OS). Povolené sú všetky inštrukcie, plný prístup k celému priestoru 4 GB pamäte, správa prerušení a konfigurácia Zón Privilégií.
* **User Mode (`PRV = 0`)** — používateľský neprivilegovaný režim. Je zakázaná ľubovoľná modifikácia systémových registrov (`$ir0..$ir15`, `$pv0..$pv15`), priame vypínanie prerušení a neoprávnený prechod do režimu správcu.

#### 4.2. Životný cyklus ochrany, Zóny Privilégií a pravidlá prepínania režimu

Hardvérová architektúra ochrany LIM M2 je postavená na modeli bezpečného štartu a kontrolovaných vstupných brán volania (Call Gates):

1. **Automatický štart v režime správcu (Power-On / Reset):**
   * Pri zapnutí napájania alebo hardvérovom resete procesor **automaticky začína prácu v privilegovanom režime (`PRV = 1`)**.
   * To zaručuje, že inicializačný kód (primárny zavádzač / jadro OS) má najvyššie oprávnenia pre počiatočnú konfiguráciu hardvéru, zásobníka, systémových tabuliek a pamäte.

2. **Počiatočná konfigurácia a odovzdanie riadenia používateľovi:**
   * Počas behu v režime správcu jadro zaregistruje adresy vektorov prerušení (`$ir0..$ir15`) a nakonfiguruje hranice Zón Privilégií (`$pv0..$pv15`, 8 chránených rozsahov `[Start:End]`).
   * Po dokončení počiatočnej inicializácie OS programovo vynuluje príznak privilégií (`PRV = 0`, napríklad pomocou `MSP.and $freg, ~0x0800` alebo `MSP.ld $freg, ...`) a odovzdá riadenie používateľskej úlohe (User Mode).

3. **Vstup do privilegovaného režimu a zmena zón:**
   * Keď procesor pracuje v User Mode (`PRV = 0`), akýkoľvek pokus svojvoľne nastaviť bit `PRV = 1` z náhodného miesta v pamäti je **hardvérovo blokovaný** jadrom a vyvolá výnimku ochrany (General Protection Fault)!
   * Aktivácia privilegovaného režimu (`PRV = 1`) programovou cestou je povolená **výhradne v prípade, ak sa aktuálne počítadlo inštrukcií `PC` nachádza striktne vo vnútri jednej z 8 zaregistrovaných Zón Privilégií**:
     $$\exists\, k \in [0..7]: \quad \$pv_{2k} \le \text{PC} \le \$pv_{2k+1}$$
   * Modifikovať a prekonfigurovať samotné registre Zón Privilégií (`$pv0..$pv15`) je povolené **iba pri vykonávaní kódu vo vnútri týchto istých Zón Privilégií**.

4. **Opustenie Zóny Privilégií NEZRUŠÍ režim automaticky:**
   * **Kriticky dôležité architektonické pravidlo:** ak bol režim správcu (`PRV = 1`) aktivovaný, tak **pri opustení hraníc Zóny Privilégií (skokom alebo bežným prechodom) procesor NENASTAVÍ bit `PRV` automaticky na 0!**
   * Jadro procesora nevynucuje skryté automatické resetovanie príznakov — **program alebo operačný systém je sám zodpovedný za zníženie privilégií (`PRV = 0`)** pred konečným návratom riadenia do neprivilegovaného používateľského kontextu.

5. **Hardvérové prerušenia (IRQ):**
   * Pri vzniku prerušenia jadro uloží aktuálne `PC` a `FREG` do zásobníka `SREG`, automaticky nastaví `PRV = 1`, vynuluje `MIE = 0` a skočí na vektor `$ir`. Návrat inštrukciou `RETI` obnoví uložený `FREG`, čím automaticky vráti pôvodný režim používateľa (`PRV = 0`).

---

### 4.3. Bit Structure of Quantized MSP Instruction (Opcode 26 / `0b11010`)

The `MSP` (Manipulate Special Register) instruction implements a unified, strictly quantized 16-bit access interface to all internal architectural and privileged processor registers. All system resources are addressed as 16-bit cells with `REG_ID` numbers from 0 to 255.

```text
Byte 0 (Opcode 11010 and Operation):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 1   1   0   1   0 | Operation |
+---+---+---+---+---+---+---+---+
 \_____ 5 bits ____/ \_ 3 bits _/
  Opcode = 26 (0x1A)

Byte 1 (Target Cell Index):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|           REG_ID              |
+---+---+---+---+---+---+---+---+
 \_____ 8 bits (0..255) ________/
```

#### Operation Codes in Byte 0 (bits [2:0]):
* `000` (`ld`): **Direct Load** 16-bit immediate into cell (`SYS_REG[id] = imm16`, length: **4 bytes**).
* `001` (`ldr7`): **Load from R7** into system cell (`SYS_REG[id] = R7`, length: **2 bytes**).
* `010` (`str7`): **Store cell into R7** (`R7 = SYS_REG[id]`, length: **2 bytes**).
* `011` (`and`): **Bitwise AND** with immediate mask (`SYS_REG[id] &= imm16`, length: **4 bytes**).
* `100` (`or`): **Bitwise OR** with immediate mask (`SYS_REG[id] |= imm16`, length: **4 bytes**).
* `101` (`xor`): **Bitwise XOR** with immediate mask (`SYS_REG[id] ^= imm16`, length: **4 bytes**).
* `110` (`onb`): **Turn bits ON** via mask (`SYS_REG[id] |= imm16`, length: **4 bytes**).
* `111` (`offb`): **Turn bits OFF** via mask (`SYS_REG[id] &= ~imm16`, length: **4 bytes**).

---

### 4.4. Map of Quantized 16-bit System Register Cells (REG_ID 0..255)

| REG_ID Range | Mnemonic | Bit-width | Functional Description and Hardware Binding |
| :---: | :--- | :---: | :--- |
| **0 – 31** | `INT_VEC[0..31]` (`$ir0_lo`..`$ir15_hi`) | 16 pairs (16-bit) | **16 Interrupt Vectors IR0..IR15:** even `2k` = `_lo`, odd `2k+1` = `_hi`. |
| **32 – 59** | `PVZ_VEC[0..27]` (`$pv0_lo`..`$pv13_hi`) | 14 pairs (16-bit) | **7 Privilege Protection Zones 0..6:** Start / End pairs (`$pv0`..`$pv13`). |
| **60, 61** | `MEM_VEC_BASE` (`$ram_base_lo`, `_hi`) | 1 pair (16-bit) | **Physical Base Address of RAM:** 60 = low 16 bits, 61 = high 16 bits. |
| **62, 63** | `MEM_VEC_LIMIT` (`$ram_limit_lo`, `_hi`)| 1 pair (16-bit) | **Physical Limit Address of RAM:** 62 = low 16 bits, 63 = high 16 bits. |
| **64 – 78** | `SYS_REG_EXT[0..14]` (15 cells) | 15 cells (16-bit) | **Reserved System Registers:** Allocated for future CPU modules and coprocessors. |
| **79 – 127** | `RESERVED` | 49 cells | Reserved for architectural extensions. |
| **128** | `FREG` | 1 cell (16-bit) | **Flags and Status Register:** ZF, CF, OF, EM, CMP, MIE, PRV, AIP, SMOD. |
| **129** | `SP_LO` (`$sp_lo`) | 1 cell (16-bit) | **Stack Pointer (SREG) Low Word:** bits [15:0] of 32-bit hardware stack pointer. |
| **130** | `SP_HI` (`$sp_hi`) | 1 cell (16-bit) | **Stack Pointer (SREG) High Word:** bits [31:16] of 32-bit hardware stack pointer. |
| **131** | `PTREG_LO` (`$ptreg_lo`) | 1 cell (16-bit) | **Base Pointer (PTREG) Low Word:** bits [15:0] of 32-bit memory streaming pointer. |
| **132** | `PTREG_HI` (`$ptreg_hi`) | 1 cell (16-bit) | **Base Pointer (PTREG) High Word:** bits [31:16] of 32-bit memory streaming pointer. |
| **133 – 255** | `RESERVED` | 123 cells | Reserved. |

> [!NOTE]
> **Composite 32-bit Vectors:** Configuring any 32-bit vector or pointer requires exactly **two 16-bit instructions**: first the lower part (`_lo`, smaller ID), then the upper part (`_hi`, larger ID). In assembler code, commands like `MSP.ld $sp, 0x00045678` or `MSP.ld $ir0, isr_timer` automatically expand into two sequential 4-byte `MSP.ld` instructions. Branching instructions `CALL`, `RET`, `INT`, `JMP` continue to operate with 32-bit linear addresses without modification.

#### MSP Assembly Examples:
```asm
; 1. Flags Register FREG (cell 128)
MSP.ld   $freg, 0x1800       ; FREG = 0x1800 (PRV=1, AIP=1)
MSP.onb  $freg, 0x0200       ; Enable MIE (bit 9)
MSP.offb $freg, 0x0200       ; Disable MIE (bit 9)

; 2. Fast Exchange with R7 (2 bytes):
MSP.str7 $freg               ; R7 = FREG (save flags into R7)
PUSH     $7                  ; Push flags onto stack
MSP.ldr7 $freg               ; Restore FREG from R7

; 3. Direct 16-bit cell load by numbers (4 bytes):
MSP.ld   0, 0xA000           ; Low 16 bits of IRQ0
MSP.ld   1, 0x0001           ; High 16 bits of IRQ0
MSP.ld   64, 0xABCD          ; Cell 64 from 15 reserved cells

; 4. Composite 32-bit registers (macro-expanded into 2 4-byte instructions):
MSP.ld   $sp, 0x00007F00     ; Setup stack pointer ($sp_lo=129, $sp_hi=130)
MSP.ld   $ptreg, 0x00010000  ; Setup memory streaming pointer ($ptreg_lo=131, $ptreg_hi=132)
MSP.ld   $ir0, isr_timer     ; Setup interrupt vector by label
```

---

## 🚀 Rýchly štart a simulácia

### 1. Spustenie simulátora cez kód procesora (`cpu.py`)

Simulátor LIM M2 funguje ako skutočný fyzický hardvér: zbernica, pamäť a firmvér sú konfigurované priamo v kóde Python ([`cpu.py`](cpu.py)). Program v assembleri sa najprv skompiluje do binárneho obrazu (`.bin`) a pripojí k zariadeniu:

```python
# Konfigurácia platformy v cpu.py:
bus = MemoryBus()
bus.attach(RAMDevice(start=0x000000, end=0x0FFFFF, file="drive.bin", persist=True, name="NVM1"))
bus.attach(RAMDevice(start=0x100000, end=0x1FFFFF, name="RAM1"))

cpu = LIM2CPU(bus=bus)
```

Príkazy na spustenie:

```bash
# Interaktívna emulácia v termináli (TUI)
python3 cpu.py -i

# Grafické rozhranie (GUI)
python3 cpu.py -g
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

