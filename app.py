import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Inteligente de Acciones", layout="wide", page_icon="📈")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .big-font { font-size: 20px !important; }
    .metric-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #d6d6d6;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIONES DE CÁLCULO (CON CACHÉ PARA VELOCIDAD) ---

@st.cache_data(ttl=3600) # Guarda datos en memoria 1 hora para ir rápido
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    return stock, stock.info

@st.cache_data(ttl=3600)
def get_historical_pe(ticker, years=10):
    """Calcula la media real del PER cruzando precios mensuales con reportes anuales."""
    try:
        stock = yf.Ticker(ticker)
        # Pedimos un poco más de tiempo para asegurar datos de inicio
        start_date = (datetime.now() - timedelta(days=years*365 + 180)).strftime('%Y-%m-%d')
        
        # Historial de precios mensual
        hist = stock.history(start=start_date, interval="1mo")
        if hist.empty: return None

        # Limpiar zonas horarias
        if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)

        # Datos financieros (EPS)
        financials = stock.financials.T
        if financials.empty: return None
        
        financials.index = pd.to_datetime(financials.index)
        if financials.index.tz is not None: financials.index = financials.index.tz_localize(None)
        financials = financials.sort_index()

        pe_values = []
        
        for date, row in hist.iterrows():
            # Buscar el reporte financiero vigente en esa fecha
            past_reports = financials[financials.index <= date]
            if not past_reports.empty:
                latest = past_reports.iloc[-1]
                
                # Lógica robusta para encontrar el EPS
                eps = np.nan
                # Intentamos varias claves comunes en Yahoo
                keys = ['Diluted EPS', 'Basic EPS', 'DilutedEPS']
                for k in keys:
                    if k in latest and pd.notna(latest[k]):
                        eps = latest[k]
                        break
                
                # Cálculo manual si falla la columna directa
                if pd.isna(eps):
                    try:
                        ni = latest.get('Net Income Common Stockholders')
                        shares = latest.get('Basic Average Shares')
                        if ni and shares: eps = ni / shares
                    except: pass

                # Solo calculamos PER si el EPS es positivo y tiene sentido
                if eps and eps > 0:
                    pe = row['Close'] / eps
                    if 0 < pe < 200: # Filtramos anomalías extremas
                        pe_values.append(pe)
        
        if not pe_values: return None
        return np.mean(pe_values)
    except Exception as e:
        return None

def create_gauge_chart(current_value, fair_value, title):
    fig = go.Figure(go.Indicator(
        mode = "number+gauge+delta",
        value = current_value,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title},
        delta = {'reference': fair_value, 'relative': True, 'valueformat': '.1%'},
        gauge = {
            'axis': {'range': [min(current_value, fair_value)*0.5, max(current_value, fair_value)*1.5]},
            'bar': {'color': "black"},
            'steps': [
                {'range': [0, fair_value], 'color': "#d4edda"}, # Verde claro (Barato)
                {'range': [fair_value, max(current_value, fair_value)*2], 'color': "#f8d7da"}], # Rojo claro (Caro)
            'threshold': {
                'line': {'color': "green", 'width': 4},
                'thickness': 0.75,
                'value': fair_value}
        }
    ))
    fig.update_layout(height=250, margin=dict(l=20,r=20,t=40,b=20))
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔍 Configuración de Análisis")
    ticker_input = st.text_input("Ticker (Yahoo Finance)", value="GOOGL").upper()
    years_hist = st.slider("Años para Media Histórica", 5, 10, 10)
    
    st.divider()
    st.subheader("📊 Estimaciones Futuras")
    
    # Enlace inteligente a ValueInvesting.io
    vi_link = f"https://valueinvesting.io/{ticker_input}/estimates"
    st.info(f"💡 Como las fuentes gratuitas protegen sus datos de predicción, revisa la estimación aquí y ajústala abajo:\n\n[👉 Ver Estimaciones de {ticker_input}]({vi_link})")
    
    growth_input = st.number_input("Crecimiento EPS Estimado (5 años) %", 
                                   min_value=0.0, max_value=100.0, value=12.0, step=0.5,
                                   help="Introduce el 'EPS Growth' medio esperado para los próximos años.")

    st.divider()
    st.caption("Desarrollado con Python & Streamlit")

# --- MAIN APP ---

