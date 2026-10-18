# Architektúra procesora LIM M2

<p align="center">
  <img src="Docs/diagram.png" alt="Schéma dátovej cesty LIM M2" width="850">
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
| **`SREG`** | **32 bitov** | Systémový zásobníkový register. Lineárne 32-bitové adresovanie zásobníka až do 4 GB. |
| **`PTREG`** | **32 bitov** | Rozšírený ukazovateľový register. Lineárne adresovanie pamäte až do 4 GB s autoincrementom (`AIP`). |
| **`FREG`** | 16 bitov | Stavový a riadiaci register procesora (bit 11: `PRV` — režim User/Supervisor). |
| **`ACCA` / `ACCB`** | 16 bitov | Pomocné akumulátory ALU. Predradené vstupy pre operandy A a B. |
| **`$ir0`..`$ir15`** | **32 bitov** | 16 vektorových registrov adries obsluhy prerušení. |
| **`$pv0`..`$pv15`** | **32 bitov** | 16 vektorových registrov hraníc 8 Zón Privilégií (`[$pv0:$pv1]`..`[$pv14:$pv15]`). |

### Bitová mapa príznakového registra (`FREG`)

```text
 15    14    13    12   11   10    9    8    7    6    5    4    3    2    1    0
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|INTR |SMOD |DBIT |AIP |PRV |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
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
* **`PRV` (11):** Režim privilégií procesora (`0`: User Mode — bežný režim; `1`: Supervisor Mode — režim správcu/jadra).
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

9. **Trieda IX: Inštrukcie vetvenia a skokov (2--6 bajtov)**
   * `JMP`, `JCR`, `JNZ`, `JZ`:
     * `MOD = 0` (000): 16-bitová priama adresa (spolu 3 bajty).
     * `MOD = 1` (001): Nepriamy registrový skok cez `Rs` (spolu 2 bajty).
     * `MOD = 2` (010): 32-bitový skok cez systémový ukazovateľ `PTREG` (spolu 2 bajty).
     * `MOD = 3` (011): 32-bitový nepriamy skok podľa ukazovateľa v pamäti `[addr32]` alebo páru `[$rd:$rs]`.

10. **Trieda X: Inštrukcie výmeny s pamäťou LMR a LRM (2--4 bajty)**
    * `LMR Rd, <SRC_MODE>` a `LRM Rs, <DST_MODE>`:
      * Bit 2 oktetu 0: `SZ` ($0 = 8$ bitov / bajt, $1 = 16$ bitov / slovo).
      * Bits 1–0 oktetu 0: `Mode` (0 = Inline dáta za kódom, 1 = Imm ukazovateľ, 2 = 32-bitový `PTREG` s autoincrementom, 3 = Dvojica registrov 32-bitovej adresy).

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
| **01001** | `0x09` | **`JMP`** | Skok | Nepodmienený skok (16-bitový lokálny alebo 32-bitový cez `PTREG`) |
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
| **10110** | `0x16` | **`PUSH`** | Zásobník | Uloženie slova do 32-bitového zásobníka (`SREG <- SREG - 2`) |
| **10111** | `0x17` | **`POP`** | Zásobník | Výber slova z 32-bitového zásobníka (`SREG <- SREG + 2`) |
| **11000** | `0x18` | **`BSL`** | Posuny | Barelový posun doľava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11001** | `0x19` | **`BSR`** | Posuny | Barelový posun doprava (nulovanie alebo cyklická rotácia cez `DBIT` pri `SMOD=1`) |
| **11010** | `0x1A` | **`MSP`** | Systém | Manipulácia so špeciálnymi registrami (`FREG`, `PTREG`, `SREG`, `VEC`) |
| **11011** | `0x1B` | **`MOD`** | Aritmetika | Výpočet zvyšku po delení (modulo): `Rd = Rs1 % Rs2` |
| **11100** | `0x1C` | **`INTR`** | Systém | Softvérové prerušenie (1 bajt): najnižšie 3 bity `[2:0]` vyberajú vektor `0..7` zo zásobníka vektorov procesora |
| **11101** | `0x1D` | **`RSV29`** | Rezerva | Slot koprocesora s pohyblivou rádovou čiarkou (FPU) |
| **11110** | `0x1E` | **`RSV30`** | Rezerva | Slot pre kryptografický akcelerátor |
| **11111** | `0x1F` | **`RSV31`** | Rezerva | Slot pre budúce rozšírenia architektúry |

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

Súčasťou SDK je oficiálny dvojprechodový kompilátor assemblera **`limasm.py`**, ktorý kompiluje zdrojové súbory `.asm` súčasne do binárneho obrazu (`.bin`) a anotovaného hexadecimálneho výpisu (`.hex`), a je priamo integrovaný do simulátora (`python3 sim/sim.py program.asm -i`).

### 1. Označovanie registrov a prípony veľkosti (`.b`, `.w`, `.d`)
* **Všeobecné registre (GPR):** zapisujú sa s prefixom `$` a číslom `$0`–`$7` (podporované sú aj klasické aliasy `R0`–`R7` a `$r0`–`$r7`).
* **Špeciálne registre:**
  * `$ptreg` — 32-bitový lineárny adresný ukazovateľ (`PTREG`, 4 GB);
  * `$freg` — 16-bitový register príznakov a stavu (`FREG`, bit 11: `PRV`);
  * `$sreg` (alebo `$sp`) — 32-bitový systémový ukazovateľ vrcholu zásobníka (`SREG`);
  * `$ir0`..`$ir15` — 16 vektorových 32-bitových registrov adries prerušení;
  * `$pv0`..`$pv15` — 16 vektorových 32-bitových registrov hraníc Zón Privilégií (8 rozsahov `[$pv0:$pv1]`..`[$pv14:$pv15]`).
* **Prípony veľkosti operandov:**
  * `.b` (*byte*, 8 bitov) — napr. `LMR.b $0, 0x42`
  * `.w` (*word*, 16 bitov, predvolené) — napr. `LMR.w $0, 0x1234` alebo `LMR $0, 0x1234`
  * `.d` (*doubleword*, 32 bitov) — napr. `LMR.d $0, [0x1000]`

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

### 4.3. Bitová štruktúra inštrukcie MSP (Opcode 26 / `0b11010`)

Inštrukcia `MSP` (Manipulate Special Register) má modulárny formát od 2 do 6 bajtov:

```text
Oktet 0 (Základný opkód a selektor registra):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 1   1   0   1   0 |MOD|  REG  |
+---+---+---+---+---+---+---+---+
 \_____ 5 bitov ___/ \1/ \_ 2b _/
  Opcode = 26 (0x1A)
