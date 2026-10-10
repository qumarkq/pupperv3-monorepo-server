# 建議忽略的檔案清單

更新日期：2026-10-10（Asia/Taipei）  
適用專案：`pupperv3-monorepo-server`

**保留原始碼、依賴配置、鎖定檔與上游原有資源；忽略本機安裝環境、第三方開發工具副本、建置產物、暫存與私人設定。**

本清單依目前 [`.gitignore`](../.gitignore) 整理。忽略規則與取消 Git 追蹤是兩個步驟；兩者目前均已完成，本機檔案保留。建立全新 repo 時，應依規則排除這些內容。

## 1. 已套用的忽略項目

下列路徑相對於專案根目錄。表格列出主要路徑／模式，完整規則以 `.gitignore` 為準。

「上游是否也有忽略」依第 4 節的 17 份上游 `.gitignore` 核對：**有**＝已有對應規則；**部分有**＝只涵蓋其中部分模式／目錄；**沒有**＝未找到對應專用規則。子目錄規則不代表全專案同名檔案都被排除，也不代表該檔案已被上游追蹤。

| 類別 | 檔案／目錄／模式 | 上游是否也有忽略 | 忽略理由與取得方式 |
| --- | --- | --- | --- |
| Python 安裝環境 | `.venv/`、`.venv-*/`、`.venv_*/`、`venv/` 及其變體、`ENV/` | 部分有：agent 與 RL 已忽略 `.venv`；環境名稱變體由本機補上 | 依保存的配置重新安裝；主 agent 使用 `uv sync --locked` |
| SymDex 環境 | `.agents/mcp/symdex-venv*/` | 沒有：上游沒有此工具環境 | 工具安裝環境，可重新建立 |
| Ponytail 工具副本 | `.agents/mcp/ponytail/` | 沒有：上游沒有此工具 | 非 Pupper 執行依賴；需要開發工具時，可取得指定版本再安裝 |
| SymDex 工具副本 | `.agents/mcp/symdex/` | 沒有：上游沒有此工具 | 非 Pupper 執行依賴；需要開發工具時，可重新取得 |
| 本機 MCP 設定 | `.agents/mcp/mcp.json` | 沒有：上游沒有這份設定 | 寫死 Windows 絕對路徑，新機器需設定；可分享設定範本應另保留 |
| Node 安裝依賴 | `node_modules/` | 有：兩個 live-audio 子專案忽略 `node_modules` | 保存 package/lock 檔，依配置重新安裝；有相容 lock 檔時使用 `npm ci` |
| ROS 建置結果 | `ros2_ws/build/`、`ros2_ws/install/`、`ros2_ws/log/` | 有：上游根目錄明列相同三個目錄 | 在已配置的 ROS 環境執行 `bash ros2_ws/build.sh`；歷史日誌不會因此還原 |
| 其他建置結果 | `build/`、`dist/`、`dist-ssr/`、`target/`、`cmake-build-*/` | 有：相關子目錄忽略 build、dist、dist-ssr、target、cmake-build；本機擴為共用規則 | 由 Python／前端／Rust／CMake 建置工具重新生成 |
| CMake 生成設定 | `CMakeFiles/`、`CMakeCache.txt`、`cmake_install.cmake`、`compile_commands.json` | 部分有：xsimd 明列 `docs/CMakeCache.txt`；其他檔名沒有專用規則 | 建置過程生成；保存手寫的 CMakeLists.txt |
| Python 快取與套件資訊 | `__pycache__/`、`*.py[cod]`、`*.egg-info/`、`*.egg`、`.eggs/` | 部分有：pyc、pycache、egg-info 已有；其他模式由本機補上 | 執行或安裝時產生 |
| 測試／檢查快取 | `.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.tox/`、`.nox/` 等 | 部分有：agent 有 pytest／ruff 快取；其餘由本機補上 | 工具產生，可重新執行；測試原始碼保留 |
| 測試報告 | `.coverage*`、`htmlcov/`、`coverage.xml`、`coverage/` | 沒有：上游沒有表列報告檔名的專用規則 | 測試生成結果，必要時重新取得 |
| 工具快取／索引 | `.cache/`、`.symdex/`、`.vite/`、`.npm/`、`.pnpm-store/`、`*.tsbuildinfo` | 部分有：xsimd 有 `.cache/`；其他表列模式沒有專用規則 | 可重新下載、建置或建立索引 |
| 本機下載的語音模型 | `ai/llm-ui/agent-starter-python/models/` | 沒有：上游沒有此 models 目錄的專用排除 | Piper 可用既有下載指令取得；Whisper 依模型名稱在首次使用時下載 |
| RL 實驗產物 | `ai/rl/` 下的 `outputs/`、`multirun/`、`output_*/`、`checkpoint/`、`checkpoints/`、`wandb/`、`.hydra/` | 部分有：RL 有 `outputs`；其他表列輸出模式由本機補上 | 本機訓練／實驗輸出；需要保存的實驗成果另行備份，不排除已部署策略 |
| 映像製作產物 | `infra/pupper_image_builder/` 下的 Packer cache/plugin、`*.img`、`*.img.*`、`pupOS_pios_full_*` | 部分有：Packer cache/plugin、img 已有；img 變體與版本標記由本機補上 | 下載快取、生成映像與版本標記；既有 DEB 資源保留 |
| 私人環境設定 | `.env`、`.env.*`，但保留 example/sample/template 範本 | 部分有：agent／映像製作等子目錄已排除私人設定；本機擴為共用規則 | 由範本填入；真實 API 金鑰、服務位址等需自行保存與設定 |
| 私鑰與憑證 | `*.pem`、`*.key`、`*.p12`、`*.pfx`、`id_rsa`、`id_ed25519` | 部分有：根目錄有 `*.pem`；其他表列金鑰模式由本機補上 | 私人資料，不由安裝指令自動還原，應另行保存 |
| 執行日誌 | `*.log`、`*.log.*`、套件管理工具 debug log | 部分有：前端已有 log 與 debug log；輪替日誌等由本機補上 | 新執行會產生新的日誌；需要的歷史日誌另行保存 |
| 系統與編輯器暫存 | `.DS_Store`、`._*`、`.AppleDouble/`、`Thumbs.db`、`.idea/`、`*.swp`、`*.swo`、`*.swn`、`*~` 等 | 部分有：DS_Store、idea、swp 等已有；其餘模式由本機補上 | 本機顯示設定或編輯器暫存；必要的復原內容應先保存 |
| Blender 備份 | `*.blend[0-9]` | 部分有：模型子專案有 `*.blend1`；本機擴為 `*.blend[0-9]` | 自動備份；原始 `.blend` 保留 |
| 本機錄音與臨時資料 | `*.wav`、`untracked_bags/` | 有：根目錄已有 `*.wav`、`untracked_bags` | 沿用原專案的排除慣例；實際錄製內容不能靠建置還原，必要時另行備份 |
| Bag 圖片分析輸出 | `bags/` 下的 `extracted_images/`、`detection_results/` | 沒有：上游沒有這兩個目錄的專用排除 | 分析衍生資料；保留原始 bags，必要時依分析流程重新取得 |

