import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuación Pro Ultra", layout="wide", page_icon="💎")

# --- ESTILOS CSS MODERNOS (BIG FONTS & CARDS) ---
st.markdown("""
    <style>
    /* Fuente Global más grande */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        font-size: 18px;
    }
    
    /* Tarjetas de Métricas */
    .metric-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid #f0f0f0;
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    
    .metric-label { 
        font-size: 14px; 
        color: #888; 
        text-transform: uppercase; 
        font-weight: 600;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }
    .metric-value { 
        font-size: 32px; 
        font-weight: 800; 
        color: #1a1a1a; 
    }
    .metric-sub { font-size: 15px; font-weight: 500; margin-top: 8px; }
    
    /* Colores Semánticos */
    .pos { color: #00b894; } /* Verde Menta */
    .neg { color: #d63031; } /* Rojo Intenso */
    .neu { color: #636e72; } /* Gris */

    /* CAJA DE VEREDICTO (NUEVO DISEÑO) */
    .verdict-box {
        padding: 25px;
        border-radius: 15px;
        text-align: center;
        color: white;
        margin-bottom: 25px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.15);
    }
    .v-undervalued { background: linear-gradient(135deg, #00b894, #00cec9); }
    .v-fair { background: linear-gradient(135deg, #fdcb6e, #e17055); }
    .v-overvalued { background: linear-gradient(135deg, #ff7675, #d63031); }
    
    .v-title { font-size: 24px; font-weight: bold; opacity: 0.9; }
    .v-main { font-size: 42px; font-weight: 900; margin: 10px 0; }
    .v-desc { font-size: 18px; opacity: 0.95; }

    /* Tablas */
    .stTable { font-size: 16px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. MOTORES DE DATOS (SCRAPING MEJORADO) ---

@st.cache_data(ttl=3600)
def get_finviz_growth_soup(ticker):
    """Scraping robusto usando BeautifulSoup buscando la etiqueta exacta."""
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Finviz pone el label en un <td> y el valor en el siguiente <td>
            # Buscamos el texto "EPS next 5Y"
            target_label = soup.find(string="EPS next 5Y")
            if target_label:
                # Subimos al padre <td> y buscamos el siguiente hermano <td>
                # Estructura: <td>EPS next 5Y</td> <td class="snapshot-td2"><b>14.50%</b></td>
                label_td = target_label.parent
                value_td = label_td.find_next_sibling('td')
                
                if value_td and value_td.text:
                    clean_text = value_td.text.replace('%', '').strip()
                    if clean_text != '-':
                        return float(clean_text)
    except Exception as e:
        print(f"Finviz Error: {e}")
        return None
    return None

@st.cache_data(ttl=3600)
def get_stockanalysis_ratios(ticker):
    """Scraping mejorado con headers de navegador real."""
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://stockanalysis.com/'
    }
    
    ratios_data = {}
    try:
        response = requests.get(url, headers=headers, timeout=4)
        if response.status_code == 200:
            # Pandas read_html a veces falla si no encuentra tablas perfectas
            # Usamos match para asegurar que pilla la tabla correcta
            dfs = pd.read_html(response.text, match="Year") 
            if dfs:
                df = dfs[0]
                # Mapeo de nombres
                metrics_map = {
                    'PE Ratio': 'PER', 
                    'PS Ratio': 'Price/Sales', 
                    'PB Ratio': 'Price/Book', 
                    'EV / EBITDA': 'EV/EBITDA'
                }
                
                for index, row in df.iterrows():
                    metric_raw = str(row[0])
                    for key, clean_name in metrics_map.items():
                        if key in metric_raw:
                            values = []
                            # Las columnas suelen ser años (2023, 2022...)
                            # Saltamos la col 0 (nombre) e intentamos convertir el resto
                            for val in row[1:]:
                                try:
                                    # Limpiar comas y símbolos
                                    v_str = str(val).replace(',', '').replace('%', '')
                                    v = float(v_str)
                                    values.append(v)
                                except:
                                    pass
                            
                            if values:
                                ratios_data[clean_name] = np.mean(values)
    except Exception as e:
        print(f"StockAnalysis Error: {e}")
        pass
        
    return ratios_data

@st.cache_data(ttl=3600)
def get_full_analysis(ticker, years_hist=10):
    stock = yf.Ticker(ticker)
    info = stock.info
    price = info.get('currentPrice', info.get('regularMarketPreviousClose'))
    if not price: return None
    
    # Dividendos (Cálculo Manual Robusto)
    div_rate = info.get('dividendRate', 0)
    if div_rate and price > 0:
        current_yield = div_rate / price
    else:
        raw_yield = info.get('dividendYield', 0)
        # Si raw_yield > 0.5, es entero (5.5), dividir por 100
        current_yield = raw_yield / 100 if (raw_yield and raw_yield > 0.5) else raw_yield

    raw_avg = info.get('fiveYearAvgDividendYield', 0)
    avg_5y_yield = raw_avg / 100 if raw_avg is not None else 0
        
    # PER Histórico
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
                            eps_val = latest[k]; break
                    if pd.isna(eps_val):
                        try:
                            if latest.get('Net Income Common Stockholders') and latest.get('Basic Average Shares'):
                                eps_val = latest.get('Net Income Common Stockholders') / latest.get('Basic Average Shares')
                        except: pass
                    if eps_val and eps_val > 0:
                        pe = row['Close'] / eps_val
                        if 5 < pe < 200: pe_values.append(pe)
            if pe_values: pe_mean = np.mean(pe_values)
    except: pass 

    # Datos Externos
    ext_ratios = get_stockanalysis_ratios(ticker)
    finviz_growth = get_finviz_growth_soup(ticker)

    return {
        'info': info, 'price': price, 'pe_mean': pe_mean,
        'div_data': {'current': current_yield, 'avg_5y': avg_5y_yield, 'rate': div_rate},
        'ext_ratios': ext_ratios, 'finviz_growth': finviz_growth
    }

# --- 2. COMPONENTES VISUALES HTML ---

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
    """Genera la caja grande de veredicto."""
    margin = ((fair_value - price) / price) * 100
    
    if margin > 15:
        # Infravalorada (Buena compra)
        css_class = "v-undervalued"
        title = "💎 OPORTUNIDAD DETECTADA"
        main_text = "INFRAVALORADA"
        emoji = "🚀"
        desc = f"Cotiza con un descuento del {margin:.1f}% sobre su valor histórico."
    elif margin < -15:
        # Sobrevalorada
        css_class = "v-overvalued"
        title = "⚠️ PRECAUCIÓN"
        main_text = "SOBREVALORADA"
        emoji = "🔥"
        desc = f"Cotiza con una prima del {abs(margin):.1f}% sobre su valor histórico."
    else:
        # Precio Justo
        css_class = "v-fair"
        title = "⚖️ MERCADO EFICIENTE"
        main_text = "PRECIO JUSTO"
        emoji = "✅"
        desc = f"La cotización está alineada con sus fundamentales históricos."

    st.markdown(f"""
    <div class="verdict-box {css_class}">
        <div class="v-title">{title}</div>
        <div class="v-main">{emoji} {main_text}</div>
        <div class="v-desc">{desc} (Fair Value: ${fair_value:.2f})</div>
    </div>
    """, unsafe_allow_html=True)

# --- 3. INTERFAZ PRINCIPAL ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)
    st.caption("v3.0 Ultra - BS4 Scraping")

if ticker:
    # Spinner de carga para dar sensación de proceso
    with st.spinner(f'🔍 Analizando {ticker} a fondo...'):
        data = get_full_analysis(ticker, years_hist)
    
    if not data:
        st.error("Ticker no encontrado.")
        st.stop()
        
    info = data['info']
    price = data['price']
    pe_mean = data['pe_mean']
    divs = data['div_data']
    ext_ratios = data['ext_ratios']
    finviz_g = data['finviz_growth']
    
    # Gestión de Crecimiento
    default_growth = finviz_g if finviz_g else 10.0
    
    with st.sidebar:
        st.subheader("⚙️ Proyección Futura")
        growth_input = st.number_input("Crecimiento Estimado (5y) %", value=float(default_growth), step=0.5)
        if finviz_g:
            st.success(f"✅ Finviz: {finviz_g}% detectado")
        else:
            st.warning("⚠️ Finviz no disponible (Usa manual)")

    eps = info.get('trailingEps', 0)
    fair_value = eps * pe_mean
    
    # HEADER PRINCIPAL
    st.title(f"{info.get('shortName', ticker)}")
    st.markdown(f"### **{info.get('sector', '')}**  •  {info.get('industry', '')}")
    
    st.markdown("---")

    # 1. CAJA DE VEREDICTO (NUEVO)
    verdict_box(price, fair_value)

    # 2. DASHBOARD DE MÉTRICAS (CARDS)
    c1, c2, c3, c4 = st.columns(4)
    with c1: card_html("Cotización", f"${price:.2f}")
    with c2: 
        card_html("Valor Razonable", f"${fair_value:.2f}", f"PER Medio: {pe_mean:.1f}x", "neu")
    with c3:
        # Analistas
        target = info.get('targetMeanPrice', 0)
        if target:
            pot = ((target - price)/price)*100
            col = "pos" if pot > 0 else "neg"
            card_html("Obj. Analistas", f"${target:.2f}", f"{pot:+.1f}% Potencial", col)
        else: card_html("Obj. Analistas", "N/A")
    with c4:
        curr, avg = divs['current'], divs['avg_5y']
        val_curr = curr if curr else 0
        val_avg = avg if avg else 0
        col = "pos" if (val_curr > 0 and val_curr > val_avg) else "neu"
        sub = f"Media 5y: {val_avg*100:.2f}%" if val_avg > 0 else "No aplica"
        card_html("Div. Yield", f"{val_curr*100:.2f}%", sub, col)

    st.markdown("<br>", unsafe_allow_html=True)

    # 3. PESTAÑAS DETALLADAS
    t1, t2, t3 = st.tabs(["🚀 PROYECCIÓN 2029", "💰 ANÁLISIS DIVIDENDOS", "📊 FUNDAMENTALES VS MEDIA"])
    
    # TAB 1: PROYECCION
    with t1:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("📝 Calculadora")
            st.markdown(f"Partiendo de **EPS ${eps:.2f}** y creciendo al **{growth_input}%**")
            
            exit_pe = st.number_input("PER de Salida Estimado", value=float(round(pe_mean, 1)))
            
            f_eps = eps * ((1 + growth_input/100)**5)
            f_price = f_eps * exit_pe
            cagr = ((f_price/price)**(1/5)-1)*100
            
            st.markdown("---")
            st.metric("Precio Objetivo 2029", f"${f_price:.2f}")
            
            col_c = "#00b894" if cagr > 10 else "#2d3436"
            st.markdown(f"<div style='font-size:20px'>Retorno Anual (CAGR): <b style='color:{col_c}; font-size:28px'>{cagr:.2f}%</b></div>", unsafe_allow_html=True)
            
        with col2:
            yrs = list(range(datetime.now().year, datetime.now().year+6))
            vals = [price * ((1 + cagr/100)**i) for i in range(6)]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=yrs, y=vals, mode='lines+markers', 
                line=dict(color='#0984e3', width=4),
                marker=dict(size=10, color='#74b9ff')
            ))
            fig.update_layout(
                title="Curva de Crecimiento del Precio",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#dfe6e9')
            )
            st.plotly_chart(fig, use_container_width=True)

    # TAB 2: DIVIDENDOS
    with t2:
        if divs['rate'] and divs['avg_5y'] > 0:
            fair_yield = divs['rate'] / divs['avg_5y']
            marg = ((fair_yield - price)/price)*100
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.info(f"ℹ️ Modelo de Geraldine Weiss (Yield Theory)")
                st.write(f"Dividendo Anual: **${divs['rate']}**")
                st.write(f"Rentabilidad Media Histórica: **{divs['avg_5y']*100:.2f}%**")
                st.write("---")
                st.metric("Valor Justo (Weiss)", f"${fair_yield:.2f}", delta=f"{marg:+.1f}%")
            with col_d2:
                fig = go.Figure(go.Bar(
                    x=['Actual', 'Media 5y'], 
                    y=[divs['current']*100, divs['avg_5y']*100], 
                    marker_color=['#00b894','#b2bec3'],
                    texttemplate='%{y:.2f}%', textposition='outside'
                ))
                fig.update_layout(title="Comparativa Rentabilidad (%)", height=300)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Esta empresa no paga dividendos suficientes para este análisis.")

    # TAB 3: RATIOS
    with t3:
        st.subheader("🔎 Salud Financiera")
        
        ratios_to_show = {
            'PER (P/E)': {'curr': info.get('trailingPE'), 'avg': ext_ratios.get('PER') or pe_mean},
            'Price/Sales': {'curr': info.get('priceToSalesTrailing12Months'), 'avg': ext_ratios.get('Price/Sales')},
            'Price/Book': {'curr': info.get('priceToBook'), 'avg': ext_ratios.get('Price/Book')},
            'EV/EBITDA': {'curr': info.get('enterpriseToEbitda'), 'avg': ext_ratios.get('EV/EBITDA')}
        }
        
        rows = []
        for name, vals in ratios_to_show.items():
            curr = vals['curr']
            avg = vals['avg']
            if curr and avg:
                # Lógica semántica: Si el ratio actual es MENOR a la media, suele ser bueno (Barato)
                is_cheap = curr < avg
                status = "🟢 Barato" if is_cheap else "🔴 Caro"
                diff = ((curr - avg)/avg)*100
                rows.append([name, f"{curr:.2f}", f"{avg:.2f}", f"{diff:+.1f}%", status])
            elif curr:
                rows.append([name, f"{curr:.2f}", "N/A", "-", "-"])
        
        df_ratios = pd.DataFrame(rows, columns=['Ratio', 'Actual', 'Media Histórica', 'Desv.', 'Diagnóstico'])
        st.table(df_ratios)
        
        if not ext_ratios:
            st.info("💡 No se pudieron cargar los históricos de StockAnalysis.com. Usando datos calculados.")