```
* **`MOD` (bit 2):**
  * `0`: **Načítanie (`MSP.ld`)** — priamy zápis hodnoty do cieľového registra.
  * `1`: **Modifikácia / Výpočet** — bitová logika pre `FREG` (`AND`, `OR`, `XOR`, `XNOR`) alebo offsetová aritmetika pre `PTREG` / `SREG` (`ADD`, `SUB`).
* **`REG` (bity [1:0]):**
  * `00`: **`FREG`** — 16-bitový register príznakov a stavu.
  * `01`: **`PTREG`** — 32-bitový ukazovateľ adresy (4 GB).
  * `10`: **`SREG`** — 32-bitový ukazovateľ vrcholu zásobníka.
  * `11`: **`VEC`** — 32 vektorových registrov po 32 bitov (`$ir0..$ir15`, `$pv0..$pv15`).

---

#### Unifikované kódovanie zdrojov (Source Bits [2:1]):
* `00`: **Registre GPR (priamo)** — operand z registra `$rs` alebo páru `$rd:$rs`.
* `01`: **Priame číslo** — konštanta `imm16` alebo `imm32` za inštrukciou.
* `10`: **Nepriamo cez `PTREG` (`[$ptreg]`)** — natívna dereferencia adresy v pamäti.
* `11`: **Ukazovateľ na dáta (Pamäť)** — pár registrov `[$rd:$rs]` alebo priama adresa `[addr]`.

---

#### 4.3.1. Režim 1: Načítanie do príznakového registra FREG (MOD = 0, REG = 00)
Príkaz: `MSP.ld $freg, <zdroj>`

```text
Oktet 0: [ 11010 | 0 | 00 ] = 0xD0 (26, LD, FREG)

