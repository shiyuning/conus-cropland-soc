"""This script calculates cropland areas and SOC weights for CONUS counties.
The cropland map is based on the LGRIP30 L3 version 2 dataset, and the soil parameters are from the SoilGrids250m
version 2.0 dataset.
"""
import geopandas as gpd
import numpy as np
import os
import pandas as pd
import rioxarray
from shapely.geometry import Polygon
from config import TOTAL_DEPTH, AREA_SOC_CSV, MIN_REPORT_AREA
from config import LU_MAP, LU_TYPES, AG_TYPES
from config import WGS84
from gadm import read_gadm
from soilgrids import SOILGRIDS_LAYERS
from soilgrids import read_soilgrids_maps, reproject_match_soilgrids_maps

CONUS_CENTRAL_LON = -98.583 # central longitude of the CONUS (degree)
DI = DJ = 0.00026949    # LGRI30 grid size (degree)
LAT0 = 24.0             # reference latitude (degree)
IND_J = lambda lat: int(round((lat - LAT0) / DJ))
FUNCS = {
    'mean': lambda x: x.mean(),
    'max': lambda x: x.max(),
    'min': lambda x: x.min(),
}


def get_lgrip_grid(x, y):
    x0 = max(-180, x)
    x1 = min(180, x + DI)
    y0 = max(-90, y)
    y1 = min(90, y + DJ)

    points = [(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]

    return Polygon([[p[0], p[1]] for p in points])


def calculate_grid_areas(latitudes, crs):
    area_df = latitudes.to_pandas().reset_index()
    area_df['ind'] = area_df['y'].map(lambda y: IND_J(y))
    area_df['grid'] = area_df.apply(lambda point: get_lgrip_grid(CONUS_CENTRAL_LON, point['y']), axis=1)
    area_gdf = gpd.GeoDataFrame(area_df, geometry='grid', crs=crs)
    area_gdf['area_ha'] = area_gdf.to_crs('+proj=cea +units=m').area / 1.0E4

    return area_gdf


def soc_weight(bulk_density, soc_percent, thickness_meter):
    return soc_percent * 0.01 * thickness_meter * bulk_density * 1.0E4


def calculate_cropland_soc(lu_xds, area_gdf, soilgrids_xds, boundary, county_id, layers, variables):
    with open(f'./temp/{county_id}', 'w') as f: pass

    # Align SoilGrids maps with cropland map
    df = reproject_match_soilgrids_maps(soilgrids_xds, lu_xds, 'lu', boundary, layers, ['bulk_density', 'soc'])

    # No cropland
    if df[df['lu'].isin(AG_TYPES)].empty : return [0.0, 0.0] + list(np.nan * np.ones(len(variables) - 2))

    # Retrieve the areas of each LGRIP30 grid
    df = df[df['lu'].isin(AG_TYPES)].reset_index()
    df['ind'] = df['y'].map(lambda y: IND_J(y))
    df = pd.merge(df, area_gdf, on='ind', how='left')

    for layer in layers:
        df[f'soc_weight_{layer}'] = df.apply(lambda x: soc_weight(x[f'bulk_density_{layer}'], x[f'soc_{layer}'], SOILGRIDS_LAYERS[layer]['thickness']), axis=1)

    df[f'soc_weight_0-{int(TOTAL_DEPTH * 100)}cm'] = df[[f'soc_weight_{layer}' for layer in layers]].sum(axis=1, skipna=False)

    result = {}
    for t in LU_TYPES:
        area = df[df['lu'].isin(LU_TYPES[t])]['area_ha'].sum()
        result[f'{t}_area'] = area if area > MIN_REPORT_AREA else 0.0

        for layer in layers + [f'0-{int(TOTAL_DEPTH * 100)}cm']:
            sub_df = df.loc[df['lu'].isin(LU_TYPES[t]), f'soc_weight_{layer}'].copy()
            for f in FUNCS:
                result[f'soc_{t}_{f}_{layer}'] = np.nan if sub_df.empty or result[f'{t}_area'] == 0.0 else FUNCS[f](sub_df)

    return [result[v] for v in variables]


def write_to_csv(conus_gdf, variables):
    conus_gdf = conus_gdf[conus_gdf['rainfed_area'] + conus_gdf['irrigated_area'] > 0.0]

    with open(AREA_SOC_CSV, 'w') as f: pass
    with open(AREA_SOC_CSV, 'a') as f:
        f.write('# CONUS county cropland areas and SOC weight at top 30-cm soil depth\n')
        f.write('#\n')
        f.write('# DATA SOURCES\n')
        f.write('#  Cropland areas: LGRIP30 L3 version 2\n')
        f.write('#  SOC: SoilGrids250m version 2.0\n')
        f.write('# UNITS\n')
        f.write('#  Cropland areas: ha\n')
        f.write('#  Cropland SOC weight: Mg/ha\n')
        f.write('# NOTE\n')
        f.write('#  Cropland areas under 10 ha is reported as 0.\n')
        conus_gdf[['NAME_1', 'NAME_2'] + variables].to_csv(
            f,
            float_format='%.2f',
        )


def main():
    # Read CONUS counties
    conus_gdf = read_gadm('USA', 'county', conus=True)

    # Read cropland map
    lu_xds = rioxarray.open_rasterio(LU_MAP, masked=True)

    # Calculate the areas of each LGRIP30 grid
    area_gdf = calculate_grid_areas(lu_xds.coords['y'], WGS84)

    # Find SoilGrids layers that are shallower than the total depth
    layers = [layer for layer in SOILGRIDS_LAYERS if SOILGRIDS_LAYERS[layer]['bottom'] <= TOTAL_DEPTH]

    os.makedirs('temp', exist_ok=True)

    # Generate a list of all variables that need to be calculated
    variables = [f'{t}_area' for t in LU_TYPES]
    for layer in layers + [f'0-{int(TOTAL_DEPTH * 100)}cm']:
        for t in LU_TYPES:
            for v in FUNCS:
                variables.append(f'soc_{t}_{v}_{layer}')

    # Calculate cropland areas and SOC weights
    output_df = pd.DataFrame()
    for i in range(52):
        state_id = f'USA.{i}_1'
        if state_id not in conus_gdf['GID_1'].unique(): continue

        sub_gdf = conus_gdf[conus_gdf['GID_1'] == state_id].copy()

        # Read SoilGrids maps
        soilgrids_xds = read_soilgrids_maps(state_id, layers, ['bulk_density', 'soc'], WGS84)

        sub_gdf[variables] = sub_gdf.apply(
            lambda x: calculate_cropland_soc(lu_xds, area_gdf, soilgrids_xds, x['geometry'], x['GID'], layers, variables),
            axis=1,
            result_type='expand',
        )

        output_df = pd.concat(
            [output_df, sub_gdf],
            axis=0,
        )

    write_to_csv(output_df, variables)


if __name__ == '__main__':
    main()
