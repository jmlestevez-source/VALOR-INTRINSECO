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
    /* 1. FUENTES GLOBALES MASIVAS */
    html, body, [class*="css"], p, div, span {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 20px; /* Base aumentada */
    }
    
    /* 2. PESTAÑAS GIGANTES */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        font-size: 24px !important; /* Letra Pestañas */
        font-weight: 700 !important;
        padding: 15px 30px !important;
        background-color: #f0f2f6;
        border-radius: 10px 10px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #2980b9 !important;
        border-top: 4px solid #2980b9;
    }

    /* 3. TABLAS LEGIBLES */
    .stTable { font-size: 22px !important; }
    thead tr th { font-size: 24px !important; background-color: #ececec !important; }
    tbody tr td { font-size: 22px !important; padding: 15px !important; }

    /* 4. TARJETAS MÉTRICAS */
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
        color: #555; 
        text-transform: uppercase; 
        font-weight: 800;
        letter-spacing: 1.2px;
        margin-bottom: 10px;
    }
    .metric-value { 
        font-size: 56px !important; /* NÚMEROS GIGANTES */
        font-weight: 900; 
        color: #2c3e50; 
        line-height: 1.1;
    }
    .metric-sub { font-size: 22px !important; font-weight: 600; margin-top: 12px; }
    
    /* 5. CAJA DE VEREDICTO */
    .verdict-box {
        padding: 35px;
        border-radius: 20px;
        text-align: center;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #fdcb6e, #e17055); }
    .v-overvalued { background: linear-gradient(135deg, #ff7675, #d63031); }
    
    .v-main { font-size: 60px; font-weight: 900; margin: 10px 0; text-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    .v-desc { font-size: 26px; font-weight: 500; opacity: 0.95; }
    
    /* CLASES DE COLOR */
    .pos { color: #00b894; font-weight:bold; } 
    .neg { color: #d63031; font-weight:bold; }
    .neu { color: #636e72; }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTORES DE DATOS (SCRAPING + CÁLCULO HÍBRIDO) ---

@st.cache_data(ttl=3600)
def get_finviz_growth_soup(ticker):
    ticker_clean = ticker.replace('.', '-')
    url = f"https://finviz.com/quote.ashx?t={ticker_clean}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            target = soup.find(string="EPS next 5Y")
            if target:
                val_td = target.parent.find_next_sibling('td')
                if val_td and val_td.text:
                    return float(val_td.text.replace('%', '').strip())
    except: return None
    return None

def calculate_internal_ratios(stock, years=5):
    """
    FALLBACK: Si StockAnalysis falla, calculamos los ratios 'in-house'
    usando datos de Yahoo Finance.
    """
    try:
        # Descargar historia
        start = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
        hist = stock.history(start=start, interval="1mo")
        financials = stock.financials.T
        financials.index = pd.to_datetime(financials.index)
        financials = financials.sort_index()
        
        if hist.empty or financials.empty: return {}

        ratios = {'PER': [], 'Price/Sales': [], 'Price/Book': []}
        
        for date, row in hist.iterrows():
            price = row['Close']
            # Dato financiero más cercano anterior
            past = financials[financials.index <= date]
            if not past.empty:
                latest = past.iloc[-1]
                
                # PER
                eps = latest.get('Diluted EPS', latest.get('Basic EPS'))
                if eps and eps > 0: ratios['PER'].append(price / eps)
                
                # Price/Sales (Total Revenue / Shares)
                rev = latest.get('Total Revenue')
                shares = latest.get('Basic Average Shares')
                if rev and shares and shares > 0:
                    rps = rev / shares
                    if rps > 0: ratios['Price/Sales'].append(price / rps)
                    
                # Price/Book
                # Yahoo a veces no da Book Value directo en financials, lo aproximamos
                # BV = (Total Assets - Total Liab) / Shares
                assets = latest.get('Total Assets')
                liab = latest.get('Total Liabilities Net Minority Interest')
                if assets and liab and shares:
                    bv = (assets - liab) / shares
                    if bv > 0: ratios['Price/Book'].append(price / bv)

        # Medias
        final_ratios = {}
        if ratios['PER']: final_ratios['PER'] = np.mean(ratios['PER'])
        if ratios['Price/Sales']: final_ratios['Price/Sales'] = np.mean(ratios['Price/Sales'])
        if ratios['Price/Book']: final_ratios['Price/Book'] = np.mean(ratios['Price/Book'])
        
        # Marcamos como calculados
        final_ratios['source'] = 'calculated'
        return final_ratios
    except:
        return {}

@st.cache_data(ttl=3600)
def get_stockanalysis_ratios_robust(ticker):
    """
    Intenta Scraping -> Si falla -> Calcula Internamente.
    """
    ticker_clean = ticker.lower().replace('.', '-')
    url = f"https://stockanalysis.com/stocks/{ticker_clean}/financials/ratios/"
    
    # Headers "reales"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1'
    }
    
    ratios_data = {}
    scraping_success = False
    
    # INTENTO 1: SCRAPING DIRECTO
    try:
        response = requests.get(url, headers=headers, timeout=4)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            if dfs:
                df = dfs[0]
                metrics_map = {'PE Ratio': 'PER', 'PS Ratio': 'Price/Sales', 'PB Ratio': 'Price/Book', 'EV / EBITDA': 'EV/EBITDA'}
                
                for index, row in df.iterrows():
                    metric_raw = str(row.iloc[0])
                    for key, clean_name in metrics_map.items():
                        if key in metric_raw:
                            values = []
                            for val in row.iloc[1:]:
                                try: values.append(float(str(val).replace(',', '').replace('%', '')))
                                except: pass
                            if values: ratios_data[clean_name] = np.mean(values)
                
                if ratios_data:
                    ratios_data['source'] = 'scraped'
                    scraping_success = True
    except:
        pass
    
    # INTENTO 2: CÁLCULO INTERNO (SI FALLA SCRAPING)
    if not scraping_success:
        stock = yf.Ticker(ticker)
        internal_data = calculate_internal_ratios(stock)
        ratios_data.update(internal_data) # Mezclamos
        
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
    if current_yield == 0:
        raw_y = info.get('dividendYield', 0)
        current_yield = raw_y / 100 if (raw_y and raw_y > 0.5) else (raw_y or 0)

    raw_avg = info.get('fiveYearAvgDividendYield', 0)
    avg_5y_yield = raw_avg / 100 if raw_avg is not None else 0
        
    # Datos Externos (Híbrido)
    ext_ratios = get_stockanalysis_ratios_robust(ticker)
    finviz_growth = get_finviz_growth_soup(ticker)
    
    # PER Histórico: Priorizamos el scrapeado, si no, el calculado
    pe_mean = ext_ratios.get('PER', 15.0)

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
        desc = f"Descuento del {margin:.1f}%"
    elif margin < -15:
        css = "v-overvalued"; title = "⚠️ CUIDADO"; main = "SOBREVALORADA"; icon = "🛑"
        desc = f"Prima del {abs(margin):.1f}%"
    else:
        css = "v-fair"; title = "⚖️ EQUILIBRIO"; main = "PRECIO JUSTO"; icon = "✅"
        desc = f"Cotizando cerca de su media"

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
    st.caption("v4.0 Big UI & Hybrid Data")

if ticker:
    with st.spinner(f'⏳ Analizando {ticker}...'):
        data = get_full_analysis(ticker)
    
    if not data:
        st.error("Ticker no encontrado.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    ext_ratios = data['ext_ratios']
    finviz_g = data['finviz_growth']
    
    # Configuración de Crecimiento
    default_g = finviz_g if finviz_g else 10.0
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        if finviz_g: st.success(f"✅ Finviz: {finviz_g}%")
        
        # Indicador de Origen de Datos
        if ext_ratios.get('source') == 'scraped':
            st.success("✅ StockAnalysis: Conectado")
        elif ext_ratios.get('source') == 'calculated':
            st.info("ℹ️ StockAnalysis: Calculado (Fallback)")
        else:
            st.warning("⚠️ Datos Históricos Limitados")

    eps = info.get('trailingEps', 0)
    fair_value = eps * pe_mean
    
    # --- HEADER ---
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

    st.markdown("<br><br>", unsafe_allow_html=True)

    # 3. PESTAÑAS GIGANTES
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 DIVIDENDOS", "📊 FUNDAMENTALES VS MEDIA"])
    
    # TAB 1: PROYECCIÓN
    with t1:
        st.markdown("<br>", unsafe_allow_html=True)
        cc1, cc2 = st.columns([1, 2])
        with cc1:
            st.subheader("📝 Calculadora")
            st.markdown(f"""
            <ul style='font-size:22px'>
                <li>EPS Actual: <b>${eps:.2f}</b></li>
                <li>Crecimiento Estimado: <b>{growth_input}%</b></li>
                <li>PER Medio Histórico: <b>{pe_mean:.1f}x</b></li>
            </ul>
            """, unsafe_allow_html=True)
            
            exit_pe = st.number_input("PER de Salida Estimado", value=float(round(pe_mean, 1)))
            
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100
            
            st.markdown("---")
            st.markdown(f"<div style='font-size:28px; margin-bottom:10px'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            c_col = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:28px'>CAGR Esperado: <b style='color:{c_col}; font-size:42px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
            
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#0984e3', width=5), marker=dict(size=14)))
            fig.update_layout(
                title={'text': "Curva de Valor Teórico", 'font': {'size': 24}},
                font=dict(size=18),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

    # TAB 2: DIVIDENDOS
    with t2:
        st.markdown("<br>", unsafe_allow_html=True)
        if divs['rate'] and divs['avg_5y'] > 0:
            fair_yld = divs['rate'] / divs['avg_5y']
            marg = ((fair_yld - price)/price)*100
            
            cd1, cd2 = st.columns(2)
            with cd1:
                st.info("ℹ️ Modelo de Geraldine Weiss (Yield Theory)")
                st.markdown(f"""
                <div style='font-size:24px; line-height:2'>
                    💰 Dividendo Anual: <b>${divs['rate']}</b><br>
                    📉 Media Histórica: <b>{divs['avg_5y']*100:.2f}%</b><br>
                    🏁 Valor Justo: <b style='color:#2980b9'>${fair_yld:.2f}</b>
                </div>
                """, unsafe_allow_html=True)
                
            with cd2:
                fig = go.Figure(go.Bar(x=['Actual', 'Media'], y=[divs['current']*100, divs['avg_5y']*100], marker_color=['#00b894','#b2bec3'], texttemplate='%{y:.2f}%', textfont={'size': 20}))
                fig.update_layout(title={'text': "Rentabilidad Comparada", 'font': {'size': 24}}, font=dict(size=18), height=350)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Empresa sin historial de dividendos suficiente.")

    # TAB 3: RATIOS (TABLA GRANDE)
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔎 Salud Financiera vs Histórico")
        
        ratios_to_show = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': ext_ratios.get('PER')},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': ext_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': ext_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': ext_ratios.get('EV/EBITDA')}
        }
        
        rows = []
        for name, vals in ratios_to_show.items():
            curr = vals['curr']
            avg = vals['avg']
            if curr and avg:
                status = "🟢 Barato" if curr < avg else "🔴 Caro"
                diff = ((curr-avg)/avg)*100
                rows.append([name, f"{curr:.2f}", f"{avg:.2f}", f"{diff:+.1f}%", status])
            elif curr:
                rows.append([name, f"{curr:.2f}", "N/A", "-", "-"])
        
        df_ratios = pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Desviación', 'Diagnóstico'])
        st.table(df_ratios)
