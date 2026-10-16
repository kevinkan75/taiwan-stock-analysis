# ETF模式

ETF要回答兩個問題：工具本身好不好（指數規則、成本、追蹤、流動性、結構），以及裝的東西現在值不值得買（持股結構、底層估值、配息品質、回撤）。辨識到標的是ETF時走本文件；評分機制、暫定訊號、歷次比較與決策層框架沿用個股版，只替換面向、檢核項與資料來源。資料與計算口徑見 [ETF資料來源與口徑](etf-data.md)。

新ETF評分模型為 `etf-1.2`，使用獨立schema 1.1；etf-1.1按原格式驗證，舊etf-1.0仍人工。ETF與個股分數不可互比，也不可合併排名。

本文依序說明：標的與子類型、五面向檢核、子類型調整、整體訊號、同類比較、快速版輸出、快照與機械驗證。

## 規則版本1.10.0的適用範圍

ETF適用R4資格三態、R5技術資料240筆、R6敏感度、R8工作立場、R9反方審查及共同摘要規則；R1–R3不套用ETF，底層估值依本文件與etf-data.md。R7只用於市場與決策第4關。新報告標「規則版本 1.14.0」，由etf_guard驗證ETF格式、標準算術與評分機械規則；不是個股snapshot_guard的延伸。定性證據、來源真實性、子類型認定、交易日曆、Beta及事件交易日仍人工核對。決策另交decision_guard；通過只代表各自明列的驗證範圍。

## 標的辨識與子類型

1. 以交易所或發行商資料確認證券類型，不靠代號猜測（台股00開頭多為ETF，仍須查證）。
2. 讀公開說明書或基金簡介，取得追蹤指數、複製方式（實物／期貨／合成）、槓桿倍數、是否主動式、成分股市場。
3. 依下表歸類；同時符合多項時取風險較高者（例如海外槓桿型→槓反類）。

| 子類型 | 判斷依據 | 處理 |
| --- | --- | --- |
| 市值型 | 依市值加權追蹤寬基指數 | 完整評分 |
| 高股息／因子型 | 以殖利率、低波、品質等條件選股或加權 | 完整評分；配息品質與周轉加重檢視 |
| 產業／主題型 | 單一產業或主題 | 完整評分；集中度依子類型調整 |
| 主動式 | 經理人選股（台股代號通常帶A） | 完整評分；指數方法與追蹤依子類型調整 |
| 債券型 | 持有債券（台股多在櫃買中心掛牌） | 調整後評分 |
| 跨境股票型 | 成分股在海外 | 調整後評分 |
| 槓反／期貨／商品／加密 | 每日重設、期貨轉倉或非股票資產 | 不評分，只出結構說明 |

槓反等類型不給燈號也不進決策層：中長期研究框架不適用每日重設工具。改輸出一段結構說明：每日重設耗損、轉倉成本、近一年實際報酬與「指數報酬×倍數」的差距，結尾寫明不適合以本技能做持有判斷。境外基金與ETN不處理；連結基金提示改看其母ETF。

## 五面向與檢核項

每項0／1／2分，缺資料記null，不補成1；每項附來源、期間、理由。沿用etf-1.0的面向權重與數值閾值，未經回測。

| 面向 | 權重 | check依序 |
| --- | --- | --- |
| 工具品質 instrument | 0.20 | index_methodology、total_cost、tracking_quality |
| 交易品質 tradability | 0.15 | fund_scale、liquidity、premium_discount |
| 持股結構 portfolio | 0.20 | concentration、exposure_fit、holdings_quality |
| 底層估值 valuation | 0.25 | band_position、relative_valuation、earnings_support |
| 風險與分配 risk | 0.20 | drawdown_volatility、distribution_quality、structural_risk |

