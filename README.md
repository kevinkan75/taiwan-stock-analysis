# analyze-stocks：股票與ETF投資分析儀表板

公開預覽準備版。核心研究與驗證可使用；互動HTML為**實驗功能**，iPhone章節連結與手機版面已由使用者實機確認；其他裝置、完整鍵盤及列印驗收仍未完成。

以可追溯的資料分析台股與美股的個股及ETF。個股涵蓋基本面、成長、估值、產業、技術面、最新事件與風險；ETF涵蓋指數規則、成本與追蹤、流動性與折溢價、持股集中度、底層估值、配息品質與結構風險。依證據評分並顯示燈號；提供快速版、詳細版、歷次比較，以及可選的投資前決策檢核。

> 本技能產出的是研究判斷，不是個人化投資建議。燈號與分數是自訂研究分，不代表勝率或獲利保證。

## 能做什麼

- **研究模式（預設）**：例如「分析台積電」「分析NVDA」「更新2330的分析」。輸出專家摘要、六面向燈號、估值區間位置、事件與風險，並在可取得前次報告時做比較。
- **ETF模式**：例如「分析0050」「00878可以買嗎」「0050和006208哪個好」。辨識子類型（市值、高股息／因子、主題、主動式、債券、跨境）後，以五面向評分並附同類ETF比較。槓桿、反向、期貨型ETF只提供結構說明，不給訊號。新紀錄可驗證格式、算術、覆蓋、總分、集中度及信心；來源與定性證據仍人工核對。
- **市場模式**：例如「分析大盤」「台股行情」。輸出台股市場快照：市場狀態、決策第4關四項指標、補充指標與族群強弱（研究候選清單，非推薦），不做漲跌預測。市場與產業快照可保存後供同日或同產業的後續分析沿用。目前為第一階段，未接上快照驗證程式。
- **決策模式**：問題含「可以買嗎」「要不要加碼」「買點」等字眼時啟動。在研究結果之上加八關檢核、進場／分批／等待／放棄結論及退場條件。不使用你的資金或持股資料。
- **互動報告（選用）**：要求「匯出互動報告」時，從已驗證的單一個股研究與review產生四分頁離線HTML。保留分數、缺口、來源與勾稽，提供指標切換與完整列印規則；無JavaScript時可用原生章節連結閱讀全部內容（iPhone版面已實機確認，列印仍待驗收）；ETF、多檔比較及決策互動介面尚未支援。詳見references/html-report.md。
- **結構化快照**：每次分析可輸出符合 `assets/snapshot.schema.json` 的 JSON，由 `scripts/snapshot_guard.py` 推導並驗證分數與燈號，供下次比較。

不處理：純查股價、選擇權、加密資產、下單、賣出決策與投資組合配置。其他市場可用，但會先確認資料可用性。

完整研究及決策另保存 `.review.json`，區分尚未完成取數與已完成查核但證據不足；等待原因可複選。信心沿用研究等級，不自行產生可信度百分比。1.12.0新增逐項主張、反方與失效條件查核，延續正文矛盾檢查，保留舊版規則；1.13.0加入最近三個完整年度的趨勢及報表勾稽，細節見references/financial-history.md與references/research-process.md。

## 需求

- 可上網搜尋與讀取網頁的 AI 環境（取得最新財報與行情）。沒有網路時只能就你提供的資料做「截至資料日期」的歷史分析。
- 選用：Python 3.8 以上（只用標準函式庫），用於計算與快照驗證；沒有時改為人工核對並在報告中註明。

## 安裝

本技能遵循 Agent Skills 開放格式，整個資料夾（保留相對路徑）即為一個技能。

- **Claude（claude.ai／桌面版）**：將資料夾壓成 zip 或使用打包好的 `.skill` 檔，在技能設定中上傳。
- **Claude Code 等支援技能資料夾的工具**：將 `analyze-stocks/` 放到該工具的技能目錄。
- **ChatGPT／Codex**：`agents/openai.yaml` 提供 OpenAI 端的顯示名稱、圖示與觸發設定，其他平台會忽略此檔。

各平台的實際安裝位置與權限以該平台當時的官方文件為準。

## 快速開始

先將整個 `analyze-stocks` 資料夾交給支援技能的AI環境載入，再輸入：

```text
請使用 analyze-stocks 分析台積電（2330），提供快速版研究。
```

研究完成後可再要求：

```text
將剛才的單一個股研究匯出互動報告，保留資料截止時間、缺值與來源。
```

