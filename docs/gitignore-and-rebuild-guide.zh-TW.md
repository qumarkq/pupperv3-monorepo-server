# Git 忽略規則與環境重建指南

更新日期：2026-10-10（Asia/Taipei）  
適用專案：`pupperv3-monorepo-server`

只查看保存與忽略項目時，可先閱讀 [建議忽略的檔案清單](gitignore-recommendations.zh-TW.md)；本指南提供完整重建步驟。

本文件說明哪些內容應上傳 GitHub、哪些內容可忽略，以及如何取得被忽略的環境和模型。原則是：**保存原始碼、依賴宣告、版本鎖定、設定範本和自訂文件；排除可重新安裝或建置的本機產物，以及私人設定。**

專案內容以 [Nate711/pupperv3-monorepo](https://github.com/Nate711/pupperv3-monorepo/tree/6f96c5e79faa05492992c19918f8cd90b9243281) 為基準，保留它原本追蹤的模型、3D、圖片、動畫、bags 和部署資源，再加入本機功能修改。

本文件是保存與重建政策，不是完整機器人安裝手冊。指令依現有專案配置與來源程式核對，尚未實際重裝全部環境或完成機器人執行驗證。Ponytail、SymDex checkout、本機 MCP 設定與兩個 Piper 模型副本的精確排除皆已套用到 `.gitignore`。

## 1. 應保存到 GitHub 的內容

| 內容 | 保存理由 |
| --- | --- |
| Python、Rust、C/C++、前端原始碼與測試 | 專案功能的來源 |
| `pyproject.toml` | Python 專案設定、依賴宣告與建置方式 |
| `uv.lock` | 鎖定解析後的 Python 依賴版本 |
| `uv.toml`、`.python-version`（若有） | uv 設定與指定的 Python 版本 |
| `requirements.txt` | 既有 pip 依賴宣告 |
| `package.json`、`package-lock.json` | Node 專案設定與依賴鎖定 |
| `Cargo.toml`、`Cargo.lock` | Rust 專案設定與依賴鎖定 |
| `.env.example`、其他 example/sample/template 範本 | 可分享的設定鍵名與安全預設值 |
| README、部署腳本、Dockerfile、ROS launch/config、建置腳本 | 安裝、建置與操作方法 |
| `.agents/skills/` | 44 個本機技能原始文件／腳本；無法由套件安裝還原 |
| `.agents/workflow-kit/` | 6 個本機開發流程與管理文件；無法由套件安裝還原 |
| `.agents/mcp/README.md` | 說明選用的開發工具與需求 |
| `.gitignore`、`.gitattributes`、授權文件 | Git 保存政策、LFS 規則與授權 |
| 上游原本追蹤的模型、3D、動畫 CSV、bags、HEF、DEB、圖片 | 原始專案的既有功能、模擬與部署資源 |

**uv 配置的角色就像 `requirements.txt`，應保留；`.venv/` 是由配置建立的安裝結果，可以忽略。** 保留鎖定檔可固定套件版本，但仍需相容的作業系統、CPU、Python、系統依賴及可取得的套件來源。

新增的機器人 Python 檔案也應保留，全部位於 `ai/llm-ui/agent-starter-python/`：

| 檔案 | 作用 |
| --- | --- |
| `src/local_voice.py` | 本機 Whisper 語音辨識、Piper 語音合成 |
| `src/ollama_session.py` | Ollama 工作階段及語音後端選擇 |
| `src/ollama_vision_interface.py` | Ollama 圖片分析介面 |
| `src/remote_voice.py` | 遠端 Whisper 辨識客戶端 |
| `src/speech_audio.py` | 共用音訊轉換與編碼 |
| `src/stt_discovery.py` | 區域網路遠端 STT 服務探索 |
| `tests/test_ollama_session.py` | Ollama 工作階段設定測試 |
| `tests/test_ollama_vision_interface.py` | 視覺 API 介面測試 |
| `tools/test_local_stt.py` | 本機語音辨識診斷工具 |

## 2. 建議忽略的內容與還原方式

| 內容 | 上游是否也有忽略 | 如何取得／處理 | 是否需要另寫程式 |
| --- | --- | --- | --- |
| `.venv/`、`.venv-local-stt/` 等 Python 環境 | 部分有：agent／RL 有 `.venv`，名稱變體由本機補上 | 使用保留的依賴設定重新安裝 | 不需要；額外手動安裝的套件必須先補入依賴宣告 |
| `node_modules/` | 有：兩個 live-audio 子專案已有規則 | 依 package/lock 檔重新安裝 | 不需要 |
| ROS `build/`、`install/`、`log/` | 有：上游根目錄明列三個 ROS 目錄 | 執行既有 ROS 建置腳本 | 不需要；須有 ROS 與系統依賴 |
| Rust `target/` | 有：pupper-rs／ui-rs 已忽略 target | 依 Cargo 配置重新建置 | 不需要；須有編譯器和平台依賴 |
| `__pycache__/`、`.pytest_cache/`、`*.egg-info/` 等 | 部分有：pycache、pytest、egg-info 等已有；其他模式是本機補強 | 執行 Python、測試或安裝套件時再產生 | 不需要 |
| `.DS_Store`、編輯器 `*.swp`、執行日誌 | 部分有：DS_Store、swap、前端日誌已有；本機擴充範圍 | 通常不必還原；系統／工具會再產生新的檔案 | 不需要；歷史日誌不會被重建 |
| `.env.local`、私鑰與憑證 | 部分有：env／PEM 已有；其他金鑰模式由本機補上 | 從範本填入或由私人備份／服務供應商取得 | 不需要寫程式，但不是自動還原 |
| `ai/llm-ui/agent-starter-python/models/` | 沒有：上游未設定此下載目錄的專用排除 | 重新下載 Whisper／Piper 模型 | 不需要；首次取得要網路 |
| 新增的 `ai/llm-ui/piper-voices/en_US-lessac-low.onnx` 與 `.onnx.json` | 沒有：上游沒有這兩個新增檔案及專用排除 | 由 Piper 下載工具取得 | 不需要；兩者為下載模型副本 |
| `.agents/mcp/ponytail/`、`.agents/mcp/symdex/` | 沒有：上游沒有 Ponytail／SymDex | 從對應來源取得第三方工具，重新安裝依賴 | 不需要開發功能，但需設定 MCP 啟動方式 |
| `.agents/mcp/symdex-venv*/`、`.symdex/` | 沒有：上游沒有此環境及 SymDex 索引 | 重新安裝工具與重建索引 | 不需要 |
| `.agents/mcp/mcp.json` | 沒有：上游沒有這份本機設定 | 在新機器重新設定工具路徑 | 需手動設定；目前寫死 Windows 絕對路徑 |

不能把整個 `.agents/` 視為可重新安裝的依賴：其中的 skills 與 workflow-kit 是應保存的原始文件。第三方 checkout 可重新下載，但若自行修改其中內容，修改必須先保存成 patch、分支或獨立倉庫。


## 3. Python／uv 環境重建

以下指令在專案根目錄的 Bash 終端執行；先安裝 uv 與相容的 Python。ROS／機器人操作以已配置 ROS Jazzy 的 Linux 為準，不代表可在 macOS 原生執行所有機器人元件。

```bash
cd ai/llm-ui/agent-starter-python
uv sync --locked
```

`--locked` 在 `pyproject.toml` 與 `uv.lock` 不一致時會報錯，不會自行更新版本鎖定。若報錯，應檢查配置與鎖定檔，而不是直接移除鎖定限制。[uv 官方文件](https://docs.astral.sh/uv/concepts/projects/sync/)

這會建立本子專案的 `.venv/`。其他子專案的環境需要在各自含 `pyproject.toml`／`uv.lock` 的目錄執行相同指令；根目錄執行一次不等於還原所有 Python 環境。

本機 `.venv-local-stt/` 可作為測試環境，但不能僅靠保留資料夾名稱還原其中任意手動安裝的套件。若其用途已被主 agent 的 uv 配置涵蓋，可直接使用主 agent 的 `.venv/`；要重建獨立測試環境時應另保留對應依賴宣告。

### 私人環境設定

同樣在 agent 子專案目錄，第一次建立設定檔時執行：

```bash
cp -n .env.example .env.local
```

`-n` 避免覆蓋已有設定。接著依實際環境編輯 `.env.local`，尤其是 Ollama 位址、模型名稱、語音模型路徑及所需的 API 金鑰。範本中的服務位址不保證適用新機器。

`.env.local`、金鑰與憑證應由私人方式保存；GitHub 上的範本只保留設定格式。遠端 STT 使用的 token／位址也由自己填入。

## 4. 本機語音與 Ollama 模型

### Piper：同時取得 ONNX 與 JSON

在 agent 子專案目錄執行：

```bash
uv run --locked python -m piper.download_voices en_US-lessac-low --data-dir models
```

現有 Piper 下載程式會取得以下兩個檔案：

```text
models/en_US-lessac-low.onnx
models/en_US-lessac-low.onnx.json
```

設定 `LOCAL_TTS_MODEL=models/en_US-lessac-low.onnx` 即對應現有 `.env.example`。不必再寫下載程式。

目前 `ai/llm-ui/piper-voices/` 與上述 `models/` 中的兩個 Piper 檔案分別具有相同 SHA256：

| 檔案 | SHA256 |
| --- | --- |
| `en_US-lessac-low.onnx` | `f7d01dde371555732c4c314111ac79672b1a5ce2fc19266ab42178fd8df7f375` |
| `en_US-lessac-low.onnx.json` | `45754dfdebb3b8661c3fc564713772deec6e064feeb5b4e9594857dc7305193a` |

ONNX 的 SHA256 也符合[公開模型來源](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/low/en_US-lessac-low.onnx)。下載工具會使用遠端 main；若未來要求逐位元組相同，應固定模型來源版本並核對上表，而不能只依模型名稱判斷。

若確實設定成從 `../piper-voices/` 讀取，也可以在 agent 子專案執行：

```bash
uv run --locked python -m piper.download_voices en_US-lessac-low --data-dir ../piper-voices
```

兩種目錄擇一，並使 `LOCAL_TTS_MODEL` 與下載位置一致。

### Whisper

現有 `LocalWhisperSTT` 會呼叫 `WhisperModel(model_name, device="cpu", compute_type="int8")`。當 `LOCAL_STT_MODEL=tiny.en` 等值是模型名稱而非本機路徑時，faster-whisper 會在首次使用時下載模型，再使用下載快取。

若 `LOCAL_STT_MODEL` 指向 `models/faster-whisper-tiny.en` 等資料夾，應先取得該資料夾的模型內容，或改回已支援的模型名稱。未完成下載的 `.incomplete` 檔案不是可用模型，可以忽略。

遠端 STT 是另一種部署方式：本專案有客戶端，但它提到的 `tools/remote_stt/server.py` 不在此倉庫。`uv sync` 不會補出該伺服器；使用遠端模式時，需另外取得並部署對應服務，設定 URL／服務探索和 token。本指南的本機 Whisper 重建不依賴它。

### Ollama

在實際執行 Ollama 的機器安裝並啟動 Ollama，再取得設定中的模型，例如：

```bash
ollama pull qwen3-vl:4b
```

機器人的 `.env.local` 必須設定成可連到該 Ollama 服務的位址。這是服務安裝與設定，不是新增機器人程式碼；模型權重也不需要放入此 Git 倉庫。

## 5. Node、Rust 與 ROS 建置產物

### Node 依賴

在對應、且 `package-lock.json` 已還原為實際 JSON 的 Node 專案目錄執行：

```bash
npm ci
```

`npm ci` 依 lock 檔安裝；package 與 lock 不一致時會失敗，且會重新建立安裝目錄。沒有 lock 檔的專案不適用此指令。[npm 官方文件](https://docs.npmjs.com/cli/v11/commands/npm-ci/)

### Rust

從專案根目錄執行：

```bash
cd pupper-rs
cargo build --locked
```

保留 Cargo 設定與鎖定檔，忽略生成的 `target/`。跨平台建置仍需對應編譯工具與系統函式庫。

### ROS

先完成原專案的 ROS Jazzy／系統依賴安裝，並取得 LFS 實體資源。從專案根目錄執行：

```bash
bash ros2_ws/build.sh
```

既有腳本會載入 ROS 環境並執行 `colcon build`。在同一個 Bash 終端要使用建置好的工作空間時，再執行：

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/local_setup.bash
```

`build/`、`install/` 可重新生成；舊 `log/` 的歷史內容不會因此恢復。完整系統安裝請參照主 README 與既有 `install_dev_dependencies.sh`；該安裝腳本會變更系統套件，本文件沒有執行它。

## 6. 選用 MCP 開發工具

Ponytail、SymDex 用於 AI 開發流程，機器人執行不依賴這兩個 MCP server。以下只在需要工具的乾淨 checkout 使用；資料夾已有內容時，不要覆蓋本機修改。

### 對這個 Pupper 專案的實際用途

2026-10-10 已檢查啟動腳本、服務設定、依賴宣告與 1,388 個執行／原始碼／設定文字檔案（排除工具副本、環境、建置、模型與本指南）：未找到對 Ponytail、SymDex 或 MCP 的直接引用。語音 agent 在 `src/agent.py` 中直接建立 `RosToolServer`，再交給 `PupsterAgent`；走路、停止、動畫及相機工具不是經由這兩個 MCP server 呼叫。此結論來自靜態檢查，未做移除工具後的完整機器人測試。

開發流程則有明確引用：`.agents/workflow-kit/docs/tools.md` 列出 SymDex 的符號搜尋、呼叫關係與程式上下文功能，以及 Ponytail 的開發建議用途。因此它們對本專案的 **AI 開發工作流程有用途**，不能描述成完全用不到。

`mcp.json` 是讓支援 MCP 的開發助手啟動工具的設定，Pupper 執行程式沒有讀取它。目前內容使用 Windows 絕對路徑，不能在此 macOS 環境直接沿用。應保存可分享的 MCP 設定範本、工具版本和安裝說明；只忽略機器專屬設定、安裝環境與可重建的第三方 checkout。可分享設定的角色與 uv 配置相似，不應因為執行時不需要就一律捨棄。

以下指令是開發工具的取得方法，不是機器人啟動的必要步驟。

從專案根目錄取得 Ponytail 的既有版本：

```bash
mkdir -p .agents/mcp
git clone https://github.com/DietrichGebert/ponytail.git .agents/mcp/ponytail
git -C .agents/mcp/ponytail checkout e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156
cd .agents/mcp/ponytail/ponytail-mcp
npm install
```

固定 checkout 對應目前本機的 [v4.10.0 提交](https://github.com/DietrichGebert/ponytail/commit/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156)。此版本 checkout 的 MCP 子專案沒有追蹤 `package-lock.json`，所以這裡使用 `npm install`；若另外保存相容的 lock 檔，才改用 `npm ci`。

SymDex 現有工具版本為 [0.1.26](https://pypi.org/project/symdex/0.1.26/)，可從專案根目錄建立專用環境：

```bash
uv venv --python 3.11 .agents/mcp/symdex-venv311
uv pip install --python .agents/mcp/symdex-venv311/bin/python "symdex==0.1.26"
```

上例是 Linux/macOS 路徑；Windows 的直譯器路徑為 `Scripts/python.exe`。此方式固定 SymDex 本身版本，但沒有鎖定全部間接依賴，不保證與目前環境逐套件完全相同。

若需閱讀或使用目前的 SymDex checkout 原始碼，其來源為 `https://github.com/husnainpk/SymDex.git`，本機 commit 為 `257bb3c215b347f623b2d1c7ab453bb621623baf`。第三方原始碼與環境可以另行取得，不需要把整份 checkout 放進機器人倉庫。

安裝後，依 MCP 客戶端格式設定 Node 入口、SymDex 執行檔及工作目錄；Windows/macOS/Linux 路徑不同，不能直接沿用目前 `mcp.json` 的 Windows 絕對路徑。可分享的設定應改成不含私人路徑的範本，再保存在 Git。

## 7. LFS 資料是另一件事

2026-10-10 的比對以實際專案目錄為準：上游 1,458 個檔名全部存在，但 89 個本機檔案仍只有 Git LFS pointer。它們包括 JSON、3D、MCAP、HEF 與 DEB。此數量為產生本文前的比對紀錄，不包含本文新增的文件。

這些不是 Python／Node 安裝依賴；`uv sync`、`npm ci` 和建置指令不會自動補回它們。保留 `.gitattributes`，並從保存實體 LFS 物件的來源取得資料。當目前倉庫的 LFS server 確實擁有相關物件時，可執行：

```bash
git lfs install
git lfs pull
```

若遠端沒有相應物件，這些指令仍會失敗。新 repo 的 LFS 物件不會隨指標文字自動出現；建立新歷史和上傳前需先從可用來源取得實體資料，再正確上傳 LFS 物件。

上游既有模型、3D、bags 等資源應照原專案保留。避免用 `*.json`、`*.onnx`、`*.stl`、`*.mcap` 等全面排除規則；本文僅對「本機新增的下載副本」提出精確排除。

## 8. 建議補充的精確忽略規則

上游原專案也有做忽略：2026-10-10 核對 main，共有 17 份 `.gitignore`，包含根目錄的 ROS 建置、DS_Store、PEM、pyc、臨時 bags、WAV 規則，以及各子目錄的 Python、Node、Rust、Packer 與編譯產物規則。完整來源連結、子目錄作用範圍與本機補充項目的對照，已加入 [建議忽略的檔案清單](gitignore-recommendations.zh-TW.md) 第 4 節。Ponytail、SymDex 及本機 MCP 設定的專用排除則是本機新增。

目前 `.gitignore` 已涵蓋多數環境、建置、快取與私人設定。以下 MCP 排除規則已依使用者要求套用：

```gitignore
# Optional third-party developer tool checkouts.
/.agents/mcp/ponytail/
/.agents/mcp/symdex/

# Machine-specific MCP configuration; keep a portable example separately.
/.agents/mcp/mcp.json
```

以下兩個 Piper 模型副本的精確排除也已依使用者要求套用；本機檔案仍保留：

```gitignore
# Locally added, downloadable Piper voice copies.
/ai/llm-ui/piper-voices/en_US-lessac-low.onnx
/ai/llm-ui/piper-voices/en_US-lessac-low.onnx.json
```

`/.agents/mcp/symdex-venv*/` 已在現有規則中。保留 `.agents/skills/`、`.agents/workflow-kit/` 和 `.agents/mcp/README.md`；不新增整個 `.agents/` 的排除。

`.gitignore` 只影響尚未追蹤的檔案。已經進入 Git 索引的虛擬環境或 gitlink 不會自動移除；若採用全新 repo／全新歷史，應從遵守此政策的乾淨內容建立首次提交。忽略也不等於刪除本機檔案。

## 9. 目前的保存決策

- 保留 uv／pip／Node／Rust 的配置與鎖定檔。
- 保留機器人新增功能、測試、自訂 AI 技能和流程原始文件。
- 保留上游原本追蹤的完整專案資源與 LFS 規則。
- 忽略安裝環境、第三方開發工具 checkout、建置產物、下載快取與暫存。
- 私人設定另外保存，新機器從範本填入。
- 已核對重建途徑；完整重裝、跨平台執行和 LFS 遷移仍需實際驗證。

本次已新增本文件，並更新 `.gitignore` 排除 Ponytail、SymDex checkout、本機 MCP 設定與兩個 Piper 模型副本。2026-10-10 已以 `git rm --cached` 取消追蹤 14,462 個符合忽略規則的項目；所有原本存在的本機檔案均保留。索引目前保留 1,513 個項目，其中包含上游全部 1,458 個檔案及 uv 配置，仍被追蹤的忽略項目為 0。

取消追蹤已暫存，尚未提交或上傳 GitHub，也不會清除舊提交歷史。未執行重裝或建置；全新 repo 應依目前規則建立新的首次提交。
