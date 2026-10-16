# 逐項主張、反方證據與失效條件（1.12.0）

## 執行與範圍

完整個股／ETF報告在research-process.md的同一份.review.json中填寫evidence_audit。
不再建立第二份來源清單或信心分數；沿用已讀原文及研究／決策／review的sources。
先盤點後核對，不能以寫完報告後自行補上的「已查證」代替實際讀取。
台股從TWSE／TPEx、MOPS及公司IR取得原文，美股從SEC申報與公司IR取得；
依data-and-methods.md分開行情、已實現財務、公司指引與外部預估。此更新不新增行情下載服務。

將status記not_run、partial或complete。complete代表已完成盤點與核對流程，仍可能有unresolved；
thesis_status只有established或insufficient。資料不足而未形成論點時標insufficient，
研究整體保持unknown，不為填滿反方或失效條件而發明論點。
coverage_note寫明盤點範圍、尚未核對的正文及其影響；程式只保證下列結構化最低覆蓋，
無法自動抽出報告全部事實，完整性仍須人工逐句核對。

## 主張紀錄

每項claims保存id、kind、statement、value、unit、period、basis、targets、report_excerpt、
material、verdict、sources、selected_source、premises、calculation及reason。
詳見assets/review.example.json（純合成，不得冒充實際取數）及review.schema.json。

| kind | 意義與核對 |
| --- | --- |
| fact | 已實現數字、公告事實；回到原文與表格位置 |
| guidance | 公司指引；只核對公司確有該說法，不保證未來實現 |
| estimate | 外部預估；核對機構、發布日、期間與原說法，不當作實際獲利 |
| assumption | 分析者假設；reviewed表示已檢視合理性，不寫成事實已證實 |
| inference | 分數、燈號或分析推論；以premises引用資料／假設，核對推論與反例 |
| calculation | 由可追溯輸入重算；保存有序premises與calculation |

verdict採supported、reviewed、unresolved或refuted。supported表示分析者已按原文核對，
不是驗證器替外部來源背書；假設與推論不能填supported。缺原文、口徑不符或尚未執行時，
保留unresolved並說明下一步；錯誤主張填refuted，先修正報告／清空依賴，再定稿。
refuted只保存已移除錯誤的歷程，targets與report_excerpt留空，錯句不可留在正文；
修正後另建新id。不再支撐結論的舊錯誤可標material=false並說明處理結果。
不要以來源家數或一致性換算上漲機率。已解決主張不得依賴未解決／已推翻的premises。

targets為實際JSON pointer，例如research:/metrics/eps_ttm/value、
research:/scores/growth/items/1/score、decision:/gates/0/signal。
claim.value須與各目標的值一致；同一目標只記一次，其他主張重用id。
無結構欄位的正文主張，report_excerpt保存定稿中的精確原句；不得只記結論而略過關鍵前提。
最低覆蓋所有非null metrics、已評分項、模型價、事件及決策八關；這些主張固定視為material。
另外人工補上財報資格、重大風險、摘要、投資論點及行動所依賴而未含於上述欄位的事實。

sources的每一候選保留url、locator（頁碼／表名／列／公告段落）、published_at、period、
basis、value、rank（primary／secondary）及retrieval（web／document／user_document／memory）。
網址須已登錄，發布日不得晚於截止日；日期相同但沒有時刻仍須揭露精度限制。
selected_source為從0開始的候選索引，未採用時null；reason交代實際核對與採用理由。
模型記憶不能支撐supported。附件只有在原文真的可見時才使用user_document。

口徑不同先分開，不比較不同期間／GAAP／股東範圍的數字。
同期間同口徑仍衝突時，優先一手來源，再取日期較新的可比申報；保留各候選值及採用理由，
不平均、不以多個轉載來源投票。無法確認比較基準就留unresolved，依舊規則清空依賴或保守處理。

## 重算與DCF口徑

calculation.method支援sum、subtract、product、divide、ratio_pct、change_pct或manual；
inputs須按premises的數值順序填入，運算只用有限數字，不執行任意formula字串。
ratio_pct為第一值÷第二值×100，change_pct為（本期÷前期−1）×100；
零分母拒絕，成長比較負基期拒絕；近零與可比性仍按data-and-methods人工核對。
自訂／複合公式可拆成中間主張，或manual保存逐步驗算說明；manual不代表已由程式重算。
原有snapshot／ETF算術檢查仍須通過，不得改用manual繞過既有公式檢查。

