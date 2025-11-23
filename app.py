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

# --- ESTILOS CSS (COMBINADO: Estilo original + Estilo del Valuómetro) ---
st.markdown("""
    <style>
    /* FUENTES Y GENERAL */
    html, body, [class*="css"], div, span, p { font-family: 'Arial', sans-serif; font-size: 18px; }
    
    /* TARJETAS MÉTRICAS */
    .metric-card {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 25px 15px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        height: 100%;
    }
    .metric-label { font-size: 16px !important; color: #666; text-transform: uppercase; font-weight: 800; margin-bottom: 10px; }
    .metric-value { font-size: 46px !important; font-weight: 900; color: #2c3e50; line-height: 1; }
    .metric-sub { font-size: 18px !important; font-weight: 600; margin-top: 10px; }

    /* VEREDICTO */
    .verdict-box { padding: 35px; border-radius: 20px; text-align: center; color: white; margin-bottom: 30px; box-shadow: 0 10px 20px rgba(0,0,0,0.15); }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #0984e3); }
    .v-fair { background: linear-gradient(135deg, #f1c40f, #e67e22); }
    .v-overvalued { background: linear-gradient(135deg, #e74c3c, #c0392b); }
    .v-main { font-size: 58px; font-weight: 900; margin: 10px 0; text-shadow: 0 2px 5px rgba(0,0,0,0.2); }
    .v-desc { font-size: 24px; font-weight: 500; }

    /* ESTILOS NUEVOS: VALUÓMETRO (TAB 3) */
    .val-container { margin-bottom: 25px; background: #f8f9fa; padding: 20px; border-radius: 12px; border: 1px solid #eee; }
    .val-header { display: flex; justify-content: space-between; font-weight: bold; font-size: 20px; margin-bottom: 10px; }
    .val-bar-bg { width: 100%; height: 20px; background-color: #dfe6e9; border-radius: 10px; position: relative; overflow: hidden; }
    .val-marker { position: absolute; top: -5px; width: 5px; height: 30px; background-color: #2d3436; z-index: 5; border: 1px solid white; }

    /* ALERTAS */
    .alert-box { padding: 15px; border-radius: 10px; margin: 15px 0; border-left: 5px solid; font-size: 16px; }
    .alert-danger { background-color: #fee; border-color: #e74c3c; color: #c0392b; }
    .alert-warning { background-color: #fef9e7; border-color: #f39c12; color: #d68910; }
    .alert-success { background-color: #e8f8f5; border-color: #00b894; color: #00875a; }

    /* ESCENARIOS (TAB 1) */
    .scenario-card { border-radius: 15px; padding: 20px; color: white; margin: 10px 0; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
    .scenario-bull { background: linear-gradient(135deg, #00b894 0%, #00cec9 100%); }
    .scenario-base { background: linear-gradient(135deg, #fdcb6e 0%, #e17055 100%); }
    .scenario-bear { background: linear-gradient(135deg, #d63031 0%, #e84393 100%); }
    .scenario-title { font-size: 24px; font-weight: 800; margin-bottom: 5px; }
    .scenario-price { font-size: 38px; font-weight: 900; margin: 5px 0; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE DATOS (VERSIÓN ROBUSTA PARA EVITAR N/A) ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'html.parser')
            t = soup.find(string="EPS next 5Y")
            if t:
                val = t.parent.find_next_sibling('td').text.replace('%', '').strip()
                if val != '-': return float(val)
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_growth(ticker):
    try:
        url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            matches = re.findall(r'(\d+\.?\d*)%\s*(?:annual|avg|average|growth)', r.text, re.IGNORECASE)
            if matches: return float(matches[0])
    except: pass
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=10):
    """
    Cálculo ROBUSTO de ratios históricos.
    Devuelve diccionario con {median, min, max} para cada ratio.
    Usa fallback: Trimestral -> Anual.
    """
    ratios = {}
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{years}y", interval="1mo")
        if hist.empty: return {}
        if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
        hist = hist[['Close']]

        # Datos Financieros
        q_fin = stock.quarterly_financials.T
        a_fin = stock.financials.T
        
        def get_col(df, candidates):
            for c in candidates:
                if c in df.columns: return df[c]
            return None

        # --- PER (EPS) ---
        eps_series = None
        use_quarterly = False
        
        # Intento Trimestral (Rolling TTM)
        if not q_fin.empty:
            eps_q = get_col(q_fin, ['Diluted EPS', 'Basic EPS', 'Net Income'])
            if eps_q is not None:
                q_fin.index = pd.to_datetime(q_fin.index).tz_localize(None)
                q_fin = q_fin.sort_index()
                if 'Diluted EPS' in q_fin.columns:
                    eps_ttm = q_fin['Diluted EPS'].rolling(4).sum()
                    if eps_ttm is not None and not eps_ttm.dropna().empty:
                        eps_series = eps_ttm
                        use_quarterly = True
        
        # Fallback Anual
        if eps_series is None and not a_fin.empty:
            a_fin.index = pd.to_datetime(a_fin.index).tz_localize(None)
            a_fin = a_fin.sort_index()
            eps_series = get_col(a_fin, ['Diluted EPS', 'Basic EPS'])

        if eps_series is not None:
            df_pe = pd.DataFrame(index=hist.index)
            df_pe['Price'] = hist['Close']
            df_pe['EPS'] = eps_series.reindex(hist.index, method='ffill')
            df_pe['PE'] = df_pe['Price'] / df_pe['EPS']
            valid_pe = df_pe['PE'][(df_pe['PE'] > 0) & (df_pe['PE'] < 200)].dropna()
            
            if not valid_pe.empty:
                ratios['PER'] = {
                    'median': float(valid_pe.median()),
                    'min': float(valid_pe.quantile(0.05)),
                    'max': float(valid_pe.quantile(0.95))
                }

        # --- Price/Sales ---
        fin_df = q_fin if use_quarterly else a_fin
        if not fin_df.empty:
            rev = get_col(fin_df, ['Total Revenue', 'Total Income'])
            shares = get_col(fin_df, ['Basic Average Shares', 'Ordinary Shares Number', 'Share Issued'])
            
            if rev is not None and shares is not None:
                if use_quarterly: rev = rev.rolling(4).sum()
                rps = rev / shares
                df_ps = pd.DataFrame(index=hist.index)
                df_ps['Price'] = hist['Close']
                df_ps['RPS'] = rps.reindex(hist.index, method='ffill')
                df_ps['PS'] = df_ps['Price'] / df_ps['RPS']
                valid_ps = df_ps['PS'][(df_ps['PS'] > 0) & (df_ps['PS'] < 50)].dropna()
                
                if not valid_ps.empty:
                    ratios['Price/Sales'] = {
                        'median': float(valid_ps.median()),
                        'min': float(valid_ps.quantile(0.05)),
                        'max': float(valid_ps.quantile(0.95))
                    }
        
        # --- Price/Book ---
        q_bs = stock.quarterly_balance_sheet.T
        a_bs = stock.balance_sheet.T
        bs_df = q_bs if not q_bs.empty else a_bs
        
        if not bs_df.empty:
            bs_df.index = pd.to_datetime(bs_df.index).tz_localize(None)
            bs_df = bs_df.sort_index()
            assets = get_col(bs_df, ['Total Assets'])
            liabs = get_col(bs_df, ['Total Liabilities Net Minority Interest', 'Total Liabilities'])
            shares_bs = get_col(fin_df, ['Basic Average Shares', 'Ordinary Shares Number']) # Shares from Income St usually
            
            if assets is not None and liabs is not None and shares_bs is not None:
                bvps = (assets - liabs) / shares_bs
                df_pb = pd.DataFrame(index=hist.index)
                df_pb['Price'] = hist['Close']
                df_pb['BVPS'] = bvps.reindex(hist.index, method='ffill')
                df_pb['PB'] = df_pb['Price'] / df_pb['BVPS']
                valid_pb = df_pb['PB'][(df_pb['PB'] > 0) & (df_pb['PB'] < 50)].dropna()
                
                if not valid_pb.empty:
                    ratios['Price/Book'] = {
                        'median': float(valid_pb.median()),
                        'min': float(valid_pb.quantile(0.05)),
                        'max': float(valid_pb.quantile(0.95))
                    }
        return ratios

    except Exception: return {}

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price: return None
        
        hist_ratios = calculate_robust_ratios(ticker, years_hist)
        div_rate = info.get('dividendRate', 0)
        current_yield = (div_rate / price) if (div_rate and price > 0) else 0
        
        # Priorizar PER calculado robustamente, sino usar Yahoo
        pe_mean = 15.0
        if 'PER' in hist_ratios: pe_mean = hist_ratios['PER']['median']
        elif info.get('trailingPE'): pe_mean = float(info.get('trailingPE'))
        
        # Historial de dividendos crudo para Weiss
        div_history = stock.dividends
        
        finviz_g = get_finviz_growth(ticker)
        if finviz_g is None: finviz_g = get_stockanalysis_growth(ticker)

        return {
            'info': info, 'price': float(price), 'pe_mean': float(pe_mean),
            'div_data': {'current': float(current_yield), 'rate': float(div_rate), 'history': div_history},
            'hist_ratios': hist_ratios, 'finviz_growth': finviz_g, 'ticker': ticker
        }
    except: return None

# --- 2. COMPONENTES VISUALES ---

def show_alert(message, alert_type="info"):
    class_map = {"danger": "alert-danger", "warning": "alert-warning", "info": "alert-info", "success": "alert-success"}
    icon_map = {"danger": "🚨", "warning": "⚠️", "info": "ℹ️", "success": "✅"}
    st.markdown(f"""<div class="alert-box {class_map[alert_type]}"><strong>{icon_map[alert_type]} {message}</strong></div>""", unsafe_allow_html=True)

def validate_projection(growth, exit_pe, cagr, price):
    warnings = []
    if growth > 25: warnings.append({"type": "warning", "msg": f"<b>Crecimiento de {growth:.1f}%</b> es muy agresivo."})
    if exit_pe > 40: warnings.append({"type": "warning", "msg": f"<b>PER de {exit_pe:.1f}x</b> sugiere valoración premium."})
    if cagr > 25: warnings.append({"type": "warning", "msg": f"<b>CAGR de {cagr:.1f}%</b> es excelente pero ambicioso."})
    return warnings

def card_html(label, value, sub_value=None, color_class="neu"):
    sub_html = f"<div class='metric-sub {color_class}'>{sub_value}</div>" if sub_value else ""
    st.markdown(f"""<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div>{sub_html}</div>""", unsafe_allow_html=True)

def verdict_box(price, fair_value):
    margin = ((fair_value - price) / price) * 100
    if margin > 15: css, title, main, icon, desc = "v-undervalued", "💎 OPORTUNIDAD", "INFRAVALORADA", "🚀", f"Descuento del {margin:.1f}%"
    elif margin < -15: css, title, main, icon, desc = "v-overvalued", "⚠️ CUIDADO", "SOBREVALORADA", "🛑", f"Prima del {abs(margin):.1f}%"
    else: css, title, main, icon, desc = "v-fair", "⚖️ EQUILIBRIO", "PRECIO JUSTO", "✅", f"Cotizando cerca de su valor"
    st.markdown(f"""<div class="verdict-box {css}"><div class="v-title">{title}</div><div class="v-main">{icon} {main}</div><div class="v-desc">{desc} (Fair: ${fair_value:.2f})</div></div>""", unsafe_allow_html=True)

def scenario_card(title, price_proj, cagr, growth, exit_pe, scenario_type="base"):
    css_class = f"scenario-{scenario_type}"
    st.markdown(f"""<div class="scenario-card {css_class}"><div class="scenario-title">{title}</div><div class="scenario-price">${price_proj:,.2f}</div><div class="scenario-cagr">CAGR: {cagr:.1f}%</div><div style="margin-top:15px; font-size:16px; opacity:0.9;">Growth: {growth:.1f}% | Exit PER: {exit_pe:.1f}x</div></div>""", unsafe_allow_html=True)

def valuation_meter(label, current, median, min_val, max_val):
    """COMPONENTE VISUAL PARA EL VALUÓMETRO (TAB 3)"""
    if current is None or median is None: return
    
    full_range = max_val - min_val
    if full_range == 0: full_range = 1
    pos_current = min(max(((current - min_val) / full_range) * 100, 0), 100)
    
    if current < median: status_color, status_text = "#00b894", "INFRAVALORADA"
    elif current > median * 1.2: status_color, status_text = "#e74c3c", "SOBREVALORADA"
    else: status_color, status_text = "#f1c40f", "JUSTA"

    diff = ((current - median) / median) * 100
    
    st.markdown(f"""
    <div class="val-container">
        <div class="val-header">
            <span>{label}</span>
            <span style="color:{status_color}">{status_text} ({diff:+.1f}%)</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:14px; color:#666; margin-bottom:5px;">
            <span>Min: {min_val:.1f}</span>
            <span>Mediana: {median:.1f}</span>
            <span>Max: {max_val:.1f}</span>
        </div>
        <div class="val-bar-bg">
            <div style="position:absolute; left:0; width: {((median-min_val)/full_range)*100}%; height:100%; background:linear-gradient(90deg, #55efc4, #dfe6e9); opacity:0.5;"></div>
            <div class="val-marker" style="left: {pos_current}%; background-color: {status_color}; box-shadow: 0 0 5px {status_color};"></div>
        </div>
        <div style="text-align:center; margin-top:8px; font-weight:bold; font-size:18px; color:#2d3436;">Actual: {current:.2f}x</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. MAIN APP ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper().strip()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)

