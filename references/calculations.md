# 計算工具

使用 `python3 <此技能目錄>/scripts/finance_math.py input.json`，或將JSON送到stdin。輸入檔屬工作暫存，勿在技能資料夾存放個股結果。工具僅計算，不抓取行情、提供買賣訊號或自動驗證來源。

## 輸入

全部欄位選用。若提供`bars`，須為非空、日期唯一且由舊到新的有效日線。

```json
{
  "price": 500,
  "eps_ttm": 25,
  "scenarios": [
    {"label": "保守", "eps": 25, "pe": 16},
    {"label": "基準", "eps": 30, "pe": 20},
    {"label": "樂觀", "eps": 35, "pe": 24}
  ],
  "bars": [
    {"date": "2026-01-02", "close": 100, "volume": 1000},
    {"date": "2026-01-05", "close": 101, "volume": 1200}
  ]
}
```

以上為虛構算例，不是任何公司的資料。將有來源的真實資料代入；事先核對EPS／price幣別及普通股或ADR單位、拆股基準及各情境年度。

## 輸出與公式

- `pe_ttm=price/eps_ttm`；EPS非正或任一輸入缺漏回null。
- `model_price=scenario.eps*scenario.pe`；EPS非正回null並標不適用，不能給負數合理股價。
- `upside_pct=(model_price/price-1)*100`，單位為百分比，不是小數比例。
- SMA20／60／120以最近相應日數平均；不足回null。
- RSI14以初始14次變動平均正負變動及Wilder遞迴平滑；至少15個收盤。純上漲=100，純下跌=0，完全平盤=50（此工具約定）。
- EMA初值取前n筆SMA，再用alpha=2/(n+1)遞迴。MACD為EMA12−EMA26；訊號取有效MACD序列EMA9，至少34筆。柱狀值=MACD−訊號，不乘2。
- `volume_sma20`使用含當日的最近20筆；`relative_volume20`=當日量／該均量。缺任一量或全為0則不計比值。
- `technical.last_close`是所提供日線價格，不能自行當作即時現價。

日期重複／倒序、非正價格、負量、非有限數值等會退出並顯示輸入錯誤；不會默默改資料。指標「最小筆數」是工具可計算的最低筆數，不是研究層門檻；研究層技術燈號與Beta的門檻為240筆（見data-and-methods.md「技術資料」）。`warmup_note`與研究層240筆門檻一致，但仍須完成來源及口徑核對。短樣本須明說不足，勿過度解讀。

技術公式為常用定義；不同資料商的調整及初始化方法可產生差異。從其他來源引用指標時列其日期、參數及方法；無從確認則說明限制，不假稱由本工具重算。

財務數值完成後，使用 `scripts/snapshot_guard.py` 對照正式Schema核對完整快照、評分及燈號；`finance_math.py`輸出不是完整報告快照，不可直接交給snapshot_guard。snapshot_guard的技術indicators欄位與finance_math輸出的欄位名稱一致，選取Schema要求的欄位，另附來源、調整方式及筆數。

共用版本、權重、四捨五入、缺值面向分、加權總分及估值門檻由scripts/rules_core.py定義；snapshot_guard直接使用同一函式推導及驗算，不另寫一套門檻。金融與證據意義依scoring.md，歷史模型仍依保留分支。

## 行情輸入檢查工具

`finance_math.py`對提供的`bars`必定先呼叫同一`inspect_bars`核心；無行情的估值計算不受影響。OHLC三欄open／high／low可全部省略以支援僅收盤資料；一旦提供其中一欄則三欄均須有效且與close同口徑。省略volume或填null均為未知，不能當作零量。

```json
{
  "bars": [
    {"date": "2026-10-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": null},
    {"date": "2026-10-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000}
  ],
  "bar_context": {
    "price_basis": "raw",
    "exchange": "TWSE",
    "source_url": "https://example.invalid/synthetic-prices",
    "expected_sessions": ["2026-10-01", "2026-10-02"],
    "calendar_source_url": "https://example.invalid/synthetic-calendar",
    "jump_threshold_pct": 100
  }
}
```

以上完全為合成示例，不是真實報價或已核對交易日曆。`source_url`、`exchange`與價格基礎未知時保留待查；日曆為呼叫端提供，程式不連網驗證。若來源另提供`ohlc_basis`、`close_basis`或逐列`price_basis`，已知值必須一致。`jump_threshold_pct`為選填的相鄰收盤變化百分比診斷，跨缺日變化不當作單日報酬；不套用官方漲跌幅限制。

```bash
python3 <技能目錄>/scripts/bar_audit.py input.json > input.audit.json
python3 <技能目錄>/scripts/bar_audit.py input.json --normalize > normalized.audit.json
python3 <技能目錄>/scripts/finance_math.py input.json
```

預設只稽核，不正規化。`--normalize`明確要求輸出另含`normalized_bars`及`changes`的稽核檔；原始輸入不改寫，同日衝突則valid=false、退出碼2且不提供可用正規化序列。採用正規化資料計算時，另建立輸入JSON並保留原始檔與audit紀錄，不把整份audit當作finance_math輸入。

