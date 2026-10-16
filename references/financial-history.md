# 三年財務趨勢與報表勾稽（1.13.0）

## 目錄

- 取數與適用範圍
- 原值、期間與單位
- 計算與勾稽
- 狀態、正文與定稿
- 驗證界線

## 取數與適用範圍

完整個股研究及決策，另核對截止時最近三個完整財年，填入共用.review.json的financial_history。
先讀最近官方年報或年度財報，再沿用其中可比前期欄；一次讀取可支援多個年度，不重複抓取。
若有重編，採同範圍較新的可比數字，註明修正與來源；不得把報表日期直接換成年份以求對齊。
financials／growth任務保留實際年度取數嘗試。來源優先與替代路徑依data-and-methods及research-process。

最新季度、TTM、月營收另列，不用來補成完整年度。上市未滿三年或取不到歷史資料時保留已取得年度、列明缺口，
不填零、不使用外部預估或年度化替代，也不因缺年度自動否決研究；既有評分與財報資格仍依原規則。
金融業等不適用毛利／PP&E方法者留該欄null並說明，不硬套製造業意義。
ETF標not_applicable，不套用單一公司年度ROE。既有財報不依賴例外仍可用，但不得保留已知ROE／FCF等內容。
純技術等聚焦模式不新增年度取數。

## 原值、期間與單位

格式見assets/review.example.json的financial_history及assets/review.schema.json；數值為合成範例，須全部換成實際資料。
status為not_run、attempted或not_applicable，並填具體reason；attempted另填報表currency、latest_period_end及0–3筆periods。
latest_period_end是截止時已確認公布的最新完整財年結束日，不從目前月份猜測。尚無法確認時保持not_run並列待查。

每筆年度填實際period_start／period_end及one_off_note，依時間遞增且相鄰；支援364／365／366／371天完整財年。
曆年與52／53週財年均列實際截止日，不混用季度、年初至今、TTM或不同合併範圍。特殊過渡短年度另行揭露，不強稱三年可比。
所有年度使用同一報表幣別與合併範圍；ADR的報表幣別可與交易幣別不同，不能無匯率依據自行換算。

每個年度固定保留14個inputs：revenue、gross_profit、operating_income、net_income_parent、diluted_eps、
total_assets、total_liabilities、total_equity、parent_equity_begin、parent_equity_end、cash_bs_end、cash_cf_end、cfo、cash_ppe_purchases。
ROE用歸母普通股淨利及歸母普通股權益；資產平衡式則用含非控制權益的總權益。特殊股權結構須人工確認普通股口徑。

每個cell保留raw_value（原表數字）、scale（1／1000／1000000／100000000）、source_url、locator及來源期間。
金額換算為原幣元後計算；EPS維持元／普通股，scale只能1。source_url須在研究、決策或review.sources登錄，locator指向原表頁碼／列名。
流量欄需匹配整個財年；期末餘額的period_start為null，period_end為年末；期初權益為財年開始前一日。
缺值cell的raw_value、scale、source_url與兩個日期均為null，locator說明未取得或不適用；不捏造發布日期或來源。

cash_ppe_purchases只填現金購置不動產、廠房及設備支出，保留原表正負號，計算時取支出絕對額。
不能用固定資產帳面淨變動、全部投資現金流或處分回收代替。無法辨識購置支出時FCF保持缺值。
one_off_note說明已辨識項目與未核對範圍；未讀相關附註時填「一次性因素尚未核對」，不能寫已全面排除。

## 計算與勾稽

financial_history.py由review_guard呼叫，不連網、不執行公式字串，也不修改研究權重或數值門檻。

| 項目 | 自動處理 |
| --- | --- |
| 年度趨勢 | 營收、歸母淨利、稀釋EPS、毛利率、營業利益率、ROE、FCF；保留年度原值 |
| YoY | 相鄰年度新值／舊值－1；前期非正或任一期缺值時不計百分比，另存實際差額 |
| CAGR | 三個相鄰完整年度的首末營收，兩個年度間隔；首末任一非正或年度未齊則null |
| 利潤率變動 | 兩期百分比相減，標百分點，不能標成百分比成長 |
| ROE | 歸母淨利／平均期初期末歸母普通股權益；任一權益非正時null，不當作正向效率證據 |
| FCF | 合併CFO－現金購置PP&E支出絕對額；不冒充FCFF或已扣全部無形資產等的現金流 |
| 資產平衡 | 總資產－總負債－總權益 |
| 期末現金 | 資產負債表與現金流量表的期末現金及約當現金相減 |
| 年度連續性 | 前期末與當期期初歸母權益相減；遇重編先核對可比來源，不自動改原值 |

勾稽容許值只取各輸入原表單位scale的一半加總，用於已公布數字的捨入差異；不設定任意百分比寬限，也不四捨五入原始差額來求通過。
每項保存pass、conflict或unavailable、實際差額與容許值；任一輸入缺值時為unavailable，不能因沒有警示就稱通過。
空年度／全null、布林、NaN、無限大、錯年、錯單位與截止後資料均有專門測試。

## 狀態、正文與定稿

assessment.financial_history保存由原值推導的年度列、變動、勾稽及缺口，不由作者自行填「完整」。
三年原值齊全且勾稽無衝突才為complete；已嘗試但缺年度或欄位為partial；存在勾稽差異為conflicting。
not_run使作業尚未完成；partial保留缺口，不自動改研究信心或價格判斷。
conflicting使本次決策證據不足，且review拒絕進場／分批定稿，必須先釐清來源／口徑；原研究與行動規則不被暗中改寫。

review_guard --render同時回傳report_block與financial_history_report。將兩者加入同一份實際交付報告，
再依research-process的順序重新綁定研究／決策雜湊、--derive及預設驗證。--derive不會修正原始來源或數字。
年度表由同一批結構資料生成，預設驗證比對完整年度區塊；手改表格數字、刪除缺口或重複區塊均拒絕。
快速版可將完整年度表放在同一交付報告附錄，正文保留一項趨勢及會影響判斷的勾稽／一次性因素限制；詳細版展開。

## 驗證界線

本模組核對輸入格式、單位、日期、固定公式與報告一致性；年度原值的來源定位另在本欄保存，
不假稱evidence_audit已自動讀過原文。原文真實性、合併及普通股範圍、查核狀態、原表捨入方式、
是否為最新可比年度、變動原因與一次性判斷仍由分析者核對。附官方連結不等於完成官方驗證。
不以本功能宣稱投資勝率、跨模型一致或資料取得率改善；互動HTML輸出留待另行評估。
