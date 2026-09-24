# tw-legal-calc｜台灣法律計算工具（給 LLM 用的單一入口）

台灣法官、律師辦案會用到的那些試算，做成**一支 LLM 能直接呼叫的工具**。

LLM 最不該做的就是心算。期間、利息、折舊、折現、年資、持分這些數字，模型算起來看似合理、
實際上經常錯在邊界（閏年、起迄日計不計入、不足一期怎麼比例、殘價怎麼定）。
這個專案把這些算術全部落到程式，模型只負責挑工具與解釋結果。

- **一個入口**：`POST /calc {"tool": ..., "params": ...}`
- **問句路由**：`GET /calc/match?q=特休沒休完折多少錢` → 候選工具（純詞彙比對，零 LLM、不會二次幻覺）
- **MCP**：`mcp_server.py`，GitHub Copilot／Claude Desktop／Cursor 直接掛
- **OpenAPI**：FastAPI 自帶 `/openapi.json`，Microsoft 365 Copilot／Copilot Studio 可做成自訂連接器
- **不會就說不會**：資料未備齊的工具回 `ok:false` + `needs`，**絕不臆測數字**
- 零 LLM、零網路、零追蹤：本服務不呼叫任何模型，不連外

## 工具清單（20 支，16 支可用）

| 類 | 工具 | id | 狀態 |
|---|---|---|---|
| 通用 | 經過時間試算 | `time.elapsed` | ✅ |
| 通用 | 上訴抗告再審期間試算 | `deadline.appeal` | 待補料 |
| 通用 | 司法規費試算 | `fee.court` | 待補料 |
| 民事 | 折舊自動試算 | `depreciation` | ✅ |
| 民事 | 霍夫曼一次給付試算 | `hoffmann.lump` | ✅ |
| 民事 | 定期給付折現金額試算 | `hoffmann.pv_periodic` | ✅ |
| 民事 | 資遣費試算（舊制／新制／跨制併計） | `severance` | ✅ |
| 民事 | 利息及違約金試算 | `interest.penalty` | ✅ |
| 民事 | 特休日數試算 | `leave.annual` | ✅ |
| 民事 | 共有人應有部分比例 | `share.ratio` | ✅ |
| 刑事 | 法定刑度加重減輕試算 | `sentence.range` | 待補料 |
| 其他 | 土地分割共有物面積與地價 | `land.partition` | ✅ |
| 其他 | 土地單筆部分維持共有 | `land.keep_share` | ✅ |
| 其他 | 土地數筆合併後應有部分 | `land.merge_share` | ✅ |
| 其他 | 相當租金不當得利試算 | `rent.unjust` | ✅ |
| 其他 | 違約金與利息多項合併試算 | `penalty.interest` | ✅ |
| 其他 | 繼承系統表 | `inheritance.tree` | 待補料 |
| 自建 | 計算機（安全算式求值） | `calc.eval` | ✅ |
| 自建 | 銀行分期利率試算（含反解實質年利率） | `loan.installment` | ✅ |
| 自建 | 借款還款餘額計算 | `loan.balance` | ✅ |

「待補料」四支缺的是法定級距表與加減例規則，缺什麼都寫在 `registry.yaml` 的 `needs:` 欄。
補齊資料即可啟用，歡迎 PR。

## 安裝與啟動

```bash
pip install -r requirements.txt
python3 -m uvicorn serve:app --port 8004
open http://localhost:8004          # 人看的目錄頁
```

## 用法

```bash
# 不知道該用哪支？先問路由
curl -s localhost:8004/calc/match --get --data-urlencode "q=被告占用我的土地五年，相當租金怎麼算"

# 單一入口
curl -s localhost:8004/calc -H 'Content-Type: application/json' \
  -d '{"tool":"leave.annual","params":{"onboard":"1100101","leave":"1150401","monthly_wage":45000}}'
```

