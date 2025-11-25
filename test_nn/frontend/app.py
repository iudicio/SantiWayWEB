import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
from datetime import datetime

API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Anomaly Detection Demo",
    layout="wide",
)

st.title("Device Activity Anomaly Detection")
st.markdown("---")

with st.sidebar:
    st.header("Settings")

    analysis_type = st.selectbox(
        "Analysis Type",
        ["Global Analysis", "Device Analysis", "View Results", "Geo Map", "Device Comparison", "Explanations"],
    )

    period = st.selectbox(
        "Time Period",
        ["24h", "7d", "30d"],
        index=0,
    )

    if analysis_type == "Device Analysis":
        device_id = st.text_input("Device ID", "device_0050")

    st.markdown("---")
    st.markdown("### Quick Stats")

    try:
        response = requests.get(f"{API_URL}/anomalies/stats")
        if response.status_code == 200:
            stats = response.json()
            for stat in stats.get('stats', []):
                label = stat.get('anomaly_type', 'Unknown')
                if not label or label.strip() == '':
                    label = 'Unknown'
                st.metric(
                    label,
                    stat['count'],
                    f"avg: {stat['avg_score']:.2f}",
                )
    except Exception:
        st.warning("API not available")

if analysis_type == "Global Analysis":
    st.header("Global Analysis")

    col1, col2 = st.columns([1, 2])

    with col1:
        detection_types = st.multiselect(
            "Detection Types",
            [
                "following",
                "relay_surveillance",
                "stationary_surveillance",
                "density_cluster",
                "dispersion",
                "night_activity",
            ],
            default=["following", "density_cluster"],
        )

        if st.button("Run Analysis", type="primary"):
            with st.spinner("Analyzing..."):
                try:
                    response = requests.post(
                        f"{API_URL}/analyze/global",
                        json={
                            "period": period,
                            "detection_types": detection_types,
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        st.session_state['global_results'] = result
                        st.success(f"Found {result['anomalies_found']} anomalies")
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

    with col2:
        if 'global_results' in st.session_state:
            result = st.session_state['global_results']

            if result['anomalies_found'] > 0:
                df = pd.DataFrame(result['anomalies'])

                fig = px.pie(
                    df,
                    names='anomaly_type',
                    title='Anomaly Types Distribution',
                )
                st.plotly_chart(fig, use_container_width=True)

    if 'global_results' in st.session_state:
        result = st.session_state['global_results']

        if result['anomalies_found'] > 0:
            st.subheader("Detected Anomalies")

            df = pd.DataFrame(result['anomalies'])

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['anomaly_score'] = df['anomaly_score'].round(3)

            st.dataframe(
                df[['timestamp', 'anomaly_type', 'anomaly_score', 'region', 'device_id']],
                use_container_width=True,
                height=400,
            )

            st.subheader("Top 5 Anomalies")
            top_5 = df.nlargest(5, 'anomaly_score')

            for _, row in top_5.iterrows():
                with st.expander(f"{row['anomaly_type']} - Score: {row['anomaly_score']:.3f}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Timestamp", row['timestamp'].strftime('%Y-%m-%d %H:%M'))
                    with col2:
                        st.metric("Region", row['region'] if row['region'] else 'N/A')
                    with col3:
                        st.metric("Device", row['device_id'] if row['device_id'] else 'Global')

                    st.json(row['details'])

elif analysis_type == "Device Analysis":
    st.header("Device-Specific Analysis")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.info(f"Analyzing device: **{device_id}**")

        if st.button("Analyze Device", type="primary"):
            with st.spinner(f"Analyzing {device_id}..."):
                try:
                    response = requests.post(
                        f"{API_URL}/analyze/device/{device_id}",
                        json={"period": period},
                    )

                    if response.status_code == 200:
                        result = response.json()
                        st.session_state['device_results'] = result
                        st.success(f"Found {result['anomalies_found']} anomalies")
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

    with col2:
        if 'device_results' in st.session_state:
            result = st.session_state['device_results']

            if result['anomalies_found'] > 0:
                df = pd.DataFrame(result['anomalies'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                fig = go.Figure()

                fig.add_trace(go.Scatter(
                    x=df['timestamp'],
                    y=df['anomaly_score'],
                    mode='lines+markers',
                    name='Anomaly Score',
                    marker=dict(size=10, color='red'),
                ))

                fig.update_layout(
                    title=f'Anomaly Timeline - {device_id}',
                    xaxis_title='Time',
                    yaxis_title='Anomaly Score',
                    hovermode='x unified',
                )

                st.plotly_chart(fig, use_container_width=True)

    if 'device_results' in st.session_state:
        result = st.session_state['device_results']

        if result['anomalies_found'] > 0:
            st.subheader("Anomalies Detected")

            df = pd.DataFrame(result['anomalies'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            st.dataframe(
                df[['timestamp', 'anomaly_score', 'region']],
                use_container_width=True,
            )

elif analysis_type == "View Results":
    st.header("Historical Anomalies")

    col1, col2, col3 = st.columns(3)

    with col1:
        limit = st.number_input("Limit", min_value=10, max_value=500, value=100)

    with col2:
        anomaly_type = st.selectbox(
            "Filter by Type",
            [
                "All",
                "following",
                "relay_surveillance",
                "stationary_surveillance",
                "density_cluster",
                "dispersion",
                "night_activity",
                "personal_deviation",
            ],
        )

    with col3:
        min_score = st.slider("Min Score", 0.0, 1.0, 0.0, 0.1)

    if st.button("Refresh Data"):
        with st.spinner("Loading..."):
            try:
                params = {
                    "limit": limit,
                    "min_score": min_score,
                }

                if anomaly_type != "All":
                    params["anomaly_type"] = anomaly_type

                response = requests.get(
                    f"{API_URL}/anomalies",
                    params=params,
                )

                if response.status_code == 200:
                    result = response.json()
                    st.session_state['historical_results'] = result
                    st.success(f"Loaded {len(result['anomalies'])} anomalies (total: {result['total']})")
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"API Error: {e}")

    if 'historical_results' in st.session_state:
        result = st.session_state['historical_results']

        if len(result['anomalies']) > 0:
            df = pd.DataFrame(result['anomalies'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['detected_at'] = pd.to_datetime(df['detected_at'])

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Anomalies", result['total'])

            with col2:
                st.metric("Avg Score", f"{df['anomaly_score'].mean():.3f}")

            with col3:
                st.metric("Max Score", f"{df['anomaly_score'].max():.3f}")

            with col4:
                unique_devices = df['device_id'].nunique()
                st.metric("Affected Devices", unique_devices)

            col1, col2 = st.columns(2)

            with col1:
                type_counts = df['anomaly_type'].value_counts()
                fig = px.bar(
                    x=type_counts.index,
                    y=type_counts.values,
                    title='Anomaly Types',
                    labels={'x': 'Type', 'y': 'Count'},
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = px.histogram(
                    df,
                    x='anomaly_score',
                    nbins=50,
                    title='Score Distribution',
                )
                st.plotly_chart(fig, use_container_width=True)

            df_timeline = df.groupby([pd.Grouper(key='timestamp', freq='1H'), 'anomaly_type']).size().reset_index(name='count')

            fig = px.line(
                df_timeline,
                x='timestamp',
                y='count',
                color='anomaly_type',
                title='Anomalies Over Time',
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Raw Data")
            st.dataframe(
                df[['detected_at', 'timestamp', 'device_id', 'anomaly_type', 'anomaly_score', 'region']],
                use_container_width=True,
                height=400,
            )

elif analysis_type == "Geo Map":
    st.header("Anomaly Map")

    col1, col2 = st.columns([1, 3])

    with col1:
        map_limit = st.number_input("Max Points", min_value=10, max_value=500, value=100)
        map_min_score = st.slider("Min Score", 0.0, 1.0, 0.3, 0.1)

        if st.button("Load Map Data"):
            with st.spinner("Loading..."):
                try:
                    response = requests.get(
                        f"{API_URL}/anomalies",
                        params={"limit": map_limit, "min_score": map_min_score}
                    )

                    if response.status_code == 200:
                        result = response.json()
                        st.session_state['map_data'] = result
                        st.success(f"Loaded {len(result['anomalies'])} points")
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

    with col2:
        if 'map_data' in st.session_state:
            anomalies = st.session_state['map_data']['anomalies']

            if len(anomalies) > 0:
                coords_query = []
                for a in anomalies:
                    if a.get('device_id'):
                        coords_query.append(a['device_id'])

                map_df = pd.DataFrame(anomalies)

                import numpy as np
                np.random.seed(42)

                if 'lat' not in map_df.columns:
                    map_df['lat'] = 55.75 + np.random.randn(len(map_df)) * 0.1
                    map_df['lon'] = 37.62 + np.random.randn(len(map_df)) * 0.1

                type_colors = {
                    'density_cluster': [255, 0, 0],
                    'night_activity': [0, 0, 255],
                    'stationary_surveillance': [255, 165, 0],
                    'personal_deviation': [128, 0, 128],
                    'following': [255, 255, 0]
                }

                map_df['color'] = map_df['anomaly_type'].apply(
                    lambda x: type_colors.get(x, [128, 128, 128])
                )
                map_df['radius'] = map_df['anomaly_score'] * 500

                layer = pdk.Layer(
                    'ScatterplotLayer',
                    data=map_df,
                    get_position='[lon, lat]',
                    get_color='color',
                    get_radius='radius',
                    pickable=True,
                    opacity=0.8,
                )

                view_state = pdk.ViewState(
                    latitude=map_df['lat'].mean(),
                    longitude=map_df['lon'].mean(),
                    zoom=10,
                    pitch=0,
                )

                st.pydeck_chart(pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    tooltip={
                        'text': '{anomaly_type}\nScore: {anomaly_score}\nDevice: {device_id}'
                    }
                ))

                st.markdown("**Legend:**")
                for atype, color in type_colors.items():
                    st.markdown(
                        f"<span style='color: rgb({color[0]},{color[1]},{color[2]})'>"
                        f"● {atype}</span>",
                        unsafe_allow_html=True
                    )

elif analysis_type == "Device Comparison":
    st.header("Device Comparison")

    tab1, tab2, tab3 = st.tabs(["Similar Devices", "Clusters", "Compare Two"])

    with tab1:
        st.subheader("Find Similar Devices")
        comp_device = st.text_input("Device ID", "device_0050", key="comp_device")
        comp_top_k = st.slider("Top K", 5, 20, 10)
        comp_min_sim = st.slider("Min Similarity", 0.5, 1.0, 0.8, 0.05)

        if st.button("Find Similar", key="find_similar"):
            with st.spinner("Searching..."):
                try:
                    response = requests.post(
                        f"{API_URL}/comparison/similar",
                        json={
                            "device_id": comp_device,
                            "hours": 168,
                            "top_k": comp_top_k,
                            "min_similarity": comp_min_sim
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()

                        if result['count'] > 0:
                            st.success(f"Found {result['count']} similar devices")

                            sim_df = pd.DataFrame(result['similar_devices'])
                            sim_df['similarity'] = sim_df['similarity'].round(3)

                            st.dataframe(
                                sim_df[['device_id', 'similarity']],
                                use_container_width=True
                            )

                            fig = px.bar(
                                sim_df,
                                x='device_id',
                                y='similarity',
                                title='Device Similarity Scores'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("No similar devices found")
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

    with tab2:
        st.subheader("Behavioral Clusters")
        cluster_eps = st.slider("Cluster Distance (eps)", 0.1, 1.0, 0.3, 0.1)
        cluster_min = st.number_input("Min Samples", 2, 10, 2)

        if st.button("Detect Clusters", key="detect_clusters"):
            with st.spinner("Clustering..."):
                try:
                    response = requests.post(
                        f"{API_URL}/comparison/clusters",
                        json={
                            "hours": 168,
                            "eps": cluster_eps,
                            "min_samples": cluster_min
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()

                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Clusters Found", result['num_clusters'])
                        with col2:
                            st.metric("Noise Devices", len(result['noise_devices']))

                        if result['num_clusters'] > 0:
                            for cluster in result['clusters']:
                                with st.expander(
                                    f"Cluster {cluster['cluster_id']} - {cluster['size']} devices"
                                ):
                                    st.write("Devices:", ', '.join(cluster['devices'][:10]))
                                    if len(cluster['devices']) > 10:
                                        st.write(f"... and {len(cluster['devices']) - 10} more")

                                    st.write("Centroid characteristics:")
                                    for key, value in cluster['centroid'].items():
                                        st.write(f"  - {key}: {value:.3f}")
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

    with tab3:
        st.subheader("Compare Two Devices")
        col1, col2 = st.columns(2)

        with col1:
            device1 = st.text_input("Device 1", "device_0050", key="device1")
        with col2:
            device2 = st.text_input("Device 2", "device_0051", key="device2")

        if st.button("Compare", key="compare_two"):
            with st.spinner("Comparing..."):
                try:
                    response = requests.post(
                        f"{API_URL}/comparison/compare",
                        json={
                            "device_id_1": device1,
                            "device_id_2": device2,
                            "hours": 168
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()

                        st.metric(
                            "Overall Similarity",
                            f"{result['overall_similarity']:.3f}"
                        )

                        st.info(result['interpretation'])

                        st.subheader("Feature Comparison")
                        comp_data = []
                        for feat, values in result['feature_comparison'].items():
                            comp_data.append({
                                'Feature': feat,
                                device1: round(values['device_1'], 3),
                                device2: round(values['device_2'], 3),
                                'Diff %': round(values['relative_diff'] * 100, 1)
                            })

                        comp_df = pd.DataFrame(comp_data)
                        st.dataframe(comp_df, use_container_width=True)

                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"API Error: {e}")

elif analysis_type == "Explanations":
    st.header("Anomaly Explanations (SHAP)")

    exp_device = st.text_input("Device ID", "device_0050", key="exp_device")
    exp_top_k = st.slider("Top Features", 3, 10, 5, key="exp_top_k")

    if st.button("Explain Anomalies", key="explain"):
        with st.spinner("Computing SHAP values..."):
            try:
                response = requests.post(
                    f"{API_URL}/explain/device",
                    json={
                        "device_id": exp_device,
                        "hours": 168,
                        "top_k": exp_top_k
                    }
                )

                if response.status_code == 200:
                    result = response.json()

                    if result['total_anomalies'] > 0:
                        st.success(
                            f"Explained {result['explained']} of "
                            f"{result['total_anomalies']} anomalies"
                        )

                        for i, exp in enumerate(result['explanations']):
                            with st.expander(
                                f"Anomaly at {exp['timestamp']} - "
                                f"Score: {exp['anomaly_score']:.3f}"
                            ):
                                st.write(f"**Method:** {exp['explanation']['method']}")

                                if exp['explanation']['top_features']:
                                    feat_df = pd.DataFrame(exp['explanation']['top_features'])

                                    fig = px.bar(
                                        feat_df,
                                        x='importance',
                                        y='feature',
                                        orientation='h',
                                        color='direction',
                                        title='Feature Contributions',
                                        color_discrete_map={
                                            'increases': 'red',
                                            'decreases': 'blue',
                                            'contributes': 'gray'
                                        }
                                    )
                                    st.plotly_chart(fig, use_container_width=True)

                                    st.write("**Feature Descriptions:**")
                                    for feat in exp['explanation']['top_features']:
                                        st.write(f"- {feat['description']}")
                    else:
                        st.warning("No anomalies detected for this device")
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"API Error: {e}")

    with st.expander("View All Feature Descriptions"):
        try:
            response = requests.get(f"{API_URL}/explain/features")
            if response.status_code == 200:
                features = response.json()

                st.write("**Basic Features:**")
                for name, desc in features['basic_features'].items():
                    st.write(f"- **{name}**: {desc}")

                st.write("**Extended Features:**")
                for name, desc in features['extended_features'].items():
                    st.write(f"- **{name}**: {desc}")
        except Exception:
            st.warning("Could not load feature descriptions")

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Anomaly Detection Demo | Powered by FastAPI, ClickHouse & PyTorch
    </div>
    """,
    unsafe_allow_html=True,
)
