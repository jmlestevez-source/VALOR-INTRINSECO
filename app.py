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
st.set_page_config(page_title="Valuación Master", layout="wide", page_icon="💎")

# --- ESTILOS CSS (MANTENIDOS EXACTAMENTE IGUAL) ---
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

    /* ALERTAS PERSONALIZADAS */
    .alert-box {
        padding: 20px;
        border-radius: 12px;
        margin: 15px 0;
        border-left: 5px solid;
        font-size: 18px;
        line-height: 1.6;
    }
    .alert-danger { background-color: #fee; border-color: #e74c3c; color: #c0392b; }
    .alert-warning { background-color: #fef9e7; border-color: #f39c12; color: #d68910; }
    .alert-info { background-color: #eaf2f8; border-color: #3498db; color: #2471a3; }
    .alert-success { background-color: #e8f8f5; border-color: #00b894; color: #00875a; }

    /* TABLAS GIGANTES */
    .stTable { font-size: 22px !important; }
    thead tr th { font-size: 24px !important; background-color: #f8f9fa !important; padding: 20px !important;}
    tbody tr td { font-size: 22px !important; padding: 20px !important; }

    /* PESTAÑAS */
    .stTabs [data-baseweb="tab"] {
        font-size: 26px !important;
        padding: 15px 30px !important;
    }
    
    /* ESCENARIOS */
    .scenario-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        padding: 25px;
        color: white;
        margin: 10px 0;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    .scenario-bull { background: linear-gradient(135deg, #00b894 0%, #00cec9 100%); }
    .scenario-base { background: linear-gradient(135deg, #fdcb6e 0%, #e17055 100%); }
    .scenario-bear { background: linear-gradient(135deg, #d63031 0%, #e84393 100%); }
    
    .scenario-title { font-size: 28px; font-weight: 800; margin-bottom: 10px; }
    .scenario-price { font-size: 42px; font-weight: 900; margin: 10px 0; }
    .scenario-cagr { font-size: 24px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- 1. FUNCIONES DE SCRAPING ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    """Scraping robusto usando BeautifulSoup"""
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            target_label = soup.find(string="EPS next 5Y")
            if target_label:
                label_td = target_label.parent
                value_td = label_td.find_next_sibling('td')
                if value_td and value_td.text:
                    clean_text = value_td.text.replace('%', '').strip()
                    if clean_text != '-':
                        return float(clean_text)
    except Exception as e:
        return None
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_growth(ticker):
    """Backup: StockAnalysis.com"""
    try:
        ticker_clean = ticker.upper()
        url = f"https://stockanalysis.com/stocks/{ticker_clean.lower()}/forecast/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()
            pattern = r'(\d+\.?\d*)%\s*(?:annual|avg|average|growth)'
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                for match in matches:
                    val = float(match)
                    if 0 < val < 100: return val
    except:
        pass
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=5):
    """
    MODIFICADO: Cálculo de ratios históricos usando MEDIANA y filtrado de outliers.
    Esto corrige el problema de PERs históricos demasiado elevados.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Intentamos obtener datos trimestrales para mayor precisión (TTM)
        hist = stock.history(period=f"{years}y", interval="1mo")
        if hist.empty: return {}
        
        # Limpiar zona horaria
        if hist.index.tz is not None: hist.index = hist.index.tz_localize(None)
        
        # Obtener financieros (preferiblemente trimestrales para evitar lags anuales grandes)
        fin_q = stock.quarterly_financials.T
        if fin_q.empty:
            fin = stock.financials.T # Fallback a anual
        else:
            fin = fin_q
            
        if fin.empty: return {}
        
        # Limpiar índice financieros
        fin.index = pd.to_datetime(fin.index)
        if fin.index.tz is not None: fin.index = fin.index.tz_localize(None)
        fin = fin.sort_index()
        
        # Preparar Dataframe base
        df_merge = pd.DataFrame(index=hist.index)
        df_merge['Price'] = hist['Close']
        
        metrics_fin = pd.DataFrame(index=fin.index)
        
        # EPS Logic (Rolling TTM si es trimestral, o forward fill si es anual)
        if 'Diluted EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Diluted EPS']
        elif 'Basic EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Basic EPS']
            
        # Si tenemos datos trimestrales, hacemos suma rolling de 4 trimestres
        if not fin_q.empty and 'EPS' in metrics_fin.columns:
            metrics_fin['EPS'] = metrics_fin['EPS'].rolling(4).sum()

        # Ventas y otros datos...
        rev = fin.get('Total Revenue')
        shares = fin.get('Basic Average Shares') or fin.get('Share Issued') or fin.get('Ordinary Shares Number')
        
        if rev is not None and shares is not None:
            # Rolling TTM para revenue si es trimestral
            if not fin_q.empty: rev = rev.rolling(4).sum()
            metrics_fin['RPS'] = rev / shares

        if 'Total Assets' in fin.columns: # Book Value (usualmente snapshot, no rolling)
            assets = fin.get('Total Assets')
            liab = fin.get('Total Liabilities Net Minority Interest')
            if assets is not None and liab is not None and shares is not None:
                metrics_fin['BVPS'] = (assets - liab) / shares

        # UNIÓN DE DATOS
        # Usamos reindex con ffill para asignar el último dato financiero conocido al precio mensual
        metrics_aligned = metrics_fin.reindex(df_merge.index, method='ffill')
        df_final = df_merge.join(metrics_aligned, lsuffix='_price', rsuffix='_fin')
        
        ratios = {}
        
        # --- CÁLCULO PER CORREGIDO (MEDIANA) ---
        if 'EPS' in df_final.columns:
            df_final['PE_Ratio'] = df_final['Price'] / df_final['EPS']
            # Filtro estricto: Solo PER positivo y menor a 150 para quitar ruido
            valid_pe = df_final['PE_Ratio'][(df_final['PE_Ratio'] > 0) & (df_final['PE_Ratio'] < 150)]
            
            if not valid_pe.empty:
                # ¡AQUÍ ESTÁ EL CAMBIO! Usamos median() en vez de mean()
                ratios['PER'] = float(valid_pe.median())
                
                # Datos extra para Geraldine Weiss (Min y Max históricos filtrados)
                ratios['PER_Min'] = float(valid_pe.quantile(0.05))
                ratios['PER_Max'] = float(valid_pe.quantile(0.95))

        # --- Price to Sales (Mediana) ---
        if 'RPS' in df_final.columns:
            df_final['PS_Ratio'] = df_final['Price'] / df_final['RPS']
            valid_ps = df_final['PS_Ratio'][(df_final['PS_Ratio'] > 0) & (df_final['PS_Ratio'] < 50)]
            if not valid_ps.empty:
                ratios['Price/Sales'] = float(valid_ps.median())

        # --- Price to Book (Mediana) ---
        if 'BVPS' in df_final.columns:
            df_final['PB_Ratio'] = df_final['Price'] / df_final['BVPS']
            valid_pb = df_final['PB_Ratio'][(df_final['PB_Ratio'] > 0) & (df_final['PB_Ratio'] < 50)]
            if not valid_pb.empty:
                ratios['Price/Book'] = float(valid_pb.median())

        return ratios
        
    except Exception as e:
        return {}

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    """Análisis completo con fuentes múltiples"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('regularMarketPreviousClose')
        if not price or price == 0: return None
        
        # Datos de Dividendos para Weiss
        div_rate = info.get('dividendRate', 0)
        current_yield = (div_rate / price) if (div_rate and price > 0) else 0
        
        # Histórico de dividendos real para gráfica Weiss
        hist_divs = stock.dividends
        
        # Calcular medias históricas
        hist_ratios = calculate_robust_ratios(ticker, years_hist)
        
        finviz_g = get_finviz_growth(ticker)
        if finviz_g is None:
            finviz_g = get_stockanalysis_growth(ticker)
        
        # Usar la mediana calculada como principal, si falla usar trailingPE de Yahoo
        pe_mean = hist_ratios.get('PER')
        if pe_mean is None or pd.isna(pe_mean):
            pe_mean = info.get('trailingPE', 15.0)
        
        # Extraer yields históricos para media de 5 años de forma más precisa
        if not hist_divs.empty and len(hist_divs) > 20:
             # Cálculo aproximado yield medio 5y basado en dividendos reales y precio aproximado
             avg_5y_yield = info.get('fiveYearAvgDividendYield', 0)
             if avg_5y_yield and avg_5y_yield > 0.5:
                 avg_5y_yield = avg_5y_yield / 100 # Normalizar a decimal
             else:
                 avg_5y_yield = 0
        else:
            avg_5y_yield = 0

        return {
            'info': info, 
            'price': float(price), 
            'pe_mean': float(pe_mean),
            'div_data': {
                'current': float(current_yield), 
                'avg_5y': float(avg_5y_yield), 
                'rate': float(div_rate),
                'history': hist_divs # Pasamos el objeto Series
            },
            'hist_ratios': hist_ratios, 
            'finviz_growth': finviz_g,
            'ticker': ticker
        }
        
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None

# --- 2. FUNCIONES DE ALERTAS Y VALIDACIÓN ---

def show_alert(message, alert_type="info"):
    class_map = {"danger": "alert-danger", "warning": "alert-warning", "info": "alert-info", "success": "alert-success"}
    icon_map = {"danger": "🚨", "warning": "⚠️", "info": "ℹ️", "success": "✅"}
    st.markdown(f"""<div class="alert-box {class_map[alert_type]}"><strong>{icon_map[alert_type]} {message}</strong></div>""", unsafe_allow_html=True)

def validate_projection(growth, exit_pe, cagr, price, shares_outstanding):
    warnings = []
    if growth > 25: warnings.append({"type": "warning", "msg": f"<b>Crecimiento de {growth:.1f}%</b> es muy agresivo."})
    if exit_pe > 40: warnings.append({"type": "warning", "msg": f"<b>PER de {exit_pe:.1f}x</b> sugiere valoración premium."})
    if cagr > 25: warnings.append({"type": "warning", "msg": f"<b>CAGR de {cagr:.1f}%</b> es excelente pero ambicioso."})
    return warnings

def calculate_historical_cagr(ticker, years=5):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{years}y")
        if len(hist) < 250: return None
        start, end = hist['Close'].iloc[0], hist['Close'].iloc[-1]
        actual_years = len(hist) / 252
        if start > 0: return ((end / start) ** (1/actual_years) - 1) * 100
    except: return None
    return None

# --- 3. COMPONENTES VISUALES ---

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
    st.markdown(f"""<div class="scenario-card {css_class}"><div class="scenario-title">{title}</div><div class="scenario-price">${price_proj:,.2f}</div><div class="scenario-cagr">CAGR: {cagr:.1f}%</div><div style="margin-top:15px; font-size:18px; opacity:0.9;">Growth: {growth:.1f}% | Exit PER: {exit_pe:.1f}x</div></div>""", unsafe_allow_html=True)

# --- 4. MAIN APP ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper().strip()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)

if ticker:
    with st.spinner(f'⚙️ Procesando datos financieros para {ticker}...'):
        data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("❌ Error: No se pudo obtener información del Ticker.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    hist_ratios = data['hist_ratios']
    finviz_g = data['finviz_growth']
    ticker_symbol = data['ticker']
    shares = info.get('sharesOutstanding', 0)
    default_g = finviz_g if finviz_g else 10.0
    
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        if finviz_g: st.success(f"✅ Finviz EPS next 5Y: **{finviz_g}%**")
        else: st.info("ℹ️ Usando estimación manual")

    eps = info.get('trailingEps', 0)
    if eps is None or eps == 0: eps = info.get('forwardEps', 1)
    if eps is None: eps = 1
        
    fair_value = float(eps) * pe_mean
    
    # HEADER
    st.title(f"📊 {info.get('shortName', ticker)}")
    st.markdown(f"### **{info.get('sector', 'N/A')}**  •  {info.get('industry', 'N/A')}")
    st.markdown("---")

    # 1. VEREDICTO
    verdict_box(price, fair_value)

    # 2. BIG CARDS
    c1, c2, c3, c4 = st.columns(4)
    with c1: card_html("Cotización", f"${price:.2f}")
    with c2: card_html("Valor Razonable", f"${fair_value:.2f}", f"PER Medio (Mediana): {pe_mean:.1f}x", "neu")
    with c3:
        target = info.get('targetMeanPrice', 0)
        if target and target > 0:
            pot = ((target - price)/price)*100
            col = "pos" if pot > 0 else "neg"
            card_html("Obj. Analistas", f"${target:.2f}", f"{pot:+.1f}% Potencial", col)
        else: card_html("Obj. Analistas", "N/A")
    with c4:
        curr, avg = divs['current'], divs['avg_5y']
        col = "pos" if (curr > 0 and curr > avg) else "neu"
        sub = f"Media: {avg*100:.2f}%" if avg > 0 else "Sin historial"
        card_html("Div. Yield", f"{curr*100:.2f}%", sub, col)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # 3. PESTAÑAS
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 DIVIDENDOS (WEISS)", "📊 FUNDAMENTALES VS MEDIA"])
    
    # TAB 1: PROYECCIÓN
    with t1:
        st.markdown("<br>", unsafe_allow_html=True)
        cc1, cc2 = st.columns([1, 2])
        
        with cc1:
            st.subheader("📝 Calculadora")
            st.markdown(f"""
            <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border:1px solid #ddd;'>
                <p style='font-size:20px'>EPS Actual: <b>${eps:.2f}</b></p>
                <p style='font-size:20px'>Crecimiento Estimado: <b>{growth_input}%</b></p>
                <p style='font-size:20px'>PER Salida Estimado: <b>{pe_mean:.1f}x</b></p>
            </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            exit_pe = st.number_input("Ajustar PER Salida", value=float(round(pe_mean, 1)), step=0.5)
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100 if price > 0 else 0
            
            st.markdown("---")
            st.markdown(f"<div style='font-size:32px; margin-bottom:10px'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            c_col = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:32px'>CAGR Esperado: <b style='color:{c_col}; font-size:48px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
            
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            fig = go.Figure(go.Scatter(x=yrs, y=vals, mode='lines+markers', line=dict(color='#0984e3', width=6), marker=dict(size=16)))
            fig.update_layout(title={'text': "Curva de Valor Teórico", 'font': {'size': 28}}, font=dict(size=20), height=450)
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🔍 Validación de Supuestos")
        warnings = validate_projection(growth_input, exit_pe, cagr, price, shares)
        if warnings:
            for w in warnings: show_alert(w['msg'], w['type'])
        else: show_alert("✅ Supuestos dentro de rangos razonables", "success")
        
        st.markdown("---")
        st.subheader("🎲 Escenarios Múltiples")
        scenarios = {
            "🚀 Bull Case": {"growth": growth_input, "pe": exit_pe, "type": "bull"},
            "🎯 Base Case": {"growth": growth_input * 0.7, "pe": exit_pe * 0.8, "type": "base"},
            "🐻 Bear Case": {"growth": max(5, growth_input * 0.4), "pe": exit_pe * 0.6, "type": "bear"}
        }
        cols_esc = st.columns(3)
        for idx, (name, params) in enumerate(scenarios.items()):
            with cols_esc[idx]:
                f_eps_s = eps * ((1 + params["growth"]/100)**5)
                f_price_s = f_eps_s * params["pe"]
                cagr_s = ((f_price_s/price)**(1/5)-1)*100 if price > 0 else 0
                scenario_card(name, f_price_s, cagr_s, params["growth"], params["pe"], params["type"])

    # TAB 2: DIVIDENDOS (MODIFICADO - WEISS MEJORADO)
    with t2:
        st.markdown("<br>", unsafe_allow_html=True)
        
        has_dividends = divs['rate'] and divs['rate'] > 0 and not divs['history'].empty
        
        if has_dividends:
            # Preparación de datos para gráfico de Weiss
            # Obtener historial de precios
            try:
                stock_obj = yf.Ticker(ticker)
                # Traemos más historia para calcular bien el canal (10y)
                hist_w = stock_obj.history(period="10y")
                div_hist = divs['history']
                
                if not hist_w.empty and not div_hist.empty:
                    # Alinear dividendos con fechas de precio
                    # Crear serie diaria de dividendos (rolling TTM)
                    # Esto es aproximado: Dividendo anualizado en cada punto
                    div_series = div_hist.reindex(hist_w.index, method='ffill').fillna(0)
                    # Para suavizar, tomamos la tasa anual aproximada en ese momento
                    # (Usando rolling mean de dividendos no es exacto para yield, mejor usar el dividendo TTM real)
                    # Simplificación robusta: Usar el dividendo acumulado últimos 365 dias
                    
                    # Unir div history con price history
                    df_weiss = pd.DataFrame(index=hist_w.index)
                    df_weiss['Close'] = hist_w['Close']
                    
                    # Asignar dividendos en fechas
                    div_events = pd.DataFrame(div_hist)
                    div_events.columns = ['Div']
                    # Acumulado anual (rolling sum 365 dias aprox 252 ruedas)
                    # Necesitamos reindexar div_events al índice diario completo primero
                    daily_idx = pd.date_range(start=hist_w.index[0], end=hist_w.index[-1])
                    div_daily = div_hist.reindex(daily_idx).fillna(0)
                    div_ttm_daily = div_daily.rolling(window=365).sum() # Dividendo pagado últimos 365 días naturales
                    
                    # Volver a alinear con los días de trading
                    df_weiss['Div_TTM'] = div_ttm_daily.reindex(hist_w.index).ffill()
                    
                    # Calcular Yield histórico diario
                    df_weiss['Yield'] = (df_weiss['Div_TTM'] / df_weiss['Close']) * 100
                    
                    # Filtrar yields absurdos (errores de datos)
                    valid_yields = df_weiss['Yield'][(df_weiss['Yield'] > 0.1) & (df_weiss['Yield'] < 20)]
                    
                    if not valid_yields.empty:
                        min_y = valid_yields.quantile(0.05) # Zona cara (yield bajo)
                        max_y = valid_yields.quantile(0.95) # Zona barata (yield alto)
                        avg_y = valid_yields.median()
                        
                        # Calcular precios teóricos
                        df_weiss['Price_Undervalued'] = (df_weiss['Div_TTM'] / max_y) * 100 # Línea verde (Suelo)
                        df_weiss['Price_Overvalued'] = (df_weiss['Div_TTM'] / min_y) * 100  # Línea roja (Techo)
                        
                        # MÉTRICAS PRINCIPALES
                        cd1, cd2, cd3 = st.columns(3)
                        curr_y = divs['current'] * 100
                        
                        with cd1:
                            st.markdown(f"### 🟢 Zona Compra (Yield > {max_y:.2f}%)")
                            st.markdown(f"Precio Objetivo: **${(divs['rate']/(max_y/100)):.2f}**")
                        with cd2:
                            st.markdown(f"### ⚖️ Zona Media (Yield ~ {avg_y:.2f}%)")
                            st.markdown(f"Precio Justo: **${(divs['rate']/(avg_y/100)):.2f}**")
                        with cd3:
                            st.markdown(f"### 🔴 Zona Venta (Yield < {min_y:.2f}%)")
                            st.markdown(f"Precio Riesgo: **${(divs['rate']/(min_y/100)):.2f}**")

                        st.markdown("<br>", unsafe_allow_html=True)

                        # GRÁFICO MEJORADO (CON BANDAS RELLENAS)
                        fig_w = go.Figure()
                        
                        # 1. Banda de Sobrevaloración (Rojo tenue)
                        # Rellenamos desde el "Techo" hasta arriba del gráfico (o un valor alto)
                        # Plotly fill es 'tonexty', así que dibujamos primero el techo
                        
                        # Línea Techo (Precio si Yield es mínimo - CARO)
                        fig_w.add_trace(go.Scatter(
                            x=df_weiss.index, y=df_weiss['Price_Overvalued'],
                            mode='lines', name='Zona Venta (Yield Mínimo)',
                            line=dict(color='rgba(231, 76, 60, 0.5)', width=1, dash='dot')
                        ))
                        
                        # Línea Suelo (Precio si Yield es máximo - BARATO)
                        fig_w.add_trace(go.Scatter(
                            x=df_weiss.index, y=df_weiss['Price_Undervalued'],
                            mode='lines', name='Zona Compra (Yield Máximo)',
                            line=dict(color='rgba(0, 184, 148, 0.5)', width=1, dash='dot'),
                            fill='tonexty', # Rellena hasta la linea anterior (Techo) -> Zona neutral
                            fillcolor='rgba(255, 255, 255, 0)' # Transparente en medio
                        ))
                        
                        # Zona Compra (Verde abajo)
                        # Truco visual: Dibujamos una linea muy abajo (0) y rellenamos hasta el suelo
                        fig_w.add_trace(go.Scatter(
                            x=df_weiss.index, y=[0]*len(df_weiss),
                            mode='lines', showlegend=False, line=dict(width=0),
                            hoverinfo='skip'
                        ))
                        fig_w.add_trace(go.Scatter(
                            x=df_weiss.index, y=df_weiss['Price_Undervalued'],
                            mode='lines', showlegend=False, line=dict(width=0),
                            fill='tonexty', 
                            fillcolor='rgba(0, 184, 148, 0.1)', # Verde muy suave fondo
                            hoverinfo='skip'
                        ))
                        
                        # Zona Venta (Rojo arriba) - Visualmente más difícil de acotar hacia infinito
                        # Lo simulamos coloreando el área entre el precio y el techo si el precio lo supera
                        
                        # PRECIO REAL
                        fig_w.add_trace(go.Scatter(
                            x=df_weiss.index, y=df_weiss['Close'],
                            mode='lines', name='Precio Real',
                            line=dict(color='#2d3436', width=3)
                        ))

                        fig_w.update_layout(
                            title={'text': f"Canal de Valoración Geraldine Weiss (10 Años)", 'font': {'size': 24}},
                            yaxis_title="Precio ($)",
                            hovermode="x unified",
                            height=550,
                            legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0.5, xanchor="center")
                        )
                        
                        # Zoom automático para que se vea bien (evitar el 0)
                        y_min = df_weiss['Close'].min() * 0.8
                        y_max = df_weiss['Close'].max() * 1.2
                        fig_w.update_yaxes(range=[y_min, y_max])
                        
                        st.plotly_chart(fig_w, use_container_width=True)
                        
                        st.caption("💡 **Interpretación:** Si la línea negra (Precio) entra en la zona sombreada verde inferior, el dividendo es históricamente alto (compra). Si toca la línea roja superior, el dividendo es bajo (venta).")
                    else:
                        st.warning("Datos de yield insuficientes para gráfico histórico.")
                else:
                    st.warning("No hay historial suficiente para generar el gráfico de Weiss.")
            except Exception as e:
                st.error(f"Error generando gráfico Weiss: {e}")
                
        else:
            st.warning("⚠️ Esta empresa no paga dividendos o no tiene historial suficiente para el modelo de Geraldine Weiss.")

    # TAB 3: RATIOS
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔎 Análisis Fundamental vs Histórico")
        st.info("ℹ️ **Actual** = Yahoo Finance | **Media Histórica** = Mediana de últimos años (sin valores extremos)")
        
        ratios_to_show = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': hist_ratios.get('PER')},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': hist_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': hist_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': hist_ratios.get('EV/EBITDA')}
        }
        
        rows = []
        for name, vals in ratios_to_show.items():
            curr, avg = vals['curr'], vals['avg']
            if curr and not pd.isna(curr) and avg and not pd.isna(avg):
                status = "🟢 Barato" if curr < avg else "🔴 Caro"
                diff = ((curr-avg)/avg)*100
                rows.append([name, f"{curr:.2f}", f"{avg:.2f}", f"{diff:+.1f}%", status])
            elif curr and not pd.isna(curr):
                rows.append([name, f"{curr:.2f}", "N/A", "-", "⚪ Sin datos"])
            else:
                rows.append([name, "N/A", "N/A", "-", "⚪ Sin datos"])
        
        if rows:
            st.table(pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Desviación', 'Diagnóstico']))
        else:
            st.warning("No hay datos de ratios disponibles.")

    # Footer
    st.markdown("---")
    st.markdown(f"""<div style='text-align:center; color:#7f8c8d; font-size:16px; padding:20px'>💡 Herramienta educativa. No es consejo financiero.<br>📊 Datos: Yahoo Finance/Finviz | Market Cap: ${(price * shares / 1e9):.2f}B</div>""", unsafe_allow_html=True)