AI環境需自行具備搜尋、讀取財報與執行Python的能力；本專案的Python腳本負責計算、驗證及呈現，不會自動抓取行情或產生完整研究。應取得同次定稿的研究JSON與 `.review.json` 後，再按references/html-report.md匯出。缺資料時保持缺值，不以內附範例代替真實研究。

不連網也可先測試**合成範例**。在專案根目錄執行以下指令（Windows可將 `python` 換成 `py`）：

```bash
python -X utf8 scripts/snapshot_guard.py assets/snapshot.example.json
python -X utf8 scripts/review_guard.py assets/review.example.json --research assets/snapshot.example.json
python -c "from pathlib import Path; Path('outputs').mkdir(exist_ok=True)"
python -X utf8 scripts/html_export.py --research assets/snapshot.example.json --review assets/review.example.json --output outputs/demo.html
python -X utf8 scripts/html_export.py --research assets/snapshot.example.json --review assets/review.example.json --verify outputs/demo.html
```

前兩步與最後一步應顯示 `valid: true`；第四步會建立 `outputs/demo.html`，可供瀏覽器驗收。此為合成資料，不代表台積電或真實行情。再次匯出時請改用新檔名，程式不覆寫既有報告。若要分析「可以買嗎」或ETF，照常使用文字／JSON模式；首版HTML不支援決策與ETF。

Git來源以 `.gitattributes` 固定UTF-8文字檔的LF換行，避免Windows換行轉換破壞原始檔雜湊。不要用編輯器重存已綁定的JSON；內容相同但位元組不同仍須視為不同來源，不能藉重算雜湊修補歷史紀錄。

## 目錄結構

```
analyze-stocks/
├── SKILL.md                 # 入口：模式分流、依賴的定義、必讀資源、流程骨架（細節在references）、交付前核對
├── references/              # 依需要載入的規則
│   ├── data-and-methods.md  # 資料來源與口徑（每次必讀）
│   ├── scoring.md           # 評分與燈號
│   ├── output-and-history.md# 輸出模板與歷次比較
│   ├── calculations.md      # 估值與技術指標計算
│   ├── market.md            # 市場模式、市場快照與其輸出／存檔格式
│   ├── portability.md       # 跨平台能力與驗證
│   ├── industry-indicators.md # 產業關鍵指標
│   ├── etf.md               # ETF模式：子類型、面向、評分、快速版模板（僅ETF）
│   ├── etf-data.md          # ETF資料來源與口徑（僅ETF）
│   ├── financial-history.md # 三年同口徑年度趨勢、單位、來源與報表勾稽
│   ├── evidence-audit.md   # 逐項主張、來源衝突、反方及失效條件
│   ├── research-process.md # 共用取數紀錄、完成度、等待原因與信心表達
│   └── decision.md          # 投資前決策檢核（僅決策模式）
├── scripts/                 # finance_math.py、rules_core.py、snapshot_guard.py、etf_guard.py、decision_guard.py、review_guard.py、financial_history.py及共用數值規則
├── assets/                  # 研究與決策的schema／example及icon.svg
├── agents/openai.yaml       # OpenAI 平台設定（其他平台忽略）
└── tests/                   # 維護者回歸測試（合成資料）
```

## 版本

| 項目 | 目前版本 | 說明 |
|---|---|---|
| 發布套件 | 1.14.1-preview.1 | HTML修正patch；保留預發布狀態 |
| 研究技能相容版本 | 1.14.0 | 見 SKILL.md `metadata.version` 與 CHANGELOG.md |
| 快照格式 schema | 1.5 | 1.2／1.3／1.4仍按原模型驗證，不回填新欄位 |
| 評分模型 model | 1.3 | 保留權重及原始門檻，整合R1–R3、資格三態與R6信心 |
| ETF評分模型 | etf-1.2 | 獨立schema 1.1；驗證子類型數值，保留etf-1.1歷史分支 |
| ETF驗證器 | 1.2.0 | 格式、算術及子類型數值門檻；來源與定性證據仍人工核對 |
| 規則版本 | 1.14.0 | 加入選用離線HTML；研究權重、數值門檻與歷史原檔保留 |
| 個股驗證器 | 1.6.0 | 發布設定及共用函式依rules_core.py，保留歷史分支 |
| 決策驗證器 | 2.1.0 | decision-1.1／schema 1.1，第2、6、7關數值、結論及研究參照 |
| 作業查核 | review-1.2／schema 1.2／驗證器1.2.0 | 股票及ETF共用附檔；年度資料與勾稽、逐項綁定及算術；外部原文仍人工核對 |
| HTML呈現器 | 1.0.1 | 單一個股研究；原生章節連結、手機卡片表格及來源一致性核對；iPhone實機確認，列印仍待驗收 |
| 市場模型 | market-1.0 | 市場與產業快照；第一階段未接驗證程式，不進入任何研究評分 |

