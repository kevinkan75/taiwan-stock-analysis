# 作業完成度、取數紀錄與信心表達（1.13.0）

## 目錄

- 執行順序與最低取數清單
- 狀態、替代路徑與停止條件
- 共用紀錄與定稿
- 信心、追問與正文檢查
- 驗收及界線

## 執行順序與最低取數清單

每次完整個股／ETF研究開始即以assets/review.example.json建立工作用.review.json；
已有可驗證來源時，優先用review_guard --init生成正確任務清單與參照，所有任務初始為not_run，不能直接當作完成。
另依SKILL.md直接連結的evidence-audit.md填寫逐項主張、反方與失效條件。
此附檔與研究、決策檔分開；不改研究權重、門檻、八關判定順序或歷史檔案。
聚焦、市場及不評分工具不使用此清單；仍須遵守資料與信心原則。

先列所需資料、期間及口徑，再取數；不要等產生燈號後補寫成功紀錄。
每取得一項就更新紀錄，沿用同次已讀原文；更換來源前先說明原路徑的問題。
研究評分完成後才處理市場環境，不以市場表現改研究分數。

| 任務id | 最低核對內容 |
| --- | --- |
| quote | 最近完成交易日或有時間戳行情、證券單位、幣別及交易日曆 |
| financials | 截止時最新財報與實際依賴的主表、附註；ETF依底層資料規則 |
| valuation | 已知倍數、合適區間與可支持情境的假設；倍數敏感度不充當模型 |
| events | 下次財報／法說與近期重大事件；記已公布、預定、未公布的區別 |
| growth（個股） | 同口徑季度與TTM營收、EPS及一次性因素，不以月營收替代TTM |
| industry（個股） | 該產業必查指標及個股產品／競爭證據 |
| fund_rules（ETF） | 基金子類型、指數或主動策略及變更規則 |
| cost_tracking（ETF） | 費用、追蹤品質及適用的歷史期間 |
| holdings（ETF） | 持股日期、覆蓋、集中及底層估值口徑 |
| distribution（ETF） | 已付／預估配息、收益來源；累積型也需核對政策 |
| market（決策加列） | 四項市場指標；有快照時先核對日期及失效事件 |
| technical（決策加列） | 自算日線；不能自算則依decision第6關取近期資料商最低指標組 |
| expectations（決策加列） | 同期12月價格及TTM盈餘原值；ETF沿用適用研究檢核 |
| exit_conditions（決策加列） | 論點、價格及時間條件，缺價格依據不能編數字 |

各模式任務順序由scripts/review_guard.py的required_tasks固定推導，不能刪掉失敗任務。
不因已知法說將至或已出現「等待」就省略其餘必要查核；可先提供簡短事件提醒，
但完整報告仍需完成上述工作，或清楚標示尚未完成。

## 狀態、替代路徑與停止條件

每任務保存status、reason及attempts。reason說明期間、口徑、缺口影響及具體下一步。
attempts保存stage（primary／alternative／calculation）、source_url、at、request、
result、detail、authority_basis。primary代表該用途的一手／權威來源，須註明依據；
不是把任何網址填primary即可證明權威。搜尋摘要只定位原文，不記為數據核對成功。

| status | 意義及最低紀錄 |
| --- | --- |
| obtained | 已取得並核對；至少一筆success，且不得與研究／數值關卡的缺值矛盾 |
| not_run | 尚未執行；attempts空陣列，作業狀態必為尚未完成 |
| partial | 已開始但尚未完成必要取數或計算；保留已有attempts，作業仍為尚未完成 |
| not_published | 權威公告／行事曆已查，所需資料尚未公布；至少一筆primary結果與說明 |
| access_failed | 主要及適用替代路徑均已嘗試，含blocked或unavailable結果 |
| conflicting | 主要及替代來源已比較，仍有conflict；依原規則採保守值或不評 |
| incompatible | 已檢查主要及替代來源，仍無可比口徑；至少一筆incompatible結果 |
| not_applicable | 僅允許現有規則明訂的財報不依賴例外；不得藉此跳過必要任務 |

來源網址須登錄於研究、決策或review的sources；查閱、嘗試及公告時間不得晚於截止／分析時間。
來源尚未核對時不得用「沒有事件」「沒有風險」代替缺值。
存取失敗時先試適用替代來源（例如官方另一入口或可核對原文的資料商）；
無權限、來源未公布或不能確認口徑時停止該路徑並保留缺口，不要求使用者登入付費資料庫。
同一任務的相同來源／request／結果不得重複登錄；重用已取得內容。
這是有界取數流程，不承諾每項必然取得，也不允許為達成覆蓋率採用較差來源。

## 共用紀錄與定稿

