[English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | 繁體中文（香港）

<div align="center">

# Neo Geo Media Player

<strong>在原裝 Neo Geo AES 上播放有聲音的全螢幕影片，<br>
並提供一個程式庫，把影片放進你自己的遊戲。</strong>

<br>

[![CI](https://img.shields.io/github/actions/workflow/status/gufranco/neogeo-media-player/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/gufranco/neogeo-media-player/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-2.0.0-blue?style=flat-square)](RELEASES.md)
[![Licence](https://img.shields.io/badge/licence-MIT-blue?style=flat-square)](LICENSE)
[![Target](https://img.shields.io/badge/target-Neo%20Geo%20AES%20and%20MVS-red?style=flat-square)](#硬件上限)
[![Hardware](https://img.shields.io/badge/hardware-runs%20on%20an%20AES%20and%20an%20MVS-brightgreen?style=flat-square)](#驗證)

</div>

<p align="center">
  <a href="#快速開始"><strong>快速開始</strong></a> &nbsp;|&nbsp;
  <a href="#運作原理"><strong>運作原理</strong></a> &nbsp;|&nbsp;
  <a href="#質素"><strong>質素</strong></a> &nbsp;|&nbsp;
  <a href="#驗證"><strong>驗證</strong></a> &nbsp;|&nbsp;
  <a href="#播放器家族"><strong>系列</strong></a>
</p>

<div align="center">

<img src="readme/demo.gif" alt="由建置好的 Neo Geo 卡帶播放 Sintel 預告片的六秒片段，擷取自 MAME" width="640">

<sub>Sintel 預告片的六秒片段，擷取自以主機原生 320x224 運行建置好卡帶的 MAME，影片開始時顯示位置列。Master System 播放器的 README 開首也是同一部影片。Sintel 由 Blender Foundation 製作，採用 CC BY 3.0。</sub>

</div>

```bash
uv --project tools run python -m neogeomedia.cartridge ~/Movies/my-film.mkv
# build/neogeomedia.neo
```

---

## 這是甚麼

**卡帶製作工具。** 指定一個影片檔案，它便會建置一個可播放該影片的 Neo Geo 卡帶，附播放控制、字幕和聲音。請從[快速開始](#快速開始)入手。

**供你自己遊戲使用的程式庫。** 同一個渲染器經過封裝，讓自製遊戲開發者可以把過場動畫放進正在製作的遊戲。一個阻塞式呼叫在影片播放期間接管螢幕，播放後交還每一個暫存器。請從[在你自己的遊戲中播放影片](#在你自己的遊戲中播放影片)入手。

卡帶建基於程式庫，而不是與之並列，所以任何令其中一方出錯的改動，也會令另一方出錯。

### 問題

Neo Geo 沒有影片解碼器、沒有影格緩衝區，也沒有縮放器。它只會繪製硬件 sprite，僅此而已。解碼後的畫面無處可放，也沒有東西可以用來解碼：68000 以 12 MHz 運行，必須維持每秒 59.2 格，同時音效晶片在底下串流。

此外也沒有殘差。編解碼器通常會在畫面上已有的內容加上差值，以修正不準確的預測。沒有影格緩衝區，就沒有東西可以加上去。修正只能把一個槽位指向某個已存在的 tile。

### 解決方法

主機上不作任何解碼。離線烘焙器把影片轉成卡帶 ROM 映像，卡帶上的播放器則在每次 vblank 把預先計算好的 tile 編號寫入 sprite 控制區塊。

螢幕是固定的 20 x 14 sprite tile 網格，共 280 個 16x16 像素的槽位，覆蓋 320x224 的光柵。影片需要的每個不同 tile，都只會在字元 ROM 的一個全域字典中收錄一次。一格畫面就是一串指派：槽位 137 現在顯示 tile 90412。沒有解壓步驟，因為 tile 編號本身就是解碼後的形式。

<table>
<tr>
<td width="50%" valign="top">

#### 執行時零解碼

播放器只把 tile 編號寫入 SCB1，別無其他。一格沒有任何變化的畫面只需兩個位元組。

</td>
<td width="50%" valign="top">

#### 經實測的質素階梯

35 級。級別由實際烘焙來源決定，而不是對照表格估價。

</td>
</tr>
<tr>
<td width="50%" valign="top">

#### 按場景重新擬合調色盤

240 個 CRAM bank 每個 epoch 重新擬合，並在一個 epoch 持續的數百格之間雙緩衝，以多 1.5% 的 tile 換取約少 6% 的誤差。

</td>
<td width="50%" valign="top">

#### 與 geolith 逐位元一致

由卡帶自身位元組重建的畫面，與模擬器繪製的逐像素相符，誤差為 0.0000。

</td>
</tr>
<tr>
<td width="50%" valign="top">

#### 逐條指令檢查時序

每次建置都會反組譯播放器，只要任何一對 VRAM 寫入的間隔低於文件記載的最少週期數，建置即告失敗。

</td>
<td width="50%" valign="top">

#### 可用的播放控制

播放、暫停、2x、5x 和 10x 快進、倒帶及跳轉，每次跳躍都會把音訊重新指向對應的 ADPCM 頁。

</td>
</tr>
</table>

## 每個播放器都具備的功能

兩個播放器都按照 [FAMILY.md](FAMILY.md) 訂下的同一份功能清單製作，而這個表格在兩份 README 中完全相同。「已計劃」表示尚未完成的工作。主機無法承載的功能會標示為「無法做到」，並附上硬件原因；目前沒有任何功能屬於此類。

| 功能 | Neo Geo | Master System |
|---|---|---|
| 一個指令就能把影片檔製成卡帶 | 是 | 是 |
| 畫面填滿螢幕，縮放至覆蓋後裁切 | 是。`--fit letterbox` 仍然存在，但即將移除 | 是 |
| 偵測並裁去來源中烘入的黑邊 | 是 | 已計劃 |
| 畫面及聲音由最佳質素逐級降低，直至影片放得進 | 是。`--quality search` 沿 35 級階梯向下烘焙，聲音採用仍放得進的最高取樣率 | 已計劃。幀率、降噪及重用均在每次烘焙時量度，但目前尚未有功能會逐級降低影片，令其放得進卡帶 |
| 最大的標準卡帶，無需額外硬件 | 是，128 MiB 字元 ROM | 已計劃。目前為 1 MB；Sega mapper 有文件記載的上限仍待查證出處 |
| 有序抖色 | 是，`--dither` | 是，預設啟用 |
| 隨影片變化重新擬合調色盤 | 是，按場景 | 是，按幀，仍然適用時會保留 |
| 無需額外硬件的聲音 | 是，在 YM2610 上使用 ADPCM-B | 已計劃，以 PSG 發聲 |
| 把聲音的空間讓給畫面的無聲建置 | 部分做到。程式庫套件可以省略聲音；聲音有獨立的 ROM，所以省略聲音不會為畫面騰出空間 | 目前每個建置都是無聲的 |
| 來自 SubRip 檔案的字幕 | 是 | 已計劃 |
| 播放及暫停 | 是 | 已計劃 |
| 快進及倒帶 | 是，快進速度為 2x、5x 及 10x | 已計劃 |
| 跳轉 | 是，後退或前進 10 秒 | 已計劃 |
| 顯示已播放時間及總時間的位置列 | 是。總時間會少顯示一秒 | 已計劃 |
| 重新開始及停止 | 已計劃 | 是 |
| 聲音開關 | 已計劃 | 已計劃 |
| 影片播放完畢後循環播放 | 是 | 是 |
| 診斷資訊疊加層 | 是 | 已計劃 |
| 串流損毀時的錯誤畫面 | 已計劃 | 是 |
| 在你自己的遊戲中播放影片 | 是，`--bundle` 會產生可直接嵌入的程式庫 | 部分做到。`--rows` 及 `--columns` 可建置較小的畫面；目前還沒有可直接嵌入的套件 |
| 預覽主機將會繪製的畫面 | 是，一段影片 | 是，四幀畫面並列於其來源旁 |
| 每次建置都檢查寫入時序 | 是 | 是 |
| 每次測試都會烘焙的回歸影片集 | 已計劃 | 是，六段影片 |
| 在原裝硬件上運行 | 是，AES 及 MVS | 尚未。Game Gear 實機測試仍待進行 |

## 運作原理

```mermaid
flowchart LR
    A[來源影片] --> B[解碼為 320x224<br/>以 vblank 速率]
    B --> C[量化為<br/>Neo Geo 顏色]
    C --> D[擬合 240 個<br/>15 色調色盤]
    D --> E[把 16x16 tile 收錄<br/>到同一個字典]
    E --> F[C-ROM<br/>tile 字典]
    E --> G[指令串流<br/>關鍵格 + 差異]
    A --> H[ADPCM-B 編碼] --> I[V-ROM 音軌]
    F --> J[卡帶]
    G --> J
    I --> J
```

執行時，播放器讀取下一格的指令，並直接寫入 sprite 控制區塊 1。

```mermaid
flowchart LR
    A[vblank] --> B{播放控制狀態}
    B -->|播放中| C[從 bank 切換的 P-ROM<br/>讀取下一格]
    B -->|跳轉中| D[經索引跳到<br/>最近的關鍵格]
    C --> E[把 tile 編號<br/>寫入 SCB1]
    D --> E
    E --> F[把 ADPCM-B 重新指向<br/>對應的頁]
```

24 fps 的來源在 59.185 Hz 的光柵上顯示，每格約重複 2.47 次，而每次重複都不花費任何成本。在十分鐘內，參考串流平均每格更新 280 個槽位中的 24.6 個。

關鍵格會重寫全部 280 個槽位，並作為跳轉目標。播放控制會在索引中找出最近的關鍵格，從那裡重新播放，從而跳到任何位置。一部十分鐘的影片帶有 913 個關鍵格。

畫面質素就是字典的豐富程度，而字典的豐富程度就是字元 ROM。這個事實決定了以下每一項設計。

## 硬件上限

這裏每個數值都是從兩個獨立模擬器的原始碼讀出，而不是取自文字說明。

| 資源 | 上限 | 影響 |
|---|---|---|
| 字元 ROM | 20 位元 tile 編號，1,048,576 個 tile，128 MiB | 在每個質素級別都是決定性的限制 |
| 程式 ROM | 3 位元 bank 鎖存器，8 個 1 MiB 的 bank | 指令串流。參考烘焙用了 5 個 bank 共 4.5 MB |
| ADPCM-B 語音 ROM | 16 MiB 的 4 位元取樣，經 16 位元頁計數器存取 | 以晶片 55.6 kHz 的上限約 10 分鐘。較長的來源會取用仍能在可定址頁結束的最高速率 |
| 每條掃描線的 sprite | 96 | 網格用了 20 |
| 調色盤 | 256 個 16 色 bank，索引 0 為透明 | 240 個用於影片，16 個保留給選單 |
| 看門狗 | 約 0.13 秒 | 限制任何初始化迴圈的長度 |
| 光柵 | 384 x 264，6 MHz 點時脈，59.185 Hz | 每個地區都相同 |

> [!IMPORTANT]
> 沒有字元 ROM 的 bankswitching，也不可能有。geolith 和 MAME 都沒有在任何主機板上實作，而算術也不容許：2^20 個 tile，每個 128 位元組，正好是 tile 編號可定址的 128 MiB。128 MiB 是絕對上限，而不是一個視窗。

整個設計建基於刷新率。播放器每次 vblank 前進一格影片，音軌按影格計數控制節奏，所以刷新率不同的主機會令影片播得較慢，音訊也會逐漸與畫面脫節。geolith 把 `LSPC_SCANLINES` 固定為 264，沒有地區差異，其地區設定影響的是 BIOS 跳線和 CD 光碟機，而不是光柵。這裏建置的卡帶，在日本、美國、亞洲或歐洲的主機板上都以相同速率播放。

## 快速開始

任何 ffmpeg 能讀取的影片檔案都可以。檔案不必放在特定資料夾，也不必使用特定名稱。

### 先決條件

| 工具 | 版本 | 安裝 |
|:-----|:--------|:--------|
| Python | >= 3.12 | [python.org](https://www.python.org) |
| uv | 最新 | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| ffmpeg 和 ffprobe | 任何近期版本 | [ffmpeg.org](https://ffmpeg.org) |
| m68k 工具鏈 | ngdevkit | [工具鏈](#工具鏈) |
| Neo Geo BIOS | 任何 | 只在運行模擬器時需要，建置時不需要 |

### 取得程式碼

烘焙器透過 [fmv-core-python](https://github.com/gufranco/fmv-core-python) 子模組與 Master System 播放器共用解碼、色彩、影片及擷取程式碼，因此請連同子模組一併複製。下載按鈕提供的原始碼壓縮檔無法包含子模組，因此無法執行。

```bash
git clone --recurse-submodules https://github.com/gufranco/neogeo-media-player.git
git submodule update --init   # in a clone made without the flag
```

### 製作卡帶

```bash
uv --project tools run python -m neogeomedia.cartridge ~/Movies/my-film.mkv
```

這會測量來源，找出能放進卡帶的最高質素級別，進行烘焙，建置 ROM，並在 `build/` 留下一個 `.neo`。用 `--subtitles ~/Movies/my-film.srt` 加入字幕；或者不加這個旗標，放在來源旁邊、名稱相同的 `.srt` 會自動被採用。

| 步驟 | 作用 | 大約時間 |
|:-----|:-------------|:--------|
| 校準 | 取樣 24 個短時段，測量內容在 tile 上的成本 | 少於一分鐘 |
| 選擇 | 印出完整階梯，找出放得進的最佳級別 | 即時 |
| 烘焙 | 量化、擬合調色盤、收錄每個 tile、編碼音訊 | 十分鐘的來源約 8 分鐘 |
| 建置 | 編譯播放器並打包 ROM 映像 | 數分鐘 |

#### 產出內容

| 路徑 | 內容 |
|:-----|:-----------|
| `build/neogeomedia.neo` | 卡帶。NeoSD 或模擬器載入的就是這個檔案 |
| `build/neogeomedia.zip` | 相同的 ROM，以 MAME 軟件清單封存檔形式提供 |
| `build/mame-hash/neogeo.xml` | MAME 尋找該封存檔所需的軟件清單項目 |
| `build/baked/` | 中間 ROM 映像，保留下來以便無需重新烘焙即可重建 ROM |
| `build/preview.mp4` | 只在指定了 `--preview` 時產生 |

#### 常用旗標

| 旗標 | 用途 |
|:-----|:----|
| `--subtitles PATH` | SubRip `.srt` 檔。預設為來源旁邊的同名檔案 |
| `--quality search` | 預設值。由 `q01` 向下烘焙直至放得進，並記住結果 |
| `--quality q17` | 指定一個級別，略過測量 |
| `--start 90 --duration 300` | 從 1:30 開始取五分鐘，而不是整個檔案 |
| `--fit letterbox` | 加上黑邊，而不是填滿 320x224 光柵 |
| `--preview out.mp4` | 另外渲染卡帶將顯示的畫面，供肉眼檢查 |
| `--bake-only` | 在建置 ROM 前停止 |
| `--build-dir DIR` | 把所有輸出放到 `build/` 以外的位置 |

### 運行

在硬件上，把 `build/neogeomedia.neo` 複製到 NeoSD 快閃卡帶，像其他遊戲一樣載入。

在 MAME 中，指向建置產生的封存檔和雜湊檔，並把 BIOS 目錄加入 ROM 路徑：

```bash
mame aes -bios unibios23 -cart neogeomedia \
    -rompath build:/path/to/bios -hashpath build/mame-hash
```

[`verify_mame.sh`](tools/scripts/verify_mame.sh) 會完成上述準備，然後把 MAME 繪製的畫面與烘焙器自己的渲染結果比較。

在 libretro 前端中，以 geolith 核心載入 `build/neogeomedia.neo`，並把 `geolith_overscan_*` 設為零，便可看到全部 320 欄。

### 工具鏈

卡帶需要 `m68k-neogeo-elf` 工具鏈。Ubuntu 從 ngdevkit 的 PPA 取得，該 PPA 只發佈 amd64 版本。Apple Silicon 則從 Homebrew tap 取得原生版本：

```bash
brew install --force-bottle dciabrin/ngdevkit/ngdevkit-toolchain \
                            dciabrin/ngdevkit/ngdevkit
```

> [!TIP]
> 在 tap 尚未標記的 macOS 版本上，`--force-bottle` 會安裝 arm64 bottle。沒有這個旗標，Homebrew 會從原始碼建置 GCC。

[`build-in-docker.sh`](toolchain/build-in-docker.sh) 在路徑上有工具鏈時直接編譯，否則以呼叫者的使用者身份在工具鏈映像內運行自己。[`Dockerfile`](Dockerfile) 固定了該映像：Ubuntu 以摘要固定，其套件取自有日期的快照，三個 ngdevkit 套件則以確切版本和 SHA-256 固定，列於 [`toolchain/ngdevkit.sha256`](toolchain/ngdevkit.sha256)。今天的建置與明年的建置會產生相同的 ROM。

### 在你自己的遊戲中播放影片

渲染器是一個程式庫，烘焙器會把它輸出為一個資料夾，供你放進 ngdevkit 專案。所有內容都以原始碼形式提供。

```bash
uv --project tools run python -m neogeomedia.bake \
    --source intro.mkv --quality q17 --duration 30 \
    --build-dir build --bundle game/fmv
```

這會寫出 `game/fmv/`，內含程式庫原始碼、烘焙好的影片、一個 `.mk` 片段，以及一份針對剛烘焙的影片撰寫的整合指南。在你的 `Makefile` 加一行，把卡帶指向影片的 ROM 映像，然後呼叫它：

```c
#include "fmv.h"
#include "movie_data.h"

fmv_options options = fmv_defaults();

options.skip_pad = FMV_PAD_A | FMV_PAD_B;
switch (fmv_play(&fmv_movie_data, &options)) {
case FMV_FINISHED: break;
case FMV_SKIPPED:  break;
}
game_redraw();
```

`fmv_play` 會阻塞，直至影片結束或玩家略過。其下有 `fmv_open`、`fmv_start`、`fmv_tick`、`fmv_seek` 和 `fmv_close`，供想自行驅動迴圈的呼叫者使用。

#### 佔用甚麼，留下甚麼

| 資源 | 影片佔用 | 留給你 |
|---|---|---|
| Sprite | 20 個，從 `options.first_sprite` 起 | 其餘所有 sprite |
| 調色盤 bank | 從烘焙的 `--base-bank` 向上 | 其下的全部 |
| C-ROM tile | 0 至字典大小 | 128 MiB 的其餘部分，以 `--tile-budget` 預先保留 |
| P-ROM bank | 串流需要多少就用多少，從 `FMV_FIRST_BANK` 起 | 其他 bank，以及整個固定的 1 MB |
| Fix 層 | 完全不佔用 | 全部 |
| Z80 和 M1 ROM | 不佔用，除非你要求聲音 | 預設歸你 |

> [!WARNING]
> 你的程式碼必須放在固定的第一個 1 MB 內。程式庫會切換 P-ROM bank 鎖存器以讀取串流，所以從可切換 bank 執行的程式碼會在自己腳下消失。

**它還原的機器狀態，就是你聲明的狀態。** LSPC 模式暫存器、fix 來源與調色盤 bank 鎖存器，以及 bank 鎖存器都是唯寫的：讀取 `0x3A0000` 以上的位址會傳回匯流排上最後一個字，讀取 `0x3C0006` 會傳回光柵行計數器而不是模式。沒有任何方法能透過讀取來保存這些值。`fmv_defaults()` 會填入一般卡帶使用的值，而使用自動動畫或主機板 fix ROM 的呼叫者只需聲明一次。

**聲音須主動啟用。** 影片路徑不需要音效驅動程式，所以已經擁有 M1 ROM 的遊戲可以保留它。影片的音軌是由三個 Z80 指令驅動的 ADPCM-B，參考驅動程式以原始碼形式提供，可供閱讀或合併。

[`examples/cutscene/`](examples/cutscene) 是一個播放過場動畫後繼續運行的遊戲，在固定 commit 的原裝 ngdevkit 專案中由輸出的資料夾建置。它的標題畫面在影片返回後才繪製，只寫入 fix tile，所以任何留在錯誤位置的暫存器都會顯現出來。

## 質素

Tile 成本取決於內容，而不是播放時間。密集的動畫成本可以是對白場景的數倍，所以只按時長索引的階梯會對容易的來源過度壓縮，對困難的來源壓縮不足。烘焙器因此改為測量來源。

同樣四段片段在 `q17` 下，以每分鐘 tile 數，以及完整 128 MiB C-ROM 可容納的播放時間表示：

| 片段 | 每分鐘 tile 數 | 可容納 |
|:-----|-----------------:|-----:|
| Big Buck Bunny，動畫 | 56,622 | 18.5 分鐘 |
| blue_sky，真人實拍 | 287,279 | 3.7 分鐘 |
| mobcal，真人實拍 | 409,600 | 2.6 分鐘 |
| parkrun，真人實拍 | 616,623 | 1.7 分鐘 |

平塗著色的動畫對 tile 字典來說是遙遙領先的最佳情況。以菲林拍攝的長片需要階梯下方很遠的級別，而 `search` 就是找出哪一級的方法。

`--quality search` 是預設值，不查任何表格。它先烘焙 `q01`，若放不進，就把步幅加倍，`q02`、`q04`、`q08`，直至有一級放得進，然後對加倍剛剛證明的區間進行二分。成本從每一級到下一級嚴格遞減，所以放得進的級別是階梯底部的一段連續區塊，只需找出其邊界。一部落在深處的影片約需九次烘焙，而不是三十次。

級別必須憑自身條件放得進。速率控制會降低畫面質素以維持在預算內，所以只因控制器達到上限才放得進的級別，不算放得進。

每個找出的級別都會寫入 [`neogeomedia-tiers.json`](neogeomedia-tiers.json)，這個檔案是用來提交的：它記錄的是影片與階梯的屬性，而不是某一台工作站的屬性，所以提交後，任何建置同一卡帶的人都可以略過相同的烘焙。

要在投入長時間運行前查看階梯，`neogeomedia.plan` 會在約兩分鐘內印出每一級及其確切超出量，且不作任何烘焙：

```bash
uv --project tools run python -m neogeomedia.plan --source film.mkv
```

[`docs/quality-ladder.md`](docs/quality-ladder.md) 列出全部 35 級及其設定，並涵蓋按場景調色盤、速率控制和顏色模型。

### 參考卡帶

Big Buck Bunny 是測試對象，而不是產品：授權自由，長度足以考驗字典，而且每次運行都不變，所以從中取得的數字可以互相比較。

| 項目 | 數值 |
|---|---|
| 級別 | `q17`，顏色 37% |
| 影格 | 35,274 格，59.2 fps，沒有停留 |
| C-ROM | 846,784 個 tile，佔 128 MiB 的 81% |
| 調色盤 epoch | 120 個，節奏取自每分鐘 6.0 次實測剪接 |
| 音訊 | 55,555 Hz，晶片的上限 |
| 顯示誤差 | 0.0010116 |
| 卡帶 | 158 MB |

音訊與影片保持同步。從播放器自身的診斷計數器讀取，播放器在第 1,800 格和第 12,000 格時都比 vblank 計數落後 8 至 9 格，所以這個偏移是影片開始前開機的成本，而不是漂移。音訊在第 0 格套用後立即開始，之後 YM2610 與光柵使用同一個晶體振盪器串流。剩餘誤差為：十分鐘內 ADPCM 速率網格造成的 3 ms、影格至頁映射造成的 3 ms，以及每次跳轉最多 4.6 ms 的捨入。

一段在卡帶自身解像度加入顆粒的五分鐘來源，是刻意建置來貼近 C-ROM 邊緣的。`--quality search` 只用一次烘焙便以每分鐘 209,667 個 tile 定於 `q01`，五分鐘合共 1,048,338 個 tile，上限為 1,048,576。這個 150 MB 的卡帶能在 MAME 中開機，並在顆粒完整的情況下繪製畫面。

## 驗證

本專案依賴的每一種硬件編碼，都是從模擬器原始碼讀出，而不是取自文件；測試套件包含 geolith 的 tile 讀取器和串流播放器的獨立轉寫，用作測試基準。geolith 與 MAME 沒有共用任何程式碼，所以兩者一致，是關於主機板的證據，而不是關於對 wiki 某一種解讀的證據。

最嚴格的檢查會由卡帶自身的位元組重建畫面：把指令串流重播到 VRAM 模型中，並從打包好的字元 ROM 渲染，再與模擬器繪製的畫面比較。

| 模擬器 | 十分鐘卡帶的結果 |
|---|---|
| geolith | 完全一致。誤差 0.0000，逐像素相符 |
| MAME | 平均 1.0066，最差 255 中的 5，另加第 0 欄 |

MAME 在全部 224 行中把第 0 欄傳回為黑色。排除這一欄後，剩餘差異是平滑的逐級差，這是數模轉換模型不同的特徵，而不是結構上的分歧。

### 在真實硬件上

卡帶已經從 NeoSD 快閃卡帶在真實的 AES 和真實的 MVS 上運行過。兩者都完整播放了十分鐘，畫面填滿光柵，音軌在整個運行期間保持同步，播放控制亦有回應。

| 論點 | 這次運行證實了甚麼 |
|---|---|
| Tile 編碼、C-ROM 打包、調色盤上傳 | 畫面在晶片上是正確的，而不只是在模型中正確 |
| 在消隱期以外寫入 VRAM | 實際上是容許的，與 wiki 所述一致 |
| ADPCM-B 速率和影格至頁映射 | 音訊在十分鐘內保持同步，沒有可聽見的漂移 |
| 3 位元 bank 鎖存器、5 個 P-ROM bank、120 個調色盤 epoch | 串流跨越每個 bank 直至影片結束都正常 |
| 關鍵格跳轉索引和音訊重新指向 | 跳轉、倒帶和快進都按設計運作 |

一次成功的運行並不是週期測量，所以寫入間隔的最小值仍以文件為依據，並由建置檢查強制執行，而不是靠觀察確認。[`docs/hardware.md`](docs/hardware.md) 載有從兩個解碼器讀出的位元配置，以及時序檢查在每次建置時檢查的內容。

[過場動畫範例](examples/cutscene)也已在主機板上運行，並在影片結束後正常返回自己的標題畫面。該畫面只寫入 fix tile，所以 fix 來源、調色盤 bank 和 LSPC 模式都必須在呼叫者留下的位置，畫面才會出現。沒有模擬器能證實這一點，因為這些暫存器在機器上同樣無法讀回。

## 儲存庫結構

| 路徑 | 內容 |
|---|---|
| [`src/fmv/`](src/fmv) | 程式庫：VRAM 設定、sprite 網格、調色盤 epoch、逐格重播、關鍵格跳轉，以及可選的 ADPCM-B 分頁 |
| [`src/player/`](src/player) | 建基於程式庫的影片卡帶。播放控制、選單、字幕、診斷 |
| [`examples/cutscene/`](examples/cutscene) | 一個播放過場動畫後繼續運行的遊戲，由輸出的套件建置 |
| [`tools/neogeomedia/`](tools/neogeomedia) | 烘焙器：解碼、顏色、調色盤、字典、編碼器、質素階梯、音訊、ROM 容器、套件輸出 |
| [`tools/tests/`](tools/tests) | 974 個測試，包括用作測試基準的模擬器轉寫 |
| [`tools/scripts/`](tools/scripts) | 擷取、驗證、時序和階梯掃描的輔助工具 |
| [`toolchain/`](toolchain) | ngdevkit 建置，原生或容器化 |
| [`FAMILY.md`](FAMILY.md) | 與 sms-media-player 和 fmv-core-python 共用的標準，三者內容相同 |
| [`CHANGELOG.md`](CHANGELOG.md) | 測量了甚麼，以及否決了甚麼 |
| [`RELEASES.md`](RELEASES.md) | 自動產生的發佈說明，每個版本一項 |

## 開發

```bash
# 安裝烘焙器及其開發工具
uv --project tools sync --all-groups

# 運行 974 個測試
uv --project tools run python -m pytest tools/tests

# 格式檢查
uv --project tools run ruff format --check tools/

# Lint 檢查
uv --project tools run ruff check tools/

# 型別檢查
uv --project tools run mypy tools/neogeomedia tools/scripts

# 在固定的工具鏈映像中，以已烘焙的內容建置 ROM
make rom

# 以 cppcheck 對播放器作靜態分析，必須以 0 結束
make analyse

# 檢查已編譯物件中的 VRAM 寫入間隔，在 make rom 之後執行
make timing

# 在工具鏈映像內開啟 shell
make shell

# 把完成的卡帶與 MAME 比較
bash tools/scripts/verify_mame.sh
```

覆蓋率在 [CI](.github/workflows/ci.yml) 中以 95% 為門檻，CI 也會端對端建置一個卡帶，並建置過場動畫範例兩次，一次只有影片，一次附帶影片自己的音效驅動程式。

### 慣例

| 慣例 | 來源 |
|------------|--------|
| Commit 格式 | [Conventional Commits](https://www.conventionalcommits.org/)，每個 pull request 都會強制檢查 |
| 版本管理 | [python-semantic-release](https://python-semantic-release.readthedocs.io/)，由 commit 標題驅動 |
| Lint 和格式 | [ruff](https://docs.astral.sh/ruff/)，在 [`tools/pyproject.toml`](tools/pyproject.toml) 中設定 |
| 型別 | [mypy](https://mypy-lang.org/)，嚴格模式 |
| 依賴更新 | [Dependabot](.github/dependabot.yml)，每週 |

### 穩定性

從 2.0 起，以下各項是承諾。任何會破壞它們的改動都屬於主要版本。

| 介面 | 承諾 |
|:--------|:--------|
| `python -m neogeomedia.cartridge <source>` | 唯一的指令。其旗標保持名稱和意義不變 |
| `python -m neogeomedia.plan --source <file>` | 以估算形式印出階梯，不作任何烘焙 |
| `python -m neogeomedia.bake --bundle DIR` | 輸出一個可直接放入的資料夾。其結構保持名稱不變：`DIR/src/`、`DIR/movie/`、`DIR/package/`、`DIR/fmv.mk`、`DIR/README.md` |
| 級別名稱 `q01` 至 `q35` | 同一名稱永遠代表相同設定。級別永不重新編號 |
| [`neogeomedia-tiers.json`](neogeomedia-tiers.json) | 可讀、可比較差異，可安全提交。其 `version` 欄位保障結構 |
| `build/neogeomedia.neo` 和 `build/neogeomedia.zip` | 卡帶的輸出位置及其名稱 |
| 結束代碼 | 成功時為 0，失敗時非零，烘焙用盡字典時有一個獨立代碼 |

C 程式庫介面是 [`fmv.h`](src/fmv/fmv.h)：

| 承諾 | 不承諾 |
|:---------|:-------------|
| `fmv_defaults`、`fmv_play` | `fmv_movie` 和 `fmv_player` 的佈局。宣告它們是為了讓呼叫者可以配置，而不是讓它讀取 |
| `fmv_open`、`fmv_start`、`fmv_tick`、`fmv_hold`、`fmv_pause`、`fmv_resume`、`fmv_seek`、`fmv_close` | [`src/fmv/`](src/fmv) 之下除 `fmv.h` 以外的任何內容。`hw.h` 屬內部檔案，可隨時變動而不另行通知 |
| `fmv_ended`、`fmv_position`、`fmv_last_updates`、`fmv_epoch`、`fmv_stream_bank` | 產生的標頭檔中的 `MOVIE_` 定義，它們描述的是一次烘焙，而不是介面 |
| `fmv_options` 的欄位及其預設值 | |
| 專案讀取的 `fmv.mk` 變數：`FMV_OBJS`、`FMV_CFLAGS`、`FMV_LDFLAGS`、`FMV_CROM_BYTES`、`FMV_PROM2_BYTES`、`FMV_VROM_BYTES`、`FMV_FIRST_FREE_TILE`、`FMV_FIRST_BANK`、`FMV_AUDIO` | |

輸出的資料夾附帶烘焙時所用的程式庫原始碼，跨主要版本把兩者混合編譯，建置會停止並列出兩個版本。

`python -m neogeomedia.bake` 帶有一些供實驗用的調節參數，所以其介面可以與 `--bundle` 分開變動。烘焙在 `report.json` 中報告的數字是測量結果，而不是介面。

### 版本

本專案遵循 [Semantic Versioning](https://semver.org/)。每次發佈都會加上標籤，版本由 commit 標題推導。請參閱 [releases](https://github.com/gufranco/neogeo-media-player/releases) 和 [`RELEASES.md`](RELEASES.md)。

## 常見問題

<details>
<summary><strong>我可以把影片放進正在製作的遊戲嗎？</strong></summary>
<br>

可以。以 `--bundle DIR` 烘焙，便會得到一個可放進 ngdevkit 專案的資料夾：程式庫原始碼、烘焙好的影片、一個 `.mk` 片段，以及針對你所烘焙影片撰寫的指南。

你要放棄的是 C-ROM，因為影片的 tile 字典與你自己的 sprite 都出自同一個 128 MiB，兩者之間沒有 bankswitching；還有程式 ROM 固定的第一個 1 MB，因為程式庫會切換 bank 鎖存器以讀取串流。

</details>

<details>
<summary><strong>為甚麼不直接使用影片編解碼器？</strong></summary>
<br>

因為沒有東西可以運行它。主機沒有影片解碼器，也沒有影格緩衝區，而 12 MHz 的 68000 每格約有 30,000 個消隱週期，重寫全部 280 個槽位便要用掉其中約 18,000 個。每一種假設有殘差路徑的編解碼技術在這裏都行不通，因為修正無法微調像素，只能把槽位指向一個已存在的 tile。

</details>

<details>
<summary><strong>烘焙需要多久？</strong></summary>
<br>

十分鐘的來源約需八分鐘，隨播放時間增減。校準約需兩分鐘，所以在投入任何烘焙之前，階梯會連同每一級的確切超出量一併印出。

</details>

<details>
<summary><strong>可以容納多長的播放時間？</strong></summary>
<br>

這取決於內容帶有多少新的細節，而不是長度。平塗著色的動畫在 `q17` 可達約 18 分鐘；顆粒多的真人實拍則不到兩分鐘。音訊以晶片 55.6 kHz 的上限約為 10 分鐘，較長的來源會取用仍能在可定址頁結束的最高速率。

</details>

<details>
<summary><strong>為甚麼真正的卡帶用 304 像素，畫面卻是 320 像素寬？</strong></summary>
<br>

因為收窄畫面反而會增加 tile，而不是節省。在一個測試時段中把兩側各 16 像素消隱，tile 數由 35,136 上升至 35,779；而把中間同樣 32 像素消隱，則降至 30,098。成本跟隨新的細節，而構圖會把細節放在中間。

</details>

## 播放器家族

本播放器屬於一個系列，在從未打算顯示全動態影片的遊戲機上播放這類影片。各成員共用一份標準 [FAMILY.md](FAMILY.md)，而凡是硬件沒有強制要求的烘焙器程式碼，都只在核心中存在一份。

| 成員 | 內容 |
|:--|:--|
| [neogeo-media-player](https://github.com/gufranco/neogeo-media-player) | 本儲存庫 |
| [sms-media-player](https://github.com/gufranco/sms-media-player) | 在 Sega Master System 上播放的全螢幕影片，播放時經 VRAM 分頁載入 tile |
| [fmv-core-python](https://github.com/gufranco/fmv-core-python) | 各播放器共用的烘焙器和測量程式碼 |

## 授權及鳴謝

[MIT](LICENSE)。

以 [ngdevkit](https://github.com/dciabrin/ngdevkit) 建置。以 [geolith](https://github.com/libretro/geolith-libretro) 和 [MAME](https://github.com/mamedev/mame) 驗證。示範影片是 Sintel 預告片，測試片段是 Big Buck Bunny 和 Tears of Steel，全部由 Blender Foundation 製作，採用 CC BY 授權。

ngdevkit 採用 LGPL-3.0，本專案採用 MIT。有兩項慣例是沿用而非自創的：檔名含 `__bank` 的物件屬於可切換的程式 ROM，以及卡帶透過 `rom.mk` 聲明，並透過包含它的 `Makefile` 建置。兩者都屬於介面而不是實作。本儲存庫沒有複製任何來自 ngdevkit 或 `ngdevkit-examples` 的檔案，[過場動畫範例](examples/cutscene)也是在建置時取得原裝專案，而不是把專案收錄進來。這裏建置的卡帶會連結 ngdevkit 的程式庫，這正是 LGPL-3.0 所針對的用途。本儲存庫不發佈任何二進位檔；所有內容都以原始碼形式提供。
