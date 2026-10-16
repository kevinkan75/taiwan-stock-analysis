# 跨平台能力與驗證

## 能力檢查與降級

先記錄 `capabilities`：resources、web、documents、python、storage，各為available／unavailable／unknown；必須根據實際可用工具或操作結果，不把模型名稱當能力證據。

| 能力不足 | 必要處理 |
| --- | --- |
| 無法讀取參考文件 | 由宿主提供SKILL.md與七份個股references全文（決策模式才需要decision.md）；ETF模式另需etf.md與etf-data.md；市場模式及決策模式第4關另需market.md。規則尚未載入完整時只給資料整理，不發研究分或燈號。 |
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

## 快照與機械驗證

個股新快照採schema 1.5／model 1.3。發布版本的單一程式來源為rules_core.py，SKILL.md metadata為介面鏡像，由測試核對；不在每份模板複製發布組合。現行與歷史支援分支分別見RELEASE_PROFILE／ARCHIVED_PROFILES，算術及摘要適用範圍見ARITHMETIC_PROFILES／SUMMARY_PROFILES。未知版本拒絕；舊格式1.0／1.1保留原檔、回報未驗證，不回填欄位或重算歷史。

市場與產業快照（model market-1.0）第一階段同樣不屬於快照與驗證器範圍：JSON標validated=false，不交snapshot_guard。個股快照採schema 1.5，不新增頂層欄位；相對強弱與Beta只用metrics額外鍵，cost_log改列於報告末行。

ETF新紀錄採獨立schema 1.1／model etf-1.2，交etf_guard，不交snapshot_guard；欄位、derive／finalize與範圍依etf.md「快照與機械驗證」。etf-1.1歷史紀錄使用etf.schema-1.0.json及原規則分支；etf-1.0舊紀錄保持validated=false、人工核對，不回填新格式。

決策結論由decision_guard另驗證，格式、命令及保存完整依decision.md「決策結論程式驗證」；不放入個股scores；ETF來源須依本身驗證器通過，不能只憑決策成功認定研究已驗證。snapshot_guard單獨的valid不證明行動正確。新decision-1.1核對第2、6、7關數值與結論；其他關卡、來源真實性與市場日曆仍人工。舊decision-1.0使用decision.schema-1.0.json，按原發布組合核對結論。

驗證器支援model 1.0、1.1、1.2及1.3；重大產業調整或自訂門檻須另定模型版本、Schema及驗證規則，不能以1.0標記取得程式通過。驗證器本身可在外部執行，不能把外部驗證能力回填為目標模型的Python能力。

範例見 `assets/snapshot.example.json`（合成資料，`tests/check_snapshot_example.py` 保證可通過驗證器）；正式格式見 `assets/snapshot.schema.json`（JSON Schema Draft 2020-12）。`scripts/snapshot_guard.py`僅執行此內附Schema所使用的關鍵字，遇未支援關鍵字即報錯，不是通用JSON Schema引擎。其他平台可另用符合Draft 2020-12的驗證器，並啟用format檢查。

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

## 1.11.0交付補充

完整新個股／ETF報告及決策另執行SKILL.md直接連結的research-process.md；保存共用.review.json及其來源檔雜湊，研究與決策之外再通過review_guard預設驗證。作業狀態、等待原因、取數紀錄及信心追問以該文件為唯一出處；舊紀錄不回填。

## 1.12.0逐項查核

SKILL.md直接連結evidence-audit.md；review-1.1在同一附檔加入逐項主張、固定算術、
反方及論點失效條件。舊review-1.0只用1.11.0原始來源，不能代替新發布的查核。
研究／ETF／決策評分模型與數值門檻不變；新增流程檢查不能作投資績效證明。

## 三年年度資料（1.13.0）

共用review升schema 1.2／review-1.2；financial_history.py在review_guard預設驗證中核對年度原值、單位、期間、來源、勾稽與最終表格，正式規則見SKILL.md直接連結的financial-history.md。股票／ETF研究schema與評分模型維持；1.12.0的review schema及範例另行凍結，不回填新欄位。執行tests/check_financial_history.py及既有全部回歸。
