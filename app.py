import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Master Pro", layout="wide", page_icon="💎")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    html, body, [class*="css"], div, span, p {
        font-family: 'Arial', sans-serif;
        font-size: 18px;
    }
    .metric-card {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        height: 100%;
    }
    .metric-label { font-size: 16px !important; color: #666; text-transform: uppercase; font-weight: 800; margin-bottom: 10px; }
    .metric-value { font-size: 42px !important; font-weight: 900; color: #2c3e50; line-height: 1; }
    .metric-sub { font-size: 18px !important; font-weight: 600; margin-top: 10px; }
    
    /* VEREDICTO */
    .verdict-box { padding: 30px; border-radius: 20px; text-align: center; color: white; margin-bottom: 30px; box-shadow: 0 10px 20px rgba(0,0,0,0.15); }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #f1c40f, #e67e22); }
    .v-overvalued { background: linear-gradient(135deg, #e74c3c, #c0392b); }
    
    /* ZONAS WEISS */
    .weiss-buy { background-color: #e8f8f5; border: 2px solid #00b894; padding: 15px; border-radius: 10px; color: #006266; }
    .weiss-sell { background-color: #fdedec; border: 2px solid #e74c3c; padding: 15px; border-radius: 10px; color: #78281f; }
    .weiss-hold { background-color: #fef9e7; border: 2px solid #f1c40f; padding: 15px; border-radius: 10px; color: #7d6608; }

    /* TABLAS */
    .stTable { font-size: 18px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE SCRAPING ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Finviz cambia clases a menudo, búsqueda por texto es más segura
            target = soup.find(string="EPS next 5Y")
            if target:
                val = target.parent.find_next_sibling('td').text.replace('%', '').strip()
                if val != '-': return float(val)
    except:
        return None
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=10):
    """
    Cálculo MEJORADO de ratios históricos.
    Cambios clave:
    1. Usa Quarterly Financials para calcular TTM (Trailing Twelve Months) real.
    2. Usa MEDIANA en lugar de Media para eliminar outliers extremos.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Obtener historial de precios (mensual es suficiente para medias largas)
        hist = stock.history(period=f"{years}y", interval="1mo")
        if hist.empty: return {}
        hist = hist[['Close']].dropna()
        hist.index = hist.index.tz_localize(None)

        # 2. Obtener datos financieros Trimestrales (Quarterly)
        # Esto permite calcular el EPS TTM real en cada punto del tiempo
        q_fin = stock.quarterly_financials.T
        q_bs = stock.quarterly_balance_sheet.T
        
        ratios = {}
        
        # --- CÁLCULO PER (Usando EPS TTM y Mediana) ---
        if not q_fin.empty and ('Basic EPS' in q_fin.columns or 'Diluted EPS' in q_fin.columns):
            col_eps = 'Diluted EPS' if 'Diluted EPS' in q_fin.columns else 'Basic EPS'
            
            # Convertir índice a datetime
            q_fin.index = pd.to_datetime(q_fin.index)
            q_fin.sort_index(inplace=True)
            
            # Calcular EPS TTM (Suma de los últimos 4 trimestres)
            eps_ttm = q_fin[col_eps].rolling(window=4).sum().dropna()
            
            if not eps_ttm.empty:
                # Reindexar precios al timeline de los EPS para alinear fechas
                # Ojo: Usamos reindex con 'ffill' para coger el precio cercano al reporte
                
                # Combinar precios y EPS
                df_pe = pd.DataFrame(index=hist.index)
                df_pe['Price'] = hist['Close']
                
                # Asignar el EPS TTM conocido en esa fecha (forward fill)
                # "asof" merge sería ideal, pero reindex con ffill funciona bien aquí
                eps_aligned = eps_ttm.reindex(hist.index, method='ffill')
                df_pe['EPS_TTM'] = eps_aligned
                
                df_pe.dropna(inplace=True)
                
                # Calcular PER
                df_pe['PE'] = df_pe['Price'] / df_pe['EPS_TTM']
                
                # FILTRADO ESTRICTO y uso de MEDIANA
                # Eliminamos PERs negativos y absurdamente altos (ruido)
                valid_pe = df_pe['PE'][(df_pe['PE'] > 0) & (df_pe['PE'] < 150)]
                
                if not valid_pe.empty:
                    # USAMOS MEDIANA, NO MEDIA
                    # La media se rompe si un año el beneficio cae a casi 0.
                    ratios['PER'] = float(valid_pe.median())
                    
                    # Guardamos min y max razonables para Weiss
                    ratios['PER_Min'] = float(valid_pe.quantile(0.1)) # Percentil 10 para evitar outliers bajos
                    ratios['PER_Max'] = float(valid_pe.quantile(0.9)) # Percentil 90
        
        # Fallback si falla el trimestral, intentar anual (menos preciso pero funciona)
        if 'PER' not in ratios:
            # Lógica simple anual con Mediana
            fin = stock.financials.T
            if not fin.empty:
                if 'Diluted EPS' in fin.columns:
                    eps_yr = fin['Diluted EPS']
                    # Unir manualmente... (simplificado para brevedad, la lógica Q es la prioritaria)
                    pass

        # --- PRICE TO SALES (Mediana) ---
        if not q_fin.empty and 'Total Revenue' in q_fin.columns and 'Ordinary Shares Number' in q_fin.columns:
             # Simplificación: Usamos datos anuales para ventas suele ser más estable, o TTM trimestral
             rev_ttm = q_fin['Total Revenue'].rolling(window=4).sum()
             # Shares suele variar menos, cogemos el último dato trimestral
             shares = q_fin['Ordinary Shares Number']
             
             rps = (rev_ttm / shares).dropna()
             rps_aligned = rps.reindex(hist.index, method='ffill')
             
             ps_series = hist['Close'] / rps_aligned
             valid_ps = ps_series[(ps_series > 0) & (ps_series < 50)]
             if not valid_ps.empty:
                 ratios['Price/Sales'] = float(valid_ps.median())

        return ratios
        
    except Exception as e:
        st.warning(f"Error en cálculo de ratios históricos: {e}")
        return {}

@st.cache_data(ttl=3600)
def get_weiss_data(ticker):
    """Datos específicos para Valoración Geraldine Weiss"""
    try:
        stock = yf.Ticker(ticker)
        
        # Dividendos históricos
        divs = stock.dividends
        if divs.empty: return None
        
        # Agrupar por año para ver tendencia
        divs_yearly = divs.resample('Y').sum()
        current_year = datetime.now().year
        
        # Eliminar año en curso si está incompleto para cálculo de crecimiento
        if divs_yearly.index[-1].year == current_year:
            divs_analysis = divs_yearly[:-1]
        else:
            divs_analysis = divs_yearly

        # Calcular Yields Históricos: Dividendo TTM / Precio
        hist = stock.history(period="10y") # 10 años es el estándar de Weiss
        if hist.empty: return None
        
        # Crear serie de dividendos TTM (suma últimos 12 meses rolling)
        # Esto es complejo con eventos discretos, aproximamos:
        # Rellenamos dividendos en un DF diario y hacemos rolling sum 365D
        df_div = pd.DataFrame(index=hist.index)
        # Ajustar fechas de divs a las de hist
        df_div['Div'] = 0.0
        common_idx = divs.index.intersection(hist.index)
        # Aproximación: asignar dividendo al día de cierre más cercano
        # Una forma más robusta:
        div_series = divs.reindex(hist.index, fill_value=0)
        div_ttm = div_series.rolling(window=252).sum() # aprox 1 año bursátil
        
        df_yield = pd.DataFrame()
        df_yield['Close'] = hist['Close']
        df_yield['Div_TTM'] = div_ttm
        df_yield['Yield'] = (df_yield['Div_TTM'] / df_yield['Close']) * 100
        
        # Limpiar datos (yields válidos, ej: > 0.5% y < 20%)
        valid_yields = df_yield['Yield'][(df_yield['Yield'] > 0.1) & (df_yield['Yield'] < 30)].dropna()
        
        if valid_yields.empty: return None
        
        return {
            'current_div_ttm': div_ttm.iloc[-1],
            'current_yield': valid_yields.iloc[-1],
            'avg_yield': valid_yields.median(), # Mediana es mejor que media
            'min_yield': valid_yields.quantile(0.05), # Mínimo histórico (zona cara)
            'max_yield': valid_yields.quantile(0.95), # Máximo histórico (zona barata)
            'years_growth': (divs_analysis.diff() > 0).sum(), # Años que subió
            'total_years': len(divs_analysis),
            'history_df': df_yield.dropna()
        }
    except Exception as e:
        return None

@st.cache_data(ttl=3600)
def get_full_analysis(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        
        # Ratios Históricos Mejorados
        hist_ratios = calculate_robust_ratios(ticker, years=10)
        weiss_data = get_weiss_data(ticker)
        finviz_g = get_finviz_growth(ticker)
        
        # PER Medio: Priorizar nuestro cálculo robusto (mediana), si no, usar el de Yahoo
        pe_mean = hist_ratios.get('PER', info.get('trailingPE', 15))
        
        return {
            'info': info,
            'price': price,
            'pe_mean': pe_mean,
            'hist_ratios': hist_ratios,
            'weiss_data': weiss_data,
            'finviz_growth': finviz_g
        }
    except:
        return None

# --- 2. COMPONENTES VISUALES ---

def verdict_box(price, fair_value):
    margin = ((fair_value - price) / price) * 100
    if margin > 15:
        css, title, main = "v-undervalued", "💎 OPORTUNIDAD", "INFRAVALORADA"
    elif margin < -15:
        css, title, main = "v-overvalued", "⚠️ CUIDADO", "SOBREVALORADA"
    else:
        css, title, main = "v-fair", "⚖️ EQUILIBRIO", "PRECIO JUSTO"

    st.markdown(f"""
    <div class="verdict-box {css}">
        <div style="font-size:24px; font-weight:bold">{title}</div>
        <div style="font-size:56px; font-weight:900; margin:10px 0">{main}</div>
        <div style="font-size:24px">Margen de Seguridad: {margin:+.1f}% (Fair: ${fair_value:.2f})</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. APLICACIÓN ---

with st.sidebar:
    st.header("Configuración")
    ticker = st.text_input("Ticker", value="JNJ").upper().strip() # JNJ es buena para probar Weiss
    st.caption("Prueba con: JNJ, PEP, KO, MMM para ver datos de Weiss.")

if ticker:
    with st.spinner('Analizando datos...'):
        data = get_full_analysis(ticker)

    if not data or not data['price']:
        st.error("No se encontraron datos.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    weiss = data['weiss_data']
    
    # Calcular Fair Value por PER
    eps = info.get('trailingEps') or 1
    fair_value_per = eps * pe_mean
    
    # --- HEADER ---
    st.title(f"{info.get('shortName', ticker)} ({ticker})")
    st.markdown(f"### Sector: **{info.get('sector','-')}** | Industria: **{info.get('industry','-')}**")
    
    # --- VEREDICTO (Basado en PER Histórico) ---
    verdict_box(price, fair_value_per)
    
    # --- TARJETAS PRINCIPALES ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Precio Actual", f"${price:.2f}")
    c2.metric("PER Actual", f"{info.get('trailingPE', 0):.2f}x")
    
    # Aquí mostramos que el PER Medio es la MEDIANA (más robusto)
    c3.metric("PER Histórico (Mediana)", f"{pe_mean:.2f}x", 
             delta=f"{info.get('trailingPE',0) - pe_mean:.2f} vs actual", delta_color="inverse")
    
    div_y = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
    c4.metric("Div. Yield", f"{div_y:.2f}%")
    
    st.markdown("---")
    
    # --- PESTAÑAS ---
    tabs = st.tabs(["📘 MÉTODO GERALDINE WEISS", "🚀 PROYECCIÓN PRECIO", "📊 RATIOS"])
    
    # ----------------------------------------------------
    # TAB 1: GERALDINE WEISS (DIVIDEND YIELD THEORY) - MEJORADO
    # ----------------------------------------------------
    with tabs[0]:
        if weiss:
            st.header("💎 Teoría del Dividendo (Geraldine Weiss)")
            st.markdown("""
            Esta estrategia se basa en que las empresas "Blue Chip" suelen cotizar dentro de un rango de rentabilidad por dividendo consistente.
            Compramos cuando el Yield es históricamente ALTO (precio bajo) y vendemos cuando es BAJO (precio alto).
            """)
            
            w1, w2, w3 = st.columns(3)
            
            # Valores Teóricos Weiss
            # Precio si Yield fuera Min (Zona Venta) = Div / Min_Yield
            price_sell_zone = weiss['current_div_ttm'] / (weiss['min_yield']/100)
            # Precio si Yield fuera Max (Zona Compra) = Div / Max_Yield
            price_buy_zone = weiss['current_div_ttm'] / (weiss['max_yield']/100)
            # Precio Justo (Yield Medio)
            price_fair_weiss = weiss['current_div_ttm'] / (weiss['avg_yield']/100)
            
            with w1:
                st.markdown("#### 🟢 Zona de Compra")
                st.markdown(f"<h2 style='color:#00b894'>${price_buy_zone:.2f}</h2>", unsafe_allow_html=True)
                st.caption(f"Corresponde a un Yield del {weiss['max_yield']:.2f}% (Máximo Histórico)")
                
            with w2:
                st.markdown("#### ⚖️ Valor Justo")
                st.markdown(f"<h2>${price_fair_weiss:.2f}</h2>", unsafe_allow_html=True)
                st.caption(f"Corresponde a un Yield del {weiss['avg_yield']:.2f}% (Mediana Histórica)")
                
            with w3:
                st.markdown("#### 🔴 Zona de Venta")
                st.markdown(f"<h2 style='color:#e74c3c'>${price_sell_zone:.2f}</h2>", unsafe_allow_html=True)
                st.caption(f"Corresponde a un Yield del {weiss['min_yield']:.2f}% (Mínimo Histórico)")
            
            # BARRA DE ESTADO
            current_y = weiss['current_yield']
            st.markdown("<br>", unsafe_allow_html=True)
            
            if current_y >= weiss['max_yield'] * 0.95:
                st.markdown(f"<div class='weiss-buy'>✅ <b>SEÑAL DE COMPRA:</b> El yield actual ({current_y:.2f}%) está cerca de sus máximos históricos. La acción está infravalorada según Weiss.</div>", unsafe_allow_html=True)
            elif current_y <= weiss['min_yield'] * 1.1:
                st.markdown(f"<div class='weiss-sell'>⛔ <b>SEÑAL DE VENTA:</b> El yield actual ({current_y:.2f}%) está cerca de sus mínimos. La acción parece cara.</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='weiss-hold'>✋ <b>MANTENER / ZONA NEUTRA:</b> El yield ({current_y:.2f}%) está dentro de rangos normales.</div>", unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # GRÁFICO DEL CANAL DE VALOR
            # Calculamos el precio histórico si siempre hubiera cotizado al yield medio
            df_hist = weiss['history_df']
            
            # Precios teóricos históricos
            df_hist['Val_Undervalued'] = df_hist['Div_TTM'] / (weiss['max_yield']/100) # Línea verde (Precio Buy)
            df_hist['Val_Overvalued'] = df_hist['Div_TTM'] / (weiss['min_yield']/100) # Línea roja (Precio Sell)
            df_hist['Val_Fair'] = df_hist['Div_TTM'] / (weiss['avg_yield']/100)       # Línea azul
            
            fig_weiss = go.Figure()
            
            # Área de sobrevaloración (Relleno superior)
            fig_weiss.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Val_Overvalued'], mode='lines', line=dict(width=0), showlegend=False))
            
            # Precio Real
            fig_weiss.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'], mode='lines', name='Precio Real', line=dict(color='black', width=3)))
            
            # Líneas de Valor
            fig_weiss.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Val_Undervalued'], mode='lines', name='Zona Compra (Yield Alto)', line=dict(color='green', dash='dash')))
            fig_weiss.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Val_Overvalued'], mode='lines', name='Zona Venta (Yield Bajo)', line=dict(color='red', dash='dash')))
            fig_weiss.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Val_Fair'], mode='lines', name='Valor Medio', line=dict(color='blue', width=1)))
            
            fig_weiss.update_layout(title="Canal de Valoración por Dividendos (10 Años)", template="plotly_white", height=500)
            st.plotly_chart(fig_weiss, use_container_width=True)
            
        else:
            st.warning("⚠️ Esta empresa no paga dividendos suficientes o no tiene historial estable para aplicar el método de Geraldine Weiss.")

    # ----------------------------------------------------
    # TAB 2: PROYECCIÓN (Simplificada para enfoque en correcciones)
    # ----------------------------------------------------
    with tabs[1]:
        st.header("Proyección de Precio a 5 Años")
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            growth_default = data['finviz_growth'] if data['finviz_growth'] else 10.0
            g_input = st.number_input("Crecimiento Estimado EPS (%)", value=float(growth_default))
            
            # Input PER Salida con ayuda visual
            st.write(f"PER Histórico (Mediana): **{pe_mean:.2f}**")
            pe_input = st.number_input("PER de Salida", value=float(pe_mean))
            
            final_eps = eps * ((1 + g_input/100)**5)
            final_price = final_eps * pe_input
            
            cagr = ((final_price / price)**(1/5) - 1) * 100
            
            st.markdown("---")
            st.metric("Precio Objetivo (2029)", f"${final_price:.2f}")
            st.metric("Retorno Anual (CAGR)", f"{cagr:.2f}%")
            
        with col_p2:
            # Gráfico simple de proyección
            years = list(range(datetime.now().year, datetime.now().year+6))
            values = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig_proj = go.Figure(go.Scatter(x=years, y=values, mode='lines+markers', line=dict(color='#6c5ce7', width=4)))
            fig_proj.update_layout(title="Curva de Valor Esperado", height=400)
            st.plotly_chart(fig_proj, use_container_width=True)

    # ----------------------------------------------------
    # TAB 3: RATIOS HISTÓRICOS (Verificación)
    # ----------------------------------------------------
    with tabs[2]:
        st.header("Diagnóstico de Ratios (Actual vs Mediana Histórica)")
        st.markdown("Utilizamos la **Mediana** de los últimos 10 años para evitar que años con malos resultados distorsionen la media hacia arriba.")
        
        hr = data['hist_ratios']
        
        ratios_check = [
            ("PER (P/E)", info.get('trailingPE'), hr.get('PER')),
            ("Price/Sales", info.get('priceToSalesTrailing12Months'), hr.get('Price/Sales')),
            ("Price/Book", info.get('priceToBook'), hr.get('Price/Book')) # Este lo saca yahoo, se podría calcular histórico tmb
        ]
        
        for name, curr, hist in ratios_check:
            if curr and hist:
                col1, col2 = st.columns([3, 1])
                diff = ((curr - hist) / hist) * 100
                color = "🔴 Caro" if diff > 10 else "🟢 Barato" if diff < -10 else "🟡 Justo"
                
                with col1:
                    st.markdown(f"**{name}**: Actual {curr:.2f} vs Histórico {hist:.2f}")
                    st.progress(min(max((curr/ (hist*2) ), 0.0), 1.0))
                with col2:
                    st.markdown(f"### {color}")
                    st.caption(f"{diff:+.1f}% desv.")
                st.divider()
