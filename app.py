import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro 360", layout="wide", page_icon="📊")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .metric-label { font-size: 12px; color: #777; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
    .metric-value { font-size: 26px; font-weight: 700; color: #2c3e50; }
    .metric-sub { font-size: 14px; font-weight: 500; margin-top: 5px; }
    .pos { color: #27ae60; }
    .neg { color: #c0392b; }
    .neu { color: #7f8c8d; }
    .ratio-table th { background-color: #f8f9fa !important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTOR DE DATOS BLINDADO ---

@st.cache_data(ttl=3600)
def get_stockanalysis_ratios(ticker):
    """
    Intenta obtener la tabla de Ratios Financieros de stockanalysis.com
    para comparar Current vs Average.
    """
    # StockAnalysis usa tickers limpios (sin .MC para USA, pero con sufijos para otros)
    # Normalmente funciona bien para USA.
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    ratios_data = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            if dfs:
                df = dfs[0]
                # Buscamos filas clave
                metrics_map = {
                    'PE Ratio': 'PER',
                    'PS Ratio': 'Price/Sales',
                    'PB Ratio': 'Price/Book',
                    'EV / EBITDA': 'EV/EBITDA'
                }
                
                # Iterar sobre el dataframe para extraer medias
                # Estructura usual: Col 0 es nombre, Cols siguientes son años
                for index, row in df.iterrows():
                    metric_name = str(row[0])
                    for key, clean_name in metrics_map.items():
                        if key in metric_name:
                            # Extraer valores numéricos de las columnas de años (excluyendo 'Current' si existe en col 1)
                            # Normalmente StockAnalysis pone los años en las columnas.
                            values = []
                            for val in row[1:]:
                                try:
                                    v = float(str(val).replace(',', ''))
                                    values.append(v)
                                except:
                                    pass
                            
                            if values:
                                ratios_data[clean_name] = np.mean(values)
    except:
        pass # Si falla el scraping, devolvemos dict vacío y usamos fallback
        
    return ratios_data

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    if not price: return None
    
    # --- CORRECCIÓN DE DIVIDENDOS ---
    div_rate = info.get('dividendRate', 0)
    if div_rate and price > 0:
        current_yield = div_rate / price
    else:
        raw_yield = info.get('dividendYield', 0)
        current_yield = raw_yield / 100 if (raw_yield and raw_yield > 0.5) else raw_yield

    raw_avg_5y = info.get('fiveYearAvgDividendYield', 0)
    avg_5y_yield = raw_avg_5y / 100 if raw_avg_5y is not None else 0
        
    # --- PER Histórico (Cálculo Propio) ---
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
                    
                    # Fallback EPS manual
                    if pd.isna(eps_val):
                        try:
                            ni = latest.get('Net Income Common Stockholders')
                            shares = latest.get('Basic Average Shares')
                            if ni and shares: eps_val = ni / shares
                        except: pass
                        
                    if eps_val and eps_val > 0:
                        pe = row['Close'] / eps_val
                        if 5 < pe < 200: pe_values.append(pe)
            
            if pe_values: pe_mean = np.mean(pe_values)
    except: pass 

    # --- RATIOS EXTERNOS (StockAnalysis) ---
    external_ratios = get_stockanalysis_ratios(ticker)

    return {
        'info': info,
        'price': price,
        'pe_mean': pe_mean,
        'div_data': {'current': current_yield, 'avg_5y': avg_5y_yield, 'rate': div_rate},
        'external_ratios': external_ratios
    }

# --- 2. VISUALES ---

def card_html(label, value, sub_value=None, color_class="neu"):
    sub_html = f"<div class='metric-sub {color_class}'>{sub_value}</div>" if sub_value else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

def plot_valuation_bar(price, fair_value, analyst_target):
    fig = go.Figure()
    y_cat = ['']
    
    fig.add_trace(go.Bar(y=y_cat, x=[price], name='Actual', orientation='h', marker_color='#e67e22', text=f"${price:.2f}", textposition='auto'))
    fig.add_trace(go.Bar(y=y_cat, x=[fair_value], name='Fair Value', orientation='h', marker_color='#27ae60', text=f"${fair_value:.2f}", textposition='auto'))
    if analyst_target:
        fig.add_trace(go.Bar(y=y_cat, x=[analyst_target], name='Analistas', orientation='h', marker_color='#2980b9', text=f"${analyst_target:.2f}", textposition='auto'))

    fig.update_layout(title="Comparativa de Valoración", barmode='group', height=200, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)

# --- 3. INTERFAZ ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="ZTS").upper()
    st.divider()
    growth_input = st.number_input("Crecimiento Estimado (5y) %", value=10.0, step=0.5)
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)
    st.caption("Fuente: Yahoo Finance + StockAnalysis")

if ticker:
    data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("Ticker no encontrado.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    ext_ratios = data['external_ratios']
    
    eps = info.get('trailingEps', 0)
    analyst_target = info.get('targetMeanPrice', 0)
    
    # Cálculos principales
    fair_value = eps * pe_mean
    margin_safety = ((fair_value - price) / price) * 100
    
    # HEADER
    st.title(f"{info.get('shortName', ticker)}")
    st.markdown(f"**{info.get('sector', '')}** | {info.get('industry', '')}")
    
    # DASHBOARD
    c1, c2, c3, c4 = st.columns(4)
    with c1: card_html("Cotización", f"${price:.2f}")
    with c2: 
        col = "pos" if margin_safety > 0 else "neg"
        card_html("Fair Value", f"${fair_value:.2f}", f"{margin_safety:+.1f}% Margen", col)
    with c3:
        if analyst_target:
            a_marg = ((analyst_target - price)/price)*100
            col = "pos" if a_marg > 0 else "neg"
            card_html("Obj. Analistas", f"${analyst_target:.2f}", f"{a_marg:+.1f}% Potencial", col)
        else: card_html("Obj. Analistas", "N/A")
    with c4:
        curr, avg = divs['current'], divs['avg_5y']
        val_curr = curr if curr else 0
        val_avg = avg if avg else 0
        col = "pos" if (val_curr > 0 and val_curr > val_avg) else "neu"
        sub = f"Media 5y: {val_avg*100:.2f}%" if val_avg > 0 else "Sin histórico"
        card_html("Div. Yield", f"{val_curr*100:.2f}%", sub, col)

    st.markdown("---")
    plot_valuation_bar(price, fair_value, analyst_target)
    
    # TABS
    t1, t2, t3 = st.tabs(["🚀 Proyección", "💰 Dividendos", "📊 Ratios vs Media"])
    
    # TAB 1: PROYECCION
    with t1:
        cc1, cc2 = st.columns([1,2])
        with cc1:
            st.subheader("Calculadora")
            exit_pe = st.number_input("PER Salida", value=float(round(pe_mean, 1)))
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100
            st.divider()
            st.write(f"**Precio 2029:** ${f_price:.2f}")
            col_c = "green" if cagr > 10 else "black"
            st.markdown(f"### CAGR: <span style='color:{col_c}'>{cagr:.2f}%</span>", unsafe_allow_html=True)
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#27ae60', width=3)))
            fig.update_layout(title="Curva de Crecimiento Teórico", height=300, margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig, use_container_width=True)
            
    # TAB 2: DIVIDENDOS
    with t2:
        if divs['rate'] and divs['avg_5y'] > 0:
            fair_yield = divs['rate'] / divs['avg_5y']
            marg = ((fair_yield - price)/price)*100
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                st.markdown("### Yield Theory")
                st.write(f"Dividendo Anual: **${divs['rate']}**")
                st.metric("Valor Justo (Weiss)", f"${fair_yield:.2f}", f"{marg:+.1f}%")
            with c_d2:
                fig = go.Figure(go.Bar(x=['Actual', 'Media 5y'], y=[divs['current']*100, divs['avg_5y']*100], marker_color=['#2980b9','#95a5a6'], textposition='auto', texttemplate='%{y:.2f}%'))
                fig.update_layout(height=250, title="Comparativa Yields")
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("No aplica modelo de dividendos.")

    # TAB 3: RATIOS COMPARATIVOS
    with t3:
        st.subheader("Análisis Fundamental: Actual vs Histórico")
        
        # Preparar datos
        ratios_to_show = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': ext_ratios.get('PER') or pe_mean},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': ext_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': ext_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': ext_ratios.get('EV/EBITDA')}
        }
        
        # Construir filas
        rows = []
        for name, vals in ratios_to_show.items():
            curr = vals['curr']
            avg = vals['avg']
            
            if curr and avg:
                diff = ((curr - avg) / avg) * 100
                # Para valoración, menor ratio usualmente es mejor (excepto a veces Book)
                # Si Current < Avg -> Verde (Barato)
                status = "🟢 Infravalorado" if curr < avg else "🔴 Sobrevalorado"
                rows.append([name, f"{curr:.2f}", f"{avg:.2f}", f"{diff:+.1f}%", status])
            elif curr:
                rows.append([name, f"{curr:.2f}", "N/A", "-", "-"])
                
        df_ratios = pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Diferencia', 'Estado'])
        st.table(df_ratios)
        
        if not ext_ratios:
            st.warning("⚠️ No se pudieron obtener las medias de StockAnalysis.com automáticamente. Se muestran solo datos disponibles.")
            st.markdown(f"[👉 Ver Ratios en StockAnalysis.com](https://stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/)")