輸出`valid`／`errors`／`issues`／`changes`／`summary`明確區分結構錯誤、待核對線索及主動正規化；`finance_math`的`bar_validation`保留同樣診斷，`technical.count`仍為原始有效輸入筆數。結構通過、日線240筆、原文與日曆交叉核對是不同條件；本工具未執行外部來源核實或報酬回測。

## 計算與欄位連動（規則1.6.0起）

新紀錄發布組合依SKILL.md metadata與rules_core.py，延續1.6.0的算術檢查；schema 1.5／model 1.3維持。下列檢查在預設驗證及`--derive`均執行；錯誤會拒絕，不自動改寫模型價、假設或來源。公式文字只供追溯，程式不執行任意formula字串。已知數值須用有限數字，不以布林值、字串、null代入。除浮點誤差外不接受四捨五入後的乘積作原始數值。

### 估值情境

每個有model_price的情境，在assumptions記currency與instrument，須與security一致。P/E的eps、P/B的book_value_per_share是匹配該證券單位的每股或每ADR數字；模型假設可不同於實際TTM，但須明列期間及依據，不冒充metrics的實際值。

| primary_metric | assumptions必要數字 | 驗算 |
| --- | --- | --- |
| pe | eps、multiple，均>0 | model_price＝eps×multiple；選填pe別名時須等於multiple |
| pb | book_value_per_share、multiple，均>0 | model_price＝book_value_per_share×multiple；仍遵守R1／R2的基礎一致性 |
| ev_sales／ev_ebitda | revenue或ebitda、multiple、net_debt、shares、adr_ratio | model_price＝（營收或EBITDA×倍數−淨負債）÷普通股流通股數×每ADR普通股數 |

EV模型金額須為同幣別的完整金額，股數為普通股股數；先將千元、百萬元換成同一單位。除net_debt可為負（淨現金）外，其餘輸入均>0；ordinary的adr_ratio固定1。計算後權益價值非正，不建立正數每股模型價。DCF、other及R3的交叉方法輸入尚未自動驗算，須保留公式與人工驗算說明，不宣稱全部估值計算已由程式驗證。不得把P/E或P/B改標other以避開檢查。

### 衍生metrics

value_status為calculated時，inputs按下表填寫。輸入名稱若與metrics中的鍵相同，數值必須等於該metric.value，缺值不能被其他數字代替。金額、時間與股東範圍的經濟口徑仍須依data-and-methods人工核對；程式驗算不證明原文真實。

| metric | inputs必要鍵 | 驗算 |
| --- | --- | --- |
| pe_ttm | price、eps_ttm | price÷eps_ttm，EPS須>0且與metrics一致 |
| market_cap | price、shares、adr_ratio | price÷adr_ratio×普通股流通股數；ordinary的adr_ratio＝1，幣別須與price一致 |
| roe_ttm | net_income_common、equity_begin_common、equity_end_common | 普通股淨利÷期初期末平均普通股權益×100；兩期權益均>0 |
| fcf_ttm | cfo_ttm、cash_capex_ttm | CFO−現金資本支出；支出以非負的流出金額填入 |
| revenue_growth_q2／eps_growth_q2 | current、previous | （current÷previous−1）×100；previous須>0，轉盈或基期≤0不使用此公式 |
| gross_margin_q2 | gross_profit、revenue | 毛利÷營收×100，營收須>0 |
| cash_yield | cash_dividend_12m、price | 已付現金股利÷現價×100，股利不得為負 |

不適用上表口徑的值改用另命名metric並揭露原因，不能把替代口徑寫進同名calculated值。其他自訂衍生值的formula仍須人工驗算，不冒稱程式已驗算。

### 歷史區間與事件

valuation.band新增current_metric，P/E只能引用pe_ttm或另建的pe_forward，P/B引用另建的pb_current；current須等於該metric.value。自行計算pe_forward／pb_current時，inputs分別為price與eps_forward／book_value_per_share，程式核對現價及比值。採資料商公布倍數時保留reported與口徑，不強制其等於自算TTM；但band.current仍須與所選metric一致。

事件published_at可填有時區時間或日期，必須不晚於data_cutoff_at；occurred／scheduled不可缺公告日期。occurred須有不晚於截止日期的event_date；scheduled須有不早於截止日期的event_date。已公告的未來事件可保留；已過期的預定事件須查核結果後改occurred或unknown。日期相同但缺公告時刻，不代表已證明截止時刻前可用，須在報告揭露時間精度限制；當日尚未確認是否發生時不填occurred。

## DCF的現金流與折現率配對

使用DCF前，先明示企業自由現金流FCFF或股權自由現金流FCFE。FCFF以WACC折現，
由營運價值加非營運資產、扣債務及其他優先請求權得到普通股價值；FCFE以股權成本折現，
不再重複扣相同債務。以淨負債調節時不要再重複加已包含的現金。
FCFF通常由EBIT×（1−稅率）＋折舊攤銷−資本支出−非現金營運資金增加計算；
從CFO出發時須交代利息、稅、非營運項目及會計分類調節，不能直接假定CFO−Capex就是FCFF。
維持與成長資本支出須能支持預測成長，不只扣維持支出卻同時假定高速擴張。
情境權重列依據，無校準時稱假設權重，不稱發生機率；逐項查核依evidence-audit.md。
此為人工方法檢查，不宣稱DCF已完整接入數值驗證器。方法參考：
[Damodaran：DCF估值框架](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html)。
