# 💎 Master Stock Valuation App

Una herramienta profesional de valoración de acciones desarrollada en Python y Streamlit. Diseñada para inversores fundamentales que buscan calcular el valor intrínseco más allá del ruido del mercado.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/)

## 🚀 Características Principales

### 1. Análisis de Crecimiento a 5 Años (Estilo Excel Pro)
Replica y mejora los modelos de proyección financiera profesionales:
- **Input Flexible:** Introduce tu tasa de crecimiento estimada manualmente o impórtala desde fuentes externas.
- **Exit Multiple Personalizable:** Tú decides el PER de salida (Exit P/E) para el año 5, aunque la app te sugiere la media histórica real.
- **Cálculo de CAGR:** Visualiza el retorno anual compuesto esperado de forma clara.

### 2. Valoración por Dividendos (Método Geraldine Weiss)
Implementación de la **Investment Yield Theory**:
- Compara la Rentabilidad por Dividendo actual (Current Yield) vs. la Media Histórica (5-10 años).
- Identifica automáticamente si una acción de dividendos está infravalorada (Zona de Compra) o sobrevalorada.

### 3. Medias Históricas Reales (Deep Data)
A diferencia de otras apps gratuitas, este algoritmo:
- Realiza una "Ingeniería Inversa" de los últimos 10 años.
- Cruza precios mensuales con los informes anuales vigentes en cada momento para calcular el **PER Medio Real**, eliminando distorsiones y outliers.

### 4. Modelos Clásicos Adicionales
- **Fórmula de Benjamin Graham:** Valoración basada en activos tangibles y beneficios (√(22.5 × EPS × BVPS)).
- **Valor Justo Peter Lynch:** Estimación rápida basada en la equivalencia PEG = 1.

---

## 🛠️ Instalación Local

Si prefieres ejecutarlo en tu ordenador en lugar de la nube:

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/TU_USUARIO/calculadora-acciones.git