## 2. 已套用的 Piper 模型排除

| 精確檔名 | 上游是否也有忽略 | 理由 |
| --- | --- | --- |
| `ai/llm-ui/piper-voices/en_US-lessac-low.onnx` | 沒有：上游沒有這個檔案，也沒有對應專用排除 | 本機新增的 Piper 英文語音模型，可由下載工具取得 |
| `ai/llm-ui/piper-voices/en_US-lessac-low.onnx.json` | 沒有：上游沒有這個檔案，也沒有對應專用排除 | 上述模型的設定，可與模型一起下載 |

已依使用者要求，把這兩個精確路徑加入 `.gitignore`。本機檔案仍保留；它們不是 Nate711 原專案追蹤的資源。不使用全面排除所有 ONNX／JSON 的規則，上游原有的模型與設定仍保留。


## 3. 明確保留的內容

| 內容 | 決策 |
| --- | --- |
| `pyproject.toml`、`uv.lock`、`uv.toml`、`.python-version`、`requirements.txt` | 保存依賴宣告與版本配置；若某子專案原本沒有其中的檔案，不會憑空新增 |
| `package.json`、`package-lock.json`、`Cargo.toml`、`Cargo.lock` | 保存各語言的依賴配置與鎖定檔 |
| `.env.example` 與 example/sample/template 範本 | 保存可分享設定格式；檔案內容應使用安全範例 |
| 9 個新增 Python 程式／測試，以及既有程式修改 | 保存機器人功能與驗證來源 |
| `.agents/skills/`、`.agents/workflow-kit/` | 保存本機自訂技能與流程原始文件；沒有忽略整個 `.agents/` |
| `.agents/mcp/README.md` | 保存第三方開發工具說明與安裝需求 |
| 可分享的 MCP 設定範本與工具版本資訊 | 應保存，角色類似 uv 配置；目前私人路徑設定不直接共享 |
| Nate711 原本追蹤的模型、3D、圖片、動畫 CSV、bags、HEF、DEB | 保存原專案內容；不因副檔名而一律排除 |
| `.gitattributes`、README、授權文件、部署／建置腳本與本專案文件 | 保存版本控制政策、安裝方式和專案知識 |

