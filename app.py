import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Valuación Pro & Dividendos", layout="wide", page_icon="📊")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f8f9fa; border-radius: 4px 4px 0 0; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-bottom: 2px solid #2c3e50; color: #2c3e50; font-weight: bold;}
    .highlight-div { background-color: #e8f5e9; padding: 10px; border-radius: 5px; border-left: 5px solid #2e7d32; }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTOR DE DATOS Y SCRAPING ---

@st.cache_data(ttl=3600)
def get_stock_basic_info(ticker):
    stock = yf.Ticker(ticker)
    return stock.info

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
                # Buscamos EPS en varias columnas posibles
                for k in ['Diluted EPS', 'Basic EPS', 'DilutedEPS']:
                    if k in latest and pd.notna(latest[k]):
                        eps = latest[k]
                        break
                
                # Si falla, intentamos calcularlo
                if pd.isna(eps):
                    try:
                        ni = latest.get('Net Income Common Stockholders')
                        shares = latest.get('Basic Average Shares')
                        if ni and shares: eps = ni / shares
                    except: pass

                if eps and eps > 0:
                    pe = row['Close'] / eps
                    if 5 < pe < 150: pe_values.append(pe) # Filtro anti-ruido
        
        return np.mean(pe_values) if pe_values else None
    except:
        return None

@st.cache_data(ttl=3600)
def scrape_valueinvesting_io(ticker):
    """Intenta obtener tabla de estimaciones con Headers de navegador real."""
    url = f"https://valueinvesting.io/{ticker}/estimates"
    
    # Headers para simular ser un humano y evitar bloqueo básico (CORS/Bot detection)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            dfs = pd.read_html(response.text)
            for df in dfs:
                # Buscamos la tabla correcta por palabras clave
                if df.apply(lambda x: x.astype(str).str.contains('Growth|Revenue|EPS', case=False)).any().any():
                    return df
    except Exception:
        return None
    return None

# --- 2. COMPONENTES VISUALES ---

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
                {'range': [0, fair], 'color': "#c8e6c9"}, # Verde (Barato)
                {'range': [fair, max(current, fair)*2], 'color': "#ffcdd2"}], # Rojo (Caro)
            'threshold': {'line': {'color': "green", 'width': 3}, 'thickness': 0.8, 'value': fair}
        }
    ))
    fig.update_layout(height=180, margin=dict(l=20,r=20,t=30,b=10))
    st.plotly_chart(fig, use_container_width=True)

# --- 3. INTERFAZ PRINCIPAL ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    
    st.divider()
    st.subheader("🔮 Parámetros de Proyección")
    
    # Scraping Intent
    scraped_df = scrape_valueinvesting_io(ticker)
    if scraped_df is not None:
        st.success("✅ Datos de ValueInvesting conectados")
        with st.expander("Ver Tabla de Estimaciones"):
            st.dataframe(scraped_df)
    else:
        st.info(f"ℹ️ No se pudo extraer la tabla automática (Captcha).")
        st.markdown(f"[👉 Ver ValueInvesting.io Manualmente](https://valueinvesting.io/{ticker}/estimates)")

    growth_input = st.number_input("Crecimiento EPS Estimado (%)", value=12.0, step=0.5, help="Crecimiento anual compuesto para los próximos 5 años.")
    
    st.divider()
    st.subheader("⚙️ Configuración Histórica")
    years_hist = st.slider("Años Historia (Media PER/Div)", 5, 10, 10)

