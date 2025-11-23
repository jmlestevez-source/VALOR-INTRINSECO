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

# --- ESTILOS CSS (BIG FONTS + NUEVOS) ---
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
        'Accept-Language': 'en-US,en;q=0.9',
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
        st.warning(f"⚠️ Error obteniendo datos de Finviz: {e}")
        return None
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_growth(ticker):
    """Backup: StockAnalysis.com"""
    ticker_clean = ticker.upper()
    url = f"https://stockanalysis.com/stocks/{ticker_clean.lower()}/forecast/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        session = requests.Session()
        time.sleep(1)
        r = session.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.content, 'html.parser')
        text = soup.get_text()
        pattern = r'(\d+\.?\d*)%\s*(?:annual|avg|average|growth)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            for match in matches:
                try:
                    val = float(match)
                    if 0 < val < 100:
                        return val
                except:
                    pass
                    
    except Exception as e:
        pass
    
    return None

@st.cache_data(ttl=3600)
def calculate_robust_ratios(ticker, years=5):
    """Cálculo interno de ratios históricos"""
    try:
        stock = yf.Ticker(ticker)
        start_date = (datetime.now() - timedelta(days=years*365 + 30)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        
        if hist.empty: 
            return {}
        
        if hist.index.tz is not None: 
            hist.index = hist.index.tz_localize(None)
        
        try:
            fin = stock.financials.T
            bal = stock.balance_sheet.T
        except:
            return {}
        
        if fin.empty: 
            return {}
        
        fin.index = pd.to_datetime(fin.index)
        if fin.index.tz is not None: 
            fin.index = fin.index.tz_localize(None)
            
        if bal is not None and not bal.empty:
            bal.index = pd.to_datetime(bal.index)
            if bal.index.tz is not None:
                bal.index = bal.index.tz_localize(None)
        
        df_merge = pd.DataFrame(index=hist.index)
        df_merge['Price'] = hist['Close']
        
        metrics_fin = pd.DataFrame(index=fin.index)
        
        if 'Diluted EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Diluted EPS']
        elif 'Basic EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Basic EPS']
        
        rev = fin.get('Total Revenue')
        shares = fin.get('Basic Average Shares')
        if shares is None:
            shares = fin.get('Share Issued')
            
        if rev is not None and shares is not None:
            metrics_fin['RPS'] = rev / shares
        
        if not bal.empty:
            assets = bal.get('Total Assets')
            liab = bal.get('Total Liabilities Net Minority Interest')
            
            if assets is not None and liab is not None and shares is not None:
                metrics_fin['BVPS'] = (assets - liab) / shares
                
            debt = bal.get('Total Debt')
            cash = bal.get('Cash And Cash Equivalents')
            ebitda = fin.get('EBITDA')
            if ebitda is None:
                ebitda = fin.get('Normalized EBITDA')
            
            if debt is not None and cash is not None and ebitda is not None and shares is not None:
                metrics_fin['Debt'] = debt
                metrics_fin['Cash'] = cash
                metrics_fin['EBITDA'] = ebitda
                metrics_fin['Shares'] = shares

        metrics_fin = metrics_fin.sort_index()
        df_merge = df_merge.sort_index()
        
        df_final = df_merge.join(metrics_fin, how='outer').ffill().dropna(subset=['Price'])
        
        ratios = {}
        
        if 'EPS' in df_final.columns:
            df_final['PE_Ratio'] = df_final['Price'] / df_final['EPS']
            valid_pe = df_final['PE_Ratio'][(df_final['PE_Ratio'] > 0) & (df_final['PE_Ratio'] < 200)]
            if not valid_pe.empty and not valid_pe.isna().all():
                ratios['PER'] = float(valid_pe.mean())

        if 'RPS' in df_final.columns:
            df_final['PS_Ratio'] = df_final['Price'] / df_final['RPS']
            valid_ps = df_final['PS_Ratio'][(df_final['PS_Ratio'] > 0) & (df_final['PS_Ratio'] < 50)]
            if not valid_ps.empty and not valid_ps.isna().all():
                ratios['Price/Sales'] = float(valid_ps.mean())

        if 'BVPS' in df_final.columns:
            df_final['PB_Ratio'] = df_final['Price'] / df_final['BVPS']
            valid_pb = df_final['PB_Ratio'][(df_final['PB_Ratio'] > 0) & (df_final['PB_Ratio'] < 50)]
            if not valid_pb.empty and not valid_pb.isna().all():
                ratios['Price/Book'] = float(valid_pb.mean())

        if all(col in df_final.columns for col in ['EBITDA', 'Debt', 'Cash', 'Shares']):
            df_final['EV'] = (df_final['Price'] * df_final['Shares']) + df_final['Debt'] - df_final['Cash']
            df_final['EV_EBITDA'] = df_final['EV'] / df_final['EBITDA']
            valid_ev = df_final['EV_EBITDA'][(df_final['EV_EBITDA'] > 0) & (df_final['EV_EBITDA'] < 100)]
            if not valid_ev.empty and not valid_ev.isna().all():
                ratios['EV/EBITDA'] = float(valid_ev.mean())
        
        return ratios
        
    except Exception as e:
        st.warning(f"⚠️ Error calculando ratios históricos: {e}")
        return {}

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    """Análisis completo con fuentes múltiples - SIN objeto stock"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        price = info.get('currentPrice')
        if not price or price == 0:
            price = info.get('regularMarketPrice')
        if not price or price == 0:
            price = info.get('regularMarketPreviousClose')
        if not price or price == 0:
            return None
        
        div_rate = info.get('dividendRate', 0)
        if div_rate is None:
            div_rate = 0
            
        current_yield = (div_rate / price) if (div_rate and price > 0) else 0
        
        if current_yield == 0:
            raw_y = info.get('dividendYield', 0)
            if raw_y:
                current_yield = raw_y / 100 if raw_y > 0.5 else raw_y
        
        raw_avg = info.get('fiveYearAvgDividendYield', 0)
        avg_5y_yield = (raw_avg / 100 if raw_avg and raw_avg > 0.5 else raw_avg) if raw_avg else 0
        
        hist_ratios = calculate_robust_ratios(ticker, years_hist)
        
        finviz_g = get_finviz_growth(ticker)
        if finviz_g is None:
            finviz_g = get_stockanalysis_growth(ticker)
        
        pe_mean = hist_ratios.get('PER')
        if pe_mean is None or pd.isna(pe_mean):
            pe_mean = info.get('trailingPE')
            if pe_mean is None or pd.isna(pe_mean):
                pe_mean = 15.0
        
        pe_mean = float(pe_mean)

        return {
            'info': info, 
            'price': float(price), 
            'pe_mean': pe_mean,
            'div_data': {
                'current': float(current_yield), 
                'avg_5y': float(avg_5y_yield), 
                'rate': float(div_rate)
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
    """Mostrar alerta personalizada"""
    class_map = {
        "danger": "alert-danger",
        "warning": "alert-warning",
        "info": "alert-info",
        "success": "alert-success"
    }
    
    icon_map = {
        "danger": "🚨",
        "warning": "⚠️",
        "info": "ℹ️",
        "success": "✅"
    }
    
    st.markdown(f"""
    <div class="alert-box {class_map[alert_type]}">
        <strong>{icon_map[alert_type]} {message}</strong>
    </div>
    """, unsafe_allow_html=True)

def validate_projection(growth, exit_pe, cagr, price, shares_outstanding):
    """Validar supuestos de proyección"""
    warnings = []
    
    # 1. Crecimiento extremo
    if growth > 40:
        warnings.append({
            "type": "danger",
            "msg": f"<b>Crecimiento de {growth:.1f}% anual</b> es raramente sostenible durante 5 años. Solo el 1% de empresas lo logra."
        })
    elif growth > 25:
        warnings.append({
            "type": "warning",
            "msg": f"<b>Crecimiento de {growth:.1f}%</b> es muy agresivo. Considera escenarios conservadores."
        })
    
    # 2. PER extremo
    if exit_pe > 60:
        warnings.append({
            "type": "danger",
            "msg": f"<b>PER de {exit_pe:.1f}x</b> es 4x la media del S&P 500 (15x). Riesgo alto de compresión múltiple."
        })
    elif exit_pe > 40:
        warnings.append({
            "type": "warning",
            "msg": f"<b>PER de {exit_pe:.1f}x</b> sugiere valoración premium. Espera volatilidad."
        })
    
    # 3. CAGR extremo
    if cagr > 40:
        warnings.append({
            "type": "danger",
            "msg": f"<b>CAGR de {cagr:.1f}%</b> implicaría superar a Warren Buffett (promedio 20% en 60 años)."
        })
    elif cagr > 25:
        warnings.append({
            "type": "warning",
            "msg": f"<b>CAGR de {cagr:.1f}%</b> es excelente pero ambicioso. Verifica supuestos."
        })
    
    # 4. Market Cap check
    if shares_outstanding and shares_outstanding > 0:
        current_mcap = price * shares_outstanding
        projected_price = price * ((1 + cagr/100)**5)
        projected_mcap = projected_price * shares_outstanding
        
        if projected_mcap > current_mcap * 8:
            mcap_t = projected_mcap / 1e12
            warnings.append({
                "type": "danger",
                "msg": f"""<b>Market Cap proyectado: ${mcap_t:.2f} TRILLONES</b><br>
                Para contexto: PIB USA = $27T, Apple máximo = $3.5T<br>
                Esta valoración implica que la empresa valdría más que las 10 mayores de hoy."""
            })
        elif projected_mcap > current_mcap * 5:
            warnings.append({
                "type": "warning",
                "msg": f"<b>Market Cap se multiplicaría por {projected_mcap/current_mcap:.1f}x</b> - Requiere dominio total del sector."
            })
    
    return warnings

def calculate_historical_cagr(ticker, years=5):
    """Calcular CAGR histórico de la acción"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{years}y")
        if len(hist) < 250:  # Al menos 1 año de datos
            return None
        
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        actual_years = len(hist) / 252
        
        if start_price > 0:
            cagr = ((end_price / start_price) ** (1/actual_years) - 1) * 100
            return cagr
    except:
        return None
    
    return None