if ticker:
    with st.spinner(f'⚙️ Procesando datos para {ticker}...'):
        data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("❌ Error: No se encontró el Ticker o faltan datos.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    hist_ratios = data['hist_ratios']
    finviz_g = data['finviz_growth']
    
    default_g = finviz_g if finviz_g else 10.0
    eps = info.get('trailingEps', 0) or info.get('forwardEps', 1)
    if eps is None: eps = 1
    fair_value = float(eps) * pe_mean

    # --- SIDEBAR INPUTS ---
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        if finviz_g: st.success(f"✅ Finviz Growth: {finviz_g}%")

    # --- HEADER & VEREDICTO ---
    st.title(f"📊 {info.get('shortName', ticker)}")
    st.markdown(f"### **{info.get('sector', 'N/A')}**  •  {info.get('industry', 'N/A')}")
    st.markdown("---")
    verdict_box(price, fair_value)

    # --- BIG CARDS ---
    c1, c2, c3, c4 = st.columns(4)
    with c1: card_html("Cotización", f"${price:.2f}")
    with c2: card_html("Valor Razonable", f"${fair_value:.2f}", f"PER Hist: {pe_mean:.1f}x", "neu")
    with c3: 
        tgt = info.get('targetMeanPrice')
        card_html("Obj. Analistas", f"${tgt}" if tgt else "N/A", f"{((tgt-price)/price)*100:+.1f}%" if tgt else "", "pos" if tgt and tgt>price else "neg")
    with c4: card_html("Div. Yield", f"{divs['current']*100:.2f}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- TABS ---
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 DIVIDENDOS (WEISS)", "📊 FUNDAMENTALES (VALUÓMETRO)"])

    # TAB 1: PROYECCIÓN (Código ORIGINAL recuperado)
    with t1:
        st.markdown("<br>", unsafe_allow_html=True)
        cc1, cc2 = st.columns([1, 2])
        with cc1:
            st.subheader("📝 Calculadora")
            st.markdown(f"<div style='background-color:#f8f9fa; padding:15px; border-radius:10px;'>EPS: ${eps:.2f} | Growth: {growth_input}% | PER Salida: {pe_mean:.1f}x</div>", unsafe_allow_html=True)
            st.write("")
            exit_pe = st.number_input("Ajustar PER Salida", value=float(round(pe_mean, 1)), step=0.5)
            f_price = eps * ((1 + growth_input/100)**5) * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100 if price > 0 else 0
            st.markdown("---")
            st.markdown(f"<div style='font-size:28px;'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:28px;'>CAGR: <b style='color:{'#00b894' if cagr>10 else '#2d3436'}'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
        
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#0984e3', width=4)))
            fig.update_layout(title="Curva de Valor Teórico", height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        warnings = validate_projection(growth_input, exit_pe, cagr, price)
        if warnings: 
            for w in warnings: show_alert(w['msg'], w['type'])
        else: show_alert("✅ Supuestos razonables", "success")
        
        st.subheader("🎲 Escenarios")
        cols = st.columns(3)
        scenarios = [("🚀 Bull", growth_input, exit_pe, "bull"), ("🎯 Base", growth_input*0.7, exit_pe*0.8, "base"), ("🐻 Bear", growth_input*0.4, exit_pe*0.6, "bear")]
        for i, (name, g, p, t) in enumerate(scenarios):
            fp = eps * ((1 + g/100)**5) * p
            cg = ((fp/price)**(1/5)-1)*100 if price>0 else 0
            with cols[i]: scenario_card(name, fp, cg, g, p, t)

    # TAB 2: WEISS (Código ORIGINAL recuperado con mejoras visuales)
    with t2:
        st.markdown("<br>", unsafe_allow_html=True)
        if divs['rate'] and not divs['history'].empty:
            try:
                stock_obj = yf.Ticker(ticker)
                hist_w = stock_obj.history(period="10y")
                div_hist = divs['history']
                if not hist_w.empty:
                    # Lógica de construcción del gráfico Weiss
                    div_series = div_hist.reindex(hist_w.index, method='ffill').fillna(0)
                    df_w = pd.DataFrame(index=hist_w.index)
                    df_w['Close'] = hist_w['Close']
                    # Dividendo TTM aproximado
                    daily_idx = pd.date_range(start=hist_w.index[0], end=hist_w.index[-1])
                    div_ttm = div_hist.reindex(daily_idx).fillna(0).rolling(365).sum().reindex(hist_w.index).ffill()
                    df_w['Yield'] = (div_ttm / df_w['Close']) * 100
                    valid_y = df_w['Yield'][(df_w['Yield'] > 0.1) & (df_w['Yield'] < 20)]
                    
                    if not valid_y.empty:
                        min_y, max_y = valid_y.quantile(0.05), valid_y.quantile(0.95)
                        df_w['Undervalued'] = (div_ttm / max_y) * 100
                        df_w['Overvalued'] = (div_ttm / min_y) * 100
                        
                        # Métricas Weiss
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Zona Compra (Yield Alto)", f"{max_y:.2f}%")
                        c2.metric("Zona Neutra", f"{valid_y.median():.2f}%")
                        c3.metric("Zona Venta (Yield Bajo)", f"{min_y:.2f}%")
                        
                        # Gráfico con relleno
                        fig_w = go.Figure()
                        # Techo (Rojo)
                        fig_w.add_trace(go.Scatter(x=df_w.index, y=df_w['Overvalued'], mode='lines', name='Zona Venta', line=dict(color='rgba(231, 76, 60, 0.5)', dash='dot')))
                        # Suelo (Verde) + Relleno medio
                        fig_w.add_trace(go.Scatter(x=df_w.index, y=df_w['Undervalued'], mode='lines', name='Zona Compra', line=dict(color='rgba(0, 184, 148, 0.5)', dash='dot'), fill='tonexty', fillcolor='rgba(255,255,255,0)'))
                        # Relleno Zona Compra (abajo)
                        fig_w.add_trace(go.Scatter(x=df_w.index, y=df_w['Undervalued']*0.01, mode='lines', line=dict(width=0), showlegend=False)) # Base falsa
                        fig_w.add_trace(go.Scatter(x=df_w.index, y=df_w['Undervalued'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(0, 184, 148, 0.1)', showlegend=False))
                        
                        fig_w.add_trace(go.Scatter(x=df_w.index, y=df_w['Close'], mode='lines', name='Precio', line=dict(color='#2d3436', width=2)))
                        fig_w.update_layout(title="Canal de Valoración Geraldine Weiss (10Y)", height=500, yaxis_range=[df_w['Close'].min()*0.8, df_w['Close'].max()*1.2])
                        st.plotly_chart(fig_w, use_container_width=True)
                        st.caption("💡 Si el precio toca la zona sombreada verde inferior, es señal de compra.")
                    else: st.warning("Datos insuficientes para gráfico.")
            except: st.warning("Error al generar gráfico Weiss.")
        else: st.warning("⚠️ Sin historial de dividendos suficiente.")

    # TAB 3: FUNDAMENTALES (NUEVO VALUÓMETRO)
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔎 Valuómetro: ¿Cara o Barata respecto a su historia?")
        st.markdown("Posición actual respecto al rango de los últimos 10 años.")
        
        metrics_check = [
            ("PER (Price to Earnings)", info.get('trailingPE'), 'PER'),
            ("Price to Sales (P/S)", info.get('priceToSalesTrailing12Months'), 'Price/Sales'),
            ("Price to Book (P/B)", info.get('priceToBook'), 'Price/Book')
        ]
        
        found = False
        for label, curr, key in metrics_check:
            if key in hist_ratios and curr is not None:
                dat = hist_ratios[key]
                valuation_meter(label, curr, dat['median'], dat['min'], dat['max'])
                found = True
        
        if not found: st.warning("⚠️ No hay suficientes datos históricos para el Valuómetro.")
        st.markdown("---")
        st.caption("💡 Barra Verde/Roja indica si cotiza por debajo/encima de su mediana histórica.")
