import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Master", layout="wide", page_icon="💎")

# --- ESTILOS CSS (BIG FONTS) ---
st.markdown("""
    <style>
    /* FUENTES GLOBALES */
    html, body, [class*="css"], div, span, p {
        font-family: 'Arial', sans-serif;
        font-size: 20px;
    }
    
    /* TARJETAS MÉTRICAS */
    .metric-card {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 30px 15px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        height: 100%;
    }
    .metric-label { 
        font-size: 18px !important; 
        color: #666; 
        text-transform: uppercase; 
        font-weight: 800;
        margin-bottom: 15px;
    }
    .metric-value { 
        font-size: 52px !important; 
        font-weight: 900; 
        color: #2c3e50; 
        line-height: 1;
    }
    .metric-sub { font-size: 22px !important; font-weight: 600; margin-top: 15px; }

    /* VEREDICTO */
    .verdict-box {
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.15);
    }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #f1c40f, #e67e22); }
    .v-overvalued { background: linear-gradient(135deg, #e74c3c, #c0392b); }
    .v-main { font-size: 64px; font-weight: 900; margin: 15px 0; text-shadow: 0 2px 5px rgba(0,0,0,0.2); }
    .v-desc { font-size: 28px; font-weight: 500; }

    /* TABLAS GIGANTES */
    .stTable { font-size: 22px !important; }
    thead tr th { font-size: 24px !important; background-color: #f8f9fa !important; padding: 20px !important;}
    tbody tr td { font-size: 22px !important; padding: 20px !important; }

    /* PESTAÑAS */
    .stTabs [data-baseweb="tab"] {
        font-size: 26px !important;
        padding: 15px 30px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTORES DE CÁLCULO ROBUSTO ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    """Scraping mejorado de Finviz con headers completos."""
    ticker_clean = ticker.replace('.', '-')
    url = f"https://finviz.com/quote.ashx?t={ticker_clean}"
    
    # Headers mejorados para evitar bloqueos
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        session = requests.Session()
        time.sleep(0.5)  # Pausa cortés
        r = session.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # Buscar la tabla de datos
        table = soup.find('table', class_='snapshot-table2')
        if table:
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                for i, cell in enumerate(cells):
                    if 'EPS next 5Y' in cell.get_text():
                        if i + 1 < len(cells):
                            val_text = cells[i + 1].get_text().strip()
                            val_clean = val_text.replace('%', '').replace(',', '').strip()
                            try:
                                return float(val_clean)
                            except:
                                pass
        
        # Método alternativo
        eps_next = soup.find(string="EPS next 5Y")
        if eps_next:
            val = eps_next.parent.find_next_sibling('td').text.replace('%', '').replace(',', '').strip()
            try:
                return float(val)
            except:
                pass
                
    except Exception as e:
        st.warning(f"⚠️ No se pudo obtener crecimiento de Finviz: {e}")
        return None
    
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_growth(ticker):
    """Scraping de StockAnalysis.com como alternativa."""
    ticker_clean = ticker.upper()
    url = f"https://stockanalysis.com/stocks/{ticker_clean.lower()}/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        session = requests.Session()
        time.sleep(1)
        r = session.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # Buscar en las tablas de forecast/estimates
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                if 'EPS Growth' in row.get_text() or 'Revenue Growth' in row.get_text():
                    cells = row.find_all('td')
                    if cells:
                        for cell in cells:
                            text = cell.get_text().strip()
                            if '%' in text:
                                try:
                                    val = float(text.replace('%', '').replace(',', '').strip())
                                    if 0 < val < 100:  # Validación razonable
                                        return val
                                except:
                                    pass
    except Exception as e:
        return None
    
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=5):
    """
    MÉTODO MATEMÁTICO INFALIBLE:
    Descarga precios y fundamentales, los alinea y calcula la media.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Historial de Precios (Mensual)
        start_date = (datetime.now() - timedelta(days=years*365 + 30)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        
        if hist.empty: 
            return {}
        
        # Limpieza de zona horaria
        if hist.index.tz is not None: 
            hist.index = hist.index.tz_localize(None)
        
        # 2. Fundamentales Anuales
        try:
            fin = stock.financials.T
            bal = stock.balance_sheet.T
        except:
            return {}
        
        if fin.empty: 
            return {}
        
        # Limpieza de índices
        fin.index = pd.to_datetime(fin.index)
        if fin.index.tz is not None: 
            fin.index = fin.index.tz_localize(None)
            
        if bal is not None and not bal.empty:
            bal.index = pd.to_datetime(bal.index)
            if bal.index.tz is not None:
                bal.index = bal.index.tz_localize(None)
        
        # 3. Fusión de Datos
        df_merge = pd.DataFrame(index=hist.index)
        df_merge['Price'] = hist['Close']
        
        # Extraemos métricas clave
        metrics_fin = pd.DataFrame(index=fin.index)
        
        # EPS
        if 'Diluted EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Diluted EPS']
        elif 'Basic EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Basic EPS']
        
        # Revenue Per Share
        rev = fin.get('Total Revenue')
        shares = fin.get('Basic Average Shares')
        if shares is None:
            shares = fin.get('Share Issued')
            
        if rev is not None and shares is not None:
            metrics_fin['RPS'] = rev / shares
        
        # Balance Sheet metrics
        if not bal.empty:
            assets = bal.get('Total Assets')
            liab = bal.get('Total Liabilities Net Minority Interest')
            
            if assets is not None and liab is not None and shares is not None:
                # Alinear shares con balance
                metrics_fin['BVPS'] = (assets - liab) / shares
                
            # EV/EBITDA
            debt = bal.get('Total Debt')
            cash = bal.get('Cash And Cash Equivalents')
            ebitda = fin.get('EBITDA')
            if ebitda is None:
                ebitda = fin.get('Normalized EBITDA')
            
            if debt is not None and cash is not None and ebitda is not None and shares is not None:
                metrics_fin['Debt'] = debt
                metrics_fin['Cash'] = cash
                metrics_fin['EBITDA'] = ebitda
                metrics_fin['Shares'] = shares

        # Ordenar y fusionar
        metrics_fin = metrics_fin.sort_index()
        df_merge = df_merge.sort_index()
        
        # Join y forward fill
        df_final = df_merge.join(metrics_fin, how='outer').ffill().dropna(subset=['Price'])
        
        # 4. Cálculo de Ratios
        ratios = {}
        
        # P/E Ratio
        if 'EPS' in df_final.columns:
            df_final['PE_Ratio'] = df_final['Price'] / df_final['EPS']
            
