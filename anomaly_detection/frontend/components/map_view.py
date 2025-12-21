import streamlit as st
import pydeck as pdk
import pandas as pd

def render_anomaly_map(anomalies_df: pd.DataFrame):
    """Отрисовка карты с аномалиями

    Аргументы:
        anomalies_df: DataFrame с колонками lat, lon, anomaly_score"""

    if anomalies_df.empty:
        st.warning("No location data available")
        return

    anomalies_df = anomalies_df.copy()
    anomalies_df['color'] = anomalies_df['anomaly_score'].apply(
        lambda x: [255, int(255 * (1 - min(1.0, float(x)))), 0, 160]
    )

    center_lat = anomalies_df['lat'].mean()
    center_lon = anomalies_df['lon'].mean()

    layer = pdk.Layer(
        'ScatterplotLayer',
        data=anomalies_df,
        get_position='[lon, lat]',
        get_color='color',
        get_radius=1000,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=10,
        pitch=0,
    )

    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style='mapbox://styles/mapbox/light-v9',
        tooltip={
            'html': '<b>Anomaly Score:</b> {anomaly_score}<br/><b>Type:</b> {anomaly_type}',
            'style': {'color': 'white'},
        },
    )

    st.pydeck_chart(r)
