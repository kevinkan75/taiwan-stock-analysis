# 評分與燈號

## 證據規則

每檢核項給0／1／2分：0為明確不利證據，1為混合或中性，2為支持證據。缺資料記null，不把未知評為1。附來源、期間及理由。定性分數為研究判斷，不是統計預測。

多條件檢核須逐一取得證據；只有毛利率改善、但資本回報口徑未知時，不足以給資本效率2分。現金高於短期有息負債不能當成完整流動性或總淨現金證據，還須檢查其他到期義務及現金限制。必要條件未確認就null，或依已明列的產業替代規則評分。部分資料支持不可直接寫成整體面向已驗證。

| 面向／權重 | 三項檢核及0／1／2參考 |
| --- | --- |
| 基本面／25% | 獲利品質：核心獲利惡化／混合／穩定且現金流支持；資產負債：流動性壓力／可管理但槓桿高／緩衝充足；資本效率：回報及利潤率低於可比歷史與同業且惡化／混合／穩定或改善。 |
| 成長性／20% | 已實現營收：最新季度與TTM均下降／兩者分歧或大致持平／兩者均成長；已實現EPS：同口徑獲利惡化／分歧、低基期或持平／成長且無重大一次性因素；未來動能：已驗證需求或指引下修／證據混合／有可核對訂單、指引或產品進度支持。轉盈須另定獲利改善判準並明列。 |
| 估值／25% | 基準模型上行(模型價÷現價−1)：低於−10%／−10%至+15%／超過+15%；可比估值：溢價且無支持／接近合理範圍或溢價部分支持／折價且無明顯基本面落差（有歷史區間時見下方區間位置規則）；情境韌性：保守模型下行超過30%／超過15%至30%／不超過15%。假設不可靠就null。 |
| 產業趨勢／15% | 終端需求：明確惡化／混合／一手數據改善；競爭位置：失去份額或技術優勢／變化未明／有份額、成本或產品證據支持；供需與政策：過剩或限制加劇／混合／供需或政策有實際支持。 |
| 風險可控程度／15% | 營運與集中：重大暴露且無緩解／暴露與部分緩解／暴露較低或緩衝已驗證；法規治理：重大已確認事件／不確定但可監控／完成公告與治理檢視且無重大發現；財務與事件抗壓：壓力已實現／緩衝不足／具體資金與營運緩衝。未發現不等於不存在，說明檢索範圍。 |

**區間位置規則（model 1.1起）**：有 `valuation.band` 時，可比估值依現價倍數在區間的位置評分：高於區間高點或位於上緣20%且無成長或ROE改善支持＝0；位於中段，或上緣但有已驗證的成長／ROE改善支持＝1；低於中位且無明顯基本面惡化＝2。週期性產業須同時參照週期位置：週期高峰的低P/E不得評2。資料商區間與自算區間同樣可評，但報告須標來源類型。

**估值輸入前置檢查（規則版本1.3.0）**：模型價須先通過data-and-methods.md估值操作第10點（淨值品質）、第11點（區間可比性），再判定第7點的方法衝突（model_upside最高1分；comparable_valuation不得給2）。三項處理套用到保守、基準、樂觀全部情境。

閾值為v1預設，未經回測。「基本面良好」不能自動使估值變綠。風險分數愈高表示已辨識風險愈可控。

## R1–R3程式整合（schema 1.4／model 1.2起）

valuation.primary_metric填pe／pb／ev_sales／ev_ebitda／dcf／other。guardrails含r1、r2、r3；每項都附reason與source_urls，狀態為不適用或未確認時也須說明原因。sources須登錄所引用來源；程式核對輸入一致性，不會上網核實。規則1.6.0另驗算所有P/E、P/B及標準EV情境與核心衍生metrics，並核對band.current_metric及事件日期；格式與範圍依calculations.md，DCF及自訂公式仍人工核對。

