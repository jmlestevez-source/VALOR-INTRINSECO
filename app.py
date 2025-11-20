import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro Ultra", layout="wide", page_icon="💎")

# --- ESTILOS CSS (BIG FONTS & HIGH CONTRAST) ---
st.markdown("""
    <style>
    /* FUENTES GLOBALES AUMENTADAS */
    html, body, [class*="css"] {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* TARJETAS MÉTRICAS (MUCHO MÁS GRANDES) */
    .metric-card {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 25px 15px;
        text-align: center;
        box-shadow: 0 6px 15px rgba(0,0,0,0.08);
        border: 1px solid #ececec;
        height: 100%;
    }
    
    .metric-label { 
        font-size: 18px !important; 
        color: #666; 
        text-transform: uppercase; 
        font-weight: 700;
        letter-spacing: 1.2px;
        margin-bottom: 10px;
    }
    
    .metric-value { 
        font-size: 48px !important; 
        font-weight: 900; 
        color: #2c3e50; 
        line-height: 1.1;
    }
    
    .metric-sub { 
        font-size: 20px !important; 
        font-weight: 500; 
        margin-top: 12px; 
    }
    
    /* CAJA DE VEREDICTO */
    .verdict-box {
        padding: 30px;
        border-radius: 20px;
        text-align: center;
        color: white;
        margin-bottom: 35px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #fdcb6e, #e17055); }
    .v-overvalued { background: linear-gradient(135deg, #ff7675, #d63031); }
    
    .v-main { font-size: 52px; font-weight: 900; margin: 10px 0; text-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    .v-desc { font-size: 22px; font-weight: 500; opacity: 0.95; }
    
    /* PESTAÑAS Y TABLAS */
    .stTabs [data-baseweb="tab"] {
        font-size: 20px !important;
        font-weight: 600;
        padding: 15px 25px;
    }
    .stTable { font-size: 18px !important; }
    div[data-testid="stMetricValue"] { font-size: 36px !important; }
    
    /* CLASES DE COLOR */
    .pos { color: #00b894; } 
    .neg { color: #d63031; }
    .neu { color: #636e72; }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTORES DE DATOS (SCRAPING CORREGIDO) ---

@st.cache_data(ttl=3600)
def get_finviz_growth_soup(ticker):
    # Finviz usa tickers con guión en vez de punto (BRK-B)
    ticker_clean = ticker.replace('.', '-')
    url = f"https://finviz.com/quote.ashx?t={ticker_clean}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            target = soup.find(string="EPS next 5Y")
            if target:
                val_td = target.parent.find_next_sibling('td')
                if val_td and val_td.text:
                    return float(val_td.text.replace('%', '').strip())
    except: return None
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_ratios(ticker):
    """
    Scraper V2: Usa Session para mantener cookies y headers completos.
    Maneja redirecciones y tickers especiales.
    """
    # StockAnalysis usa guiones (BRK-B) y minúsculas
    ticker_clean = ticker.lower().replace('.', '-')
    url = f"https://stockanalysis.com/stocks/{ticker_clean}/financials/ratios/"
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://stockanalysis.com/',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
    })
    
    ratios_data = {}
    try:
        response = session.get(url, timeout=6)
        if response.status_code == 200:
            # Usamos read_html con BeautifulSoup backend implícito
            dfs = pd.read_html(response.text)
            if dfs:
                df = dfs[0] # La primera tabla suele ser la buena
                
                # Mapeo
                metrics_map = {
                    'PE Ratio': 'PER',
                    'PS Ratio': 'Price/Sales',
                    'PB Ratio': 'Price/Book',
                    'EV / EBITDA': 'EV/EBITDA'
                }
                
                for index, row in df.iterrows():
                    # Convertimos a string por seguridad
                    metric_raw = str(row.iloc[0])
                    
                    for key, clean_name in metrics_map.items():
                        if key in metric_raw:
                            values = []
                            # Iteramos desde la columna 1 en adelante (los años)
                            for val in row.iloc[1:]:
                                try:
                                    # Limpiar basura
                                    v_str = str(val).replace(',', '').replace('%', '')
                                    v = float(v_str)
                                    values.append(v)
                                except:
                                    pass
                            
                            if values:
                                ratios_data[clean_name] = np.mean(values)
    except Exception as e:
        # print(f"Debug Error: {e}") # Descomentar solo para debug local
        pass
        
    return ratios_data

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    stock = yf.Ticker(ticker)
    info = stock.info
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    if not price: return None
    
    # Dividendos
    div_rate = info.get('dividendRate', 0)
    current_yield = (div_rate / price) if (div_rate and price > 0) else 0
    
    # Fallback yield
    if current_yield == 0:
        raw_y = info.get('dividendYield', 0)
        if raw_y and raw_y > 0.5: current_yield = raw_y / 100
        else: current_yield = raw_y or 0

    raw_avg = info.get('fiveYearAvgDividendYield', 0)
    avg_5y_yield = raw_avg / 100 if raw_avg is not None else 0
        
    # PER Histórico
    pe_mean = 15.0
    try:
        start_date = (datetime.now() - timedelta(days=years_hist*365 + 180)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        if not hist.empty:
            if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
            financials = stock.financials.T
            financials.index = pd.to_datetime(financials.index)
            if financials.index.tz is not None: financials.index = financials.index.tz_localize(None)
            financials = financials.sort_index()
            
            pe_values = []
            for date, row in hist.iterrows():
                past = financials[financials.index <= date]
                if not past.empty:
                    latest = past.iloc[-1]
                    eps_val = np.nan
                    for k in ['Diluted EPS', 'Basic EPS', 'DilutedEPS']:
                        if k in latest and pd.notna(latest[k]):
                            eps_val = latest[k]; break
                    if pd.isna(eps_val):
                        try:
                            if latest.get('Net Income Common Stockholders') and latest.get('Basic Average Shares'):
                                eps_val = latest.get('Net Income Common Stockholders') / latest.get('Basic Average Shares')
                        except: pass
                    if eps_val and eps_val > 0:
                        pe = row['Close'] / eps_val
                        if 5 < pe < 200: pe_values.append(pe)
            if pe_values: pe_mean = np.mean(pe_values)
    except: pass 

    ext_ratios = get_stockanalysis_ratios(ticker)
    finviz_growth = get_finviz_growth_soup(ticker)

    return {
        'info': info, 'price': price, 'pe_mean': pe_mean,
        'div_data': {'current': current_yield, 'avg_5y': avg_5y_yield, 'rate': div_rate},
        'ext_ratios': ext_ratios, 'finviz_growth': finviz_growth
    }

# --- 2. COMPONENTES VISUALES ---

def card_html(label, value, sub_value=None, color_class="neu"):
    sub_html = f"<div class='metric-sub {color_class}'>{sub_value}</div>" if sub_value else ""
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>{label}</div>
        <div class='metric-value'>{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

def verdict_box(price, fair_value):
    margin = ((fair_value - price) / price) * 100
    
    if margin > 15:
        css = "v-undervalued"; title = "💎 OPORTUNIDAD"; main = "INFRAVALORADA"; icon = "🚀"
        desc = f"Descuento del {margin:.1f}% vs Histórico"
    elif margin < -15:
        css = "v-overvalued"; title = "⚠️ CUIDADO"; main = "SOBREVALORADA"; icon = "🛑"
        desc = f"Prima del {abs(margin):.1f}% vs Histórico"
    else:
        css = "v-fair"; title = "⚖️ EQUILIBRIO"; main = "PRECIO JUSTO"; icon = "✅"
        desc = f"Cotizando cerca de su media histórica"

    st.markdown(f"""
    <div class="verdict-box {css}">
        <div class="v-title">{title}</div>
        <div class="v-main">{icon} {main}</div>
        <div class="v-desc">{desc} (Fair: ${fair_value:.2f})</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. MAIN ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)
    st.caption("v3.5 Big Font Edition")