if ticker:
    info = get_stock_basic_info(ticker)
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))

    if not price:
        st.error("Ticker no encontrado.")
        st.stop()

    # --- CÁLCULOS PREVIOS ---
    eps = info.get('trailingEps', 0)
    pe_current = info.get('trailingPE', 0)
    div_yield = info.get('dividendYield', 0) # Ej: 0.03
    avg_div_5y = info.get('fiveYearAvgDividendYield', 0) # Ej: 3.5 (Yahoo suele darlo en %)

    # Normalización de Dividendos (Yahoo es inconsistente)
    if avg_div_5y and avg_div_5y > 1: avg_div_5y = avg_div_5y / 100
    
    # Cálculo PER Histórico
    pe_hist_mean = get_historical_pe_mean(ticker, years=years_hist)
    if pe_hist_mean is None: pe_hist_mean = 15.0 # Fallback si no hay datos

    # --- DASHBOARD SUPERIOR ---
    st.title(f"{info.get('shortName', ticker)}")
    st.caption(f"{info.get('sector')} | {info.get('industry')}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precio Actual", f"${price}")
    m2.metric("EPS (TTM)", f"${eps}")
    
    # Métricas de Dividendos en Dashboard Principal
    delta_div = None
    if div_yield and avg_div_5y:
        delta_div = f"Media 5y: {avg_div_5y*100:.2f}%"
    
    m3.metric("Div. Yield Actual", f"{div_yield*100:.2f}%" if div_yield else "0%", delta=None)
    m4.metric("Media Histórica Div.", f"{avg_div_5y*100:.2f}%" if avg_div_5y else "N/A", 
              delta="Infravalorada (Yield Alto)" if (div_yield and avg_div_5y and div_yield > avg_div_5y) else "Sobrevalorada")

    # --- PESTAÑAS ---
    tab_proj, tab_div, tab_val, tab_data = st.tabs(["🚀 Proyección 5 Años (Calculadora)", "💰 Dividendos (Geraldine Weiss)", "⚖️ Modelos Clásicos", "📉 Gráficos"])

    # TAB 1: PROYECCIÓN 5 AÑOS (SOLICITUD USUARIO: PER FINAL ELEGIBLE)
    with tab_proj:
        st.subheader("Calculadora de Retorno Esperado (5 Años)")
        
        col_p1, col_p2 = st.columns([1, 2])
        
        with col_p1:
            st.markdown("#### 1. Configura tu Escenario")
            g_rate = growth_input
            # EL USUARIO ELIGE EL PER DE SALIDA (Por defecto sugerimos la media histórica)
            exit_pe = st.number_input("PER de Salida (Año 5)", value=float(round(pe_hist_mean, 1)), step=0.5, 
                                     help="¿A qué múltiplo crees que cotizará la acción dentro de 5 años? Por defecto es su media histórica.")
            
            st.markdown("---")
            
            # Cálculos
            future_eps = eps * ((1 + g_rate/100) ** 5)
            future_price = future_eps * exit_pe
            total_return = (future_price / price) - 1
            cagr = ((future_price / price) ** (1/5) - 1) * 100
            
            st.write("Resultados:")
            st.metric("EPS Estimado (Año 5)", f"${future_eps:.2f}")
            st.metric("Precio Objetivo (Año 5)", f"${future_price:.2f}")
            
        with col_p2:
            st.markdown("#### 2. Análisis de Retorno")
            
            color_cagr = "green" if cagr > 10 else "orange" if cagr > 0 else "red"
            st.markdown(f"""
            <div style="text-align:center; padding: 20px; border: 2px solid {color_cagr}; border-radius: 10px; background-color: #fafafa;">
                <h3 style="margin:0; color: #555;">Retorno Anual Compuesto (CAGR)</h3>
                <h1 style="font-size: 60px; color: {color_cagr}; margin: 10px;">{cagr:.2f}%</h1>
                <p>Si compras a <b>${price}</b> y vendes a <b>${future_price:.2f}</b> en 5 años.</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Gráfico de proyección
            years = list(range(datetime.now().year, datetime.now().year + 6))
            prices_proj = [price * ((1 + cagr/100) ** i) for i in range(6)]
            
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=years, y=prices_proj, mode='lines+markers', name='Proyección Precio', line=dict(color='#2980b9', width=4)))
            fig_proj.add_trace(go.Scatter(x=[years[-1]], y=[future_price], mode='markers+text', text=[f"${future_price:.0f}"], textposition="top center", marker=dict(size=12, color='green'), name='Target'))
            fig_proj.update_layout(title="Trayectoria del Precio Teórico", height=300, showlegend=False)
            st.plotly_chart(fig_proj, use_container_width=True)

    # TAB 2: DIVIDENDOS (GERALDINE WEISS)
    with tab_div:
        st.subheader("Teoría de la Rentabilidad por Dividendo (Geraldine Weiss)")
        st.markdown("""
        > *Geraldine Weiss ("La Dama de los Dividendos") sugiere que las acciones "Blue Chip" oscilan entre extremos de rentabilidad. 
        > Cuando la rentabilidad (Yield) es históricamente alta, la acción está barata. Cuando es baja, está cara.*
        """)
        
        if div_yield and avg_div_5y and avg_div_5y > 0:
            div_rate = info.get('dividendRate', 0)
            
            # Valor Justo = Dividendo Actual / Yield Medio Histórico
            fair_value_weiss = div_rate / avg_div_5y
            margin_weiss = ((fair_value_weiss - price) / price) * 100
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("#### Datos de Entrada")
                st.write(f"**Dividendo Anual:** ${div_rate}")
                st.write(f"**Yield Actual:** {div_yield*100:.2f}%")
                st.write(f"**Yield Medio (5-10 años):** {avg_div_5y*100:.2f}%")
                
                if div_yield > avg_div_5y:
                    st.success(f"✅ OPORTUNIDAD: El dividendo actual ({div_yield*100:.2f}%) es superior a su media histórica.")
                else:
                    st.warning(f"⚠️ PRECAUCIÓN: El dividendo actual ({div_yield*100:.2f}%) es inferior a su media histórica.")
            
            with c2:
                st.markdown("#### Valoración Weiss")
                st.metric("Precio Justo (Teórico)", f"${fair_value_weiss:.2f}", delta=f"{margin_weiss:.1f}% Margen")
                render_gauge(price, fair_value_weiss, "Precio vs Valor Justo (Div)")
                
        else:
            st.warning("Esta empresa no paga dividendos suficientes o no tiene historial estable para aplicar el método Weiss.")

    # TAB 3: OTROS MODELOS
    with tab_val:
        st.subheader("Otros Modelos de Referencia")
        
        # 1. Modelo Graham (Revisión Clásica)
        bvps = info.get('bookValue', 0)
        val_graham = (22.5 * eps * bvps)**0.5 if (eps>0 and bvps>0) else 0
        
        # 2. Peter Lynch Fair Value (PEG = 1 Simple)
        # Nota: Lynch dice que un PER justo = Tasa de Crecimiento.
        # Si crece al 15%, debería valer PER 15.
        lynch_fair_pe = growth_input 
        val_lynch = eps * lynch_fair_pe
        
        c_m1, c_m2 = st.columns(2)
        
        with c_m1:
            st.markdown("#### Fórmula de Benjamin Graham")
            st.caption("√(22.5 × EPS × Valor en Libros)")
            if val_graham > 0:
                st.metric("Valor Graham", f"${val_graham:.2f}", delta=f"{((val_graham-price)/price)*100:.1f}%")
                render_gauge(price, val_graham, "Graham")
            else:
                st.write("No aplicable (EPS o BVPS negativos)")
                
        with c_m2:
            st.markdown("#### Valor Justo Instantáneo (Peter Lynch)")
            st.caption(f"Asume PER Justo = Crecimiento ({growth_input}x)")
            st.metric("Valor Lynch", f"${val_lynch:.2f}", delta=f"{((val_lynch-price)/price)*100:.1f}%")
            render_gauge(price, val_lynch, "Lynch (PEG=1)")

    # TAB 4: GRÁFICOS
    with tab_data:
        st.subheader("Evolución Histórica")
        hist_price = stock.history(period="5y")
        
        # Gráfico de Velas
        fig = go.Figure(data=[go.Candlestick(x=hist_price.index,
                        open=hist_price['Open'],
                        high=hist_price['High'],
                        low=hist_price['Low'],
                        close=hist_price['Close'])])
        fig.update_layout(title=f"Cotización {ticker} (5 años)", height=500)
        st.plotly_chart(fig, use_container_width=True)
