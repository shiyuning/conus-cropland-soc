"""Generate representative county-level soil files for rainfed and irrigated cropland using gSSURGO and SoilGrids data

For each irrigation type in a county, find the dominant soil type of cropland using gSSURGO data, and generate a
gSSURGO soil file using gSSURGO parameters.
Then find the nearest point in the dominant soil type to the county centroid, and sample SoilGrids parameters at that
point to generate a SoilGrids soil file.
For both type (gSSURGO and SoilGrids) soil files, hte hydrologic soil groups, slopes, and soil depths are determined
using gSSURGO data.
"""
import geopandas as gpd
import numpy as np
import os
import pandas as pd
import rioxarray
from rasterio.enums import Resampling
from shapely.geometry import Point
from settings import AREA_SOC_CSV
from settings import COUNTY_SHP
from settings import LU_MAP, LU_TYPES, AG_TYPES
from settings import SOIL_LAYERS
from settings import SOILGRIDS_DIRECTORY, SOILGRIDS_PARAMETERS, SOILGRIDS_LAYERS
from settings import GSSURGO, GSSURGO_LUT, GSSURGO_PARAMETERS, GSSURGO_NON_SOIL_TYPES
from settings import CURVE_NUMBERS
from settings import WGS84, NAD83, AEAC
from soil import generate_soil_file


