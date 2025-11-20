import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Valuación Pro & Dividendos", layout="wide", page_icon="💎")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f8f9fa; border-radius: 4px 4px 0 0; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-bottom: 2px solid #2c3e50; color: #2c3e50; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES AUXILIARES ---

def normalize_yahoo_data(value):
    """
    Normaliza los datos erráticos de Yahoo Finance.
    Algunas veces el Yield viene como 5.5 (5.5%) y otras como 0.055 (5.5%).
    Regla heurística: Si es > 0.3 (30%), asumimos que viene en formato 100 based.
    """
    if value is None: return 0
    if isinstance(value, (int, float)):
        # Si el dividendo es mayor al 30%, probablemente sea un error de escala de Yahoo (ej. mandan 45 en vez de 0.45)
        # A menos que sea un REIT en crisis, es raro ver >30%. 
        if value > 0.30: 
            return value / 100
    return value

# --- 2. MOTOR DE DATOS ---

@st.cache_data(ttl=3600)
def get_stock_basic_info(ticker):
    stock = yf.Ticker(ticker)
    return stock.info

@st.cache_data(ttl=3600)
def get_historical_pe_mean(ticker, years=10):
    try:
        stock = yf.Ticker(ticker)
        start_date = (datetime.now() - timedelta(days=years*365 + 180)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        
        if hist.empty: return None
        if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)

        financials = stock.financials.T
        if financials.empty: return None
        
        financials.index = pd.to_datetime(financials.index)
        if financials.index.tz is not None: financials.index = financials.index.tz_localize(None)
        financials = financials.sort_index()

        pe_values = []
        for date, row in hist.iterrows():
            past_reports = financials[financials.index <= date]
            if not past_reports.empty:
                latest = past_reports.iloc[-1]
                eps = np.nan
                for k in ['Diluted EPS', 'Basic EPS', 'DilutedEPS']:
                    if k in latest and pd.notna(latest[k]):
                        eps = latest[k]
                        break
                
                if pd.isna(eps):
                    try:
                        ni = latest.get('Net Income Common Stockholders')
                        shares = latest.get('Basic Average Shares')
                        if ni and shares: eps = ni / shares
                    except: pass

                if eps and eps > 0:
                    pe = row['Close'] / eps
                    if 5 < pe < 200: pe_values.append(pe) # Filtro más amplio
        
        return np.mean(pe_values) if pe_values else None
    except:
        return None

@st.cache_data(ttl=3600)
def scrape_valueinvesting_io(ticker):
    url = f"https://valueinvesting.io/{ticker}/estimates"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            for df in dfs:
                if df.apply(lambda x: x.astype(str).str.contains('Growth|Revenue|EPS', case=False)).any().any():
                    return df
    except:
        return None
    return None

# --- 3. COMPONENTES VISUALES ---

def render_gauge(current, fair, title):
    fig = go.Figure(go.Indicator(
        mode = "number+gauge+delta",
        value = current,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title, 'font': {'size': 14}},
        delta = {'reference': fair, 'relative': True, 'valueformat': '.1%'},
        gauge = {
            'axis': {'range': [min(current, fair)*0.5, max(current, fair)*1.5]},
            'bar': {'color': "#2c3e50"},
            'steps': [
                {'range': [0, fair], 'color': "#c8e6c9"},
                {'range': [fair, max(current, fair)*2], 'color': "#ffcdd2"}],
            'threshold': {'line': {'color': "green", 'width': 3}, 'thickness': 0.8, 'value': fair}
        }
    ))
    # Ajuste de márgenes para evitar warnings
    fig.update_layout(height=180, margin=dict(l=20,r=20,t=30,b=10), autosize=True)
    # Usamos width='stretch' implícitamente al no pasar argumentos fijos, Streamlit lo maneja bien ahora
    st.plotly_chart(fig, use_container_width=True)

# --- 4. INTERFAZ PRINCIPAL ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    
    st.divider()
    st.subheader("🔮 Proyección")
    
    scraped_df = scrape_valueinvesting_io(ticker)
    if scraped_df is not None:
        st.success("✅ Datos detectados")
        with st.expander("Ver Tabla"):
            st.dataframe(scraped_df)
    else:
        st.info(f"ℹ️ Sin conexión automática.")
        st.markdown(f"[👉 Ver ValueInvesting.io](https://valueinvesting.io/{ticker}/estimates)")

    growth_input = st.number_input("Crecimiento EPS Estimado (%)", value=12.0, step=0.5)
    
    st.divider()
    years_hist = st.slider("Años Historia", 5, 10, 10)

