"""Generate representative county-level soil files for rainfed and irrigated cropland using gSSURGO and SoilGrids data

For each irrigation type in a county, find the dominant soil type of cropland using gSSURGO data, and generate a
gSSURGO soil file using gSSURGO parameters.
Then find the nearest point in the dominant soil type to the county centroid, and sample SoilGrids parameters at that
point to generate a SoilGrids soil file.
For both type (gSSURGO and SoilGrids) soil files, hte hydrologic soil groups, slopes, and soil depths are determined
using gSSURGO data.
"""
import geopandas as gpd
import os
import pandas as pd
import rioxarray
from shapely.geometry import Point
from config import AREA_SOC_CSV
from config import LU_MAP, LU_TYPES
from soil import SOIL_LAYERS
from soilgrids import SOILGRIDS_PROPERTIES, SOILGRIDS_LAYERS
from soilgrids import read_soilgrids_maps, reproject_match_soilgrids_maps
from gssurgo import GSSURGO, GSSURGO_NON_SOIL_TYPES, GSSURGO_URBAN_TYPES
from gssurgo import NAD83
from gssurgo import read_state_gssurgo_luts
from config import WGS84, AEAC
from gadm import STATE_ABBREVIATIONS
from gadm import read_gadm
from soil import generate_soil_file


