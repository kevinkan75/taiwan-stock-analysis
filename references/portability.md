# 跨平台能力與驗證

## 目錄

- 依模式載入規則
- 能力檢查與降級
- 匯出與載入
- 平台接入方式
- 快照與機械驗證
- 報告文字與版本追溯
- 固定案例與跨模型驗收
- 驗收紀錄與已知狀態
- 版本交付補充

## 依模式載入規則

先讀SKILL.md，再按下表載入全文；檔名均相對於references/。不要用固定的文件份數判定完整性，不把目錄或搜尋摘要當作已讀全文。依階段載入即可，不要求每次載入全部14份參考文件。

| 模式／階段 | 必讀文件 | 條件式追加 |
| --- | --- | --- |
| 個股完整研究（快速／詳細） | portability.md、data-and-methods.md、scoring.md、output-and-history.md、research-process.md、evidence-audit.md、financial-history.md、industry-indicators.md | 計算估值或技術指標時讀calculations.md；研究評分完成前不讀market.md；沒有決策需求不讀decision.md。 |
| ETF完整研究 | portability.md、data-and-methods.md、scoring.md、output-and-history.md、research-process.md、evidence-audit.md、financial-history.md、etf.md、etf-data.md | ETF專屬規則取代個股不適用規則；calculations.md與industry-indicators.md按實際計算及產業分析需要追加。不評分工具依etf.md分流。 |
| 市場快照 | portability.md、data-and-methods.md、output-and-history.md、market.md | 涉及額外計算時讀calculations.md；不啟動個股研究評分或決策流程。 |
| 聚焦單一面向 | portability.md、data-and-methods.md、output-and-history.md；對指定面向發出評分或燈號前讀scoring.md | 估值／技術計算讀calculations.md；產業分析讀industry-indicators.md；ETF另讀etf.md與etf-data.md。不得因載入評分規則而補做未要求的其他面向或整體評分。 |
| 決策層 | 先依完整個股或ETF研究列完成研究，評分完成後讀decision.md與market.md | 保留原研究分數；市場資訊僅用於決策指定關卡，不反向改寫研究評分。 |
| 僅匯出既有互動HTML | portability.md、html-report.md，取得同次已驗證研究與review原檔 | 檔案不足須回到原研究模式補做，不從正文重建數字、不套合成範例。 |

移植時逐份確認上述適用文件及其所需scripts/、assets/可讀取。若宿主只能提供文字，將必讀全文作為有檔名的獨立區塊交付；上下文不足時分階段載入，明列尚未載入項目。缺必讀規則時只整理資料，不發出依賴該規則的評分、燈號或決策；HTML原檔與程式不足時不宣稱已匯出。

## 能力檢查與降級

先記錄 `capabilities`：resources、web、documents、python、storage，各為available／unavailable／unknown；必須根據實際可用工具或操作結果，不把模型名稱當能力證據。

| 能力不足 | 必要處理 |
| --- | --- |
| 無法讀取參考文件 | 由宿主依上方「依模式載入規則」提供SKILL.md與適用文件全文；規則尚未載入完整時只給資料整理，不發出依賴該規則的研究分、燈號或決策。 |
| 無網路／搜尋 | 使用已提供文件，按可核對截止日提供歷史分析；不以模型記憶補最新報價或申報，不宣稱目前訊號。 |
| 無PDF／文件解析 | 改用可讀官方HTML或使用者提供的原文；讀不到的數值保持缺值。搜尋摘要不能替代原文。 |
| 無Python | 可用等效可驗算計算工具；否則按公式人工核對並標未完成程式驗證。技術指標未計算時保持not_run，不填趨勢。 |
| 無持久保存 | 在當次對話交付報告與JSON文字；明列尚未留存，跨次比較需要重新提供快照。不得假稱已保存。市場與產業快照無法保存時只供當次使用，不宣稱可跨對話沿用。 |

平台只提供工具映射：搜尋及網頁讀取、文件解析、Python、來源引用、持久儲存。核心不綁定任何工具名稱或帳號。ChatGPT的Pages／Library是可選保存方式；其他平台可用一般Markdown、JSON檔或資料庫。不要把ChatGPT內部頁面ID／引用ID當成跨平台文件內容；保存穩定來源網址，附件用 `attachment:檔名#page=頁碼` 識別並一併提供。