| 檢查 | 狀態與必要資料 | 分數處理 |
| --- | --- | --- |
| r1 | not_applicable（非淨值估值）；clean（完整數據且未觸發）；adjusted（調整後）；four_quarter_average（近四季平均）；unadjusted（品質待調整仍採原淨值）；unconfirmed（原淨值口徑未確認） | unadjusted使model_upside、scenario_resilience最高1；unconfirmed使兩項為null；已調整者依調整後模型價評分。 |
| r2 | not_applicable（非歷史區間）；comparable；adjusted_multiple；unconfirmed | unconfirmed使model_upside最高1；其他狀態在核對模型與倍數後依模型價評分。 |
| r3 | not_applicable（無另一可行交叉方法）；checked（至少兩方法）；unconfirmed（交叉方法尚無可靠資料） | checked時程式以嚴格>+15%及<−10%判斷衝突；衝突使model_upside、comparable_valuation最高1。未確認不冒充已查證。 |

r1.checks填latest_book_value、previous_book_value、oci_share_of_book_change、listed_holding_share；占比用小數，50%填0.5。clean必須四項皆已取得，且每股淨值變動不超過15%、OCI占比不超過0.5、單一上市持股占比低於0.2。unadjusted須有已確認的latest_book_value，缺失時改unconfirmed。P/B不得標not_applicable，程式也檢查method文字中的淨值方法。adjusted／four_quarter_average填reference_book_value；後者另填按時序排列的四個quarterly_book_values，程式重算平均。這兩種狀態下所有有價情境的assumptions須填book_value_basis、book_value_per_share與multiple；來源、基礎及乘積須一致，不可只改基準情境。

P/B亦須保留valuation.eps_basis，這是既有「EPS或淨值來源」欄位，不代表P/B必須使用EPS。如每股淨值由分析假設調整或計算，填analysis_assumption，並在情境假設明列數值為每股淨值；不可因此填入不存在的EPS。

r2填ttm_roe_pct、annual_roe_pct（同口徑的歷史年度ROE，百分比18%填18）。comparable若TTM低於年度中位數一半會被拒，須改adjusted_multiple或unconfirmed。adjusted_multiple填selected_multiple及adjustment_method（approx_p25／pb_roe）；approx_p25須等於band低點與中位的中點。基準assumptions.multiple須等於選定倍數；P/E另填eps、P/B另填book_value_per_share，程式核對基準模型價乘積。PB–ROE的要求報酬率與推導另列assumptions及formula，仍須人工核對經濟假設。

r3.models逐項填method、base_model_price、currency、instrument、source_urls、post_adjustment=true與reason；必須包含與valuation.method同名且與base情境同價的主方法，其他方法名稱不得重複。所有價格為完成適用R1／R2處理後的價格，幣別與普通股／ADR單位一致。交叉方法的輸入品質由分析者查證，不因post_adjustment標記即視為外部資料已驗證。

執行順序：核對模型基礎→算原始門檻分→套用所有上限及null→重算覆蓋、面向與整體分數。多項限制取最低上限；0分不因最高1分而升為1分，null不自動補分。`--derive`會回寫有效分及valuation.applied_adjustments；預設驗證要求快照與推導一致。報告以有效分為準，並列觸發條件；不得只寫附註而保留原2分。人工敏感度檢查改動估值分時，也必須遵守已套用的上限與null條件。

## 面向與總分