| 檢核項 | 0分 | 1分 | 2分 |
| --- | --- | --- | --- |
| index_methodology | 規則不公開或與名稱明顯不符 | 規則公開但年周轉>50%或常有臨時調整 | 規則公開、可複製、周轉合理 |
| total_cost | 總費用率高於同類中位數1.5倍以上 | 介於同類中位數至1.5倍 | 不高於同類中位數 |
| tracking_quality | 年化追蹤差距落後超過「費用率+0.5個百分點」 | 落後介於「費用率+0.2」至「+0.5」個百分點 | 落後不超過「費用率+0.2」個百分點 |
| fund_scale | 台股<20億元／美股<1億美元，或接近公開說明書終止條件 | 台股20–100億元／美股1–10億美元 | 台股≥100億元／美股≥10億美元 |
| liquidity | 20日均成交值<1,000萬元（美股<100萬美元） | 1,000萬–1億元（美股100萬–1,000萬美元） | ≥1億元（美股≥1,000萬美元） |
| premium_discount | 近20日平均絕對折溢價>1%，或單日極值>3% | 平均0.3%–1%，或極值1%–3% | 平均≤0.3%且極值≤1% |
| concentration | 單一成分股>40%，或前十大>80% | 單一25%–40%，或前十大60%–80% | 單一≤25%且前十大≤60% |
| exposure_fit | 實際曝險與名稱、定位明顯不符 | 大致相符但明顯偏重 | 曝險與名稱、定位一致 |
| holdings_quality | 覆蓋權重的成分股加權獲利衰退、ROE下滑 | 混合 | 加權獲利成長與ROE均不低於對應大盤 |
| band_position | 加權P/E（或P/B）高於歷史區間或位於上緣20%，且無獲利成長支持 | 位於中段，或上緣但有已驗證獲利成長支持 | 低於中位，且成分股獲利無明顯惡化 |
| relative_valuation | 相對大盤或同類ETF溢價且無獲利或ROE優勢支持 | 接近，或溢價部分有支持 | 折價且無明顯體質落差 |
| earnings_support | 12個月淨值漲幅超過組合盈餘成長2倍 | 1–2倍 | 不超過1倍 |
| drawdown_volatility | 近3年最大回撤或年化波動高於基準20%以上 | 與基準相差±20%以內 | 低於基準20%以上 |
| distribution_quality | 配息中收益平準金或資本利得>30%，或配息率長期高於底層殖利率 | 平準金或資本利得占10%–30% | 配息≥90%來自股利或利息收入 |
| structural_risk | 合成複製、期貨部位重大，或發行商、基金有重大事件 | 有匯率、單一市場或部分衍生品曝險 | 實物持股、無槓桿、發行商無重大事件 |

評分口徑：
- **concentration評的是分散程度，不是品質。** 0050這類單一成分股約六成的市值型ETF此項為0分，報告須說明這是市值型的結構特性；為免集中風險被其他高分平均掉，整體訊號另設集中度上限（見下）。
- holdings_quality與估值三項須有成分股資料覆蓋至少70%權重，否則null；band_position另需80%（見etf-data.md）。
- tracking_quality須至少一個完整年度；成立未滿一年記null，不用短期數據補。
- drawdown_volatility的基準：市值型用所屬市場大盤報酬指數（例如0050對加權報酬指數），不用其追蹤指數，否則永遠接近1分；主題型用對應大盤；債券型用對應債券指數。
- earnings_support：組合盈餘成長以目前持股計算，各成分股最新TTM盈餘與一年前TTM盈餘按目前權重加總後比較。正成長時，淨值漲幅≤盈餘成長給2分、超過1倍至2倍（含）給1分、超過2倍給0分；盈餘成長≤0且淨值漲幅>0給0分，盈餘成長≤0且淨值漲幅≤0給1分，不因跌得更多而給2分。基期盈餘≤0、口徑不一致或缺原值時記null；已確認成長主要為低基期或一次性因素時給0分並說明。決策第7關直接沿用本項，不另算一套倍數。
- 同類中位數：取同子類型、同市場、規模前段的同類ETF至少3檔；不足3檔時改用絕對門檻（台股股票型≤0.3%給2、0.3%–0.8%給1、>0.8%給0；美股≤0.2%／0.2%–0.6%／>0.6%）並註明。

## 子類型調整