## 匯出與載入

- 對外可攜目錄命名 `analyze-stocks`，保持SKILL.md、references、scripts、assets及相對路徑。不要改動本平台管理的安裝目錄。
- `agents/openai.yaml`只屬OpenAI介面與觸發設定；目標平台可排除或忽略，再使用自身觸發方式。資產中的圖示可選；Schema及計算腳本須保留。`tests/`為維護者回歸測試，隨技能發布但不影響分析執行。排除__pycache__、個股報告、暫存與帳號資料。
- 本技能的Python程式只用標準函式庫，執行環境採Python 3.8以上；跨平台應實跑自身版本。JSON／Markdown可讀不等於自動載入、工具權限或結果一致。
- Claude Code、Gemini CLI等平台的安裝位置及權限，以當時官方文件為準；本技能不授權跳過目標平台的權限程序。不宣稱一般聊天介面或任意API原生支援技能安裝。

## 平台接入方式

先確認宿主的實際能力，再選接入方式；本節是能力介面要求，不是特定產品的安裝保證。

| 接入方式 | 宿主需完成的工作 | 驗收界線 |
| --- | --- | --- |
| 支援技能目錄的代理工具 | 保留相對目錄，設定自身觸發方式；允許代理讀取適用規則，並按授權呼叫搜尋、文件解析與本地Python。 | 能顯示技能名稱不代表已讀取規則；須實際完成固定案例及驗證。OpenAI介面設定可忽略。 |
| 僅可上傳文件的聊天介面 | 明確要求依SKILL.md及適用全文執行；確認附件內容確實可讀。只有文字能力時依降級規則交付。 | 上傳ZIP不代表平台會解壓、讀取巢狀文件或執行程式；不支援時由使用者或宿主提供全文。 |
| API／自建代理 | 由宿主提供模式路由、規則載入、搜尋／原文取得、計算及驗證呼叫、檔案保存與錯誤回傳；記錄工具結果。 | 單一模型API呼叫不等於完整執行環境；程式庫或模型名稱本身不證明任何工具能力。 |

工具可替換實作，但須回傳可核對的資料：原文取得保留穩定網址、文件日期及定位；計算保留原始輸入與口徑；驗證保留命令、退出狀態及valid/errors；保存保留可重新取得的檔案識別。工具失敗時按能力表降級，不臆造成功結果。

保留原JSON欄位名稱、版本、固定摘要欄名、規則版本行及結果行；僅更換宿主工具，不翻譯或改寫驗證器所需的格式。一般JSON Schema驗證只涵蓋結構，不能取代snapshot_guard、etf_guard、decision_guard及review_guard的適用檢查。等效實作須用相同案例比對，未驗證前不得宣稱等同原驗證器。

外部執行驗證時，在驗收紀錄分列模型本身能力與外部宿主能力；模型無Python而宿主可執行時，capabilities.python仍按被評估對象實際能力記錄，不回填為模型原生能力。不得將任一模式的能力紀錄加入既有研究JSON頂層而破壞Schema。

## 快照與機械驗證

個股新快照採schema 1.5／model 1.3。發布版本的單一程式來源為rules_core.py，SKILL.md metadata為介面鏡像，由測試核對；不在每份模板複製發布組合。現行與歷史支援分支分別見RELEASE_PROFILE／ARCHIVED_PROFILES，算術及摘要適用範圍見ARITHMETIC_PROFILES／SUMMARY_PROFILES。未知版本拒絕；舊格式1.0／1.1保留原檔、回報未驗證，不回填欄位或重算歷史。

市場與產業快照（model market-1.0）第一階段同樣不屬於快照與驗證器範圍：JSON標validated=false，不交snapshot_guard。個股快照採schema 1.5，不新增頂層欄位；相對強弱與Beta只用metrics額外鍵，cost_log改列於報告末行。

ETF新紀錄採獨立schema 1.1／model etf-1.2，交etf_guard，不交snapshot_guard；欄位、derive／finalize與範圍依etf.md「快照與機械驗證」。etf-1.1歷史紀錄使用etf.schema-1.0.json及原規則分支；etf-1.0舊紀錄保持validated=false、人工核對，不回填新格式。

