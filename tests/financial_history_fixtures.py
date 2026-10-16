"""Only synthetic annual statements. Never use as market data or retrieval logs."""
from datetime import date, timedelta

import financial_history as history


def sample(url='https://example.invalid/sample-source'):
    periods=[]
    for year, revenue, ni, eps, opening, closing, assets, liabilities, equity, cash, cfo, capex in [
        (2023, 100, 10, 1, 40, 50, 200, 140, 60, 20, 20, 8),
        (2024, 120, 12, 1.2, 50, 60, 240, 170, 70, 24, 24, 10),
        (2025, 144, 18, 1.8, 60, 75, 300, 210, 90, 30, 30, 12)]:
        begin=f'{year}-01-01';end=f'{year}-12-31'
        values=dict(revenue=revenue,gross_profit=revenue*.4,operating_income=revenue*.2,
                    net_income_parent=ni,diluted_eps=eps,total_assets=assets,
                    total_liabilities=liabilities,total_equity=equity,
                    parent_equity_begin=opening,parent_equity_end=closing,
                    cash_bs_end=cash,cash_cf_end=cash,cfo=cfo,cash_ppe_purchases=capex)
        inputs={}
        for key,value in values.items():
            # Amounts in millions; EPS remains currency per ordinary share.
            inputs[key]=dict(raw_value=value,scale=1 if key=='diluted_eps' else 1000000,
                             source_url=url,locator='合成年度附表 '+str(year)+' '+key,
                             period_start=begin if key in history.FLOWS else None,
                             period_end=(date.fromisoformat(begin)-timedelta(days=1)).isoformat()
                             if key=='parent_equity_begin' else end)
        periods.append(dict(period_start=begin,period_end=end,inputs=inputs,
                            one_off_note='合成資料：一次性損益尚未核對，不假稱已排除'))
    return dict(status='attempted',reason='合成三個完整年度；非真實公司資料或取數結果',
                currency='TWD',basis='consolidated',latest_period_end='2025-12-31',periods=periods)


def missing(cell):
    cell.update(raw_value=None,scale=None,source_url=None,period_start=None,period_end=None,
                locator='合成缺值；未取得，不填零')
