import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Master Valuation App", layout="wide", page_icon="💎")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e9ecef; }
    h1, h2, h3 { color: #2c3e50; }
    .highlight { color: #27ae60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE DATOS (CORREGIDAS Y CACHEABLES) ---

@st.cache_data(ttl=3600)
def get_fundamental_data(ticker):
    """Obtiene datos fundamentales sin guardar el objeto Ticker entero."""
    stock = yf.Ticker(ticker)
    return stock.info

@st.cache_data(ttl=3600)
def get_historical_pe_data(ticker, years=10):
    """Calcula la media del PER histórico."""
    try:
        stock = yf.Ticker(ticker)
        start_date = (datetime.now() - timedelta(days=years*365 + 180)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        
        if hist.empty: return None

        # Limpieza de zona horaria (Fix del error anterior)
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
                # Extracción robusta de EPS
                eps = np.nan
                for key in ['Diluted EPS', 'Basic EPS', 'DilutedEPS']:
                    if key in latest and pd.notna(latest[key]):
                        eps = latest[key]
                        break
                
                if pd.isna(eps) or eps <= 0: continue
                
                pe = row['Close'] / eps
                if 0 < pe < 200: pe_values.append(pe) # Filtrar ruido
        
        if not pe_values: return None
        return np.mean(pe_values)
    except:
        return None

@st.cache_data(ttl=3600)
def try_scrape_growth(ticker):
    """Intenta extraer la tabla de crecimiento de valueinvesting.io."""
    url = f"https://valueinvesting.io/{ticker}/estimates"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        # Nota: Pandas read_html busca tablas en el HTML
        dfs = pd.read_html(url, header=0)
        # Buscamos la tabla que tenga "Revenue Growth" o "EPS Growth"
        for df in dfs:
            if 'EPS Growth' in df.columns or (df.iloc[:, 0].astype(str).str.contains("EPS Growth").any()):
                # Limpieza básica si la encuentra
                return df
    except:
        return None # Si falla por captcha, devolvemos None silenciosamente
    return None

# --- 2. FUNCIONES DE VISUALIZACIÓN ---

def draw_gauge(current, fair, title):
    """Dibuja un velocímetro comparando precio actual vs valor justo."""
    fig = go.Figure(go.Indicator(
        mode = "number+gauge+delta",
        value = current,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title, 'font': {'size': 16}},
        delta = {'reference': fair, 'relative': True, 'valueformat': '.1%'},
        gauge = {
            'axis': {'range': [min(current, fair)*0.6, max(current, fair)*1.4]},
            'bar': {'color': "#2c3e50"},
            'steps': [
                {'range': [0, fair], 'color': "#d4edda"},
                {'range': [fair, max(current, fair)*1.5], 'color': "#f8d7da"}],
            'threshold': {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': fair}
        }
    ))
    fig.update_layout(height=200, margin=dict(l=30, r=30, t=40, b=10))
    return fig

# --- 3. INTERFAZ DE USUARIO ---

with st.sidebar:
    st.header("🔎 Panel de Control")
    ticker = st.text_input("Ticker (ej. GOOGL, META)", value="META").upper()
    
    st.divider()
    st.subheader("⚙️ Parámetros de Crecimiento")
    
    # Intentar scraping automático
    scraped_data = try_scrape_growth(ticker)
    default_growth = 12.0
    
    if scraped_data is not None:
        st.success("✅ Datos de valueinvesting.io detectados")
        # Aquí podrías procesar el DF para sacar la media, pero por seguridad mostramos tabla
    else:
        st.info("ℹ️ Conexión directa bloqueada por Captcha. Usa el enlace:")
        
    st.markdown(f"[🔗 Ver Estimaciones Oficiales](https://valueinvesting.io/{ticker}/estimates)")
    
    growth_rate = st.number_input("Crecimiento EPS Estimado (5 años) %", 
                                 value=default_growth, min_value=0.0, max_value=100.0, step=0.5)
    
    years_hist = st.slider("Años historia PER", 5, 10, 10)

# --- LÓGICA PRINCIPAL ---

if ticker:
    # 1. Cargar Datos
    info = get_fundamental_data(ticker)
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    
    if not price:
        st.error("Ticker no encontrado.")
        st.stop()

    # Variables clave
    eps = info.get('trailingEps', 0)
    bvps = info.get('bookValue', 0) # Valor en libros por acción
    pe_current = info.get('trailingPE', 0)
    
    # Header
    st.title(f"{info.get('shortName', ticker)}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio", f"${price}")
    col2.metric("EPS (TTM)", f"${eps}")
    col3.metric("PER Actual", f"{pe_current:.2f}x" if pe_current else "N/A")
    col4.metric("Beta", f"{info.get('beta', 'N/A')}")

    # --- PESTAÑAS DE ANÁLISIS ---
    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Valoración Múltiple", "📈 Crecimiento & Lynch", "💵 Dividendos", "🔎 Graham"])

    # TAB 1: RESUMEN DE VALORACIONES
    with tab1:
        st.subheader("Comparativa de Modelos de Valoración")
        
        # A. PER Histórico
        avg_pe = get_historical_pe_data(ticker, years=years_hist)
        val_pe = eps * avg_pe if (avg_pe and eps > 0) else 0
        
        # B. Peter Lynch (Fair Value = Growth * EPS)
        # Lynch decía que un PER justo es igual a su tasa de crecimiento (PEG = 1)
        val_lynch = growth_rate * eps if (eps > 0) else 0
        
        # C. Fórmula de Graham (Raíz de 22.5 * EPS * BookValue)
        val_graham = 0
        if eps > 0 and bvps > 0:
            val_graham = (22.5 * eps * bvps) ** 0.5

        # Mostrar Resultados
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.markdown("#### 1. Histórica (PER)")
            if val_pe > 0:
                st.plotly_chart(draw_gauge(price, val_pe, f"Obj: ${val_pe:.2f}"), use_container_width=True)
                st.caption(f"Basado en PER medio de {avg_pe:.1f}x")
            else:
                st.warning("Datos insuficientes")

        with c2:
            st.markdown("#### 2. Crecimiento (Lynch)")
            if val_lynch > 0:
                st.plotly_chart(draw_gauge(price, val_lynch, f"Obj: ${val_lynch:.2f}"), use_container_width=True)
                st.caption(f"Asume que PER Justo = Crecimiento ({growth_rate}x)")
            else:
                st.warning("Requiere EPS positivo")

        with c3:
            st.markdown("#### 3. Valor (Graham)")
            if val_graham > 0:
                st.plotly_chart(draw_gauge(price, val_graham, f"Obj: ${val_graham:.2f}"), use_container_width=True)
                st.caption("Fórmula clásica: √(22.5 × EPS × BVPS)")
            else:
                st.warning("Requiere beneficios y valor contable positivos")

        # Tabla Resumen
        st.markdown("---")
        models_df = pd.DataFrame({
            'Modelo': ['Media Histórica', 'Peter Lynch (Crecimiento)', 'Benjamin Graham (Activos)'],
            'Precio Objetivo': [val_pe, val_lynch, val_graham],
            'Margen Seguridad': [
                f"{((val_pe-price)/price)*100:.1f}%" if val_pe else "-",
                f"{((val_lynch-price)/price)*100:.1f}%" if val_lynch else "-",
                f"{((val_graham-price)/price)*100:.1f}%" if val_graham else "-"
            ]
        })
        st.table(models_df)

    # TAB 2: DETALLE CRECIMIENTO
    with tab2:
        st.subheader("Análisis de Proyección a 5 Años")
        
        col_input, col_graph = st.columns([1, 2])
        with col_input:
            st.write(f"Usando un crecimiento anual del **{growth_rate}%** y retornando a un PER de **{avg_pe if avg_pe else 15:.1f}x**:")
            
            future_eps = eps * ((1 + growth_rate/100) ** 5)
            future_price = future_eps * (avg_pe if avg_pe else 15)
            cagr = ((future_price/price)**(1/5) - 1) * 100
            
            st.info(f"EPS en 2029: **${future_eps:.2f}**")
            st.success(f"Precio Objetivo 2029: **${future_price:.2f}**")
            st.metric("Retorno Anual Esperado (CAGR)", f"{cagr:.2f}%")

        with col_graph:
            # Gráfico de linea proyectada
            years = list(range(datetime.now().year, datetime.now().year + 6))
            eps_proj = [eps * ((1 + growth_rate/100) ** i) for i in range(6)]
            
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=years, y=eps_proj, mode='lines+markers', name='EPS Proyectado', line=dict(color='green', width=3)))
            fig_proj.update_layout(title="Crecimiento de Beneficios Estimado", xaxis_title="Año", yaxis_title="EPS ($)")
            st.plotly_chart(fig_proj, use_container_width=True)
            
            if scraped_data is not None:
                st.write("📊 **Datos extraídos de ValueInvesting.io:**")
                st.dataframe(scraped_data)

    # TAB 3: DIVIDENDOS
    with tab3:
        st.subheader("Yield Theory (Reversión a la Media)")
        curr_yield = info.get('dividendYield', 0)
        avg_yield = info.get('fiveYearAvgDividendYield', 0)
        
        if curr_yield and avg_yield:
            # Normalizar (a veces viene en % a veces en decimal)
            if avg_yield > 1: avg_yield /= 100
            
            rate = info.get('dividendRate', 0)
            fair_div = rate / avg_yield if avg_yield > 0 else 0
            
            c1, c2 = st.columns(2)
            c1.metric("Rentabilidad Actual", f"{curr_yield*100:.2f}%")
            c1.metric("Rentabilidad Media (5y)", f"{avg_yield*100:.2f}%")
            
            c2.metric("Precio Objetivo (Dividendos)", f"${fair_div:.2f}", delta=f"{((fair_div-price)/price)*100:.1f}%")
            st.plotly_chart(draw_gauge(price, fair_div, "Valoración por Dividendos"), use_container_width=True)
        else:
            st.warning("Esta empresa no paga dividendos o faltan datos históricos.")

    # TAB 4: GRAHAM
    with tab4:
        st.markdown("""
        > *"El inversor inteligente es un realista que vende a optimistas y compra a pesimistas."* - Benjamin Graham
        """)
        st.write(f"El Número de Graham mide el valor fundamental basándose en ganancias y activos tangibles.")
        
        col_g1, col_g2 = st.columns(2)
        col_g1.metric("Valor en Libros (BVPS)", f"${bvps}")
        col_g1.metric("EPS", f"${eps}")
        
        col_g2.metric("Número de Graham", f"${val_graham:.2f}", delta=f"{((val_graham-price)/price)*100:.1f}% Margen")
        
        st.info("Nota: Este modelo es muy conservador y funciona mejor para empresas industriales/financieras estables, no tecnológicas de alto crecimiento.")

else:
    st.info("👈 Introduce un Ticker en el menú de la izquierda para comenzar.")