```python
import router
router.run("depreciation", {"cost": 600000, "years": 5, "used_years": 3})
```

```bash
python3 router.py list
python3 router.py match 相當租金
python3 router.py run time.elapsed '{"start":"1100101","end":"1150401"}'
```

日期一律吃民國 `YYYMMDD`（如 `1150924`），也接受西元 `YYYYMMDD` 與 `YYYY-MM-DD`。

## 接上 Copilot

### GitHub Copilot（VS Code，agent mode）

專案根目錄建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "tw-legal-calc": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/mcp_server.py"]
    }
  }
}
```

同一份設定也適用 Claude Desktop（`claude_desktop_config.json` 的 `mcpServers`）與 Cursor。

### Microsoft 365 Copilot／Copilot Studio

服務啟動後，`http://<host>:8004/openapi.json` 就是可直接匯入的 OpenAPI 規格：
在 Copilot Studio 建 agent →「動作」→「新增動作」→「從 OpenAPI 匯入」。
Copilot 需要能連到這個位址，所以請把服務跑在 Copilot 觸得到的網段（內網部署即可，本服務本來就不需要外網）。

### 其他 OpenAI 相容的模型

```bash
curl -s localhost:8004/calc/schema?flavor=ollama
```

直接回 function-calling schema，貼進 `tools` 欄即可。端到端示範：

```bash
python3 llm_demo.py "民國110年1月1日到職，115年4月1日離職，月薪4萬5，特休沒休完可以折多少錢？"
# 模型自選 leave.annual → 51.7 日 / 77,548 元，並另呼叫 calc.eval 複核算式

python3 llm_demo.py "標的金額500萬的民事第一審裁判費是多少？"
# fee.court 回 ok:false → 模型據此拒答並列出缺的級距表，未自行推算
```

## 設計上的幾個堅持

1. **不會就說不會**。未備料的工具回 `ok:false` 與 `needs`，讓模型能誠實說「查不到」，
   而不是生一個看起來對的數字。這比多支能用的工具更重要。
2. **中間不捨入**。全程 `Decimal`，只在輸出時四捨五入。逐次小結捨入會累積成可見誤差。
3. **裁量不代勞**。例如相當租金的年息是法官裁量事項，工具只照輸入計算並附上法條上限的提醒。
4. **規則在 YAML 不在 code**。工具目錄、參數規格、特別休假日數表、詞彙路由表全在
   `registry.yaml`，改了免重啟（改 `.py` 才要重啟）。法令修正時改 YAML 即可。
5. **結果自帶計算式與法源**，模型寫書狀或理由時可以直接引用。

## 驗證

```bash
python3 test_calc.py
```

錨點取自司法院辦案小工具各頁說明欄自載的範例，例如利息給付基數
`111.3.10~111.6.5 = 88/365`、`112.3.10~112.6.5 = 88/366`、`111.3.10~113.6.5 = 2又88/365`，
三例皆與本實作一致。特別休假日數表亦與勞動基準法第 38 條逐款核對。

## 檔案

```
registry.yaml    工具目錄＋參數規格＋特休日數表＋詞彙路由表（canonical，可校訂）
router.py        單一入口：list / describe / match / run ＋ CLI
serve.py         FastAPI（含 OpenAPI、function-calling schema、目錄頁）
mcp_server.py    MCP stdio server（零額外相依）
llm_demo.py      端到端示範：模型拿 schema → 自選工具 → 據回傳數字作答
test_calc.py     回歸測試
calc/            dates 期間基礎｜basic 算式求值｜period 經過時間｜money 利息折舊租金
                 hoffmann 霍夫曼折現｜labor 資遣費特休｜land 土地持分｜loan 分期借還款
```

## 免責

試算結果僅供參考，實際仍應以法院裁判結果為準。法令有修正時請先校對 `registry.yaml`
與各模組所引條文。歡迎回報計算錯誤。

## 授權

MIT