def main():
    # Read county boundaries
    conus_gdf = read_gadm('USA', 'county', conus=True)

    # Read cropland areas of counties
    conus_gdf = conus_gdf.join(
        pd.read_csv(
            AREA_SOC_CSV,
            comment='#',
            usecols=['GID_2', 'rainfed_area', 'irrigated_area'],
            index_col='GID_2',
        ),
        how='inner',
    )

    # Read cropland land use map
    conus_lu = rioxarray.open_rasterio(LU_MAP, masked=True)

    os.makedirs('soil', exist_ok=True)

    for state_id in conus_gdf['GID_1'].unique():
        state_abbreviation = STATE_ABBREVIATIONS[state_id]

        # Read state SoilGrids data
        soilgrids_xds = read_soilgrids_maps(state_id, SOILGRIDS_LAYERS, SOILGRIDS_PROPERTIES, WGS84)

        # Read gSSURGO data
        _state_soil = gpd.read_file(
            GSSURGO(state_abbreviation),
            layer='MUPOLYGON',
        )
        _state_soil.columns = [x.lower() for x in _state_soil.columns]
        _state_soil.mukey = _state_soil.mukey.astype(int)

        gssurgo_luts = read_state_gssurgo_luts(state_abbreviation, group=True)

        # Merge the mapunit polygon table with the mapunit aggregated attribute table
        state_soil = _state_soil.merge(gssurgo_luts['muaggatt'], on='mukey')

        for index, county in conus_gdf[conus_gdf['GID_1'] == state_id].iterrows():
            # Get county boundary and centroid
            boundary = gpd.GeoSeries(county['geometry'], crs=WGS84)
            centroid = boundary.to_crs('+proj=cea').centroid.to_crs(WGS84)

            # Get county gSSURGO map
            # Note that CRS of gSSURGO is NAD83 (EPSG:5070). Due to the size of The gSSURGO dataset, converting the CRS
            # of the state gSSURGO database is much less computationally efficient thatn converting the CRS of state
            # boundary. Therefore, use converted state boundary to crop the state gSSURGO map and then convert to WGS84.
            soil = gpd.clip(state_soil, boundary.to_crs(NAD83), keep_geom_type=False).to_crs(WGS84)

            county_df = reproject_match_soilgrids_maps(soilgrids_xds, conus_lu, 'lu', county['geometry'], SOILGRIDS_LAYERS, SOILGRIDS_PROPERTIES)

            for t in LU_TYPES:
                if county[f'{t}_area'] <= 0.0: continue

                # Filter data by cropland type
                sub_df = county_df[county_df['lu'].isin(LU_TYPES[t])].copy()

                if sub_df.empty: continue

                # Create a GeoDataFrame for spatial data processing
                sub_df['coord'] = [Point(c[1], c[0]) for c in list(sub_df.index)]
                sub_df = gpd.GeoDataFrame(sub_df, geometry='coord', crs=WGS84)

                # Find the soil types of each cropland grid by joining the cropland GeoDataFrame with gSSURGO
                # GeoDataFrame. Remove grids that are not categorized as soil
                df = gpd.tools.sjoin(sub_df, soil, predicate='within', how='left')
                df = df[df['mukey'].notna()]
                df = df[~df['muname'].isin(GSSURGO_NON_SOIL_TYPES)]
                df = df[~df['muname'].str.contains('|'.join(GSSURGO_URBAN_TYPES), na=False)]

                if df.empty: continue

                df['muname'] = df['muname'].astype(str)
                df['mukey'] = df['mukey'].astype(int)
                df = df.reset_index()

                # Get the average slope and dominant hydrologic soil group
                slope = df['slopegradwta'].mean()
                try:
                    hsg = df['hydgrpdcd'].mode()[0]
                except:
                    hsg = ''

                # Find the dominant soil type
                muname = df['muname'].mode()[0]
                selected_soil = soil[soil['muname'] == muname].iloc[0]
                selected_soil['mukey'] = selected_soil['mukey'].astype(int)

                # Get soil parameters of the dominant soil type
                selected_soil = selected_soil.to_frame().T.merge(gssurgo_luts['component'], on='mukey').merge(gssurgo_luts['chorizon'], on='cokey')
                if not selected_soil[selected_soil['majcompflag'] == 'Yes'].empty:
                    selected_soil = selected_soil[selected_soil['majcompflag'] == 'Yes'].sort_values(by='top')
                else:
                    selected_soil = selected_soil.sort_values(by='top')
                selected_soil = selected_soil[selected_soil['hzname'] != 'R']

                # Calculate soil depth
                layer_depths = [layer['bottom'] for layer in SOIL_LAYERS]
                soil_depth = min(layer_depths, key=lambda x: abs(x - selected_soil.iloc[-1]['bottom']))

                # Generate a soil file using gSSURGO data
                fn = f'./soil/{index}_{t}_gSSURGO.soil'
                generate_soil_file(fn, 'gSSURGO', county['NAME_2'], county['NAME_1'], t, hsg, slope, soil_depth, selected_soil)

                # Use the dominant soil type and drop grids with missing SoilGrids data
                df = df[df['muname'] == muname].dropna(subset=[name for name in soilgrids_xds])

                if df.empty: continue

                # Project to USA Contiguous Albers Equal Area Conic for the calculation of distances
                df_projected = df.to_crs(AEAC)
                centroid = centroid.to_crs(AEAC)

                # Find the grids with the dominant soil type and closest to the county centroid
                df['distance_to_centroid'] = df_projected.geometry.distance(centroid.iloc[0])
                selected_point = df.loc[df['distance_to_centroid'].idxmin()]

                # Generate a soil file using SoilGrids parameters
                fn = f'soil/{index}_{t}_SoilGrids.soil'
                soilgrids_df = pd.DataFrame.from_dict(
                    {v: [SOILGRIDS_LAYERS[layer][v] for layer in SOILGRIDS_LAYERS] for v in SOILGRIDS_LAYERS[list(SOILGRIDS_LAYERS.keys())[0]]}
                )

                for v in SOILGRIDS_PROPERTIES:
                    soilgrids_df[v] = soilgrids_df.apply(lambda x: selected_point[f'{v}_{int(x["top"] * 100)}-{int(x["bottom"] * 100)}cm'], axis=1)

                generate_soil_file(fn, 'SoilGrids', county['NAME_2'], county['NAME_1'], t, hsg, slope, soil_depth, soilgrids_df, lat=selected_point['y'], lon=selected_point['x'])


if __name__ == '__main__':
    main()