兩個軸分開：作業檢核complete表示每個必要任務已完成最低查核流程，即使結果仍缺資料；
incomplete表示有not_run或partial，或逐項查核尚未完成。決策證據sufficient依已驗證研究、報價及八關均可判定推導，
不是投資勝率，也不因所有任務填obtained自動成立；逐項查核的關鍵未解決主張及反方另依evidence-audit.md限制。重大風險不被完成度覆蓋。
此為資訊完整性的描述，不改變原規則可在非核心關卡仍有缺口時給附前提的分批方案。
研究信心沿用原overall.confidence，不從作業完成度另算分數。

等待原因僅於行動wait推導，可複選：data_pending、event_pending、price_conditions、
risk_conditions；不得把資料不足寫成價格不划算。保留原行動／命中條款不變。

1. 完成研究JSON推導、報告及原驗證器預設驗證；決策模式再完成decision_guard。
2. 依financial-history.md填financial_history；年度嘗試併記financials／growth任務。以review_guard --render取得financial_history_report與作業狀態區塊；這仍是草稿，不宣稱全案通過。
   完成evidence-audit的論點連結後，同一輸出的thesis_comparison_report提供多空對照草稿；檢查支持與反方沒有混用，納入定稿或依快速版精簡，仍保留實際影響及重評條件。
   若已修改研究report_markdown或論點，先重新推導並預設驗證研究，再執行review --render；render不會修復失效的研究雜湊。決策模式另按原流程更新決策參照。
3. 將兩個區塊加入實際交付全文，重新綁定、驗證研究／決策。若研究全文也含決策，先定研究檔，再更新決策參照雜湊。
4. review_guard --derive更新實際來源檔案雜湊及assessment，另存.review.json；再跑不帶derive的預設驗證。
5. 完整新報告必須研究／ETF、適用決策、review三層均通過才稱已完成對應程式核對。
   僅有snapshot_guard或decision_guard通過不得宣稱取數作業已完成。

```bash
python3 <技能目錄>/scripts/review_guard.py --research research.json --decision final.decision.json --init > draft.review.json
python3 <技能目錄>/scripts/review_guard.py draft.review.json --research research.json --decision final.decision.json --render
python3 <技能目錄>/scripts/review_guard.py draft.review.json --research research.json --decision final.decision.json --derive > final.review.json
python3 <技能目錄>/scripts/review_guard.py final.review.json --research research.json --decision final.decision.json
```

研究模式省略--decision。紀錄參照保存原檔版本及SHA-256，舊版缺值保持未知，不回填。
檔名沿用原研究基底加.review.json；保存方式沿用既有規則。
附檔的通過不會改變研究分數或放寬既有資料門檻。

HTML查核階段沿用tasks及assessment，不另推導成功率。obtained表示已取得並核對；complete僅表示完成最低作業流程，仍可能包含access_failed、conflicting或incompatible。尚未執行與部分完成分開；失敗不退回合成報告、不補中性分數。紀錄只描述截止／匯出時的狀態，不宣稱即時進度、持續監控或工具呼叫已由程式證明。

## 信心、追問與正文檢查

固定區分資料查核紀錄、研究判斷信心、決策限制。資料查核紀錄列主要／替代來源及未解決項目，
不宣稱這些數量能證明資料正確；「研究信心高」只表示既有研究規則下的證據／敏感度等級。
使用者追問信心時解釋依據及限制，不另產生主觀65／100、85%或上漲勝率。
如需要數字，可列已核對項數／必要項數，明標為覆蓋狀態，不稱可信度或獲利機率。
不把「對等待規則有把握」轉述為「目前買入不划算」。

1.11.0起研究、ETF及決策驗證器共用report_checks.py，攔下明確自述信心數字、
與研究等級不符的高信心主張，以及等待／放棄／分批報告中的無條件立即進場。
條件須先於動作；「現在買入，條件以後再補」仍不合格。否定句與明確標示的引用／錯誤範例分開處理。
這是保守詞彙檢查，不是完整語意證明；定稿仍人工逐句核對前提、行動與信心。
舊規則的歷史檔沿用原檢查，不批次改寫。

## 驗收及界線

執行tests/check_review_guard.py及既有全部check_*.py。案例須包括：有事件但資料齊全、
取數已完成仍無估值、尚未計算、來源失敗與衝突、條件／否定／引用句、矛盾買進及信心數字、
股票與ETF共用紀錄、CLI定稿、篡改雜湊及歷史1.10.0相容。
真實案例只重播當時已讀原文及執行紀錄，未執行的步驟保持not_run；不把事後補寫當成當時已完成。
比較必要資料查核、重複嘗試、耗時與引用錯誤；無同條件實測不得宣稱效率或資料取得率改善。
attempts為人工提供的紀錄，驗證器不會證明工具呼叫真的發生，也不證明來源本身正確。

新review採schema 1.2／review-1.2／驗證器1.2.0，含financial_history。1.11.0及1.12.0的舊review各依凍結schema驗證，不以舊schema包裹新分析略過年度查核。