決策結論由decision_guard另驗證，格式、命令及保存完整依decision.md「決策結論程式驗證」；不放入個股scores；ETF來源須依本身驗證器通過，不能只憑決策成功認定研究已驗證。snapshot_guard單獨的valid不證明行動正確。新decision-1.1核對第2、6、7關數值與結論；其他關卡、來源真實性與市場日曆仍人工。舊decision-1.0使用decision.schema-1.0.json，按原發布組合核對結論。

驗證器支援model 1.0、1.1、1.2及1.3；重大產業調整或自訂門檻須另定模型版本、Schema及驗證規則，不能以1.0標記取得程式通過。驗證器本身可在外部執行，不能把外部驗證能力回填為目標模型的Python能力。

範例見 `assets/snapshot.example.json`（合成資料，`tests/check_snapshot_example.py` 保證可通過驗證器）；正式格式見 `assets/snapshot.schema.json`（JSON Schema Draft 2020-12）。`scripts/snapshot_guard.py`僅執行此內附Schema所使用的關鍵字，遇未支援關鍵字即報錯，不是通用JSON Schema引擎。其他平台可另用符合Draft 2020-12的驗證器並啟用format檢查，作為結構檢查；仍須執行原技能的適用驗證器或已驗收的等效實作，才能宣稱業務規則通過。

執行：

```bash
python3 <技能目錄>/scripts/snapshot_guard.py input.json --report final-report.md --derive > derived.json
python3 <技能目錄>/scripts/snapshot_guard.py derived.json
```

`--derive`在model 1.2起會先計算估值原始門檻分，再套用R1–R3的上限或null規則、回寫估值三項有效分與applied_adjustments，然後填入覆蓋數、面向分、固定權重、技術燈號及整體訊號。結構或證據檢核失敗時不輸出修正快照。預設不改檔，列valid／errors／derived，錯誤退出2；資料不足但燈號正確是有效快照。

手動完成：確認截止日期→記四項資格狀態及同名validation→核對財報依賴與三項證據→套用R1–R3、R4、R6→確認重大事件優先及技術狀態→保存完整報告與版本→核對Schema。無程式時須標未完成程式驗證，不能把人工敏感度聲稱為snapshot_guard結果。

## 報告文字與版本追溯

- model 1.3必填report_markdown，內容為實際定稿報告（含摘要、結論、評分與決策文字），不能用摘要或「待產生」替代。`--report final-report.md --derive`將UTF-8全文帶入，推導report_sha256與信心；把推導結果反映到報告後再帶入、再驗證。定稿需獨立一行「規則版本〔來源研究rule_version〕」，當前新分析由SKILL.md metadata填入，並保留單一結果行「整體投資訊號：🟡；總分：75；暫定：否；信心：高」（數值依推導換填，未知或重大風險寫總分不計分、信心未評定）。這一行由預設驗證核對，不能與overall矛盾；--derive不替作者改寫報告。歷次比較可另寫前次規則版本，不當作當次標頭。存檔兩者必須使用同一最終文字；預設驗證拒絕不符的雜湊。--report不適用舊模型。
- 文字篩檢覆蓋最終報告、各評分reason、估值方法／假設／理由、風險、事件、缺口與重大風險理由；結構化財務數值檢查仍保留。財報未直接核對時，出現ROE、FCF、淨值、負債比、流動比、現金轉換等肯定主張即拒絕，即使financials_dependent宣告true或false。明確「未取得、已清空、不使用」且同分句無數值／肯定證據者可保留（R1–R10規則編號不算數值）。含歧義的分句採保守拒絕，改寫清楚或補原文查證。
- 這是可追蹤位置的詞彙篩檢，非通用語意證明，不能涵蓋所有同義改寫。原文查證與最終人工核對仍必要；雜湊只綁定文字，不證明內容真實。不掃技能說明、來源標題或外部未帶入的報告。
- 每筆新研究快照保存skill_version、rule_version、validator_version；按上方版本映射執行，回傳calculation_checks／summary_checks只標檢查範圍，須同時valid=true才表示通過。主.次號或模型不同的歷次分數依output-and-history僅列示，不改歷史。決策另保存其schema／model、結論驗證器版本及原研究檔案雜湊；不得用決策版本覆寫來源研究版本。
- --derive不改原檔；自動回寫三項有效分、調整紀錄、信心、暫定、sensitivity及report_sha256，不替資料缺漏、原始證據或歷史版本補值。`--sensitivity`只輸出R6結果；`--compare previous.json`驗證兩份快照後檢查證券與版本，未知／不相容時回傳comparable=false。比較仍需核對財務期間、截止時間與假設。