- 每面向至少2／3項可評，否則⚪待確認。
- 面向分數＝有效項平均分÷2×100，顯示整數；≥75為🟢有利，≥40且<75為🟡中性／需觀察，<40為🔴不利。列取得項數，缺值不作0。
- 五面向各至少2項且總共至少12／15項可評、有效現價及最新財報已核對、估值方法可支持時才給正式總分（信心：高）。
- **暫定訊號（model 1.1起）**：正式門檻未齊，但同時符合下列條件時，給「暫定」訊號：報價已核對且為最近交易時點、最新財報已核對、估值面向可評（至少2項）、至少4個面向可評、總覆蓋至少10／15項。暫定分數＝可評面向分×原權重÷可評面向權重合計；燈號沿用下方門檻，但缺任一面向時不得為🟢。五面向齊備且覆蓋≥12時信心為「中」，其餘為「低」。報告寫成「🟡暫定（中信心）」等形式，並列出造成暫定的缺口。
- 不符合暫定條件時為「⚪資料不足」；估值面向不可評時一律⚪，因為無法回答價格問題。
- ⚪表示尚無足夠資料形成整體判斷，不代表所有分項均未知；可列已確認的營運或產業證據及待補估值，不能另命名「研究訊號」給綜合綠／黃／紅燈繞過門檻。既有重大風險優先規則仍適用。
- 缺外部Forward EPS不是自動否決估值的條件；有可靠的獨立模型或產業替代方法仍按三項檢核評分。只有TTM P/E或無依據反推敏感度，不足以補齊模型上行或情境韌性。
- 總分＝五面向分各乘原權重相加；用未四捨五入值計算，最後取整數。閾值比較亦用未四捨五入值。
- 技術面獨立：日線完整性及筆數依data-and-methods「技術資料」；不足為⚪（technical.status＝insufficient_data）。須有SMA20／60、RSI14、MACD。現價>SMA20>SMA60且MACD>訊號且RSI≤70：🟢趨勢偏強；現價<SMA20<SMA60且MACD<訊號：🔴偏弱；其餘🟡混合／需觀察。不足為⚪。附RSI極端及量能說明，不解讀成勝率。
- **交叉幅度（規則版本1.3.1，不改變燈號判定）**：提到MACD黃金／死亡交叉時，須寫交叉日、交叉日柱狀值與最近一日柱狀值。交叉日＝柱狀值由≤0轉>0（或由≥0轉<0）的日子。交叉日|柱狀值|低於收盤價0.1%者標「交叉日幅度微弱」；自交叉日（含）起至今未滿3個交易日者標「交叉待確認」；已滿3個交易日且最近一日|柱狀值|不低於收盤價0.1%者標「交叉已確認」，已滿3日但低於0.1%者標「幅度微弱」。描述動能時以最近柱狀值及其變化為主，不以幅度微弱的交叉日當作動能證據。0.1%與3日為自訂值，未經回測。

## 整體投資訊號

按序判定：
1. 已核對、直接威脅營運持續或論點的重大事件（如違約、繼續經營重大疑慮、實質財報舞弊、核心業務被禁止）：🔴重大風險，即使缺資料仍先顯示事件。舉證影響，不以一般產業風險套用否決。
2. 未滿足正式門檻但符合暫定條件（model 1.1起）：依3–5的規則給暫定燈號並標信心；不符合暫定條件：⚪資料不足，暫不形成整體判斷。
3. 總分<40或估值／風險任一面向<40：🔴現階段條件不利。
4. 總分≥75、估值及風險均≥75、基本面及成長均≥40：🟢目前條件具吸引力。
5. 其餘：🟡值得觀察，等待條件改善或更多證據。

不得將🟢寫成必須買入，或🔴寫成必須放空。給可觀察條件，如財報證實毛利率、EPS預估修訂、現價落入有依據的區間。

## 結論敏感度檢查（R6）

評分完成後，將理由含保留語（需打折、待確認、近似、邊界、有限制）的分項在0–2範圍內各上下調1分，重算整體燈號；另外至少檢查估值面向全部三項。

- 任一單項調整即翻轉整體燈號：信心最高「中」；「一眼結論」加「⚠ 結論脆弱：〔分項〕改為X分時，燈號變為Y」；data_gaps記錄。
- 個股model 1.3由snapshot_guard自動逐項擾動，存sensitivity（cases、fragile、confidence_cap）；`--sensitivity`可單獨查看結果。只調有效分±1，保留null與R1–R3上限，不改來源、模型價或原分數。這是反事實檢查，不是新的證據評分；未知或重大風險結論不做翻轉測試。R4與R6取較低信心，R6不自行改成暫定。舊模型及etf-1.0紀錄仍人工核對，不回寫舊快照；新ETF的R6由etf_guard實作，見etf.md。

