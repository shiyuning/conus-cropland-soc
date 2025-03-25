"""This script calculates cropland areas and SOC weights for CONUS counties.
The cropland map is based on the LGRIP30 L3 version 2 dataset, and the soil organic carbon stocks are from SoilGrids250m
version 2.0 dataset.
"""
import geopandas as gpd
import numpy as np
import os
import pandas as pd
import rioxarray
from cycles.gadm import read_gadm
from cycles.soilgrids import read_soilgrids_maps, reproject_match_soilgrids_maps
from shapely.geometry import Polygon
from config import GADM_PATH, SOILGRIDS_PATH
from config import AREA_SOC_CSV, MIN_REPORT_AREA
from config import LU_MAP, LU_TYPES, AG_TYPES

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


def calculate_cropland_soc(lu_xds, area_gdf, soilgrids_xds, boundary, county_id, variables):
    with open(f'./temp/{county_id}', 'w') as f: pass

    # Align SoilGrids maps with cropland map
    df = reproject_match_soilgrids_maps(soilgrids_xds, lu_xds, 'lu', boundary, ['0-30cm'], ['organic_carbon_stocks'])

    # No cropland
    if df[df['lu'].isin(AG_TYPES)].empty : return [0.0, 0.0] + list(np.nan * np.ones(len(variables) - 2))

    # Retrieve the areas of each LGRIP30 grid
    df = df[df['lu'].isin(AG_TYPES)].reset_index()
    df['ind'] = df['y'].map(lambda y: IND_J(y))
    df = pd.merge(df, area_gdf, on='ind', how='left')

    result = {}
    for t in LU_TYPES:
        area = df[df['lu'].isin(LU_TYPES[t])]['area_ha'].sum()
        result[f'{t}_area'] = area if area > MIN_REPORT_AREA else 0.0

        sub_df = df.loc[df['lu'].isin(LU_TYPES[t])]
        if sub_df.empty or result[f'{t}_area'] == 0.0:
            result.update({f'soc_{t}_{f}': np.nan for f in FUNCS})
            continue

        result.update({f'soc_{t}_{f}': FUNCS[f](sub_df['organic_carbon_stocks_0-30cm']) for f in FUNCS})

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
    conus_gdf = read_gadm(GADM_PATH, 'USA', 'county', conus=True)

    # Read cropland map
    lu_xds = rioxarray.open_rasterio(LU_MAP, masked=True)

    # Calculate the areas of each LGRIP30 grid
    area_gdf = calculate_grid_areas(lu_xds.coords['y'], lu_xds.rio.crs)

    os.makedirs('temp', exist_ok=True)

    # Generate a list of all variables that need to be calculated
    variables = [f'{t}_area' for t in LU_TYPES]
    for t in LU_TYPES:
        for v in FUNCS:
            variables.append(f'soc_{t}_{v}')

    # Calculate cropland areas and SOC weights
    output_df = pd.DataFrame()

    for i in range(52):
        state_id = f'USA.{i}_1'
        if state_id not in conus_gdf['GID_1'].unique(): continue

        sub_gdf = conus_gdf[conus_gdf['GID_1'] == state_id].copy()

        # Read SoilGrids maps
        soilgrids_xds = read_soilgrids_maps(SOILGRIDS_PATH, state_id, ['0-30cm'], ['organic_carbon_stocks'])

        sub_gdf[variables] = sub_gdf.apply(
            lambda x: calculate_cropland_soc(lu_xds, area_gdf, soilgrids_xds, x['geometry'], x['GID'], variables),
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