DCF仍須依calculations.md人工建立口徑調節：FCFF搭配WACC，FCFE搭配股權成本；
不得直接把一般CFO−Capex視為已完成FCFF調節。維持與成長資本支出須與預測一致，
企業價值轉股權價值時核對淨負債及非營運資產，避免重複扣加。
多／中／空權重須有理由，沒有校準就明標情境假設，不稱真實機率。

## 反方與失效條件

### 多空論點對照

沿用同一份review，不另建角色分數或來源清單。先完成研究，再由目前執行技能的模型依序檢視支持論點、針對該論點的反方質疑及綜合判斷；後一步須實際閱讀前一步內容，不把角色名稱或觀點並列當成已消除偏見。反方不是固定唱反調，沒有證據時記為待查假設。

新完整報告中，每項已形成的research.thesis[i]建立一筆kind=inference主張，value填該論點原文、targets填`research:/thesis/i`，premises引用實際支持主張；期間、口徑、reason依本次研究填寫。推論採reviewed或unresolved，不填supported；前提未解決時不得把根論點標為reviewed。沿用既有JSON pointer、前提圖與來源驗證，不修改schema或研究門檻。

用counter_cases.thesis_index記錄質疑針對哪個論點，claim_ids只引用該質疑實際依賴的證據或假設，不能把反方claim_ids直接當成多方支持依據。沿用既有三項反方總數，無需每個論點再發明三項。逐項讀完後，在impact記錄受影響的具體分數／估值假設／關卡及採用理由，follow_up記下一步；成立時先按原規則修正，再標adjusted。disclosed僅代表已揭露，不得改寫為「維持判斷」或「風險已排除」。unresolved維持原有限制。

將「原始論點、支持依據、反方質疑、處理結果、重新評估條件」列為對照表。`review_guard --render`的thesis_comparison_report依明確連結產生文字草稿，可納入定稿再按原流程綁定與驗證；來源及定性判斷仍須人工核對，文字表格不是新增驗證憑證。快速版保持精簡，詳細版展開依據；既有研究及決策規則不變。

既有有效原檔可原樣呈現；缺少明確支持連結、對應反方或失效條件時顯示缺口，不以相似文字、同一來源或事後推測補連結。沒有形成論點時保留不足狀態。對照視圖不新增勝率、權重或交易指令。

已形成論點時，counter_cases保留最可能推翻結論的三個原因；每項連結實際thesis_index、
claim_ids、scenario、impact、disposition（adjusted／disclosed／unresolved）、follow_up及report_excerpt。
描述若成立會改變哪個分數、假設或關卡，先依既有規則處理再標adjusted；純揭露填disclosed。
未處理的重大反方填unresolved，不能只靠高總分跳過。快速版可合併為一段，詳細版展開三項，
但每項仍須有可在最終正文找到的原句，不能只留在附檔。

invalidation_conditions至少一項，連結實際thesis_index及claim_ids，
列driver、observable、trigger、review_on與report_excerpt。
從本次營運／估值或ETF結構驅動因素導出：觀察什麼、何種公告／門檻推翻哪項假設、何時重評。
事件可作客觀條件，不強求數字；價格停損與期限仍依decision第8關另列，
不能用通用跌破均線或總體轉差替代公司論點失效。條件合理性及原文支持仍須人工判斷。

## 定稿與驗證界線

沿用research-process.md的render→更新全文→研究／決策驗證→review derive→預設驗證順序。
新review採schema 1.2／review-1.2／validator 1.2.0，年度欄依financial-history.md另行核對；逐項主張規則延續1.12.0，報告另列程式產生的「主張查核」行。
查核未完成會使作業狀態incomplete；material未解決或論點不足會使決策證據insufficient。
這些情況拒絕進場／分批定稿，保留等待與明確缺口；不擅自改研究分、八關或既有行動條款。
若主張或反方推翻原判斷，回到原研究／決策規則修正，再重新綁定檔案雜湊。
不能把完整報告稱為已通過三層驗證，卻只執行snapshot_guard。

1.11.0的review-1.0與其原始來源保留舊驗證分支，不回填逐項查核；
1.12.0研究／決策不得改交review-1.0規避逐項查核；1.13.0不得改交review-1.1規避年度查核。
tests/check_evidence_audit.py核對數值篡改、來源衝突、缺覆蓋、反方與失效條件、
進場限制、真實CLI及舊版相容。合成測試通過不代表資料自動查證、跨模型一致或策略績效。
