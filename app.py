import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Master", layout="wide", page_icon="💎")

# --- ESTILOS CSS (BIG FONTS) ---
st.markdown("""
    <style>
    /* FUENTES GLOBALES */
    html, body, [class*="css"], div, span, p {
        font-family: 'Arial', sans-serif;
        font-size: 20px;
    }
    
    /* TARJETAS MÉTRICAS */
    .metric-card {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 30px 15px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        height: 100%;
    }
    .metric-label { 
        font-size: 18px !important; 
        color: #666; 
        text-transform: uppercase; 
        font-weight: 800;
        margin-bottom: 15px;
    }
    .metric-value { 
        font-size: 52px !important; 
        font-weight: 900; 
        color: #2c3e50; 
        line-height: 1;
    }
    .metric-sub { font-size: 22px !important; font-weight: 600; margin-top: 15px; }

    /* VEREDICTO */
    .verdict-box {
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.15);
    }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #f1c40f, #e67e22); }
    .v-overvalued { background: linear-gradient(135deg, #e74c3c, #c0392b); }
    .v-main { font-size: 64px; font-weight: 900; margin: 15px 0; text-shadow: 0 2px 5px rgba(0,0,0,0.2); }
    .v-desc { font-size: 28px; font-weight: 500; }

    /* TABLAS GIGANTES */
    .stTable { font-size: 22px !important; }
    thead tr th { font-size: 24px !important; background-color: #f8f9fa !important; padding: 20px !important;}
    tbody tr td { font-size: 22px !important; padding: 20px !important; }

    /* PESTAÑAS */
    .stTabs [data-baseweb="tab"] {
        font-size: 26px !important;
        padding: 15px 30px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTORES DE CÁLCULO ROBUSTO ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    """Scraping simple de Finviz."""
    ticker = ticker.replace('.', '-')
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(r.content, 'html.parser')
        t = soup.find(string="EPS next 5Y")
        if t:
            val = t.parent.find_next_sibling('td').text.replace('%', '').strip()
            return float(val)
    except: return None
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=5):
    """
    MÉTODO MATEMÁTICO INFALIBLE:
    Descarga precios y fundamentales, los alinea y calcula la media.
    Ignora el scraping externo para asegurar que siempre haya datos.
    """
    stock = yf.Ticker(ticker)
    
    # 1. Historial de Precios (Mensual)
    start_date = (datetime.now() - timedelta(days=years*365 + 30)).strftime('%Y-%m-%d')
    hist = stock.history(start=start_date, interval="1mo")
    
    if hist.empty: return {}
    
    # Limpieza de zona horaria
    if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
    
    # 2. Fundamentales Anuales (Más estables que trimestrales)
    fin = stock.financials.T
    bal = stock.balance_sheet.T
    
    if fin.empty: return {}
    
    # Limpieza de índices
    fin.index = pd.to_datetime(fin.index)
    if bal is not None and not bal.empty:
        bal.index = pd.to_datetime(bal.index)
    
    if fin.index.tz is not None: fin.index = fin.index.tz_localize(None)
    
    # 3. Fusión de Datos (Resampling)
    # Creamos un DataFrame base con los precios mensuales
    df_merge = pd.DataFrame(index=hist.index)
    df_merge['Price'] = hist['Close']
    
    # Unimos los fundamentales por fecha más cercana anterior (asof)
    # Para hacerlo fácil en Pandas: Concatenamos y hacemos ffill()
    
    # Extraemos métricas clave de Financials
    metrics_fin = pd.DataFrame(index=fin.index)
    
    # EPS
    metrics_fin['EPS'] = fin.get('Diluted EPS', fin.get('Basic EPS'))
    # Ventas por Acción
    rev = fin.get('Total Revenue')
    shares = fin.get('Basic Average Shares', fin.get('Share Issued'))
    if rev is not None and shares is not None:
        metrics_fin['RPS'] = rev / shares # Revenue Per Share
    
    # Unimos Balance si existe
    if not bal.empty:
        if bal.index.tz is not None: bal.index = bal.index.tz_localize(None)
        # Valor en Libros
        assets = bal.get('Total Assets')
        liab = bal.get('Total Liabilities Net Minority Interest')
        # Buscamos shares de financial correspondiente o del mismo balance
        if assets is not None and liab is not None and shares is not None:
            # Alineamos shares con balance por índice si es posible, si no usamos el de fin
            # Simplificación: Usamos el Book Value directo si existe, o calculamos
            metrics_fin['BVPS'] = (assets - liab) / shares
            
            # EV/EBITDA Componentes
            debt = bal.get('Total Debt')
            cash = bal.get('Cash And Cash Equivalents')
            ebitda = fin.get('EBITDA', fin.get('Normalized EBITDA'))
            
            if debt is not None and cash is not None and ebitda is not None:
                metrics_fin['Debt'] = debt
                metrics_fin['Cash'] = cash
                metrics_fin['EBITDA'] = ebitda
                metrics_fin['Shares'] = shares

    # Ordenar y mezclar
    metrics_fin = metrics_fin.sort_index()
    
    # Unir precios con fundamentales usando "asof" (el reporte válido en esa fecha)
    # Pandas merge_asof requiere orden ascendente
    df_merge = df_merge.sort_index()
    
    # Reindexamos fundamentales a las fechas de los precios usando ffill (el dato se mantiene hasta el siguiente reporte)
    df_final = df_merge.join(metrics_fin, how='outer').ffill().dropna(subset=['Price'])
    
    # 4. Cálculo de Ratios Históricos
    ratios = {'PER': [], 'Price/Sales': [], 'Price/Book': [], 'EV/EBITDA': []}
    
    # Vectorizado (Mucho más rápido y seguro)
    if 'EPS' in df_final.columns:
        df_final['PE_Ratio'] = df_final['Price'] / df_final['EPS']
        # Filtrar anomalías
        valid_pe = df_final['PE_Ratio'][(df_final['PE_Ratio'] > 0) & (df_final['PE_Ratio'] < 200)]
        if not valid_pe.empty: ratios['PER'] = valid_pe.mean()

    if 'RPS' in df_final.columns:
        df_final['PS_Ratio'] = df_final['Price'] / df_final['RPS']
        valid_ps = df_final['PS_Ratio'][(df_final['PS_Ratio'] > 0) & (df_final['PS_Ratio'] < 50)]
        if not valid_ps.empty: ratios['Price/Sales'] = valid_ps.mean()

    if 'BVPS' in df_final.columns:
        df_final['PB_Ratio'] = df_final['Price'] / df_final['BVPS']
        valid_pb = df_final['PB_Ratio'][(df_final['PB_Ratio'] > 0) & (df_final['PB_Ratio'] < 50)]
        if not valid_pb.empty: ratios['Price/Book'] = valid_pb.mean()

    if 'EBITDA' in df_final.columns and 'Debt' in df_final.columns:
        # EV = MarketCap + Debt - Cash
        # MarketCap = Price * Shares
        df_final['EV'] = (df_final['Price'] * df_final['Shares']) + df_final['Debt'] - df_final['Cash']
        df_final['EV_EBITDA'] = df_final['EV'] / df_final['EBITDA']
        valid_ev = df_final['EV_EBITDA'][(df_final['EV_EBITDA'] > 0) & (df_final['EV_EBITDA'] < 100)]
        if not valid_ev.empty: ratios['EV/EBITDA'] = valid_ev.mean()
        
    return ratios

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
    
    # HISTÓRICOS (CÁLCULO INTERNO SEGURO)
    hist_ratios = calculate_robust_ratios(ticker, years_hist)
    
    # Crecimiento
    finviz_g = get_finviz_growth(ticker)
    
    # PER Medio para Valuation
    # Si el cálculo falló, usamos 15 como fallback de seguridad
    pe_mean = hist_ratios.get('PER', 15.0)
    
    # Asegurar que no es numpy.nan
    if pd.isna(pe_mean): pe_mean = 15.0

    return {
        'info': info, 'price': price, 'pe_mean': pe_mean,
        'div_data': {'current': current_yield, 'avg_5y': avg_5y_yield, 'rate': div_rate},
        'hist_ratios': hist_ratios, 'finviz_growth': finviz_growth
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
        desc = f"Cotizando cerca de su valor"

    st.markdown(f"""
    <div class="verdict-box {css}">
        <div class="v-title">{title}</div>
        <div class="v-main">{icon} {main}</div>
        <div class="v-desc">{desc} (Fair: ${fair_value:.2f})</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. MAIN APP ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)