| 子類型 | 檢核項 | 替代方式 |
| --- | --- | --- |
| 高股息／因子型 | index_methodology | 周轉門檻由50%放寬為80%（超過才降為1分），報告必列年周轉與換股次數 |
| 產業／主題型 | concentration | 單一成分股門檻不變；前十大門檻放寬為70%／90%，註明產業集中屬定位本身 |
| 主動式 | index_methodology | 改評策略一致性：持股揭露頻率、策略陳述與實際持股是否一致 |
| 主動式 | tracking_quality | 改評相對基準超額報酬（扣費後年化）：≥0給2、−2至0個百分點給1、<−2個百分點給0；成立未滿1年null |
| 債券型 | holdings_quality | 改評加權信用評等與違約／降評事件 |
| 債券型 | band_position | 改評到期殖利率在歷史區間位置（殖利率愈高，位置愈有利） |
| 債券型 | relative_valuation | 改評相對同天期公債或同評等指數的利差 |
| 債券型 | earnings_support | 改評存續期間與利率方向的匹配：說明利率上升1個百分點的約略淨值變動，與近期利率趨勢比較評分 |
| 跨境股票型 | premium_discount | 因有時差，平均≤0.5%且極值≤1.5%給2；平均0.5%–1.5%或極值1.5%–4%給1；其餘0 |
| 跨境股票型 | structural_risk | 無避險機制時匯率曝險使本項最高1分 |

調整須在報告列出替代指標、閾值及理由；跨子類型分數不可當客觀排名。

## 評分與整體訊號

面向分、面向燈號、正式總分、暫定訊號、⚪規則及技術面獨立，全部依 [評分與燈號](scoring.md) 的model 1.1機制計算，只把面向與權重換成上表，「最新財報已核對」改為「最新持股與成分股財報已核對」。估值面向不可評時整體一律⚪。

整體訊號依序判定：
1. **🔴重大風險**：已核對的清算或終止上市公告、暫停申購且溢價持續>5%、發行商重大違規影響基金運作、追蹤指數將停編且無替代安排。
2. 未達正式門檻：符合暫定條件給暫定燈號並標信心；不符合為⚪資料不足。
3. **🔴現階段條件不利**：總分<40，或估值、風險任一面向<40。
4. **🟢目前條件具吸引力**：總分≥75、估值與風險均≥75、工具品質與交易品質均≥40，且concentration已確認為1或2分。
5. **🟡值得觀察**：其餘。concentration為0分時，即使其他條件達第4條，整體最高🟡並說明原因。

etf-1.1明確處理集中度缺值：不可🟢，信心最高中，標集中度上限「待確認」。相對估值覆蓋70%至未滿80%時valuation_supported不得pass，改limited或fail並說明低覆蓋。這些限制不回填etf-1.0歷史紀錄。

## 同類比較

ETF報告必附同類比較：使用者指定對象時優先；未指定時自動挑2–3檔同曝險或同子類型ETF，並說明挑選理由（例如追蹤同一指數、同市場同定位且規模前段）。比較總費用率、追蹤差距、規模、20日均成交值、近12個月殖利率及配息組成。同指數ETF的差異主要在成本、規模與流動性，須直接點出。

## ETF快速版輸出

篇幅同個股快速版（見output-and-history「快速版」）；詳細版、技術面狀態、歷次比較與保存規則不變。槓反等只出結構說明的ETF，改為標頭＋結構說明＋近一年實際報酬與「指數報酬×倍數」差距，不出燈號表。

1. **標頭**：ETF名稱、代號、交易所、子類型、追蹤指數、發行商、幣別、分析時間、行情時間及狀態、持股資料日期、中長期研究假設、模型etf-1.2、規則版本 1.14.0。10個交易日內有換股生效或除息時加「⏰ 判斷時效短：X月X日〔事件〕」。
2. **專家摘要四行**：依output-and-history「摘要共同規則」；估值位置使用ETF底層估值，下一個催化劑可列換股、除息或主要持股財報，最大單一風險說明集中度或結構風險；缺值寫法與個股一致，不省略關鍵缺口行。
3. **一眼結論**：整體訊號（含暫定與信心、集中度上限是否觸發）＋2句理由；小表列工具品質、交易品質、持股結構、底層估值、風險與分配、技術面，含燈號、一句依據、面向分與覆蓋數。
4. **核心數據**：市價與淨值、折溢價（當日／20日平均／極值）、規模、20日均成交值、總費用率、近1年及近3年年化追蹤差距、前三大成分股與權重、加權P/E與覆蓋權重、近12個月配息與殖利率、配息組成、近3年最大回撤。每列附期間、口徑、來源。
5. **持股與曝險**：前十大與產業分布摘要，一句說明實際曝險。
6. **同類比較**：2–3檔，依本文件「同類比較」規則挑選並說明理由。
7. **事件與風險**：2–3項。
8. **與上次比較**、**下一步觀察**：同output-and-history個股快速版。
9. 完成預設驗證時列下方精確驗證範圍行；未執行時寫「ETF機械規則尚未程式核對」。另保留研究判斷、非獲利保證的一句。