if ticker:
    # CORRECCIÓN CRÍTICA: Instanciamos el objeto stock aquí para usarlo globalmente
    stock = yf.Ticker(ticker)
    info = get_stock_basic_info(ticker) # Usamos caché para info básica
    
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))

    if not price:
        st.error(f"No se encontraron datos de precio para {ticker}.")
        st.stop()

    # --- EXTRACCIÓN Y LIMPIEZA DE DATOS ---
    eps = info.get('trailingEps', 0)
    
    # Limpieza de Dividendos (Corrección del error del 29%)
    raw_yield = info.get('dividendYield')
    raw_avg_yield = info.get('fiveYearAvgDividendYield')
    
    div_yield = normalize_yahoo_data(raw_yield)
    avg_div_5y = normalize_yahoo_data(raw_avg_yield)
    
    # Media PER Histórica
    pe_hist_mean = get_historical_pe_mean(ticker, years=years_hist)
    if pe_hist_mean is None: pe_hist_mean = 15.0

    # --- DASHBOARD ---
    st.title(f"{info.get('shortName', ticker)}")
    st.caption(f"{info.get('sector')} | {info.get('industry')}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precio Actual", f"${price}")
    m2.metric("EPS (TTM)", f"${eps}")
    
    # Lógica de color para el dividendo
    delta_msg = None
    delta_col = "normal"
    if div_yield and avg_div_5y:
        if div_yield > avg_div_5y:
            delta_msg = "Zona de Compra (Yield Alto)"
            delta_col = "normal" # Verde en Streamlit
        else:
            delta_msg = "Zona Cara (Yield Bajo)"
            delta_col = "inverse" # Rojo en Streamlit

    m3.metric("Div. Yield Actual", f"{div_yield*100:.2f}%" if div_yield else "0.00%")
    m4.metric("Media Histórica Div.", f"{avg_div_5y*100:.2f}%" if avg_div_5y else "N/A", 
              delta=delta_msg, delta_color=delta_col)

    # --- PESTAÑAS ---
    tab_proj, tab_div, tab_val, tab_data = st.tabs(["🚀 Proyección 5 Años", "💰 Dividendos", "⚖️ Modelos Clásicos", "📉 Gráficos"])

    # TAB 1: CALCULADORA
    with tab_proj:
        st.subheader("Calculadora de Retorno Esperado")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.markdown("#### Inputs")
            g_rate = growth_input
            # Input PER Final editable por el usuario
            exit_pe = st.number_input("PER de Salida (Año 5)", value=float(round(pe_hist_mean, 1)), step=0.5,
                                     help="Múltiplo al que crees que cotizará en el futuro.")
            
            future_eps = eps * ((1 + g_rate/100) ** 5)
            future_price = future_eps * exit_pe
            cagr = ((future_price / price) ** (1/5) - 1) * 100
            
            st.divider()
            st.metric("Precio Objetivo (2029)", f"${future_price:.2f}")
            
        with c2:
            st.markdown("#### Retorno Anualizado (CAGR)")
            color = "#2ecc71" if cagr > 10 else "#e74c3c"
            st.markdown(f"<h1 style='color:{color}; font-size:48px;'>{cagr:.2f}%</h1>", unsafe_allow_html=True)
            st.caption("Incluye solo apreciación del capital (sin dividendos reinvertidos).")
            
            # Gráfico proyección
            years = list(range(datetime.now().year, datetime.now().year + 6))
            prices = [price * ((1 + cagr/100) ** i) for i in range(6)]
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=years, y=prices, mode='lines+markers', name='Proyección', line=dict(color='#3498db', width=3)))
            fig_proj.update_layout(height=300, margin=dict(l=0,r=0,t=20,b=20))
            st.plotly_chart(fig_proj, use_container_width=True)

    # TAB 2: DIVIDENDOS (WEISS)
    with tab_div:
        st.subheader("Método Geraldine Weiss (Yield Theory)")
        if div_yield and avg_div_5y and avg_div_5y > 0:
            div_rate = info.get('dividendRate', 0)
            fair_weiss = div_rate / avg_div_5y
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.write(f"**Dividendo Anual:** ${div_rate}")
                st.write(f"**Yield Medio Histórico:** {avg_div_5y*100:.2f}%")
                st.info("Si la acción recupera su rentabilidad media, el precio debería subir.")
            with col_d2:
                st.metric("Precio Justo (Weiss)", f"${fair_weiss:.2f}", delta=f"{((fair_weiss-price)/price)*100:.1f}% Margen")
                render_gauge(price, fair_weiss, "Valoración Dividendo")
        else:
            st.warning("Datos insuficientes para modelo de dividendos.")

    # TAB 3: OTROS
    with tab_val:
        st.subheader("Otros Modelos")
        bvps = info.get('bookValue', 0)
        val_graham = (22.5 * eps * bvps)**0.5 if (eps>0 and bvps>0) else 0
        val_lynch = eps * growth_input # PEG = 1
        
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            st.markdown("**Benjamin Graham**")
            if val_graham > 0: render_gauge(price, val_graham, "Graham")
            else: st.write("N/A")
        with c_m2:
            st.markdown("**Peter Lynch (PEG=1)**")
            if val_lynch > 0: render_gauge(price, val_lynch, "Lynch")
            else: st.write("N/A")

    # TAB 4: GRÁFICOS (CORREGIDO)
    with tab_data:
        st.subheader("Cotización Histórica (5 años)")
        try:
            # Ahora sí usamos el objeto 'stock' que instanciamos arriba
            hist_price = stock.history(period="5y")
            
            if not hist_price.empty:
                fig = go.Figure(data=[go.Candlestick(x=hist_price.index,
                                open=hist_price['Open'],
                                high=hist_price['High'],
                                low=hist_price['Low'],
                                close=hist_price['Close'])])
                fig.update_layout(height=500, title_text="Gráfico de Velas")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No hay datos históricos disponibles.")
        except Exception as e:
            st.error(f"Error cargando gráfico: {e}")
