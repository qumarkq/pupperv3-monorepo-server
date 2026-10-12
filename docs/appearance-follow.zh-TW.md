# 語音指定上衣顏色的人物跟隨

本功能將 `robotdog` 的顏色選人、單人鎖定和跟隨策略整合至 server 的 `person_follower` ROS 套件。沿用既有 Whisper → Ollama → Pupster ROS 工具流程；不再另外啟動 `voice_remote_qwen_dry_run.py`、Qwen llama-server 或 `/home/pi/pupper-tests` 堆疊。

支援「跟隨穿紅色上衣的人」等單一上衣顏色：red、orange、yellow、green、blue、purple、black、white、gray。這是 HSV 顏色與方框連續性追蹤，不是人臉／姓名辨識；同色衣服、遮擋或光線改變可能導致停止。

## 建置與設定

在已具備 Pupper V3 硬體設定、ROS 2 Jazzy、Hailo 模型及相機校正資料的狗端使用既有建置環境。GitHub 的來源碼不能替代被排除的大型部署資產。ROS 視覺套件使用系統 ROS Python；語音環境仍由 `uv` 管理，勿用語音虛擬環境取代 ROS Python 或修改系統 NumPy。

在儲存庫根目錄：

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
# 已有完整 ROS workspace 的增量建置；首次部署仍依主專案流程建置全部依賴。
colcon build --packages-select hailo person_follower neural_controller --symlink-install
source install/setup.bash
```

`hailo/setup.py` 現在會安裝 `camera_params.yaml` 到套件內，確保安裝後可取得與 Hailo 相同的投影校正。請確認這份校正對應實際相機，不要用其他機器的校正覆蓋。

在語音專案 `ai/llm-ui/agent-starter-python/.env.local` 增加：

```dotenv
PUPSTER_PERSON_FOLLOW_MODE=appearance
PUPSTER_CMD_VEL_TOPIC=/llm_cmd_vel
```

沿用現有 `AGENT_DESIGN=ollama` 與 Ollama/STT/TTS 設定。若使用遠端中文 Whisper，設定 `STT_BACKEND=remote`、`REMOTE_STT_LANGUAGE=zh`，並使用現有 `REMOTE_STT_URL`／自動探索設定。若使用本機中文辨識，Whisper 模型須支援多語言（不要選 `.en`），並設定 `LOCAL_STT_LANGUAGE=zh`。遠端 STT 服務仍須另外啟動。

## 啟動

先結束其他會占用相機、Hailo 或馬達控制器的堆疊。此模式僅支援真實相機，不能使用 `sim:=True`。

在上述 `ros2_ws` 終端機執行：

```bash
python3 ../robot/utils/run_appearance_follow_safe.py --max-seconds 600
```

啟動器使用 `person_follow_mode:=appearance`，只啟動顏色跟隨節點，不啟動原本的一般跟隨節點；相機、Hailo、速度分配器與馬達控制器仍共用主專案的節點。顏色跟隨一開始未啟用，不會自行選擇預設目標。

啟動器會等待本次啟動日誌中的 `Finished homing!` 與 12 個不同的 `Homed actuator` 確認，再設定顏色節點的 `homing_verified`。等待校正上限 120 秒；放行後運行時間可指定 30–600 秒，預設 180 秒。時間到、Ctrl+C 或啟動失敗會關閉自己啟動的 ROS 程序群組。等待 `HOMING VERIFIED` 後才開始語音測試；跟隨仍要求控制器 active 與新鮮的 12 關節回授。直接使用原 launch 的顏色模式時，校正門檻預設關閉，不能直接啟動跟隨。

另一個已載入 ROS workspace 的終端機，進入語音專案：

```bash
cd ../ai/llm-ui/agent-starter-python
uv run python src/agent.py console
```

說「跟隨穿紅色上衣的人」。模型會先停止舊動作、排入步行啟動，再呼叫 `activate_appearance_following(shirt_color="red")`。這個工具會等待已排入的步行啟動完成，停止舊跟隨、清理其餘舊動作，再檢查控制器、唯一跟隨速度發布者與同步影像，選色並等待唯一穩定目標鎖定。

本整合透過語音工具執行，不使用原獨立腳本的終端機 `y` 確認。只有 `Target locked` 的工具成功回覆才表示跟隨已啟用；選色成功或模型口頭答應不代表已跟隨。若服務或鎖定失敗，不會改用一般人物跟隨。

預覽在狗端 `http://127.0.0.1:8766`，顏色跟隨模式為唯讀。模型必須要求明確上衣顏色；「跟著我」、姓名、人臉或不支援的外觀不能推測為指定顏色。

## 停止與模式切換

說「停止」會呼叫既有停止工具，並取消仍在等待步行啟動或目標鎖定的請求。也可在 ROS 終端機手動停止跟隨：

```bash
ros2 service call /appearance_follow/deactivate std_srvs/srv/Trigger '{}'
```

跟隨停止不代表馬達斷電。Ctrl+C 關閉 ROS launch 才是結束整個堆疊；實體／手動急停仍依既有狗端方法使用。語音服務故障且無法確認停止時，語音工具會回報失敗，並在獨立 ROS executor 執行緒持續發布零速度，避免速度分配器的 500 ms 過期後重新放行跟隨；不要只依靠語音停止作硬體急停。

目標遺失、同色目標不唯一、重疊、影像過期或控制器／12 關節回授失效時，節點輸出零速度，不會自行尋找替代人物；需要重新明確下達指令。前進上限 0.10 m/s、轉向上限 0.15 rad/s，沒有新增障礙物避讓。

回到原本一般跟隨時，結束現有堆疊，再使用預設 launch 或 `person_follow_mode:=ordinary`，並將語音環境改為 `PUPSTER_PERSON_FOLLOW_MODE=ordinary`。ROS 與語音的模式設定必須一致。

## 離線驗證

使用有 NumPy、pytest 的隔離 Python 環境，在儲存庫根目錄：

```bash
python -m pytest -q \
  ros2_ws/src/person_follower/test/test_appearance_policy.py \
  ros2_ws/src/person_follower/test/test_appearance_readiness.py \
  ros2_ws/src/person_follower/test/test_appearance_homing.py \
  ai/llm-ui/agent-starter-python/tests/test_appearance_follow_client.py \
  ai/llm-ui/agent-starter-python/tests/test_appearance_ros_integration.py
```

離線測試覆蓋選色不自行啟動、目標遺失與過期、歧義、馬達回授就緒條件、停止取消等待中的請求、服務失敗、鎖定逾時、控制模式不符、持續零速度和跟隨狀態更新。不能替代實機的 ROS 建置、聲音辨識、相機影像同步、馬達與步態驗證。