技術資料筆數：研究層門檻為240筆（scoring.md、data-and-methods.md）。model 1.1起snapshot_guard在observation_count低於240時拒絕computed，須改標insufficient_data；model 1.0舊快照仍用60筆下限，以維持舊檔可驗證。Beta的240筆門檻仍由分析者人工遵守，驗證器尚未檢查。

`analysis_scope=current`要求報價為最近可用交易時點；`historical`只代表截至data_cutoff_at的研究，不對目前價格作結論。analysis_at是實際執行時間，data_cutoff_at是資料截止時間；都須有時區。不可因歷史模式而回填截止時未公開的財報或預估。

## 固定案例與跨模型驗收

執行 `python3 <技能目錄>/tests/check_portability.py`，檢查檔案連結、依賴、Schema／評分門檻與固定算例。新增tests/check_calculation_links.py直接呼叫正式驗證器及命令列，檢查各情境乘積、核心衍生公式、輸入引用、區間current_metric、公告截止與事件狀態，以及舊1.5.0版本不被改寫。具體輸入與未涵蓋方法見calculations「計算與欄位連動」。其中規則案例（R1–R3、R5、R7、R10）使用測試檔內自寫函式固定公式，不證明驗證器已實作；驗證器實際把關的規則另有直接呼叫它的測試：`tests/check_financials_dependent.py`（財報依賴）、`tests/check_technical_gate.py`（技術面240筆）、`tests/check_snapshot_example.py`（快照範例）。`tests/portability_cases.json`使用合成資料，股票名稱僅作路由與口徑識別，不是該股票實際行情或分析。

新增tests/check_summary_format.py直接驗證1.7.0摘要缺行、順序、重複、空值與舊1.5.0／1.6.0格式相容；tests/decision_cases.json保存八個人工驗收案例，check_decision_guard.py以固定完整燈號重跑正式結論程式，另遍歷65,536種燈號組合檢查安全性質；不宣稱數據證據已驗證。check_rules_core.py使用重構前凍結雜湊核對歷史原檔與完整推導結果。

新增 `tests/check_valuation_guardrails.py` 直接呼叫正式snapshot_guard，驗證R1–R3及舊模型相容。`tests/check_consistency.py`直接驗證文字漏檢、否定敘述、R4／R6、版本、雜湊、命令列及舊檔保留；新增tests/snapshot.model-1.2.json固定保存舊模型範例作回歸資料。ETF／市場／決策專屬規則與Beta等仍未全部接程式，不宣稱整份技能已全自動驗證。

讓各目標平台在相同資料、來源、截止時間與假設下各產生schema 1.5快照，再交snapshot_guard驗證；不得只比文字或只看成功載入。至少涵蓋2330／TSM辨識、尖點低基期、台達電估值缺口、過期報價、技術資料不足、重大事件、無外部EPS但有獨立模型。不得洩露案例預期結果給執行模型。

保留平台、模型版本、執行日期、工具能力、輸入／輸出及測試結果。只完成本地腳本或同平台獨立驗收，不能寫成Claude／Gemini已通過。沒有實際執行介面時標跨模型未執行，不阻擋可完成的Skill更新。

## 驗收紀錄與已知狀態

分別判斷「規則可讀取」「工具流程可執行」「相同輸入的規則結果一致」與「不同模型的證據判讀一致」。同一份模型產生的JSON交同一驗證器兩次，不是跨模型驗收；程式通過也不證明來源真實。