# --- 3. COMPONENTES VISUALES ---

def card_html(label, value, sub_value=None, color_class="neu"):
    """Tarjeta métrica HTML"""
    sub_html = f"<div class='metric-sub {color_class}'>{sub_value}</div>" if sub_value else ""
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>{label}</div>
        <div class='metric-value'>{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

def verdict_box(price, fair_value):
    """Caja de veredicto"""
    margin = ((fair_value - price) / price) * 100
    if margin > 15:
        css = "v-undervalued"
        title = "💎 OPORTUNIDAD"
        main = "INFRAVALORADA"
        icon = "🚀"
        desc = f"Descuento del {margin:.1f}%"
    elif margin < -15:
        css = "v-overvalued"
        title = "⚠️ CUIDADO"
        main = "SOBREVALORADA"
        icon = "🛑"
        desc = f"Prima del {abs(margin):.1f}%"
    else:
        css = "v-fair"
        title = "⚖️ EQUILIBRIO"
        main = "PRECIO JUSTO"
        icon = "✅"
        desc = f"Cotizando cerca de su valor"

    st.markdown(f"""
    <div class="verdict-box {css}">
        <div class="v-title">{title}</div>
        <div class="v-main">{icon} {main}</div>
        <div class="v-desc">{desc} (Fair: ${fair_value:.2f})</div>
    </div>
    """, unsafe_allow_html=True)

def scenario_card(title, price_proj, cagr, growth, exit_pe, scenario_type="base"):
    """Tarjeta de escenario"""
    css_class = f"scenario-{scenario_type}"
    
    st.markdown(f"""
    <div class="scenario-card {css_class}">
        <div class="scenario-title">{title}</div>
        <div class="scenario-price">${price_proj:,.2f}</div>
        <div class="scenario-cagr">CAGR: {cagr:.1f}%</div>
        <div style="margin-top:15px; font-size:18px; opacity:0.9;">
            Growth: {growth:.1f}% | Exit PER: {exit_pe:.1f}x
        </div>
    </div>
    """, unsafe_allow_html=True)

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
        st.error("❌ Error: No se pudo obtener información del Ticker. Verifica que sea válido.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    hist_ratios = data['hist_ratios']
    finviz_g = data['finviz_growth']
    ticker_symbol = data['ticker']
    
    # Shares outstanding
    shares = info.get('sharesOutstanding', 0)
    
    # Crecimiento
    default_g = finviz_g if finviz_g else 10.0
    
    with st.sidebar:
        st.subheader("⚙️ Proyección")
        growth_input = st.number_input("Crecimiento (5y) %", value=float(default_g), step=0.5)
        
        if finviz_g:
            st.success(f"✅ Finviz EPS next 5Y: **{finviz_g}%**")
        else:
            st.warning("⚠️ No se pudo obtener de Finviz")
            st.info("ℹ️ Usando estimación manual")

    # EPS y Fair Value
    eps = info.get('trailingEps', 0)
    if eps is None or eps == 0:
        eps = info.get('forwardEps', 1)
    if eps is None:
        eps = 1
        
    fair_value = float(eps) * pe_mean
    
    # HEADER
    st.title(f"📊 {info.get('shortName', ticker)}")
    st.markdown(f"### **{info.get('sector', 'N/A')}**  •  {info.get('industry', 'N/A')}")
    st.markdown("---")

    # 1. VEREDICTO
    verdict_box(price, fair_value)

    # 2. BIG CARDS
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        card_html("Cotización", f"${price:.2f}")
        
    with c2:
        card_html("Valor Razonable", f"${fair_value:.2f}", f"PER Medio: {pe_mean:.1f}x", "neu")
        
    with c3:
        target = info.get('targetMeanPrice', 0)
        if target and target > 0:
            pot = ((target - price)/price)*100
            col = "pos" if pot > 0 else "neg"
            card_html("Obj. Analistas", f"${target:.2f}", f"{pot:+.1f}% Potencial", col)
        else:
            card_html("Obj. Analistas", "N/A")
            
    with c4:
        curr, avg = divs['current'], divs['avg_5y']
        v_c = curr if curr else 0
        v_a = avg if avg else 0
        col = "pos" if (v_c > 0 and v_c > v_a) else "neu"
        sub = f"Media: {v_a*100:.2f}%" if v_a > 0 else "Sin historial"
        card_html("Div. Yield", f"{v_c*100:.2f}%", sub, col)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # 3. PESTAÑAS
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 DIVIDENDOS", "📊 FUNDAMENTALES VS MEDIA"])
    
    # TAB 1: PROYECCIÓN MEJORADA
    with t1:
        st.markdown("<br>", unsafe_allow_html=True)
        
        # CALCULADORA + VALIDACIÓN
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
            
            if price > 0:
                cagr = ((f_price/price)**(1/5)-1)*100
            else:
                cagr = 0
            
            st.markdown("---")
            st.markdown(f"<div style='font-size:32px; margin-bottom:10px'>Precio 2029: <b>${f_price:.2f}</b></div>", unsafe_allow_html=True)
            c_col = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:32px'>CAGR Esperado: <b style='color:{c_col}; font-size:48px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
            
        with cc2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            
            fig = go.Figure(go.Scatter(
                x=yrs, y=vals, 
                mode='lines+markers', 
                line=dict(color='#0984e3', width=6), 
                marker=dict(size=16)
            ))
            fig.update_layout(
                title={'text': "Curva de Valor Teórico", 'font': {'size': 28}},
                font=dict(size=20),
                height=450,
                yaxis_title="Precio ($)",
                xaxis_title="Año"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # VALIDACIÓN Y ALERTAS
        st.markdown("---")
        st.subheader("🔍 Validación de Supuestos")
        
        warnings = validate_projection(growth_input, exit_pe, cagr, price, shares)
        
        if warnings:
            for w in warnings:
                show_alert(w['msg'], w['type'])
        else:
            show_alert("✅ Supuestos dentro de rangos razonables", "success")
        
        # COMPARACIÓN CON HISTÓRICO
        hist_cagr = calculate_historical_cagr(ticker_symbol, 5)
        if hist_cagr:
            st.markdown("---")
            st.subheader("📈 Comparación con Histórico")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("CAGR Histórico (5Y)", f"{hist_cagr:.1f}%")
            with col2:
                st.metric("CAGR Proyectado", f"{cagr:.1f}%")
            with col3:
                diff = cagr - hist_cagr
                st.metric("Diferencia", f"{diff:+.1f}%", 
                         delta=f"{'Más agresivo' if diff > 0 else 'Más conservador'}")
            
            if cagr > hist_cagr * 1.5:
                show_alert(
                    f"Tu proyección ({cagr:.1f}%) supera en 50%+ el rendimiento histórico ({hist_cagr:.1f}%). "
                    "Verifica si hay catalizadores nuevos que justifiquen esta aceleración.",
                    "warning"
                )
        
        # ESCENARIOS MÚLTIPLES
        st.markdown("---")
        st.subheader("🎲 Escenarios Múltiples")
        
        scenarios = {
            "🚀 Bull Case": {
                "growth": growth_input,
                "pe": exit_pe,
                "type": "bull"
            },
            "🎯 Base Case": {
                "growth": growth_input * 0.7,
                "pe": exit_pe * 0.8,
                "type": "base"
            },
            "🐻 Bear Case": {
                "growth": max(5, growth_input * 0.4),
                "pe": exit_pe * 0.6,
                "type": "bear"
            }
        }
        
        cols_esc = st.columns(3)
        
        for idx, (name, params) in enumerate(scenarios.items()):
            with cols_esc[idx]:
                f_eps_s = eps * ((1 + params["growth"]/100)**5)
                f_price_s = f_eps_s * params["pe"]
                cagr_s = ((f_price_s/price)**(1/5)-1)*100 if price > 0 else 0
                
                scenario_card(name, f_price_s, cagr_s, params["growth"], params["pe"], params["type"])
        
        st.caption("💡 **Bull Case** = Tus supuestos actuales | **Base Case** = Escenario más probable | **Bear Case** = Escenario defensivo")
        
        # TABLA DE SENSIBILIDAD
        st.markdown("---")
        st.subheader("📊 Análisis de Sensibilidad")
        
        growth_scenarios = [10, 20, 30, 40, 50]
        pe_scenarios = [20, 30, 40, 50, 60, 70]
        
        sensitivity_data = []
        for g in growth_scenarios:
            row = []
            for pe in pe_scenarios:
                f_eps_sens = eps * ((1 + g/100)**5)
                f_price_sens = f_eps_sens * pe
                cagr_sens = ((f_price_sens/price)**(1/5)-1)*100 if price > 0 else 0
                
                # Colorear según CAGR
                if cagr_sens > 30:
                    color = "🟢"
                elif cagr_sens > 15:
                    color = "🟡"
                else:
                    color = "🔴"
                
                row.append(f"{color} {cagr_sens:.1f}%")
            sensitivity_data.append(row)
        
        df_sens = pd.DataFrame(
            sensitivity_data,
            columns=[f"PER {pe}x" for pe in pe_scenarios],
            index=[f"Growth {g}%" for g in growth_scenarios]
        )
        
        st.dataframe(df_sens, use_container_width=True)
        st.caption("💡 CAGR esperado según diferentes combinaciones | 🟢 Excelente (>30%) | 🟡 Bueno (15-30%) | 🔴 Conservador (<15%)")

    # TAB 2: DIVIDENDOS
    with t2:
        st.markdown("<br>", unsafe_allow_html=True)
        
        if divs['rate'] and divs['rate'] > 0 and divs['avg_5y'] > 0:
            fair_yld = divs['rate'] / divs['avg_5y']
            marg = ((fair_yld - price)/price)*100
            
            cd1, cd2 = st.columns(2)
            
            with cd1:
                st.info("ℹ️ Modelo de Geraldine Weiss (Yield Theory)")
                st.markdown(f"""
                <div style='font-size:26px; line-height:2'>
                    💰 Dividendo Anual: <b>${divs['rate']:.2f}</b><br>
                    📉 Yield Actual: <b>{divs['current']*100:.2f}%</b><br>
                    📊 Media Histórica: <b>{divs['avg_5y']*100:.2f}%</b><br>
                    🏁 Valor por Dividendo: <b style='color:#2980b9'>${fair_yld:.2f}</b>
                </div>
                """, unsafe_allow_html=True)
                
            with cd2:
                fig = go.Figure(go.Bar(
                    x=['Actual', 'Media 5Y'], 
                    y=[divs['current']*100, divs['avg_5y']*100], 
                    marker_color=['#00b894','#b2bec3'], 
                    text=[f"{divs['current']*100:.2f}%", f"{divs['avg_5y']*100:.2f}%"],
                    textposition='outside',
                    textfont={'size': 24}
                ))
                fig.update_layout(
                    title={'text': "Rentabilidad por Dividendo", 'font': {'size': 28}}, 
                    font=dict(size=20), 
                    height=400,
                    yaxis_title="Yield (%)"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ Esta empresa no paga dividendos o no tiene historial suficiente.")

    # TAB 3: RATIOS
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔎 Análisis Fundamental vs Histórico")
        
        st.info("ℹ️ **Actual** = Yahoo Finance (dato directo) | **Media Histórica** = Cálculo interno con datos históricos de YFinance")
        
        ratios_to_show = {
            'PER (P/E)': {
                'curr': info.get('trailingPE'), 
                'avg': hist_ratios.get('PER')
            },
            'Price/Sales': {
                'curr': info.get('priceToSalesTrailing12Months'), 
                'avg': hist_ratios.get('Price/Sales')
            },
            'Price/Book': {
                'curr': info.get('priceToBook'), 
                'avg': hist_ratios.get('Price/Book')
            },
            'EV/EBITDA': {
                'curr': info.get('enterpriseToEbitda'), 
                'avg': hist_ratios.get('EV/EBITDA')
            }
        }
        
        rows = []
        for name, vals in ratios_to_show.items():
            curr = vals['curr']
            avg = vals['avg']
            
            if curr and not pd.isna(curr) and avg and not pd.isna(avg):
                status = "🟢 Barato" if curr < avg else "🔴 Caro"
                diff = ((curr-avg)/avg)*100
                rows.append([name, f"{curr:.2f}", f"{avg:.2f}", f"{diff:+.1f}%", status])
            elif curr and not pd.isna(curr):
                rows.append([name, f"{curr:.2f}", "N/A", "-", "⚪ Sin datos"])
            else:
                rows.append([name, "N/A", "N/A", "-", "⚪ Sin datos"])
        
        if rows:
            df_ratios = pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Desviación', 'Diagnóstico'])
            st.table(df_ratios)
        else:
            st.warning("No hay datos de ratios disponibles para este ticker.")

    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style='text-align:center; color:#7f8c8d; font-size:16px; padding:20px'>
        💡 Esta herramienta es solo educativa. No constituye asesoramiento financiero.<br>
        📊 <b>Fuentes:</b> Yahoo Finance (ratios actuales y históricos) • Finviz (EPS next 5Y)<br>
        🔍 <b>Market Cap actual:</b> ${(price * shares / 1e9):.2f}B | <b>Shares:</b> {shares/1e9:.2f}B
    </div>
    """, unsafe_allow_html=True)
