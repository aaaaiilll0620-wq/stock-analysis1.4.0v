import os
import pandas as pd
from datetime import datetime, timedelta
from FinMind.data import DataLoader

def download_stock_csv(stock_id="4958", lookback_days=120):
    """
    透過 FinMind 抓取本機回測所需的真實日線數據並匯出成 CSV（修復欄位對應錯誤）。
    """
    print(f"正在透過 FinMind 抓取 {stock_id} 的真實歷史數據...")
    api = DataLoader()
    
    # 2026年當前時間，往前抓 120 天確保扣除假日有足夠 90 個交易日
    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    
    try:
        df = api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date
        )
        
        if df.empty:
            print("❌ 抓取失敗：FinMind 回傳空資料。")
            return
            
        # 【核心修正】強制將所有欄位名稱轉為小寫，避免大小寫不一致的 KeyError
        df.columns = df.columns.str.lower()
        
        # 進行欄位標準化對應
        rename_dict = {}
        if 'trading_volume' in df.columns:
            rename_dict['trading_volume'] = 'volume'
        if 'max' in df.columns:
            rename_dict['max'] = 'high'
        if 'min' in df.columns:
            rename_dict['min'] = 'low'
            
        df = df.rename(columns=rename_dict)
        
        # 檢查必備欄位是否存在
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"❌ 依然缺少欄位: {missing_cols}，目前有的欄位是: {list(df.columns)}")
            return
            
        # 只取最近 90 個交易日並匯出
        df_final = df.tail(90)[required_cols].copy()
        
        output_filename = f"{stock_id}_actual_data.csv"
        df_final.to_csv(output_filename, index=False)
        print(f"✅ 成功！真實數據已寫入本機檔案：{output_filename}")
        print(f"📊 資料區間：{df_final['date'].iloc[0]} 至 {df_final['date'].iloc[-1]} (共 {len(df_final)} 個交易日)")
        
        print("\n--- CSV 資料預覽（可直接全選複製貼給 Claude）---")
        print(df_final.to_csv(index=False)[:500] + "...\n[下略]")
        
    except Exception as e:
        print(f"❌ 發生錯誤: {str(e)}")

if __name__ == "__main__":
    download_stock_csv("4958")