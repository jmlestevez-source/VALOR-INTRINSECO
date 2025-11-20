import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro & Dividendos", layout="wide", page_icon="💎")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .highlight-card { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 5px solid #2c3e50; }
    h1, h2, h3 { color: #2c3e50; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE DATOS ROBUSTAS ---

@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """Obtiene el objeto Ticker y su info básica."""
    stock = yf.Ticker(ticker)
    return stock, stock.info

@st.cache_data(ttl=3600)
def get_historical_pe_mean(ticker, years=10):
    """Calcula media PER histórica eliminando outliers."""
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
                # Buscamos EPS
                for k in ['Diluted EPS', 'Basic EPS', 'DilutedEPS']:
                    if k in latest and pd.notna(latest[k]):
                        eps = latest[k]
                        break
                
                # Fallback cálculo manual
                if pd.isna(eps):
                    try:
                        ni = latest.get('Net Income Common Stockholders')
                        shares = latest.get('Basic Average Shares')
                        if ni and shares: eps = ni / shares
                    except: pass

                if eps and eps > 0:
                    pe = row['Close'] / eps
                    if 5 < pe < 150: pe_values.append(pe)
        
        return np.mean(pe_values) if pe_values else None
    except:
        return None

@st.cache_data(ttl=3600)
def scrape_valueinvesting_io(ticker):
    """Intenta obtener tabla de estimaciones evitando bloqueo simple."""
    url = f"https://valueinvesting.io/{ticker}/estimates"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            for df in dfs:
                if df.apply(lambda x: x.astype(str).str.contains('Growth|Revenue|EPS', case=False)).any().any():
                    return df
    except:
        pass
    return None

# --- 2. INTERFAZ ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    
    st.divider()
    st.subheader("🔮 Proyección")
    
    # Scraping
    scraped_df = scrape_valueinvesting_io(ticker)
    if scraped_df is not None:
        st.success("✅ Datos externos conectados")
        with st.expander("Ver Tabla Estimaciones"):
            st.dataframe(scraped_df)
    else:
        st.info("ℹ️ Protección activa en fuente externa.")
        st.markdown(f"[👉 Ver Estimaciones Manualmente](https://valueinvesting.io/{ticker}/estimates)")

    growth_input = st.number_input("Crecimiento EPS Estimado (%)", value=12.0, step=0.5)
    
    st.divider()
    years_hist = st.slider("Años Historia", 5, 10, 10)

if ticker:
    # CORRECCIÓN 1: Inicializamos 'stock' aquí para que esté disponible en todo el script
    stock, info = get_stock_data(ticker)
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))

    if not price:
        st.error("Ticker no encontrado o sin precio.")
        st.stop()

    # --- PREPARACIÓN DE DATOS ---
    eps = info.get('trailingEps', 0)
    pe_hist_mean = get_historical_pe_mean(ticker, years=years_hist)
    
    # CORRECCIÓN 2: Lógica Robusta de Dividendos
    # Yahoo devuelve a veces decimales (0.005) y a veces porcentajes (0.5)
    raw_yield = info.get('dividendYield')
    raw_5y_avg = info.get('fiveYearAvgDividendYield')
    
    # Normalización Yield Actual
    if raw_yield is not None:
        # Si es mayor que 1 (ej. 3.5), asumimos que es porcentaje y lo pasamos a decimal
        # Si es una tech como Google y da > 0.10 (10%), probablemente sea un error de datos (Payout ratio?), lo filtramos
        div_yield_pct = raw_yield * 100 if raw_yield < 1 else raw_yield
    else:
        div_yield_pct = 0.0

    # Normalización Yield 5 años
    if raw_5y_avg is not None:
        avg_div_5y_pct = raw_5y_avg # Yahoo suele dar este en formato 3.45 (porcentaje) directamente
    else:
        avg_div_5y_pct = None

    # --- DASHBOARD ---
    st.title(f"{info.get('shortName', ticker)}")
    st.caption(f"{info.get('sector')} | {info.get('industry')}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precio", f"${price}")
    m2.metric("EPS (TTM)", f"${eps}")
    
    # Mostrar Dividendos (Solo si paga)
    m3.metric("Div. Yield Actual", f"{div_yield_pct:.2f}%")
    
    if avg_div_5y_pct:
        delta_val = div_yield_pct - avg_div_5y_pct
        m4.metric("Media Histórica Div.", f"{avg_div_5y_pct:.2f}%", 
                  delta=f"{delta_val:.2f}% vs Media", delta_color="normal")
    else:
        m4.metric("Media Histórica Div.", "N/A", help="No hay historial suficiente de dividendos (ej. Google/Meta)")

    # --- PESTAÑAS ---
    tab_proj, tab_weiss, tab_models, tab_chart = st.tabs(["🚀 Proyección (5 Años)", "💰 Dividendos (Weiss)", "⚖️ Modelos Valor", "📉 Gráficos"])

    # 1. PROYECCIÓN
    with tab_proj:
        st.subheader("Calculadora de Retorno Futuro")
        col_a, col_b = st.columns([1, 2])
        
        with col_a:
            st.markdown("##### Parámetros")
            # Input del PER de Salida (sugerido: media histórica)
            default_pe = float(pe_hist_mean) if pe_hist_mean else 15.0
            exit_pe = st.number_input("PER de Salida (Año 5)", value=round(default_pe, 1), step=0.5,
                                     help="Múltiplo al que crees que cotizará en el futuro.")
            
            # Cálculos
            future_eps = eps * ((1 + growth_input/100) ** 5)
            future_price = future_eps * exit_pe
            cagr = ((future_price / price) ** (1/5) - 1) * 100
            
            st.divider()
            st.metric("Precio Objetivo (2029)", f"${future_price:.2f}")
            st.metric("EPS Estimado (2029)", f"${future_eps:.2f}")

        with col_b:
            st.markdown("##### Retorno Anualizado (CAGR)")
            color = "green" if cagr > 10 else "orange" if cagr > 0 else "red"
            st.markdown(f"""
                <div style="background-color:white; border: 2px solid {color}; border-radius:10px; padding:20px; text-align:center;">
                    <h2 style="color:{color}; font-size:40px; margin:0;">{cagr:.2f}%</h2>
                    <p style="color:gray;">Retorno anual compuesto esperado</p>
                </div>
            """, unsafe_allow_html=True)
            
            # Gráfico Proyección
            years = list(range(datetime.now().year, datetime.now().year + 6))
            values = [price * ((1 + cagr/100) ** i) for i in range(6)]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=years, y=values, mode='lines+markers', line=dict(color='#2c3e50', width=3), name='Proyección'))
            fig.update_layout(height=250, margin=dict(l=20,r=20,t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

    # 2. DIVIDENDOS (WEISS)
    with tab_weiss:
        st.subheader("Yield Theory (Geraldine Weiss)")
        
        if div_yield_pct > 0 and avg_div_5y_pct is not None:
            div_rate = info.get('dividendRate', 0)
            
            # Fórmula Weiss: Precio Justo = Dividendo / Yield Medio Histórico
            # Ojo: avg_div_5y_pct está en formato 3.5, hay que dividir por 100 para cálculo matemático
            fair_yield_decimal = avg_div_5y_pct / 100
            
            if fair_yield_decimal > 0:
                fair_value_weiss = div_rate / fair_yield_decimal
                margin = ((fair_value_weiss - price) / price) * 100
                
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"La acción paga **${div_rate}** al año.")
                    if div_yield_pct > avg_div_5y_pct:
                        st.success(f"✅ **INFRAVALORADA:** Rentabilidad actual ({div_yield_pct:.2f}%) > Media ({avg_div_5y_pct:.2f}%).")
                    else:
                        st.warning(f"⚠️ **SOBREVALORADA:** Rentabilidad actual ({div_yield_pct:.2f}%) < Media ({avg_div_5y_pct:.2f}%).")
                
                with c2:
                    st.metric("Valor Justo (Teoría Weiss)", f"${fair_value_weiss:.2f}", delta=f"{margin:.1f}% Margen")
            else:
                st.error("Error en datos de yield medio.")
        else:
            st.warning(f"El modelo Weiss no es aplicable a {ticker}. Requiere historial de dividendos establecido (media 5 años). Google o Meta son demasiado nuevas en dividendos.")

    # 3. OTROS MODELOS
    with tab_models:
        st.subheader("Instantáneas de Valor")
        
        bvps = info.get('bookValue', 0)
        
        # Graham
        val_graham = (22.5 * eps * bvps)**0.5 if (eps>0 and bvps>0) else 0
        
        # Lynch (Simplificado: Fair PE = Growth)
        val_lynch = eps * growth_input
        
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            st.markdown("**Fórmula Benjamin Graham**")
            st.caption("Para empresas defensivas/industriales")
            if val_graham > 0:
                st.metric("Valor Graham", f"${val_graham:.2f}", delta=f"{((val_graham-price)/price)*100:.1f}%")
            else:
                st.write("N/A (Datos negativos)")
        
        with c_m2:
            st.markdown("**Regla del Pulgar (Peter Lynch)**")
            st.caption(f"Si crece al {growth_input}%, 'merece' PER {growth_input}x")
            st.metric("Valor Lynch", f"${val_lynch:.2f}", delta=f"{((val_lynch-price)/price)*100:.1f}%")

    # 4. GRÁFICOS (CORREGIDO)
    with tab_chart:
        st.subheader("Evolución del Precio")
        # CORRECCIÓN 3: Usamos 'stock' que ya está definido globalmente
        hist_price = stock.history(period="5y")
        
        fig = go.Figure(data=[go.Candlestick(x=hist_price.index,
                        open=hist_price['Open'],
                        high=hist_price['High'],
                        low=hist_price['Low'],
                        close=hist_price['Close'])])
        fig.update_layout(height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True) # Warning arreglado usando la versión estándar
