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

## 工具清單（21 支，19 支可用）

| 類 | 工具 | id | 狀態 |
|---|---|---|---|
| 通用 | 經過時間試算 | `time.elapsed` | ✅ |
| 通用 | 上訴抗告再審期間試算 | `deadline.appeal` | 待補料 |
| 通用 | 司法規費試算（含各高院依§77-27 累進加徵） | `fee.court` | ✅ |
| 通用 | 地址→管轄地方法院（含在途期間） | `address.court` | ✅ |
| 民事 | 折舊自動試算 | `depreciation` | ✅ |
| 民事 | 霍夫曼一次給付試算 | `hoffmann.lump` | ✅ |
| 民事 | 定期給付折現金額試算 | `hoffmann.pv_periodic` | ✅ |
| 民事 | 資遣費試算（舊制／新制／跨制併計） | `severance` | ✅ |
| 民事 | 利息及違約金試算 | `interest.penalty` | ✅ |
| 民事 | 特休日數試算 | `leave.annual` | ✅ |
| 民事 | 共有人應有部分比例 | `share.ratio` | ✅ |
| 刑事 | 法定刑度加重減輕試算（處斷刑範圍＋宣告刑逾越檢查） | `sentence.range` | ✅ |
| 其他 | 土地分割共有物面積與地價 | `land.partition` | ✅ |
| 其他 | 土地單筆部分維持共有 | `land.keep_share` | ✅ |
| 其他 | 土地數筆合併後應有部分 | `land.merge_share` | ✅ |
| 其他 | 相當租金不當得利試算 | `rent.unjust` | ✅ |
| 其他 | 違約金與利息多項合併試算 | `penalty.interest` | ✅ |
| 其他 | 繼承系統表 | `inheritance.tree` | 待補料 |
| 自建 | 計算機（安全算式求值） | `calc.eval` | ✅ |
| 自建 | 銀行分期利率試算（含反解實質年利率） | `loan.installment` | ✅ |
| 自建 | 借款還款餘額計算 | `loan.balance` | ✅ |

「待補料」兩支（上訴期間、繼承系統表）缺的是法定規則表，缺什麼都寫在 `registry.yaml` 的 `needs:` 欄。
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
# 模型自選 leave.annual → 63 日 / 94,500 元（離職當期特休權利已取得，全額計）

python3 llm_demo.py "標的金額500萬的民事第一審裁判費是多少？"
# 模型自選 fee.court → 臺灣高等法院轄區加徵後 60,000 元（純民訴§77-13 為 46,000 元）
```

## 設計上的幾個堅持

1. **不會就說不會**。未備料的工具回 `ok:false` 與 `needs`，讓模型能誠實說「查不到」，
   而不是生一個看起來對的數字。這比多支能用的工具更重要。
2. **中間不捨入**。全程 `Decimal`，只在輸出時四捨五入。逐次小結捨入會累積成可見誤差。
3. **裁量不代勞**。例如相當租金的年息是法官裁量事項，工具只照輸入計算並附上法條上限的提醒。
4. **規則在 YAML 不在 code**。工具目錄、參數規格、特別休假日數表、詞彙路由表全在
   `registry.yaml`，改了免重啟（改 `.py` 才要重啟）。法令修正時改 YAML 即可。
5. **結果自帶計算式與法源**，模型寫書狀或理由時可以直接引用。

## 訂正紀錄

- **v0.2.0（2026-09-24）新增三支**：
  - `fee.court` 啟用：「114/1/1 新法」並非民訴§77-13 修正，而是各高等法院依§77-27 報准之**加徵**，且為**累進三級**（十萬以下 +5/10、逾十萬至一千萬 +3/10、逾一千萬 +1/10；強制執行 +1/7）。已收臺灣高等法院與福建高等法院金門分院兩部標準；須依**原審法院**定轄區，舊法版本拒算。
  - `sentence.range` 啟用：依刑法§33、§64–§73 算處斷刑範圍，§71 先加後減自動排序；給宣告刑即檢查是否逾越。只算形式範圍，不判斷加減事由、不代為量刑。
  - `address.court` 新增：以「法院訴訟當事人在途期間標準」§2 附表為管轄區域表（新北市分屬 4 院、臺北與高雄各 2 院）；行政區撞名（如臺北與臺中皆有大安區）或只到縣市時**拒答並列候選**，不猜。
  - 公開版清理：移除作者名與內部用語。

- **v0.1.2（2026-09-24）特休**：v0.1.1 對離職當期特休「按在職比例」折算，並引「勞基法施行細則§24-1Ⅱ②」為據。
  該款實為發給工資之期限（契約終止依第九條發給），**並無比例計給規定**，引用錯誤。
  依施行細則§24第1項（符合條件時取得權利）、§24-1第2項第1款第1目（未休日數×一日工資），離職當期應全額計。
  例：110.1.1 到職、115.4.1 離職、月薪 4.5 萬：v0.1.1 誤算 77,548 元，正確為 **94,500 元**。
  若您曾使用 v0.1.1 的特休結果，請重算。
- **v0.1.2 折舊**：說明文字「不足一月不計」與查核準則§95第6款「不滿一月者以月計」相反，已更正；
  「殘價＝成本÷(耐用年數+1)」原標為§95明文，實為法院車損折舊實務慣用算法，已改標。

## 驗證

```bash
python3 test_calc.py
```

錨點取自司法院辦案小工具各頁說明欄自載的範例，例如利息給付基數
`111.3.10~111.6.5 = 88/365`、`112.3.10~112.6.5 = 88/366`、`111.3.10~113.6.5 = 2又88/365`，
三例皆與本實作一致。特別休假日數表亦與勞動基準法第 38 條逐款核對。
規費錨點（標的 0 元一審 1,500、二三審 2,250）取自司法院小工具畫面實測；刑度錨點含 §33③但書、§64–§65 死刑無期之加減例。

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
                 fees 司法規費｜sentence 刑度加減例｜address 管轄法院與在途期間
data/            court_fees.yaml 規費級距與加徵標準｜court_jurisdiction.yaml 在途期間標準§2 解析之管轄區域表
```

## 免責

試算結果僅供參考，實際仍應以法院裁判結果為準。法令有修正時請先校對 `registry.yaml`
與各模組所引條文。歡迎回報計算錯誤。

## 授權

MIT