## 4. 上游是否也有忽略？有。

已重新讀取 Nate711 的 main 分支，確認 **共有 17 份已追蹤的 `.gitignore`**。核對日期為 2026-10-10，固定版本為 [6f96c5e79faa](https://github.com/Nate711/pupperv3-monorepo/tree/6f96c5e79faa05492992c19918f8cd90b9243281)，包含 1,458 個已追蹤檔案。以下來源連結固定到本次核對版本，避免日後 main 變動造成歧義。

上游已排除多數虛擬環境、依賴、建置產物與暫存；本機的 `.gitignore` 是在這些慣例上補強，並排除額外安裝的 MCP 開發工具。

### 4.1 上游根目錄的實際規則

根目錄 [`.gitignore`](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/.gitignore) 的有效規則如下：

```gitignore
ros2_ws/build/
ros2_ws/log/
ros2_ws/install/
*.DS_Store
*.pem
*.pyc
untracked_bags
*.wav
```

因此 ROS 建置／安裝／日誌目錄、macOS 暫存、PEM、Python bytecode、臨時 bags 與 WAV 的忽略，原版就已經有設定。

### 4.2 上游全部 17 份忽略檔案

下表列出每份檔案與主要規則；完整內容可開啟來源連結。

| 上游 `.gitignore` 路徑／來源 | 主要忽略內容 |
| --- | --- |
| [.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/.gitignore) | ROS `build/log/install`、`*.DS_Store`、`*.pem`、`*.pyc`、`untracked_bags`、`*.wav` |
| [ai/llm-ui/agent-starter-python/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/llm-ui/agent-starter-python/.gitignore) | `.env`、`.env.*`（保留 `.env.example`）、`.venv`、`__pycache__`、`*.egg-info`、pytest/ruff 快取與本機編輯器目錄 |
| [ai/llm-ui/live-audio-original/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/llm-ui/live-audio-original/.gitignore) | `node_modules`、`dist`、`dist-ssr`、日誌、`*.local` 與編輯器暫存 |
| [ai/llm-ui/live-audio/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/llm-ui/live-audio/.gitignore) | `node_modules`、`dist`、`dist-ssr`、日誌、`*.local` 與編輯器暫存 |
| [ai/llm-ui/ui-rs/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/llm-ui/ui-rs/.gitignore) | `target`、`*.wav` |
| [ai/playground/fisheye_reprojection_benchmark/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/playground/fisheye_reprojection_benchmark/.gitignore) | 該基準測試目錄內的 `*.jpg` |
| [ai/playground/image-description-benchmark/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/playground/image-description-benchmark/.gitignore) | 該測試目錄內的 `*.env.local`、`*.json`、`*.csv`、`*.egg-info`、`*.pth`、圖片處理輸出與 `visualizations` |
| [ai/rl/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ai/rl/.gitignore) | `.venv`、`outputs` |
| [infra/pupper_image_builder/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/infra/pupper_image_builder/.gitignore) | Packer cache/plugin、`*.img`、`random`、`.DS_Store`、`.env.local` 及其變體、`*.zip` |
| [pupper-rs/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/pupper-rs/.gitignore) | `target` |
| [ros2_ws/src/control_board_hardware_interface/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/control_board_hardware_interface/.gitignore) | `.DS_Store`、`build`、`__pycache__` |
| [ros2_ws/src/neural_controller/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/neural_controller/.gitignore) | `.DS_Store`、`.vscode/`、`__pycache__` |
| [ros2_ws/src/neural_controller/modules/RTNeural/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/neural_controller/modules/RTNeural/.gitignore) | `build*`、`cmake-build*`、`__pycache__`、`docs` 與本機編輯器目錄 |
| [ros2_ws/src/neural_controller/modules/RTNeural/examples/hello_rtneural/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/neural_controller/modules/RTNeural/examples/hello_rtneural/.gitignore) | `*.o`、`*.exe` |
| [ros2_ws/src/neural_controller/modules/RTNeural/modules/xsimd/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/neural_controller/modules/RTNeural/modules/xsimd/.gitignore) | 編譯產物、函式庫、執行檔、`*.swp`、`build/`、生成文件目錄與 VSCode/clangd 快取 |
| [ros2_ws/src/pupper_v3_description/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/pupper_v3_description/.gitignore) | `.DS_Store`、`build`、`*.blend1` |
| [ros2_ws/src/real2sim_controller/.gitignore](https://github.com/Nate711/pupperv3-monorepo/blob/6f96c5e79faa05492992c19918f8cd90b9243281/ros2_ws/src/real2sim_controller/.gitignore) | `.DS_Store`、`.vscode/`、`__pycache__` |

**子目錄規則只作用在該目錄及其下層。** 例如 fisheye benchmark 的 `*.jpg` 與 image-description benchmark 的 `*.json`／`*.csv`，不代表上游把整個專案的圖片、JSON 或動畫 CSV 全部排除。`.gitignore` 也不會自動取消已追蹤檔案。

### 4.3 本機規則與上游的差別

| 內容 | 與上游的關係 | 本機目前處理 |
| --- | --- | --- |
| ROS build/install/log、DS_Store、PEM、pyc、WAV、臨時 bags | 上游根目錄已設定 | 沿用 |
| Python 環境與快取、Node 依賴／建置、Rust target | 上游相關子目錄已設定 | 根目錄增加共用規則及環境名稱變體 |
| 私人 `.env`、日誌、編輯器暫存 | 上游部分子目錄已設定 | 擴充到共用規則；保留設定範本 |
| RL 輸出 | 上游有 `.venv`、`outputs` | 補上 multirun、checkpoints、wandb 等本機輸出模式 |
| Packer／映像產物 | 上游已有 cache/plugin、img、zip 等規則 | 補上其他下載快取、映像副檔名及版本標記 |
| Ponytail、SymDex、SymDex 環境、本機 `mcp.json`、`.symdex/` | 上游沒有這些工具或 `.agents/` 目錄，也沒有對應的專用排除規則 | 本機新增，已套用精確排除 |
| agent `models/` 下載目錄、Bag 圖片分析輸出 | 上游沒有對應的專用目錄排除規則 | 本機補充，已套用 |
| 新增的兩個 Piper 副本 | 上游沒有這兩個追蹤檔案 | 已依使用者要求套用精確排除 |

表格中的「補上」只表示忽略規則涵蓋這些路徑，不代表目前每種產物都已存在。
`.agents/skills/` 和 `.agents/workflow-kit/` 也是本機新增，但目前保留其原始文件；沒有忽略整個 `.agents/`。

### 4.4 上游資源與 LFS 仍保留

前述規則不改變「保存上游原本追蹤內容」的決策。本次已用 `git check-ignore --no-index` 核對上游全部 1,458 個檔案路徑，沒有任何一個被本機目前的忽略規則排除。

先前內容比對發現，其中 89 個本機檔案仍只有 LFS 指標，必須取得實體內容。這些不列為忽略項目；`uv sync`、`npm ci` 和建置指令不會自動還原它們。

## 5. 指令與限制

環境、依賴與下載模型通常可用既有工具取得，不需另寫機器人功能程式。但私人設定、憑證、自訂文件、原始錄製資料和歷史日誌不能一概視為可自動重建。

完整重建指令、指定的工具版本、模型 SHA256、MCP 設定與 LFS 限制，請參閱 [Git 忽略規則與環境重建指南](gitignore-and-rebuild-guide.zh-TW.md)。目前已核對配置與指令語法，尚未實際重裝、跨平台建置或執行完整機器人測試。

2026-10-10 已使用 `git rm --cached` 將 14,462 個符合忽略規則的項目移出 Git 索引，所有原本存在的本機檔案均保留。驗證結果：仍被追蹤的忽略項目為 0，索引保留 1,513 個項目，其中包含上游全部 1,458 個檔案及 uv 配置。取消追蹤已暫存，尚未提交或上傳 GitHub；舊提交歷史不會因此清除。建立全新 repo 時應依規則建立新的首次提交。