## 快照與機械驗證

### 子類型數值輸入（etf-1.2）

subtype_inputs為必填，格式直接沿用範例。active_management與cross_border可組合，例如債券型加主動管理或跨境曝險；主要子類型與資產仍依原始資料確認，不靠旗標代替查證。主動式、跨境股票型不可關閉對應旗標繞過檢查。

- premium提供20日平均絕對折溢價、極值、觀測數與same_basis。程式按跨境或一般門檻推導premium_discount分；不足20筆或口徑未確認必須null，與同名metrics數值一致。等號先歸入2分條件，再判0分，其餘1分。
- fx_hedging記hedged／unhedged／unknown／not_applicable及來源。跨境未避險structural_risk最高1，R6擾動也守上限；避險不明必須null，整體不得綠燈且信心最高中，不因省略風險分項而提高判斷。已確認其他結構不利時adverse_structure_confirmed=true、分數0且附證據，保留已確認不利優先。避險有效性仍人工查證。
- active_return記扣費後、同幣別、含息的年化超額報酬、1–3個完整年度及起迄日期；須連動tracking_difference_pct。程式按既有0／−2百分點門檻判tracking_quality；未滿年度、未扣費或口徑不齊為null，不將累計報酬冒充年化。策略一致性仍人工。
- bond保存modified_duration、yield_shift_pct、approx_price_change_pct、當期／可比基準到期殖利率、credit_spread_pct、信用與天期可比聲明及已觀察rate_trend。驗算價格變動百分比近似為−修正存續期間×殖利率變動百分點，利差為兩個同口徑殖利率的百分點差。修正存續期間不等於Macaulay存續期間，近似不含凸性與非平行曲線變動，不當作價格保證或完整保守估值。
- 債券holdings_quality、band_position、relative_valuation、earnings_support仍依現有方向與證據人工給分。manual_assessments逐項記checked／insufficient／not_applicable、理由與來源；只有checked可保留分數，否則null。band須有當期殖利率、relative須有可比利差、earnings_support須有存續期間情境與利率方向；不把「輸入完整」當成程式已判定信用或利率匹配良好。

etf-1.1紀錄依assets/etf.schema-1.0.json與原規則分支驗證，不新增subtype_inputs；完整原檔及推導雜湊由回歸測試保留。

以assets/etf.example.json為格式底，合成資料全部換成實際證據；錯誤或新增欄位時才讀assets/etf.schema.json。security.instrument=etf、schema_version=1.1、model_version=etf-1.2；發布組合依rules_core.py的ETF_RELEASE_PROFILE。不可把ETF面向改成個股名稱交snapshot_guard。舊etf-1.0保持validated=false，ETF驗證器回報legacy_manual_etf，不轉成新紀錄或聲稱已驗證。

### 輸入與連動

- scores固定五面向、各三項及上表權重；缺值null，每面向至少兩項、正式總覆蓋至少12，暫定至少四面向且總覆蓋10。面向平均及總分使用未四捨五入值，最後恰半向上取整數。技術面獨立，computed須滿240筆且指標齊備。
- eligibility為quote_verified、quote_is_current、holdings_financials_verified、valuation_supported；前三態沿用R4，holdings_financials_verified僅pass／fail。validation須有同名、同狀態及來源；缺任何必要資格不給整體分（重大風險仍優先）。歷史模式只免最近交易時點，不免截止日報價及持股財報核對。
- coverage記holdings_quality、band_position、relative_valuation、earnings_support的權重百分比、期間、來源及method。reported為來源公布覆蓋，真實性人工查證；calculated提供唯一id、weight_pct與data_available的contributors，程式累計有資料權重，總權重不得超過100%。低於各項門檻必須將該score記null，不能用0或1湊覆蓋。band_position另須至少36筆月度資料或公布3年以上區間。
- concentration記單一最大及前十大權重。calculated須完整持股、唯一id且總權重100%，程式排序重算；reported允許使用發行商公布值，但不能低於另附持股清單的下限；清單完整或自算P/E成分股權重合計100%時，最大及前十大權重必須精確一致。缺資料兩項均null。依子類型重算concentration分及整體上限；25%／40%與60%／80%（主題70%／90%）等號歸較有利區間。
- earnings_support_inputs保存目前權重的前後TTM盈餘原值、淨值漲幅及低基期／一次性標記，程式驗算已給的非null分；缺原值、不可比或基期非正時不能保留分數。債券basis=bond_manual，改評存續期間與利率方向，不能放股票加權P/E。
- fund保存子類型依據、發行商、策略／指數、資產、複製方式、成立日及來源。tracking_quality非null須有成立日且至少一完整年；槓桿倍數只能1，不接受槓反、期貨、商品及加密類型投資訊號。

