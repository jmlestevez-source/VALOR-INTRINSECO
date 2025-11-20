import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro (Estilo Excel)", layout="wide", page_icon="📈")

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
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTOR DE DATOS BLINDADO ---

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    """Obtiene data y corrige manualmente los dividendos."""
    stock = yf.Ticker(ticker)
    info = stock.info
    
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    if not price: return None
    
    # --- CORRECCIÓN DE DIVIDENDOS (LÓGICA MANUAL) ---
    # 1. Yield Actual: Lo calculamos nosotros (Cash / Precio) para evitar errores de formato
    div_rate = info.get('dividendRate', 0) # Dinero anual (ej: 1.50)
    
    if div_rate and price > 0:
        current_yield = div_rate / price # Ej: 1.50 / 100 = 0.015 (1.5%)
    else:
        # Fallback si no hay dividendRate, usamos dividendYield con precaución
        raw_yield = info.get('dividendYield', 0)
        if raw_yield and raw_yield > 0.5: # Si es mayor a 0.5 (50%), Yahoo mandó entero
            current_yield = raw_yield / 100
        else:
            current_yield = raw_yield

    # 2. Media 5 Años: Yahoo suele mandar esto siempre como ENTERO (ej: 0.81 para 0.81%)
    raw_avg_5y = info.get('fiveYearAvgDividendYield', 0)
    
    if raw_avg_5y is not None:
        # SIEMPRE dividimos por 100 la media histórica de Yahoo
        avg_5y_yield = raw_avg_5y / 100
    else:
        avg_5y_yield = 0
        
    # 3. PER Histórico
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
                            eps_val = latest[k]
                            break
                    # Fallback cálculo manual EPS
                    if pd.isna(eps_val):
                        try:
                            ni = latest.get('Net Income Common Stockholders')
                            shares = latest.get('Basic Average Shares')
                            if ni and shares: eps_val = ni / shares
                        except: pass
                        
                    if eps_val and eps_val > 0:
                        pe = row['Close'] / eps_val
                        if 5 < pe < 200: pe_values.append(pe)
            
            if pe_values:
                pe_mean = np.mean(pe_values)
    except:
        pass 

    return {
        'info': info,
        'price': price,
        'pe_mean': pe_mean,
        'div_data': {'current': current_yield, 'avg_5y': avg_5y_yield, 'rate': div_rate}
    }

# --- 2. COMPONENTES VISUALES ---

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
    y_cat = ['Valoración']
    fig = go.Figure()
    
    # Precio Actual
    fig.add_trace(go.Bar(
        y=y_cat, x=[price], name='Cotización Actual', orientation='h',
        marker_color='#e67e22', text=f"${price:.2f}", textposition='auto',
        hovertemplate="Actual: $%{x:.2f}<extra></extra>"
    ))
    
    # Valor Razonable
    fig.add_trace(go.Bar(
        y=y_cat, x=[fair_value], name='Valor Razonable (Histórico)', orientation='h',
        marker_color='#27ae60', text=f"${fair_value:.2f}", textposition='auto',
        hovertemplate="Fair Value: $%{x:.2f}<extra></extra>"
    ))
    
    # Analistas
    if analyst_target and analyst_target > 0:
        fig.add_trace(go.Bar(
            y=y_cat, x=[analyst_target], name='Obj. Analistas', orientation='h',
            marker_color='#2980b9', text=f"${analyst_target:.2f}", textposition='auto',
            hovertemplate="Analistas: $%{x:.2f}<extra></extra>"
        ))

    fig.update_layout(
        title="Comparativa de Valoración",
        barmode='group',
        height=250,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
        plot_bgcolor='white'
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 3. INTERFAZ PRINCIPAL ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="ZTS").upper()
    st.divider()
    
    st.subheader("⚙️ Parámetros")
    growth_input = st.number_input("Crecimiento Estimado (5y) %", value=10.0, step=0.5)
    years_hist = st.slider("Años para Media Histórica", 5, 10, 10)
    
    st.divider()
    st.info("Introduce el ticker para comenzar el análisis.")