## 資格三態（R4）

eligibility四項分pass／limited／fail。limited範例（financials_verified 不適用 limited）：
- financials_verified只用pass／fail；報表依賴、清空項目與快速版例外完整依SKILL.md「依賴的定義」，不另設limited例外。
- valuation_supported：R1或R2觸發，或使用近似分位。
- quote_verified：只有資料商報價，無交易所頁面。

limited視同滿足正式門檻與暫定訊號的資格條件，但：一項limited→信心最高「中」；兩項以上→改為暫定訊號（信心「低」）。

**個股程式整合（schema 1.5／model 1.3）**：eligibility的quote_verified、quote_is_current、valuation_supported填pass／limited／fail；financials_verified只填pass／fail。每項須有同名validation且status一致，包括fail。不得以reason文字代替狀態。任一必要資格fail即無整體訊號；財報的「確實不依賴」例外依SKILL.md保留。R1調整、平均、未調整或未確認，以及R2調整或未確認，valuation_supported不得標pass。歷史模式不把quote_is_current納入限制數量，仍須核對截止時價格。

一項limited使信心最高medium；兩項以上改provisional=true、信心low，仍沿用有依據的分數與燈號。資料覆蓋原本已造成低信心時不得升為中信心。報告與快照均採程式推導結果。舊schema 1.3／1.4紀錄的布林及【limited】文字只按舊模型驗證，不因此補造三態；etf-1.0仍人工依本節規則評估並標未經程式驗證；etf-1.1的資格、覆蓋與信心驗證見etf.md。

## 程式驗證與固定名稱

新快照採schema 1.5、model 1.3，以 `scripts/snapshot_guard.py` 驗證；schema 1.2／model 1.0、schema 1.3／model 1.1及schema 1.4／model 1.2仍按原規則驗證；model 1.0不產生暫定訊號。面向名稱固定為fundamentals、growth、valuation、industry、risk，weight分別為0.25、0.20、0.25、0.15、0.15。每面向三個check固定如下；不得重複檢核項以湊完整性：

| 面向 | check依序 |
| --- | --- |
| fundamentals | earnings_quality、balance_sheet、capital_efficiency |
| growth | realized_revenue、realized_eps、future_drivers |
| valuation | model_upside、comparable_valuation、scenario_resilience |
| industry | end_demand、competitive_position、supply_policy |
| risk | operations_concentration、regulatory_governance、financial_event_buffer |

有效項須有reason、period、source_urls，來源列入sources。未知仍為null。面向raw_score不足兩項時為null；顯示分數按四捨五入（恰半向上），閾值只用未四捨五入值。整體signal為unknown／green／yellow／red／major_risk；major_risk顯示🔴重大風險，優先於資料門檻與暫定訊號且不計總分。model 1.1起另有 `overall.provisional`（是否暫定）與 `overall.confidence`（high／medium／low／null），由程式推導。技術面仍獨立。

資格欄位、限制與一致性依上方「資格三態（R4）」；quote_verified是報價口徑、quote_is_current是最近交易時點，financials_verified是截止日最新正式財報，valuation_supported是模型假設支持。截止與歷史模式的時間判定依data-and-methods及portability，不把歷史判斷轉稱目前條件。

估值scenarios的label固定conservative／base／optimistic。model_upside須匹配base模型價格，scenario_resilience須匹配conservative模型價格；程式重算兩項閾值。財務、競爭、風險證據及可比估值分數仍需分析者依原文判斷，程式只核對結構與機械規則。

## 產業調整

金融、REIT、虧損／轉盈、強週期與新上市公司，先調整不適用檢核與估值方法，明列替代指標、閾值及理由，保留五面向與原權重。沒有可信替代就null。重大調整標記模型版本變更；前次無法同口徑重算，分數僅列示，不聲稱改善。跨產業分數不可當客觀選股排名。