if ticker:
    with st.spinner(f'⏳ Conectando con StockAnalysis & Finviz para {ticker}...'):
        data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("Ticker no encontrado.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    ext_ratios = data['ext_ratios']
    finviz_g = data['finviz_growth']
    
    # Crecimiento
    default_g = finviz_g if finviz_g else 10.0
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        if finviz_g: st.success(f"✅ Finviz: {finviz_g}%")
        else: st.warning("⚠️ Manual (Finviz N/A)")
        if ext_ratios: st.success(f"✅ StockAnalysis: Conectado")
        else: st.warning("⚠️ StockAnalysis: Fallo conexión")

    eps = info.get('trailingEps', 0)
    fair_value = eps * pe_mean
    
    # Header
    st.title(f"{info.get('shortName', ticker)}")
    st.markdown(f"### **{info.get('sector', '')}**  •  {info.get('industry', '')}")
    st.markdown("---")

    # 1. VEREDICTO
    verdict_box(price, fair_value)

    # 2. BIG CARDS
    c1, c2, c3, c4 = st.columns(4)
    with c1: card_html("Cotización", f"${price:.2f}")
    with c2: card_html("Valor Razonable", f"${fair_value:.2f}", f"PER Medio: {pe_mean:.1f}x", "neu")
    with c3:
        target = info.get('targetMeanPrice', 0)
        if target:
            pot = ((target - price)/price)*100
            col = "pos" if pot > 0 else "neg"
            card_html("Obj. Analistas", f"${target:.2f}", f"{pot:+.1f}% Potencial", col)
        else: card_html("Obj. Analistas", "N/A")
    with c4:
        curr, avg = divs['current'], divs['avg_5y']
        v_c = curr if curr else 0
        v_a = avg if avg else 0
        col = "pos" if (v_c > 0 and v_c > v_a) else "neu"
        sub = f"Media: {v_a*100:.2f}%" if v_a > 0 else "N/A"
        card_html("Div. Yield", f"{v_c*100:.2f}%", sub, col)

    st.markdown("<br>", unsafe_allow_html=True)

    # 3. TABS
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 DIVIDENDOS", "📊 FUNDAMENTALES VS MEDIA"])
    
    with t1:
        cc1, cc2 = st.columns([1, 2])
        with cc1:
            st.subheader("Calculadora")
            st.markdown(f"<div style='font-size:20px'>EPS: <b>${eps:.2f}</b> | Crecimiento: <b>{growth_input}%</b></div>", unsafe_allow_html=True)
            st.write("")
            exit_pe = st.number_input("PER de Salida Estimado", value=float(round(pe_mean, 1)))
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100
            st.markdown("---")
            st.markdown(f"<div style='font-size:24px'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            c_col = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:24px'>CAGR: <b style='color:{c_col}; font-size:36px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#0984e3', width=5), marker=dict(size=12)))
            fig.update_layout(title="Curva de Valor", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(size=14))
            st.plotly_chart(fig, use_container_width=True)

    with t2:
        if divs['rate'] and divs['avg_5y'] > 0:
            fair_yld = divs['rate'] / divs['avg_5y']
            marg = ((fair_yld - price)/price)*100
            cd1, cd2 = st.columns(2)
            with cd1:
                st.markdown(f"<div style='font-size:22px'>Dividendo Anual: <b>${divs['rate']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:22px'>Media Histórica: <b>{divs['avg_5y']*100:.2f}%</b></div>", unsafe_allow_html=True)
                st.markdown("---")
                st.metric("Valor Justo (Weiss)", f"${fair_yld:.2f}", f"{marg:+.1f}%")
            with cd2:
                fig = go.Figure(go.Bar(x=['Actual', 'Media'], y=[divs['current']*100, divs['avg_5y']*100], marker_color=['#00b894','#b2bec3'], texttemplate='%{y:.2f}%'))
                fig.update_layout(title="Rentabilidad (%)", font=dict(size=16))
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("Datos de dividendos insuficientes.")

    with t3:
        st.subheader("Análisis de Ratios Históricos")
        ratios = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': ext_ratios.get('PER') or pe_mean},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': ext_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': ext_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': ext_ratios.get('EV/EBITDA')}
        }
        rows = []
        for n, v in ratios.items():
            c, a = v['curr'], v['avg']
            if c and a:
                stat = "🟢 Barato" if c < a else "🔴 Caro"
                diff = ((c-a)/a)*100
                rows.append([n, f"{c:.2f}", f"{a:.2f}", f"{diff:+.1f}%", stat])
            elif c: rows.append([n, f"{c:.2f}", "N/A", "-", "-"])
        
        st.table(pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media 5y', 'Desv.', 'Estado']))
        if not ext_ratios: st.warning("⚠️ Medias calculadas con datos parciales (StockAnalysis Bloqueado)")