if ticker:
    data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("Ticker no encontrado.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    
    eps = info.get('trailingEps', 0)
    analyst_target = info.get('targetMeanPrice', 0)
    
    # --- CÁLCULOS CORE ---
    fair_value = eps * pe_mean
    margin_safety = ((fair_value - price) / price) * 100
    
    # --- HEADER ---
    st.title(f"{info.get('shortName', ticker)}")
    st.markdown(f"**{info.get('sector', '')}** | {info.get('industry', '')}")
    
    # --- DASHBOARD PRINCIPAL (KPIs) ---
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        card_html("Cotización Actual", f"${price:.2f}")
        
    with c2:
        margin_color = "pos" if margin_safety > 0 else "neg"
        card_html("Valor Razonable (Histórico)", f"${fair_value:.2f}", 
                 f"{margin_safety:+.1f}% Margen", margin_color)
                 
    with c3:
        if analyst_target:
            analyst_margin = ((analyst_target - price) / price) * 100
            a_color = "pos" if analyst_margin > 0 else "neg"
            card_html("Precio Obj. Analistas", f"${analyst_target:.2f}", 
                     f"{analyst_margin:+.1f}% Potencial", a_color)
        else:
            card_html("Precio Obj. Analistas", "N/A")
            
    with c4:
        # Dashboard Dividendos Corregido
        curr = divs['current']
        avg = divs['avg_5y']
        
        # Si curr es 0, mostramos 0%
        curr_val = curr if curr else 0
        avg_val = avg if avg else 0
        
        sub_text = ""
        color_div = "neu"
        
        if curr_val > 0 and avg_val > 0:
            diff = curr_val - avg_val
            # Si el yield actual es MAYOR a la media, es bueno (pos)
            color_div = "pos" if diff > 0 else "neg"
            sub_text = f"Media 5y: {avg_val*100:.2f}%"
        elif curr_val > 0:
            sub_text = "Sin media histórica"
        else:
            sub_text = "No paga dividendo"

        card_html("Rentabilidad / Div.", f"{curr_val*100:.2f}%", sub_text, color_div)

    # --- GRÁFICO PRINCIPAL ---
    st.markdown("---")
    plot_valuation_bar(price, fair_value, analyst_target)
    
    # --- PESTAÑAS DE DETALLE ---
    tab1, tab2, tab3 = st.tabs(["🚀 Proyección a 5 Años", "💰 Análisis Dividendos", "📋 Datos Fundamentales"])
    
    # TAB 1: PROYECCIÓN
    with tab1:
        col_calc, col_res = st.columns([1, 2])
        
        with col_calc:
            st.subheader("Calculadora")
            st.caption(f"Partiendo de un EPS de ${eps:.2f} y la media histórica.")
            
            exit_pe = st.number_input("PER de Salida (Año 5)", value=float(round(pe_mean, 1)), 
                                     help="Por defecto es la media histórica.")
            
            future_eps = eps * ((1 + growth_input/100) ** 5)
            future_price = future_eps * exit_pe
            cagr = ((future_price / price) ** (1/5) - 1) * 100
            
            st.divider()
            st.write(f"**EPS (Año 5):** ${future_eps:.2f}")
            st.write(f"**Precio (Año 5):** ${future_price:.2f}")
            
            c_color = "green" if cagr > 10 else "black"
            st.markdown(f"#### CAGR Esperado: <span style='color:{c_color}'>{cagr:.2f}%</span>", unsafe_allow_html=True)

        with col_res:
            # Gráfico de línea simple proyección
            years = list(range(datetime.now().year, datetime.now().year + 6))
            vals = [price * ((1 + cagr/100) ** i) for i in range(6)]
            
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=years, y=vals, mode='lines+markers', name='Crecimiento', line=dict(color='#27ae60', width=3)))
            fig_proj.update_layout(title="Proyección de Precio Teórico", height=300, showlegend=False)
            st.plotly_chart(fig_proj, use_container_width=True)
            
    # TAB 2: DIVIDENDOS
    with tab2:
        curr = divs['current']
        avg = divs['avg_5y']
        div_rate = divs['rate']
        
        if curr and avg and avg > 0:
            fair_yield_price = div_rate / avg
            margin_yield = ((fair_yield_price - price) / price) * 100
            
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                st.markdown("### Yield Theory (Geraldine Weiss)")
                st.write(f"El dividendo anual es **${div_rate}**.")
                st.write(f"La media histórica de rentabilidad es **{avg*100:.2f}%**.")
                st.write("Si la acción cotizara a su media histórica, el precio sería:")
                st.metric("Valor Justo (Por Dividendos)", f"${fair_yield_price:.2f}", f"{margin_yield:+.1f}%")
                
            with c_d2:
                # Gráfico comparativo Yields
                fig_y = go.Figure()
                fig_y.add_trace(go.Bar(x=['Yield Actual', 'Media 5 Años'], y=[curr*100, avg*100], marker_color=['#2980b9', '#95a5a6'], text=[f"{curr*100:.2f}%", f"{avg*100:.2f}%"], textposition='auto'))
                fig_y.update_layout(title="Comparativa de Rentabilidad (%)", height=300)
                st.plotly_chart(fig_y, use_container_width=True)
        else:
            st.info("Datos insuficientes para aplicar la Teoría de Dividendos (Weiss).")
            
    # TAB 3: DATOS
    with tab3:
        st.markdown("#### Métricas Clave")
        dat = {
            'Métrica': ['PER Actual', 'PER Medio Histórico', 'Beta', 'Precio/Ventas', 'EV/EBITDA'],
            'Valor': [
                f"{info.get('trailingPE', 0):.2f}x",
                f"{pe_mean:.2f}x",
                f"{info.get('beta', 0):.2f}",
                f"{info.get('priceToSalesTrailing12Months', 0):.2f}x",
                f"{info.get('enterpriseToEbitda', 0):.2f}x"
            ]
        }
        st.table(pd.DataFrame(dat))