def main():
    # Read county boundaries
    usa_gdf = gpd.read_file(f'{COUNTY_SHP}')
    usa_gdf.set_index('GID_2', inplace=True)
    usa_gdf['GID'] = usa_gdf.index

    # Generate a CONUS GeoDataFrame by removing Alaska and Hawaii
    conus_gdf = usa_gdf.drop(usa_gdf[(usa_gdf['NAME_1'] == 'Alaska') | (usa_gdf['NAME_1'] == 'Hawaii')].index)

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

    # Get the abbreviation of states
    states = conus_gdf[['GID_1', 'HASC_2']].groupby('GID_1').agg('first')
    states['state'] = states['HASC_2'].map(lambda x: x.split('.')[1])

    # Read cropland land use map
    conus_lu = rioxarray.open_rasterio(LU_MAP, masked=True)

    os.makedirs('soil', exist_ok=True)

    for state_id in ['USA.1_1', 'USA.3_1', 'USA.4_1', 'USA.5_1', 'USA.6_1']:
        state = states.loc[state_id, 'state']

        # Read state SoilGrids data
        soilgrids = {}
        for layer in SOILGRIDS_LAYERS:
            for v in SOILGRIDS_PARAMETERS:
                soilgrids[v+layer['name']] = rioxarray.open_rasterio(f'{SOILGRIDS_DIRECTORY}/{state_id}/{SOILGRIDS_PARAMETERS[v]["variable"]}_{layer["name"]}.tif', masked=True).rio.reproject(WGS84)

        # Read gSSURGO data
        _state_soil = gpd.read_file(
            GSSURGO(state),
            layer='MUPOLYGON',
        )
        _state_soil.columns = [x.lower() for x in _state_soil.columns]
        _state_soil.mukey = _state_soil.mukey.astype(int)

        gssurgo_luts = {}
        gssurgo_luts['component'] = pd.read_csv(
            GSSURGO_LUT('component', state),
            usecols=['mukey', 'cokey', 'majcompflag'],
        )
        gssurgo_luts['chorizon'] = pd.read_csv(
            GSSURGO_LUT('chorizon', state),
            usecols=['hzname', 'hzdept_r', 'hzdepb_r', 'sandtotal_r', 'silttotal_r', 'claytotal_r', 'om_r', 'dbthirdbar_r', 'cokey'],
        )
        # Rename table columns
        gssurgo_luts['chorizon'] = gssurgo_luts['chorizon'].rename(
            columns={GSSURGO_PARAMETERS[v]['variable']: v for v in GSSURGO_PARAMETERS}
        )
        # Convert units (note that organic matter is also converted to soil organic carbon in this case)
        for v in GSSURGO_PARAMETERS: gssurgo_luts['chorizon'][v] *= GSSURGO_PARAMETERS[v]['multiplier']

        gssurgo_luts['muaggatt'] = pd.read_csv(
            GSSURGO_LUT('muaggatt', state),
            usecols=['hydgrpdcd', 'muname', 'slopegradwta', 'mukey'],
        )

        # In the gSSURGO database many map units are the same soil texture with different slopes, etc. To find the
        # dominant soil series, same soil texture with different slopes should be aggregated together. Therefore we use
        # the map unit names to identify the same soil textures among different soil map units.
        gssurgo_luts['muaggatt']['muname'] = gssurgo_luts['muaggatt']['muname'].map(lambda name: name.split(',')[0])

        # Merge the mapunit polygon table with the mapunit aggregated attribute table
        state_soil = _state_soil.merge(gssurgo_luts['muaggatt'], on='mukey')

        for index, county in conus_gdf[conus_gdf['GID_1'] == state_id].iterrows():
            # Get county boundary and centroid
            boundary = gpd.GeoSeries(county['geometry'], crs=conus_gdf.crs)
            centroid = boundary.to_crs('+proj=cea').centroid.to_crs(conus_gdf.crs)

            # Get county gSSURGO map
            # Note that CRS of gSSURGO is NAD83 (EPSG:5070). Due to the size of The gSSURGO dataset, converting the CRS
            # of the state gSSURGO database is much less computationally efficient thatn converting the CRS of state
            # boundary. Therefore, use converted state boundary to crop the state gSSURGO map and then convert to WGS84.
            soil = gpd.clip(state_soil, boundary.to_crs(NAD83), keep_geom_type=False).to_crs(WGS84)

            # Get county cropland map
            county_lu = conus_lu.rio.clip(boundary, from_disk=True)
            county_df = pd.DataFrame(county_lu[0].to_series().rename('lu'))

            # Get county SoilGrids map, and merge with cropland map
            for v in SOILGRIDS_PARAMETERS:
                for layer in SOILGRIDS_LAYERS:
                    _soil = soilgrids[v+layer['name']].rio.reproject_match(county_lu, resampling=Resampling.nearest)
                    _soil = _soil.rio.clip(boundary, from_disk=True)

                    _df = _soil[0].to_pandas().stack(dropna=False) * SOILGRIDS_PARAMETERS[v]['multiplier']
                    _df.name = f'{v}_{layer["name"]}'
                    county_df = pd.concat([county_df, _df], axis=1)

            for t in LU_TYPES:
                if county[f'{t}_area'] <= 0.0: continue

                # Filter data by cropland type
                sub_df = county_df[county_df['lu'].isin(LU_TYPES[t])].copy()

                if sub_df.empty: continue

                # Create a GeoDataFrame for spatial data processing
                sub_df['coord'] = [Point(c[1], c[0]) for c in list(sub_df.index)]
                sub_df = gpd.GeoDataFrame(sub_df, geometry="coord", crs=WGS84)

                # Find the soil types of each cropland grid by joining the cropland GeoDataFrame with gSSURGO
                # GeoDataFrame. Remove non-soil grids
                df = gpd.tools.sjoin(sub_df, soil, predicate="within", how="left")
                df = df[~df['muname'].isin(GSSURGO_NON_SOIL_TYPES)]
                df = df[df['mukey'].notna()]

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
                selected_soil = selected_soil[selected_soil['majcompflag'] == 'Yes'].sort_values(by='top')
                selected_soil = selected_soil[selected_soil['hzname'] != 'R']

                # Calculate soil depth
                layer_depths = [layer['bottom'] for layer in SOIL_LAYERS]
                soil_depth = min(layer_depths, key=lambda x: abs(x - selected_soil.iloc[-1]['bottom']))

                # Generate a soil file using gSSURGO data
                fn = f'./soil/{index}_{t}_gSSURGO.soil'
                generate_soil_file(fn, 'gSSURGO', county['NAME_2'], county['NAME_1'], t, hsg, slope, soil_depth, selected_soil)

                # Use the dominant soil type and drop grids with missing SoilGrids data
                df = df[df['muname'] == muname].dropna()

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
                    {v: [layer[v] for layer in SOILGRIDS_LAYERS] for v in SOILGRIDS_LAYERS[0]}
                )

                for v in SOILGRIDS_PARAMETERS:
                    soilgrids_df[v] = soilgrids_df.apply(lambda x: selected_point[f'{v}_{x["name"]}'], axis=1)

                generate_soil_file(fn, 'SoilGrids', county['NAME_2'], county['NAME_1'], t, hsg, slope, soil_depth, soilgrids_df, lat=selected_point['y'], lon=selected_point['x'])


if __name__ == '__main__':
    main()