if ticker_input:
    try:
        stock, info = get_stock_data(ticker_input)
        price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
        
        if not price:
            st.error("No se pudo obtener la cotización actual. Verifica el ticker.")
            st.stop()

        # ENCABEZADO
        st.title(f"{info.get('shortName', ticker_input)}")
        st.markdown(f"**Sector:** {info.get('sector', 'N/A')} | **Industria:** {info.get('industry', 'N/A')} | **País:** {info.get('country', 'N/A')}")
        
        # MÉTRICAS TOP
        m1, m2, m3 = st.columns(3)
        m1.metric("Precio Actual", f"${price}", delta=None)
        
        beta = info.get('beta', 'N/A')
        m2.metric("Beta (Volatilidad)", f"{beta:.2f}" if isinstance(beta, (int, float)) else beta)
        
        mcap = info.get('marketCap', 0)
        m3.metric("Capitalización", f"${mcap/1e9:.1f} B")

        # PESTAÑAS DE ANÁLISIS
        tab_val, tab_div, tab_data = st.tabs(["💎 Valoración (PER & Crecimiento)", "💸 Dividendos (Yield Theory)", "📉 Gráficos"])

        # --- PESTAÑA 1: VALORACIÓN PER ---
        with tab_val:
            st.subheader("Análisis de Valor Intrínseco (Método PER Histórico)")
            
            # Cálculos
            eps_ttm = info.get('trailingEps', 0)
            pe_current = info.get('trailingPE', 0)
            
            with st.spinner(f'Calculando la media de PER real de los últimos {years_hist} años...'):
                pe_historical = get_historical_pe(ticker_input, years=years_hist)

            if pe_historical and eps_ttm > 0:
                # Fórmulas
                fair_value_hist = eps_ttm * pe_historical
                margin_safety = ((fair_value_hist - price) / price) * 100
                
                # Proyección a 5 años
                # Valor Futuro = EPS Actual * (1+Crecimiento)^5 * PER Histórico
                future_eps = eps_ttm * ((1 + growth_input/100) ** 5)
                future_stock_price = future_eps * pe_historical
                # Retorno esperado (CAGR)
                cagr = ((future_stock_price / price) ** (1/5) - 1) * 100

                # --- VISUALIZACIÓN ---
                col_v1, col_v2 = st.columns([1, 2])
                
                with col_v1:
                    st.markdown("#### 1. Valoración Histórica (Actual)")
                    st.write(f"Si la acción vuelve a su PER medio de **{pe_historical:.1f}x**:")
                    st.metric("Valor Razonable Hoy", f"${fair_value_hist:.2f}", delta=f"{margin_safety:.1f}% Margen")
                    
                    st.divider()
                    
                    st.markdown("#### 2. Proyección a 5 Años")
                    st.write(f"Asumiendo crecimiento del **{growth_input}%**:")
                    st.metric("Precio Objetivo (2029)", f"${future_stock_price:.2f}")
                    st.metric("Retorno Anual Esperado", f"{cagr:.1f}%")

                with col_v2:
                    st.plotly_chart(create_gauge_chart(price, fair_value_hist, "Precio Actual vs Valor Histórico"), use_container_width=True)
                    
                    # Tabla Comparativa
                    st.markdown("##### 📋 Tabla de Datos")
                    val_df = pd.DataFrame({
                        'Métrica': ['EPS (Beneficio/Acción)', 'PER Actual', 'PER Medio Histórico'],
                        'Valor': [f"${eps_ttm:.2f}", f"{pe_current:.2f}x", f"{pe_historical:.2f}x"]
                    })
                    st.table(val_df)

            else:
                st.warning("⚠️ No se pudo realizar la valoración por PER. La empresa puede tener pérdidas (EPS negativo) o faltan datos históricos.")

        # --- PESTAÑA 2: DIVIDENDOS ---
        with tab_div:
            st.subheader("Teoría de la Rentabilidad por Dividendo")
            
            div_yield = info.get('dividendYield', 0)
            div_yield_5y = info.get('fiveYearAvgDividendYield', 0)
            div_rate = info.get('dividendRate', 0) # Dinero contante y sonante por acción

            if div_yield and div_yield_5y and div_rate:
                # Normalización de datos (Yahoo a veces da 3.5 y a veces 0.035)
                if div_yield_5y > 1: div_yield_5y = div_yield_5y / 100
                
                # Precio Justo por Dividendos = Dividendo Anual / Yield Medio Histórico
                if div_yield_5y > 0:
                    fair_value_div = div_rate / div_yield_5y
                    margin_div = ((fair_value_div - price) / price) * 100
                    
                    c_d1, c_d2 = st.columns(2)
                    
                    with c_d1:
                        st.markdown("#### 📊 Comparativa de Rentabilidad")
                        st.metric("Rentabilidad (Yield) Actual", f"{div_yield*100:.2f}%")
                        st.metric("Rentabilidad Media (5 años)", f"{div_yield_5y*100:.2f}%", 
                                  delta="Mejor que la media" if div_yield > div_yield_5y else "Peor que la media")
                        st.info(f"La empresa paga **${div_rate}** por acción al año.")

                    with c_d2:
                        st.markdown("#### 🎯 Valoración")
                        st.write("Si la rentabilidad vuelve a su media histórica:")
                        st.metric("Precio Objetivo (Dividendos)", f"${fair_value_div:.2f}", delta=f"{margin_div:.1f}% Margen")
                        st.plotly_chart(create_gauge_chart(price, fair_value_div, "Valuación por Dividendos"), use_container_width=True)
                else:
                    st.warning("Datos insuficientes para calcular la media histórica del dividendo.")
            else:
                st.info("Esta empresa no parece pagar dividendos regulares o faltan datos en Yahoo Finance.")

        # --- PESTAÑA 3: GRÁFICOS ---
        with tab_data:
            st.subheader("Evolución del Precio (5 Años)")
            hist_price = stock.history(period="5y")
            st.line_chart(hist_price['Close'])
            
            with st.expander("Ver Datos Fundamentales Raw"):
                st.json({k:v for k,v in info.items() if k in ['totalRevenue', 'netIncomeToCommon', 'totalDebt', 'operatingCashflow']})

    except Exception as e:
        st.error(f"Error inesperado: {e}")

else:
    st.info("👈 Introduce un ticker en el menú lateral para comenzar.")