修改權重、門檻或面向定義時，請另訂 model 版本與驗證規則，不要沿用 1.3 標記，否則不同版本的燈號無法比較。

## 驗證

```bash
python -X utf8 scripts/run_checks.py
```

完整檢查使用Python 3.8以上及Node.js 24，不需安裝Python或npm套件。未安裝Node時可明確執行 `python -X utf8 scripts/run_checks.py --python-only`，但這不包括互動邏輯測試。以 `python -X utf8 tests/check_release_files.py --git` 另行核對本機Git在 `core.autocrlf=true` 下的下載位元組。

檢查14份參考文件連結（含ETF與市場模式文件）、依賴是否僅限標準函式庫、Schema 與評分門檻、19 個固定合成案例與 7 個規則層合成案例。另執行 `python3 tests/check_valuation_guardrails.py`，直接驗證R1–R3的降分、缺值、模型基礎、方法衝突及往返一致性。check_consistency.py涵蓋最終文字、資格三態、信心、R6、版本及命令列；完整報告與快照的使用方式見references/portability.md。通過只代表本地規則與計算一致，不代表資料來源真實或跨模型結果一致。

check_rules_core.py核對重構前保存的歷史原檔與完整推導結果雜湊；check_decision_guard.py直接呼叫正式程式及CLI，核對八關結論、來源連動、時效、報告與條件，並遍歷65,536組燈號檢查安全性質。check_etf_guard.py直接驗證ETF格式、算術、評分門檻與決策來源；etf-1.0舊來源仍只核對人工參照外框。

年度資料附於同一review，保留原表數字、單位與期間，再生成年度表；資產平衡、兩表期末現金及跨年度歸母權益由正式程式核對。缺年度或欄位如實揭露，已有衝突時不認證進場／分批；不新增投資訊號、評分權重或固定流動比率門檻。

互動邏輯可另執行 `node tests/check_html_interactions.js`；此為Node模擬DOM合約測試，非瀏覽器呈現測試。使用者已於2026-10-16確認iPhone章節連結及mobile-v4版面符合預期；該模板納入呈現器1.0.1。此為單一實機與報告的確認，不能推定其他裝置、完整鍵盤、列印或所有檔案預覽器通過。

GitHub Actions已設定Linux／Windows與Python 3.8、3.12、3.14的矩陣，以及Node.js 24互動邏輯測試；工作流程首次實際執行前，不宣稱這些組合均已通過。本地已驗證Python 3.12；HTML的其他裝置與列印驗收、跨模型一致性仍未完成。

## 發布與維護

將本技能目錄獨立作為GitHub專案根目錄，保留本技能的公開檔案與發布設定，不沿用個人技能共用儲存庫的歷史。提交前執行完整檢查，確認沒有帳號資料、實際分析報告或本機輸入。`.gitignore`只防止一般誤加入，不能替代逐項檢查。

公開版本見 [GitHub Releases](https://github.com/kevinkan75/taiwan-stock-analysis/releases)。1.14.1-preview.1為HTML修正patch，提供安裝ZIP、相對上一公開版的差異patch及SHA-256；研究技能與規則相容版本維持1.14.0，HTML呈現器為1.0.1。仍保留Pre-release，完整鍵盤及列印等瀏覽器驗收完成後再評估穩定發布。

## 使用須知與免責

- **免費提供，非投顧服務。** 本技能免費分享，作者並非證券投資信託事業或證券投資顧問事業，亦不因本技能的提供或使用收取任何直接或間接報酬。
- **研究判斷，非投資建議。** 輸出內容是依公開資料與固定規則產生的研究判斷，不構成任何個股的買賣推薦。燈號、分數與決策結論不保證獲利，使用者應自行判斷並承擔投資風險。
- **授權與再利用。** 本專案採MIT授權，允許商業使用、修改及散布，並須保留授權與著作權聲明。作者不背書任何第三方付費服務、選股推薦或獲利承諾；使用者應自行確認並遵守適用的金融監管、資料使用及其他法規。此為使用責任提醒，不另限制MIT授權。
- **資料來源條款。** 文件中提及的交易所、公開資訊觀測站及資料商（例如 Goodinfo）各有使用條款。請以一般瀏覽方式查閱並遵守其規定，不要以本技能為由進行自動化大量抓取。
- **資料可能有誤或延遲。** 搜尋結果、資料商數據與模型判讀都可能出錯；重要數字請回到原始財報或公告核對。

## 授權

MIT，見 LICENSE。
