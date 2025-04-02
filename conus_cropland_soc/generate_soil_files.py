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
from config import WGS84, AEAC
from config import AREA_SOC_CSV
from config import LU_MAP, LU_TYPES
from config import GADM_PATH, SOILGRIDS_PATH, GSSURGO_PATH
from cycles.soil import SOIL_LAYERS
from cycles.soilgrids import SOILGRIDS_PROPERTIES, SOILGRIDS_LAYERS
from cycles.soilgrids import read_soilgrids_maps, reproject_match_soilgrids_maps
from cycles.gssurgo import GSSURGO_NON_SOIL_TYPES, GSSURGO_URBAN_TYPES
from cycles.gssurgo import NAD83
from cycles.gssurgo import read_state_gssurgo, get_soil_profile_parameters
from cycles.gadm import STATE_ABBREVIATIONS
from cycles.gadm import read_gadm
from cycles.soil import generate_soil_file


def generate_description(source, county, state, irrigation_type, hsg, muname='', mukey=None, lat=None, lon=None):
    strs = f"# Cycles soil file for {irrigation_type} cropland in {county}, {state}\n#\n"
    strs += f"# Clay, sand, soil organic carbon, and bulk density are obtained from {source}.\n"
    strs += "# Hydrologic soil group, slope, and soil depth are obtained from gSSURGO.\n"
    if source == 'SoilGrids':
        strs += f"# The data are sampled at Latitude {f'%.4f' % lat}, Longitude {f'%.4f' % lon}.\n"
    else:
        strs += f"# The data are sampled from MUNAME: {muname}, MUKEY: {mukey}\n"
    strs += "# NO3, NH4, and fractions of horizontal and vertical bypass flows are default empirical values.\n#\n"
    if hsg == '':
        strs += "# Hydrologic soil group MISSING DATA.\n"
    else:
        strs += f"# Hydrologic soil group {hsg}.\n"
        strs += "# The curve number for row crops with straight row treatment is used.\n"

    return strs


def filter_non_soil(df):
    df = df[df['mukey'].notna()]
    df = df[~df['muname'].isin(GSSURGO_NON_SOIL_TYPES)]
    df = df[~df['muname'].str.contains('|'.join(GSSURGO_URBAN_TYPES), na=False)]

    df['muname'] = df['muname'].astype(str)
    df['mukey'] = df['mukey'].astype(int)
    df = df.reset_index()

    return df


def main():
    # Read county boundaries
    conus_gdf = read_gadm(GADM_PATH, 'USA', 'county', conus=True)

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

    maps = []
    for v in ['clay', 'sand', 'soc', 'bulk_density']:
        maps = maps + [f'{v}@{layer}' for layer in SOILGRIDS_PROPERTIES[v]['layers']]

    for state_id in [f'USA.{s}_1' for s in range(52)]:
        if state_id not in conus_gdf['GID_1'].unique(): continue

        state_abbreviation = STATE_ABBREVIATIONS[state_id]

        # Read state SoilGrids data
        soilgrids_xds = read_soilgrids_maps(f'{SOILGRIDS_PATH}/{state_id}', maps)

        # Read gSSURGO data
        state_soil, gssurgo_luts = read_state_gssurgo(GSSURGO_PATH, state_abbreviation, group=True)

        for index, county in conus_gdf[conus_gdf['GID_1'] == state_id].iterrows():
            # Get county boundary and centroid
            boundary = gpd.GeoSeries(county['geometry'], crs=WGS84)
            centroid = boundary.to_crs('+proj=cea').centroid.to_crs(WGS84)

            # Get county gSSURGO map
            # Note that CRS of gSSURGO is NAD83 (EPSG:5070). Due to the size of The gSSURGO dataset, converting the CRS
            # of the state gSSURGO database is much less computationally efficient than converting the CRS of state
            # boundary. Therefore, use converted state boundary to crop the state gSSURGO map and then convert to WGS84.
            soil = gpd.clip(state_soil, boundary.to_crs(NAD83), keep_geom_type=False).to_crs(WGS84)

            county_df = reproject_match_soilgrids_maps(soilgrids_xds, conus_lu, 'lu', county['geometry'])

            for t in LU_TYPES:
                if county[f'{t}_area'] <= 0.0: continue

                # Filter data by cropland type
                sub_df = county_df[county_df['lu'].isin(LU_TYPES[t])].copy()

                if sub_df.empty: continue

                # Create a GeoDataFrame for spatial data processing
                sub_df['coord'] = [Point(c[1], c[0]) for c in list(sub_df.index)]
                sub_df = gpd.GeoDataFrame(sub_df, geometry='coord', crs=WGS84)

                # Find the soil types of each cropland grid by joining the cropland GeoDataFrame with gSSURGO
                # GeoDataFrame
                df = gpd.tools.sjoin(sub_df, soil, predicate='within', how='left')

                # Remove grids that are not categorized as soil
                df = filter_non_soil(df)
                if df.empty: continue

                # Get the average slope and dominant hydrologic soil group
                slope = df['slopegradwta'].mean()
                try:
                    hsg = df['hydgrpdcd'].mode()[0]
                except:
                    hsg = ''

                # Find the dominant soil type
                muname = df['muname'].mode()[0]
                selected_soil = soil[soil['muname'] == muname].iloc[0]

                # Get soil parameters of the dominant soil type
                soil_df = get_soil_profile_parameters(gssurgo_luts, selected_soil.mukey)

                # Calculate soil depth
                layer_depths = [layer['bottom'] for layer in SOIL_LAYERS]
                soil_depth = min(layer_depths, key=lambda x: abs(x - soil_df.iloc[-1]['bottom']))

                # Generate a soil file using gSSURGO data
                fn = f'./soil/{index}_{t}_gSSURGO.soil'
                desc = generate_description('gSSURGO', county['NAME_2'], county['NAME_1'], t, hsg, muname=muname, mukey=selected_soil.mukey)
                generate_soil_file(fn, desc, hsg, slope, soil_depth, soil_df)

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

                for v in ['clay', 'sand', 'soc', 'bulk_density']:
                    soilgrids_df[v] = soilgrids_df.apply(lambda x: selected_point[f'{v}@{int(x["top"] * 100)}-{int(x["bottom"] * 100)}cm'], axis=1)

                desc = generate_description('SoilGrids', county['NAME_2'], county['NAME_1'], t, hsg, lat=selected_point['y'], lon=selected_point['x'])
                generate_soil_file(fn, desc, hsg, slope, soil_depth, soilgrids_df)


if __name__ == '__main__':
    main()