### 標準算術

每筆metric沿用etf-data.md欄位。百分數用百分點：3%填3、unit=%、currency=null；P/E用倍、currency=null；價格、淨值與配息為每受益單位，幣別相同。分割調整、公布值與原值是否同口徑仍須人工核對。calculated只接受下表的固定輸入，不執行formula字串；維持原始精度，展示數字可另四捨五入。

| metric | inputs及檢查 |
| --- | --- |
| premium_discount_pct | price、nav；(price/nav−1)×100，正價／正淨值，同交易日；引用值須與同名metric一致，公布值亦核對乘除 |
| yield_ttm_pct | distribution_ttm_per_unit、price；已支付近12月配息/現價×100，不接受年化最近一次估計 |
| weighted_pe | constituents的id、weight_pct、pe_ttm；虧損股用負P/E，缺值null，權重按有資料者重新標準化；覆蓋不足70%或合計盈餘殖利率非正時value=null。已評的band／relative覆蓋須與此成分股清單一致 |
| premium_abs_mean20_pct／premium_abs_max20_pct | daily_premium_pct恰20筆，同口徑百分數；重算絕對值均值及極值，交易日期完整性仍人工查證 |
| tracking_difference_pct | annual_periods含start、end、基金／含息指數報酬百分數、雙方幣別及total_return=true；1–3個完整、按時序且不重疊年度，重算差距平均，主動式用其基準 |

非上述calculated metric拒絕，不以任意公式字串繞過；來源公布值可用reported並列來源與口徑。weighted_pe的非正盈餘處理不是便宜訊號。

### 信心、定稿與保存

一項limited信心最高medium、兩項以上改暫定且low，不覆蓋原本較低信心。R6逐項檢查估值及含保留語的有效分±1，維持null、覆蓋與集中度上限；任一翻燈信心最高medium。保存完整sensitivity，並在報告人工揭露最脆弱假設。R6不是新證據或勝率驗證。

```bash
python3 <技能目錄>/scripts/etf_guard.py input.etf.json --report final-report.md --derive > derived.etf.json
python3 <技能目錄>/scripts/etf_guard.py derived.etf.json
python3 <技能目錄>/scripts/etf_guard.py derived.etf.json --finalize > final.etf.json
python3 <技能目錄>/scripts/etf_guard.py final.etf.json
```

--derive核對原始算術、證據外框與門檻後填面向、總分、信心、敏感度及報告雜湊，仍validated=false；不補缺值、不修原始資料或不當分數。將推導結果反映到報告後，重新帶入全文derive；必須再執行預設驗證。--finalize實際執行全部預設檢查，通過才輸出validated=true；不改原檔。decision_guard對實際研究檔重新驗證，不只信任此旗標。

定稿須四行摘要、單一規則標頭、共同「整體投資訊號」結果行，另有「集中度上限：🟡／未觸發／待確認」（按實際值選一）。保留精確一行：

ETF驗證範圍：格式、算術及評分機械規則；來源與定性證據仍人工核對。

回傳scope=etf_structure_arithmetic_scores；草稿加_draft。程式檢查格式、分數與算術連動，不驗證來源真實、完整持股聲明、覆蓋資料是否足以支持定性分、日曆、所有替代指標或整段正文語意。保存報告與JSON依output-and-history，不寫入技能目錄；歷史版本分數僅列示，不重算舊紀錄。沒有Python時人工按同規則核對，validated=false，明列尚未程式核對。

## 1.13.0交付補充

完整新個股／ETF報告及決策另執行SKILL.md直接連結的research-process.md；保存共用.review.json及其來源檔雜湊，研究與決策之外再通過review_guard預設驗證。作業狀態、等待原因、取數紀錄及信心追問以該文件為唯一出處；舊紀錄不回填。
