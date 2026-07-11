# config.py
import os
from dotenv import load_dotenv
from FinMind.data import DataLoader

# 載入環境變數 (.env)
load_dotenv()

# 取出 FinMind 金鑰並驗證
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
if not FINMIND_TOKEN:
    raise ValueError("Error: FINMIND_TOKEN is missing in .env file.")

# 統一初始化全域的 FinMind DataLoader 物件
fm = DataLoader()
fm.login_by_token(FINMIND_TOKEN)