Oktet 1 pri SRC=00 (z registra GPR $rs, dĺžka 2 bajty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|    Rs     | 0   0   0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \_ 3 bity _/ \_ Rezerva / \SRC=00/
Príklad: MSP.ld $freg, $0 -> D0 00

Oktet 1..3 pri SRC=01 (priama konštanta imm16, dĺžka 4 bajty):
Oktet 1: [ 0   0   0   0   0   0 | 0   1 ] = 0x01 (SRC=01)
Oktet 2: [        imm16 [15:8]         ] (vyšší bajt konštanty)
Oktet 3: [        imm16 [7:0]          ] (nižší bajt konštanty)
Príklad: MSP.ld $freg, 0x0000 -> D0 01 00 00

Oktet 1 pri SRC=10 (z pamäte cez ukazovateľ [$ptreg], dĺžka 2 bajty):
Oktet 1: [ 0   0   0   0   0   0 | 1   0 ] = 0x02 (SRC=10)
Príklad: MSP.ld $freg, [$ptreg] -> D0 02

Oktet 1..3 pri SRC=11 (z pamäte na priamej adrese [addr16], dĺžka 4 bajty):
Oktet 1: [ 0   0   0   0   0   0 | 1   1 ] = 0x03 (SRC=11)
Oktet 2..3: [ addr16_hi | addr16_lo ]
Príklad: MSP.ld $freg, [0x1000] -> D0 03 10 00
```

---

#### 4.3.2. Režim 2: Bitová logická modifikácia FREG (MOD = 1, REG = 00)
Príkazy: `MSP.and $freg`, `MSP.or $freg`, `MSP.xor $freg`, `MSP.xnor $freg`
Operácia: `OP [7:6]`: `00`=AND, `01`=OR, `10`=XOR, `11`=XNOR.

```text
Oktet 0: [ 11010 | 1 | 00 ] = 0xD4 (26, MOD, FREG)

Oktet 1 pri SRC=00 (maska z registra GPR $rs, dĺžka 2 bajty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  OP   |    Rs     | 0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \_ 2b _/ \_ 3 bity _/ \1/ \SRC=00/
Príklad: MSP.xor $freg, $2 -> D4 90 (OP=10_2, Rs=2, SRC=00)

Oktet 1..3 pri SRC=01 (priama maska imm16, dĺžka 4 bajty):
Oktet 1: [  OP  | 0   0   0   0 | 0   1 ] (bity [5:2] rezerva, SRC=01)
Oktet 2..3: [ mask [15:8] | mask [7:0] ]
Príklad: MSP.or $freg, 0x0200 -> D4 41 02 00 (OP=01_2, maska MIE=1)

Oktet 1 pri SRC=10 (maska z pamäte cez ukazovateľ [$ptreg], dĺžka 2 bajty):
Oktet 1: [  OP  | 0   0   0   0 | 1   0 ] (SRC=10)
Príklad: MSP.and $freg, [$ptreg] -> D4 02

Oktet 1..3 pri SRC=11 (maska z pamäte z adresy [addr16], dĺžka 4 bajty):
Oktet 1: [  OP  | 0   0   0   0 | 1   1 ] (SRC=11)
Oktet 2..3: [ addr16_hi | addr16_lo ]
Príklad: MSP.and $freg, [0x2000] -> D4 03 20 00
```

---

#### 4.3.3. Režim 3: Načítanie ukazovateľov PTREG / SREG (MOD = 0, REG = 01 / 10)
Príkazy: `MSP.ld $ptreg, ...` (`REG=01`, oktet 0 = `0xD1`), `MSP.ld $sreg, ...` (`REG=10`, oktet 0 = `0xD2`).

```text
Oktet 0: [ 11010 | 0 | REG ] (0xD1 pre PTREG, 0xD2 pre SREG)

Variant 3.1: Načítanie z páru registrov GPR ($rd, $rs alebo [$rd:$rs]) (dĺžka 2 bajty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|    Rd_hi      |    Rs_lo      | 0   0 |
+---+---+---+---+---+---+---+---+
 \___ 3 bity ___/ \___ 3 bity ___/ \SRC=00/
   Vyšších 16 b     Nižších 16 b
Príklad: MSP.ld $ptreg, [$0:$1] -> D1 04 (PTREG = ($0 << 16) | $1)
Príklad: MSP.ld $sreg, [$0:$1]  -> D2 04 (SREG = ($0 << 16) | $1)

Variant 3.2: Priame načítanie imm32 / imm16 (dĺžka 4–6 bajtov):
Oktet 1: [ 0   0   0   0   0 | SZ | 0   1 ] (SZ: 0=16b, 1=24/32b; SRC=01)
Oktet 2..5 (pri SZ=1): [ imm32 (31:24) | imm32 (23:16) | imm32 (15:8) | imm32 (7:0) ]
Príklad: MSP.ld $ptreg, 0x00010000 -> D1 05 00 01 00 00 (6 bajtov)
Príklad: MSP.ld $ptreg, 0xA000 -> D1 01 A0 00 (4 bajty)

Variant 3.3: NATÍVNE 1-TAKTOVÉ DEREFERENCOVANIE UKAZOVATEĽA [$ptreg] (dĺžka 2 bajty!):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   0   0   0 | 0 | 1   0 | = 0x02
+---+---+---+---+---+---+---+---+
 \_____ 5 bitov núl _____/ \1/ \SRC=10/
Význam: Hardvérový procesorový cyklus PTREG <- MEM[PTREG] za jeden 2-bajtový príkaz!
Príklad: MSP.ld $ptreg, [$ptreg] -> D1 02 (2 bajty!)
Príklad: MSP.ld $sreg, [$ptreg]  -> D2 02 (2 bajty!)

Variant 3.4: Načítanie ukazovateľa z pamäte podľa odkazu [addr] (dĺžka 4–6 bajtov):
Oktet 1: [ 0   0   0   0   0 | SZ | 1   1 ] (SRC=11)
Oktet 2..3 (alebo 2..5): [ addr_hi | addr_lo ]
Príklad: MSP.ld $ptreg, [0xA000] -> D1 03 A0 00 (4 bajty: čítanie ukazovateľa z MEM[0xA000])
```

---

#### 4.3.4. Režim 4: Aritmetika posunu PTREG / SREG (MOD = 1, REG = 01 / 10)
Príkazy: `MSP.add $ptreg, ...`, `MSP.sub $ptreg, ...` (`0xD5`), `MSP.add/sub $sreg` (`0xD6`).
Operácia: `OP [7]`: `0` = `ADD` (+posun), `1` = `SUB` (-posun).

```text
Oktet 0: [ 11010 | 1 | REG ] (0xD5 pre PTREG, 0xD6 pre SREG)

Oktet 1 pri SRC=00 (posun z GPR $rs, dĺžka 2 bajty):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|OP |    Rs     | 0   0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \1/ \_ 3 bity _/ \_rezerva/ \SRC=00/
Príklad: MSP.add $ptreg, $3 -> D5 30 (OP=0, Rs=3, SRC=00)
Príklad: MSP.sub $sreg, $4  -> D6 C0 (OP=1, Rs=4, SRC=00)

Oktet 1..3 pri SRC=01 (priamy posun imm16, dĺžka 4 bajty):
Oktet 1: [ OP | 0   0   0   0   0 | 0   1 ] (SRC=01)
Oktet 2..3: [ offset [15:8] | offset [7:0] ]
Príklad: MSP.add $ptreg, 0x0010 -> D5 01 00 10 (4 bajty)
Príklad: MSP.sub $sreg, 0x0004  -> D6 81 00 04 (4 bajty)

Oktet 1 pri SRC=10 (posun podľa hodnoty z pamäte [$ptreg], dĺžka 2 bajty):
Oktet 1: [ OP | 0   0   0   0   0 | 1   0 ] (SRC=10)
Príklad: MSP.add $ptreg, [$ptreg] -> D5 02

Oktet 1..3 pri SRC=11 (posun podľa hodnoty z pamäte [addr16], dĺžka 4 bajty):
Oktet 1: [ OP | 0   0   0   0   0 | 1   1 ] (SRC=11)
Oktet 2..3: [ addr16_hi | addr16_lo ]
Приклад: MSP.add $ptreg, [0x3000] -> D5 03 30 00
```

---

#### 4.3.5. Režim 5: Načítanie 32-bitových vektorových registrov (MOD = 0, REG = 11)
Príkazy: `MSP.ld $ir0..$ir15, ...` (vektory prerušení, ID: 0..15), `MSP.ld $pv0..$pv15, ...` (hranice Zón Privilégií, ID: 16..31).
*Poznámka:* Modifikácia (`MOD=1`) pre vektory je hardvérovo zablokovaná.

```text
Oktet 0: [ 11010 | 0 | 11 ] = 0xD3 (26, LD, VEC)

Variant 5.1: Zo zloženej dvojice registrov [$rd:$rs] (dĺžka 3 bajty):
Oktet 1: [      Vector_ID [7:3]      | 0   0 | 0 ] (SRC=00, SUB=0)
Oktet 2: [    Rd_hi [7:5]    |    Rs_lo [4:2]    | 0   0 ]
Príklad: MSP.ld $ir0, [$0:$1] -> D3 00 04 (3 bajty: ID=0, Rd=0, Rs=1)
Príklad: MSP.ld $pv0, [$2:$3] -> D3 80 4C (3 bajty: ID=16, Rd=2, Rs=3)

Variant 5.2: Priamy 32-bitový vektor adresy imm32 (dĺžka 6 bajtov):
Oktet 1: [      Vector_ID [7:3]      | 0   1 | 0 ] (SRC=01, SUB=0)
Oktet 2: [          imm32 [31:24]            ]
Oktet 3: [          imm32 [23:16]            ]
Oktet 4: [          imm32 [15:8]             ]
Oktet 5: [          imm32 [7:0]              ]
Príklad: MSP.ld $ir0, 0x00010000 -> D3 02 00 01 00 00 (6 bajtov)
Príklad: MSP.ld $pv0, 0x00008000 -> D3 82 00 00 80 00 (6 bajtov)

Variant 5.3: Čítanie vektora z pamäte cez ukazovateľ [$ptreg] (dĺžka 2 bajty!):
Oktet 1: [      Vector_ID [7:3]      | 1   0 | 0 ] (SRC=10, SUB=0)
Príklad: MSP.ld $ir1, [$ptreg] -> D3 0C (2 bajty: číta MEM32[PTREG])
Príklad: MSP.ld $pv1, [$ptreg] -> D3 8C (2 bajty)

Variant 5.4: Čítanie vektora z pamäte podľa odkazu na pár GPR [$rd:$rs] (dĺžka 3 bajty):
Oktet 1: [      Vector_ID [7:3]      | 1   1 | 0 ] (SRC=11, SUB=0)
Oktet 2: [    Rd_hi [7:5]    |    Rs_lo [4:2]    | 0   0 ]
Príklad: MSP.ld $ir2, [$0:$1] -> D3 16 04 (3 bajty: číta MEM32[(R0<<16)|R1])

Variant 5.5: Čítanie vektora z pamäte z priamej 32-bitovej adresy [addr32] (dĺžka 6 bajtov):
Oktet 1: [      Vector_ID [7:3]      | 1   1 | 1 ] (SRC=11, SUB=1)
Oktet 2..5: [ addr32 (31:24) | addr32 (23:16) | addr32 (15:8) | addr32 (7:0) ]
Príklad: MSP.ld $ir0, [0x00005000] -> D3 07 00 00 50 00 (6 bajtov)
```

---

### 4.4. 25 Konkrétnych príkladov inštrukcie MSP s bitovým rozpisom

| # | Inštrukcia v assembleri | Oktet 0 (bity / hex) | Oktet 1 (bity / hex) | Oktet 2..5 (hex) | Výsledok (Hex bajty) | Popis operácie |
|---|---|---|---|---|---|---|
| **1** | `MSP.ld $ir0, 0x00010000` | `11010 0 11` (`0xD3`) | `00000 01 0` (`0x02`) | `00 01 00 00` | `D3 02 00 01 00 00` | Nastavenie vektora prerušenia IRQ0 na adresu 0x00010000 |
| **2** | `MSP.ld $ir1, 0x00025000` | `11010 0 11` (`0xD3`) | `00001 01 0` (`0x0A`) | `00 02 50 00` | `D3 0A 00 02 50 00` | Nastavenie vektora prerušenia IRQ1 na adresu 0x00025000 |
| **3** | `MSP.ld $pv0, 0x00008000` | `11010 0 11` (`0xD3`) | `10000 01 0` (`0x82`) | `00 00 80 00` | `D3 82 00 00 80 00` | Spodná hranica Zóny Privilégií 0 ($pv0 = 0x8000) |
| **4** | `MSP.ld $pv1, 0x00008FFF` | `11010 0 11` (`0xD3`) | `10001 01 0` (`0x8A`) | `00 00 8F FF` | `D3 8A 00 00 8F FF` | Horná hranica Zóny Privilégií 0 ($pv1 = 0x8FFF) |
| **5** | `MSP.ld $ir2, [$0:$1]` | `11010 0 11` (`0xD3`) | `00010 00 0` (`0x10`) | `000 001 00` (`0x04`) | `D3 10 04` | Načítanie vektora IRQ2 zo zloženej dvojice [$0:$1] ($0 = vyššie, $1 = nižšie) |
| **6** | `MSP.ld $pv2, [$2:$3]` | `11010 0 11` (`0xD3`) | `10010 00 0` (`0x90`) | `010 011 00` (`0x4C`) | `D3 90 4C` | Načítanie začiatku Zóny 1 ($pv2) zo zloženej dvojice [$2:$3] |
| **7** | `MSP.ld $ir3, [$ptreg]` | `11010 0 11` (`0xD3`) | `00011 10 0` (`0x1C`) | — | `D3 1C` | Nepriame načítanie vektora IRQ3 z pamäte cez PTREG (2 bajty) |
| **8** | `MSP.ld $pv3, [$ptreg]` | `11010 0 11` (`0xD3`) | `10011 10 0` (`0x9C`) | — | `D3 9C` | Nepriame načítanie hranice Zóny 1 ($pv3) cez PTREG (2 bajty) |
| **9** | `MSP.ld $ir4, [$4:$5]` | `11010 0 11` (`0xD3`) | `00100 11 0` (`0x26`) | `100 101 00` (`0x94`) | `D3 26 94` | Načítanie vektora IRQ4 cez 32-bitový ukazovateľ v registroch [$4:$5] |
| **10** | `MSP.ld $pv4, [0x0000A000]` | `11010 0 11` (`0xD3`) | `10100 11 1` (`0xA7`) | `00 00 A0 00` | `D3 A7 00 00 A0 00` | Načítanie $pv4 z pamäte podľa priamej 32-bitovej adresy [0xA000] |
| **11** | `MSP.ld $freg, 0x0000` | `11010 0 00` (`0xD0`) | `000 00 01 0` (`0x02`) | `00 00` | `D0 02 00 00` | Nulovanie registra príznakov (FREG = 0) |
| **12** | `MSP.or $freg, 0x0200` | `11010 1 00` (`0xD4`) | `01 000 01 0` (`0x42`) | `02 00` | `D4 42 02 00` | Povolenie prerušení (FREG \|= 0x0200, bit MIE) |
| **13** | `MSP.and $freg, 0x0001` | `11010 1 00` (`0xD4`) | `00 000 01 0` (`0x02`) | `00 01` | `D4 02 00 01` | Maska AND: zachovanie len príznaku nuly (ZF) |
| **14** | `MSP.xor $freg, $1` | `11010 1 00` (`0xD4`) | `10 001 00 0` (`0x88`) | — | `D4 88` | Inverzia bitov FREG podľa masky v registri $1 |
| **15** | `MSP.xnor $freg, 0x00FF` | `11010 1 00` (`0xD4`) | `11 000 01 0` (`0xC2`) | `00 FF` | `D4 C2 00 FF` | Bitová operácia XNOR registra FREG s maskou |
| **16** | `MSP.ld $freg, $2` | `11010 0 00` (`0xD0`) | `010 00 00 0` (`0x40`) | — | `D0 40` | Priame obnovenie príznakov FREG z registra $2 |
| **17** | `MSP.ld $freg, [$ptreg]` | `11010 0 00` (`0xD0`) | `000 00 10 0` (`0x04`) | — | `D0 04` | Načítanie uloženého slova príznakov zo zásobníkového buffera cez PTREG |
| **18** | `MSP.ld $ptreg, 0x00100000` | `11010 0 01` (`0xD1`) | `000 000 01` (`0x01`) | `00 10 00 00` | `D1 01 00 10 00 00` | Priame načítanie 32-bitovej adresy do PTREG (1 Megabajt) |
| **19** | `MSP.ld $ptreg, [$0:$1]` | `11010 0 01` (`0xD1`) | `000 001 00` (`0x04`) | — | `D1 04` | Zloženie 32-bitového PTREG zo zloženej dvojice [$0:$1] ($0 = vyššie, $1 = nižšie) |
| **20** | `MSP.ld $ptreg, [$ptreg]` | `11010 0 01` (`0xD1`) | `000 000 10` (`0x02`) | — | `D1 02` | **1-taktová natívna dereferencia ukazovateľa** (PTREG <- MEM[PTREG]) |
| **21** | `MSP.ld $ptreg, [0x5000]` | `11010 0 01` (`0xD1`) | `000 000 11` (`0x03`) | `50 00` | `D1 03 50 00` | Načítanie ukazovateľa z fixnej bunky tabuľky pamäte |
| **22** | `MSP.add $ptreg, 0x0020` | `11010 1 01` (`0xD5`) | `0 000 01 00` (`0x04`) | `00 20` | `D5 04 00 20` | Hardvérový posun ukazovateľa PTREG dopredu o +32 bajtov |
| **23** | `MSP.sub $ptreg, $3` | `11010 1 01` (`0xD5`) | `1 011 00 00` (`0xB0`) | — | `D5 B0` | Zníženie ukazovateľa PTREG o dynamický posun z registra $3 |
| **24** | `MSP.ld $sreg, 0x00003F00` | `11010 0 10` (`0xD2`) | `000 000 01` (`0x01`) | `00 00 3F 00` | `D2 01 00 00 3F 00` | Inicializácia 32-bitového ukazovateľa vrcholu zásobníka SREG |
| **25** | `MSP.add $sreg, 0x0010` | `11010 1 10` (`0xD6`) | `0 000 01 00` (`0x04`) | `00 10` | `D6 04 00 10` | Uvoľnenie zásobníkového rámca (+16 bajtov k SREG) |


### 5. Viacnásobné dereferencovanie ukazovateľov cez `PTREG`
Natívne viacnásobné dereferencovanie reťazcov ukazovateľov (`**ptr`, `***ptr`) prebieha cez register `PTREG` pomocou inštrukcie `MSP.ld $ptreg, [$ptreg]`, ktorá vykoná `PTREG = MEM16[PTREG]`. Opakovaním `MSP.ld $ptreg, [$ptreg]` (sekvenčne alebo v cykle) sa ukazovateľ dereferencuje $N$-krát:
```asm
; Načítanie koreňovej adresy ukazovateľa 0xA000 do PTREG:
MSP.ld $ptreg, 0xA000
MSP.ld $ptreg, [$ptreg]     ; 1. dereferencovanie: PTREG = *0xA000
MSP.ld $ptreg, [$ptreg]     ; 2. dereferencovanie: PTREG = **0xA000
MSP.ld $ptreg, [$ptreg]     ; 3. dereferencovanie: PTREG = ***0xA000
; Načítanie cieľovej hodnoty do $0:
LMR.w  $0, [$ptreg]
```

### 6. Kompilácia do `.bin` a `.hex`
```bash
# Kompilácia cez pohodlný vstupný bod compiler.py s výpisom (-l):
python3 compiler/compiler.py compiler/demo.asm -l

# Priame spustenie .asm súboru v interaktívnom simulátore:
python3 sim/sim.py compiler/demo.asm -i
```

---

## 🚀 Rýchly štart a simulácia

### 1. Spustenie simulátora

```bash
# Interaktívny terminálový monitor (podporuje .asm, .bin aj .hex)
python3 sim/sim.py sim/demo.asm -i
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

