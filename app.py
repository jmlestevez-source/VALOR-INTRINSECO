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

# --- 1. SCRAPING MEJORADO DE FINVIZ ---

@st.cache_data(ttl=3600)
def get_finviz_growth(ticker):
    """
    Scraping DIRECTO de Finviz para EPS next 5Y.
    Métodos múltiples para máxima compatibilidad.
    """
    ticker_clean = ticker.replace('.', '-').upper()
    url = f"https://finviz.com/quote.ashx?t={ticker_clean}"
    
    # Headers realistas para evitar bloqueos
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        session = requests.Session()
        time.sleep(0.3)  # Pausa cortés
        
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.warning(f"⚠️ Finviz respondió con código {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # MÉTODO 1: Buscar en la tabla snapshot-table2 (estructura actual de Finviz)
        # Finviz usa una tabla con class "snapshot-table2"
        table = soup.find('table', {'class': 'snapshot-table2'})
        
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for i in range(0, len(cells)-1, 2):  # Las celdas van en pares (label, value)
                    label = cells[i].get_text(strip=True)
                    if 'EPS next 5Y' in label or 'EPS next Y' in label:
                        value_text = cells[i+1].get_text(strip=True)
                        # Limpiar y convertir
                        value_clean = value_text.replace('%', '').replace(',', '').strip()
                        try:
                            growth_value = float(value_clean)
                            if -100 < growth_value < 500:  # Validación razonable
                                return growth_value
                        except ValueError:
                            continue
        
        # MÉTODO 2: Búsqueda por texto (backup)
        all_text = soup.get_text()
        pattern = r'EPS next 5Y[^\d]*?([-+]?\d+\.?\d*)%'
        match = re.search(pattern, all_text)
        if match:
            try:
                return float(match.group(1))
            except:
                pass
        
        # MÉTODO 3: Buscar en TODAS las tablas
        all_tables = soup.find_all('table')
        for table in all_tables:
            text = table.get_text()
            if 'EPS next 5Y' in text:
                # Buscar el valor siguiente
                cells = table.find_all('td')
                for i, cell in enumerate(cells):
                    if 'EPS next 5Y' in cell.get_text():
                        if i + 1 < len(cells):
                            val_text = cells[i+1].get_text(strip=True)
                            val_clean = val_text.replace('%', '').replace(',', '').strip()
                            try:
                                val = float(val_clean)
                                if -100 < val < 500:
                                    return val
                            except:
                                pass
        
        st.info(f"ℹ️ No se encontró 'EPS next 5Y' en Finviz para {ticker}")
        return None
        
    except requests.exceptions.Timeout:
        st.warning("⚠️ Timeout conectando a Finviz")
        return None
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ Error de conexión a Finviz: {e}")
        return None
    except Exception as e:
        st.warning(f"⚠️ Error procesando Finviz: {e}")
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
        
        # Buscar patrones de crecimiento
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
    """
    CÁLCULO INTERNO: Descarga datos históricos de Yahoo Finance
    y calcula la media de los ratios en el periodo especificado.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Historial de Precios (Mensual)
        start_date = (datetime.now() - timedelta(days=years*365 + 30)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_date, interval="1mo")
        
        if hist.empty: 
            return {}
        
        # Limpieza de zona horaria
        if hist.index.tz is not None: 
            hist.index = hist.index.tz_localize(None)
        
        # 2. Fundamentales Anuales
        try:
            fin = stock.financials.T
            bal = stock.balance_sheet.T
        except:
            return {}
        
        if fin.empty: 
            return {}
        
        # Limpieza de índices
        fin.index = pd.to_datetime(fin.index)
        if fin.index.tz is not None: 
            fin.index = fin.index.tz_localize(None)
            
        if bal is not None and not bal.empty:
            bal.index = pd.to_datetime(bal.index)
            if bal.index.tz is not None:
                bal.index = bal.index.tz_localize(None)
        
        # 3. Fusión de Datos
        df_merge = pd.DataFrame(index=hist.index)
        df_merge['Price'] = hist['Close']
        
        # Extraemos métricas clave
        metrics_fin = pd.DataFrame(index=fin.index)
        
        # EPS
        if 'Diluted EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Diluted EPS']
        elif 'Basic EPS' in fin.columns:
            metrics_fin['EPS'] = fin['Basic EPS']
        
        # Revenue Per Share
        rev = fin.get('Total Revenue')
        shares = fin.get('Basic Average Shares')
        if shares is None:
            shares = fin.get('Share Issued')
            
        if rev is not None and shares is not None:
            metrics_fin['RPS'] = rev / shares
        
        # Balance Sheet metrics
        if not bal.empty:
            assets = bal.get('Total Assets')
            liab = bal.get('Total Liabilities Net Minority Interest')
            
            if assets is not None and liab is not None and shares is not None:
                metrics_fin['BVPS'] = (assets - liab) / shares
                
            # EV/EBITDA
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

        # Ordenar y fusionar
        metrics_fin = metrics_fin.sort_index()
        df_merge = df_merge.sort_index()
        
        # Join y forward fill
        df_final = df_merge.join(metrics_fin, how='outer').ffill().dropna(subset=['Price'])
        
        # 4. Cálculo de Ratios
        ratios = {}
        
        # P/E Ratio
        if 'EPS' in df_final.columns:
            df_final['PE_Ratio'] = df_final['Price'] / df_final['EPS']
            valid_pe = df_final['PE_Ratio'][(df_final['PE_Ratio'] > 0) & (df_final['PE_Ratio'] < 200)]
            if not valid_pe.empty and not valid_pe.isna().all():
                ratios['PER'] = float(valid_pe.mean())

        # P/S Ratio
        if 'RPS' in df_final.columns:
            df_final['PS_Ratio'] = df_final['Price'] / df_final['RPS']
            valid_ps = df_final['PS_Ratio'][(df_final['PS_Ratio'] > 0) & (df_final['PS_Ratio'] < 50)]
            if not valid_ps.empty and not valid_ps.isna().all():
                ratios['Price/Sales'] = float(valid_ps.mean())

        # P/B Ratio
        if 'BVPS' in df_final.columns:
            df_final['PB_Ratio'] = df_final['Price'] / df_final['BVPS']
            valid_pb = df_final['PB_Ratio'][(df_final['PB_Ratio'] > 0) & (df_final['PB_Ratio'] < 50)]
            if not valid_pb.empty and not valid_pb.isna().all():
                ratios['Price/Book'] = float(valid_pb.mean())

        # EV/EBITDA
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
    """Análisis completo con fuentes múltiples."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Precio actual
        price = info.get('currentPrice')
        if not price or price == 0:
            price = info.get('regularMarketPrice')
        if not price or price == 0:
            price = info.get('regularMarketPreviousClose')
        if not price or price == 0:
            return None
        
        # Dividendos
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
        
        # HISTÓRICOS (Calculados internamente)
        hist_ratios = calculate_robust_ratios(ticker, years_hist)
        
        # CRECIMIENTO: Prioridad a Finviz
        finviz_g = get_finviz_growth(ticker)
        
        # Si Finviz falla, intentar StockAnalysis
        if finviz_g is None:
            finviz_g = get_stockanalysis_growth(ticker)
        
        # PER Medio
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
            'finviz_growth': finviz_g
        }
        
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None

# --- 2. COMPONENTES VISUALES ---

def card_html(label, value, sub_value=None, color_class="neu"):
    """Tarjeta métrica HTML."""
    sub_html = f"<div class='metric-sub {color_class}'>{sub_value}</div>" if sub_value else ""
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>{label}</div>
        <div class='metric-value'>{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

def verdict_box(price, fair_value):
    """Caja de veredicto."""
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

# --- 3. MAIN APP ---

with st.sidebar:
    st.header("🎛️ Configuración")
    ticker = st.text_input("Ticker", value="GOOGL").upper().strip()
    st.divider()
    years_hist = st.slider("Años Media Histórica", 5, 10, 10)
    
    # Opción de debug
    debug_mode = st.checkbox("🔍 Modo Debug (ver detalles scraping)", value=False)

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
    st.markdown("""
    <div style='text-align:center; color:#7f8c8d; font-size:16px; padding:20px'>
        💡 Esta herramienta es solo educativa. No constituye asesoramiento financiero.<br>
        📊 <b>Fuentes:</b> Yahoo Finance (ratios actuales y históricos) • Finviz (crecimiento estimado)
    </div>
    """, unsafe_allow_html=True)