每次驗收另存下列紀錄，不加入研究快照Schema；可存一般Markdown或JSON。使用相同的輸入原檔、來源、截止時間及假設，評分前不提供預期答案；比較機械結果與定性證據的差異，不要求報告逐字相同。失敗或部分完成須保留實際輸出及未完成範圍。

```json
{
  "executed_at": null,
  "platform": null,
  "model_version": null,
  "runtime": {"os": null, "python": null, "node": null},
  "skill_version": null,
  "rule_version": null,
  "capabilities": {
    "resources": "unknown", "web": "unknown", "documents": "unknown",
    "python": "unknown", "storage": "unknown"
  },
  "external_host_tools": [],
  "loaded_files": [],
  "case_id": null,
  "input_sha256": null,
  "data_cutoff_at": null,
  "assumptions_reference": null,
  "output_reference": null,
  "validator_results": [],
  "comparison_reference": null,
  "differences": [],
  "status": "not_run",
  "limitations": []
}
```

capabilities使用available／unavailable／unknown；status使用passed／failed／partial／not_run。填入實際模型版本與完整帶時區時間；未執行欄位保持null或空陣列，不填虛構版本。validator_results逐項保留命令、退出碼、valid及錯誤；僅語法檢查時寫明未在該Python版本實際執行。紀錄避免帳號憑證與個人本機路徑。

截至2026-10-16，本次維護已取得的驗收證據如下；僅代表當次環境，不代表其他平台或未來版本。

| 項目 | 實際環境／方法 | 狀態與範圍 |
| --- | --- | --- |
| 完整本地回歸 | Linux、Python 3.12.14、Node.js 24.19.0；scripts/run_checks.py | 通過18組Python共1,794項、25項Node檢查及65,536種決策燈號組合；為合成資料與本地邏輯檢查。 |
| 獨立目錄、排除OpenAI設定 | 複製至臨時目錄，排除agents/與Git資料；執行check_portability.py、個股與review範例驗證、HTML匯出及verify | 214項可攜性檢查與四個CLI流程通過；未呼叫其他模型、未取得即時行情。 |
| Python 3.8語法 | 以Python 3.12的ast.parse(feature_version=(3,8))解析14份scripts/*.py | 語法檢查通過；不是Python 3.8執行驗收。 |
| 行情輸入稽核1.0.0 | check_bar_audit.py；合成行情、公開CLI及finance_math共用核心 | 157項通過；涵蓋排序／重複、OHLC、缺量與零量、口徑衝突、日曆差異與百分比邊界；未驗證外部來源或歷史回測。 |
| 其他Python版本及Windows實機 | 本次未實際執行 | 未執行；CI配置及換行模擬不等於這些環境通過。 |
| Claude／Gemini等目標平台的固定案例 | 本次沒有可用的目標平台模型執行介面 | 跨模型未執行；不宣稱安裝、完整工具流程或結果一致性已驗收。 |
| HTML行動裝置 | 2026-10-16使用者確認單一報告mobile-v4之iPhone章節連結及版面；共用模板移植為呈現器1.0.1 | 該實機範圍已確認；其他裝置、所有預覽器、完整鍵盤、圖表互動及列印仍未驗收。程式測試不能取代實機結果。 |

## 1.11.0交付補充

完整新個股／ETF報告及決策另執行SKILL.md直接連結的research-process.md；保存共用.review.json及其來源檔雜湊，研究與決策之外再通過review_guard預設驗證。作業狀態、等待原因、取數紀錄及信心追問以該文件為唯一出處；舊紀錄不回填。

## 1.12.0逐項查核

SKILL.md直接連結evidence-audit.md；review-1.1在同一附檔加入逐項主張、固定算術、
反方及論點失效條件。舊review-1.0只用1.11.0原始來源，不能代替新發布的查核。
研究／ETF／決策評分模型與數值門檻不變；新增流程檢查不能作投資績效證明。

## 三年年度資料（1.13.0）

共用review升schema 1.2／review-1.2；financial_history.py在review_guard預設驗證中核對年度原值、單位、期間、來源、勾稽與最終表格，正式規則見SKILL.md直接連結的financial-history.md。股票／ETF研究schema與評分模型維持；1.12.0的review schema及範例另行凍結，不回填新欄位。執行tests/check_financial_history.py及既有全部回歸。
