import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro (Estilo Excel)", layout="wide", page_icon="📊")

# --- ESTILOS CSS (DISEÑO V1 MEJORADO) ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .metric-label { font-size: 14px; color: #666; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px;}
    .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
    .metric-delta-pos { font-size: 14px; color: #27ae60; font-weight: 600; }
    .metric-delta-neg { font-size: 14px; color: #c0392b; font-weight: 600; }
    h1, h2, h3 { font-family: 'Source Sans Pro', sans-serif; color: #333; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #f8f9fa; border-radius: 4px; }
    .stTabs [aria-selected="true"] { background-color: #fff; border-bottom: 2px solid #2980b9; color: #2980b9; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE DATOS ---

@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """Obtiene info básica y calcula dividendos manualmente para evitar errores."""
    stock = yf.Ticker(ticker)
    info = stock.info
    
    # CORRECCIÓN DIVIDENDOS: Cálculo manual para precisión
    # Yahoo a veces da el yield en 0.05 y otras en 5.0. 
    # Lo más seguro es: (DividendRate / CurrentPrice)
    
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    div_rate = info.get('dividendRate', 0) # Dinero real (ej $1.50)
    
    # 1. Yield Actual Real
    if div_rate and price and price > 0:
        calculated_yield = div_rate / price
    else:
        calculated_yield = 0
        
    # 2. Media 5 Años (Normalización)
    avg_5y = info.get('fiveYearAvgDividendYield')
    if avg_5y is not None:
        # Si es mayor que 1 (ej: 3.5), es un porcentaje, dividimos por 100.
        # Si es menor (ej: 0.035), ya es decimal.
        if avg_5y > 1: 
            avg_5y = avg_5y / 100
    else:
        avg_5y = 0
        
    return info, price, calculated_yield, avg_5y

@st.cache_data(ttl=3600)
def get_historical_pe_mean(ticker, years=10):
    """Calcula la media del PER de los últimos X años."""
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
                    if 5 < pe < 200: pe_values.append(pe)
        
        return np.mean(pe_values) if pe_values else None
    except:
        return None

@st.cache_data(ttl=3600)
def scrape_estimates_check(ticker):
    """Verifica si hay conexión con VI (solo headers)."""
    url = f"https://valueinvesting.io/{ticker}/estimates"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.head(url, headers=headers, timeout=3)
        return r.status_code == 200
    except:
        return False

# --- 2. COMPONENTES VISUALES (ESTILO EXCEL/V1) ---

def card(label, value, delta=None, is_good=True):
    """Crea una tarjeta métrica HTML bonita."""
    delta_html = ""
    if delta:
        color_class = "metric-delta-pos" if is_good else "metric-delta-neg"
        delta_html = f"<div class='{color_class}'>{delta}</div>"
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

def plot_bar_comparison(current, target, title, label_target="Valor Objetivo"):
    """Gráfico de Barras Horizontales (Estilo Excel)."""
    fig = go.Figure()
    
    # Barra Precio Actual
    fig.add_trace(go.Bar(
        y=['Comparativa'], x=[current], name='Precio Actual', orientation='h',
        marker_color='#95a5a6', text=f"${current:.2f}", textposition='auto',
        hovertemplate="Precio Actual: $%{x:.2f}<extra></extra>"
    ))
    
    # Barra Objetivo
    color = '#27ae60' if target > current else '#c0392b'
    fig.add_trace(go.Bar(
        y=['Comparativa'], x=[target], name=label_target, orientation='h',
        marker_color=color, text=f"${target:.2f}", textposition='auto',
        hovertemplate=f"{label_target}: $%{{x:.2f}}<extra></extra>"
    ))

    fig.update_layout(
        title=title,
        barmode='group', 
        height=250,
        xaxis_title="Precio ($)",
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor='rgba(0,0,0,0)'
    )
    # Corrección Warning: Usamos el standard de Streamlit sin width explícito
    st.plotly_chart(fig, use_container_width=True)

# --- 3. INTERFAZ PRINCIPAL ---

with st.sidebar:
    st.header("🎛️ Panel de Control")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    
    st.divider()
    st.subheader("🔮 Proyección")
    
    # Link externo limpio
    st.info("Para ver estimaciones fiables, consulta:")
    st.markdown(f"[👉 ValueInvesting.io/{ticker}](https://valueinvesting.io/{ticker}/estimates)")
    
    growth_input = st.number_input("Crecimiento EPS Estimado (%)", value=12.0, step=0.5)
    
    st.divider()
    years_hist = st.slider("Años Historia (PER)", 5, 10, 10)

if ticker:
    try:
        info, price, div_yield, avg_div_5y = get_stock_data(ticker)
    except Exception:
        st.error("Ticker no encontrado o error de conexión.")
        st.stop()

    eps = info.get('trailingEps', 0)
    pe_hist_mean = get_historical_pe_mean(ticker, years=years_hist)
    if pe_hist_mean is None: pe_hist_mean = 15.0

    # --- HEADER ---
    st.title(f"{info.get('shortName', ticker)}")
    st.caption(f"Sector: {info.get('sector')} | Industria: {info.get('industry')}")

    # --- DASHBOARD DE MÉTRICAS (CARDS V1) ---
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: card("Precio Actual", f"${price:.2f}")
    with c2: card("EPS (TTM)", f"${eps:.2f}")
    
    # Lógica Dividendos Dashboard
    yield_display = f"{div_yield*100:.2f}%"
    avg_display = f"{avg_div_5y*100:.2f}%" if avg_div_5y else "N/A"
    
    delta_msg = None
    good_div = False
    if div_yield and avg_div_5y:
        diff = div_yield - avg_div_5y
        delta_msg = f"{diff*100:+.2f}% vs Media"
        good_div = diff > 0 # Es bueno si el yield actual es mayor a la media
        
    with c3: card("Div. Yield Actual", yield_display)
    with c4: card("Yield Media 5y", avg_display, delta=delta_msg, is_good=good_div)

    st.markdown("---")

    # --- PESTAÑAS ---
    tab_proj, tab_div, tab_models = st.tabs(["🚀 Proyección a 5 Años", "💰 Dividendos (Weiss)", "⚖️ Otros Modelos"])

    # --- TAB 1: PROYECCIÓN (Estilo Excel) ---
    with tab_proj:
        col_input, col_res = st.columns([1, 2])
        
        with col_input:
            st.subheader("Configuración")
            # PER Final editable
            exit_pe = st.number_input("PER de Salida (Año 5)", value=float(round(pe_hist_mean, 1)), step=0.5,
                                     help="El múltiplo al que crees que cotizará la acción en el futuro.")
            st.caption(f"*La media histórica calculada es {pe_hist_mean:.1f}x*")
            
            # Cálculos
            future_eps = eps * ((1 + growth_input/100) ** 5)
            future_price = future_eps * exit_pe
            cagr = ((future_price / price) ** (1/5) - 1) * 100
            
            st.divider()
            st.markdown(f"**EPS Año 5:** ${future_eps:.2f}")
            st.markdown(f"**Precio Objetivo:** ${future_price:.2f}")
            
            color_cagr = "green" if cagr > 10 else "red"
            st.markdown(f"**CAGR Esperado:** <span style='color:{color_cagr}; font-size:18px; font-weight:bold'>{cagr:.2f}%</span>", unsafe_allow_html=True)

        with col_res:
            plot_bar_comparison(price, future_price, "Potencial de Revalorización (5 Años)", "Precio Objetivo 2029")
            
            # Tabla estilo Excel
            df_excel = pd.DataFrame({
                'Concepto': ['EPS Actual', 'Crecimiento Estimado', 'EPS Futuro (5y)', 'PER de Salida', 'Precio Objetivo'],
                'Valor': [f"${eps:.2f}", f"{growth_input}%", f"${future_eps:.2f}", f"{exit_pe}x", f"${future_price:.2f}"]
            })
            st.table(df_excel)

    # --- TAB 2: DIVIDENDOS (WEISS - Corregido) ---
    with tab_div:
        if div_yield > 0 and avg_div_5y > 0:
            div_rate = info.get('dividendRate', 0)
            
            # Valor Justo Weiss
            fair_weiss = div_rate / avg_div_5y
            margin_weiss = ((fair_weiss - price) / price) * 100
            
            c_d1, c_d2 = st.columns([1, 2])
            with c_d1:
                st.subheader("Análisis Yield Theory")
                st.write(f"La acción paga **${div_rate}** al año.")
                st.write(f"Históricamente, el mercado exige un retorno del **{avg_div_5y*100:.2f}%**.")
                st.write(f"Actualmente ofrece un **{div_yield*100:.2f}%**.")
                
                if div_yield > avg_div_5y:
                    st.success("✅ INFRAVALORADA: Yield actual superior a la media.")
                else:
                    st.error("❌ SOBREVALORADA: Yield actual inferior a la media.")
            
            with c_d2:
                plot_bar_comparison(price, fair_weiss, "Valoración por Dividendos (Weiss)", "Valor Justo (Weiss)")

        else:
            st.info("Esta empresa no paga dividendos o faltan datos históricos para el análisis.")

    # --- TAB 3: MODELOS CLÁSICOS ---
    with tab_models:
        st.subheader("Referencias Rápidas")
        
        # Graham
        bvps = info.get('bookValue', 0)
        val_graham = (22.5 * eps * bvps)**0.5 if (eps>0 and bvps>0) else 0
        
        # Lynch (Snapshot)
        val_lynch = eps * growth_input
        
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            st.markdown("#### Fórmula Benjamin Graham")
            if val_graham > 0:
                st.metric("Valor Graham", f"${val_graham:.2f}", delta=f"{((val_graham-price)/price)*100:.1f}%")
                st.progress(min(val_graham/max(price, val_graham+1), 1.0))
            else:
                st.warning("No aplicable (EPS o Valor en Libros negativo)")
                
        with col_m2:
            st.markdown("#### Valoración Peter Lynch (PEG=1)")
            if val_lynch > 0:
                st.metric("Valor Lynch", f"${val_lynch:.2f}", delta=f"{((val_lynch-price)/price)*100:.1f}%")
                st.progress(min(val_lynch/max(price, val_lynch+1), 1.0))
            else:
                st.warning("No aplicable (EPS negativo)")