if ticker:
    with st.spinner(f'⚙️ Procesando datos financieros para {ticker}...'):
        data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("Error: No se pudo obtener información del Ticker.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    hist_ratios = data['hist_ratios']
    finviz_g = data['finviz_growth']
    
    # Crecimiento
    default_g = finviz_g if finviz_g else 10.0
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        if finviz_g: st.success(f"✅ Finviz: {finviz_g}%")
        else: st.info("ℹ️ Estimación Manual")

    eps = info.get('trailingEps', 0)
    fair_value = eps * pe_mean
    
    # HEADER
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
            <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border:1px solid #ddd;'>
                <p>EPS Actual: <b>${eps:.2f}</b></p>
                <p>Crecimiento Estimado: <b>{growth_input}%</b></p>
                <p>PER Salida Estimado: <b>{pe_mean:.1f}x</b></p>
            </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            exit_pe = st.number_input("Ajustar PER Salida", value=float(round(pe_mean, 1)))
            
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100
            
            st.markdown("---")
            st.markdown(f"<div style='font-size:32px; margin-bottom:10px'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            c_col = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:32px'>CAGR Esperado: <b style='color:{c_col}; font-size:48px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
            
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#0984e3', width=6), marker=dict(size=16)))
            fig.update_layout(
                title={'text': "Curva de Valor Teórico", 'font': {'size': 28}},
                font=dict(size=20),
                height=450
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
                <div style='font-size:26px; line-height:2'>
                    💰 Dividendo Anual: <b>${divs['rate']}</b><br>
                    📉 Media Histórica: <b>{divs['avg_5y']*100:.2f}%</b><br>
                    🏁 Valor Justo: <b style='color:#2980b9'>${fair_yld:.2f}</b>
                </div>
                """, unsafe_allow_html=True)
            with cd2:
                fig = go.Figure(go.Bar(x=['Actual', 'Media'], y=[divs['current']*100, divs['avg_5y']*100], marker_color=['#00b894','#b2bec3'], texttemplate='%{y:.2f}%', textfont={'size': 24}))
                fig.update_layout(title={'text': "Rentabilidad Comparada", 'font': {'size': 28}}, font=dict(size=20), height=400)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Empresa sin historial de dividendos suficiente.")

    # TAB 3: RATIOS GIGANTES
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔎 Análisis Fundamental vs Histórico")
        
        ratios_to_show = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': hist_ratios.get('PER')},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': hist_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': hist_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': hist_ratios.get('EV/EBITDA')}
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
        
        df_ratios = pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Desv.', 'Diagnóstico'])
        st.table(df_ratios)
