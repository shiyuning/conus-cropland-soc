import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import rioxarray
from matplotlib.colors import ListedColormap
from rasterio.enums import Resampling
from shapely.geometry import Polygon
from settings import TOTAL_DEPTH, AREA_SOC_CSV
from settings import COUNTY_SHP
from settings import LU_MAP, LU_TYPES, AG_TYPES
from settings import SOILGRIDS_DIRECTORY, SOILGRIDS_PARAMETERS, SOILGRIDS_LAYERS

CONUS_CENTRAL_LON = -98.583
DI = DJ = 0.00026949
LAT0 = 24.0
IND_J = lambda lat: int(round((lat - LAT0) / DJ))
FUNCS = {
    'mean': lambda x: x.mean(),
    'max': lambda x: x.max(),
    'min': lambda x: x.min(),
}
MIN_REPORT_AREA = 10.0 # ha


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


def plot_cropland_area(county_lu, county_boundary, gid, county, state, state_abbreviation):
    colors = [
        'blue',
        'silver',
        'lime',
        'yellow',
    ]
    cmap = ListedColormap(colors)

    gdf = gpd.GeoDataFrame({'id': [1], 'geometry': [county_boundary]}, crs='epsg:4326')

    try:
        fig, ax = plt.subplots()
        img = county_lu.plot(ax=ax, vmin=-0.5, vmax=3.5, cmap=cmap)
        cb = img.colorbar
        cb.set_ticks([0, 1, 2, 3])
        cb.set_ticklabels(['water', 'non-croplands', 'irrigated', 'rainfed'])

        gdf.plot(ax=ax, fc='None')
        ax.set_title(f'{county}, {state}')
        ax.set_xlabel('Longitude (degree)')
        ax.set_ylabel('Latitude (degree)')
        plt.tight_layout()
        fig.savefig(f'img/{gid}_{county.replace(" ", "")}_{state_abbreviation}.png', dpi=300)
        plt.close()
    except: pass


def soc_weight(bulk_density, soc_percent, thickness_meter):
    return soc_percent * 0.01 * thickness_meter * bulk_density * 1.0E4


def calculate_cropland_soc(lu_xds, area_gdf, boundary, gid, county, state, state_abbreviation, layers, variables):
    with open(f'./temp/{gid}', 'w') as f: pass

    county_lu = lu_xds.rio.clip([boundary], from_disk=True)

    plot_cropland_area(county_lu, boundary, gid, county, state, state_abbreviation)

    df = county_lu[0].to_pandas().stack(dropna=False)
    df.name = 'lu'

    # No cropland
    if df[df.isin(AG_TYPES)].empty : return [0.0, 0.0] + list(np.nan * np.ones(len(variables) - 2))

    for v in ['bulk_density', 'soc']:
        for layer in layers:
            soil_xds = rioxarray.open_rasterio(f'{SOILGRIDS_DIRECTORY}/USA.{gid.split(".")[1]}_1/{SOILGRIDS_PARAMETERS[v]["variable"]}_{layer["name"]}.tif', masked=True).rio.reproject('EPSG:4326')
            _soil = soil_xds.rio.reproject_match(county_lu, resampling=Resampling.nearest)
            _soil = _soil.rio.clip([boundary], from_disk=True)

            _df = _soil[0].to_pandas().stack(dropna=False) * SOILGRIDS_PARAMETERS[v]['multiplier']
            _df.name = f'{v}_{layer["name"]}'
            df = pd.concat([df, _df], axis=1)

    # Retrieve the areas of each LGRIP30 grid
    df = df[df['lu'].isin(AG_TYPES)].reset_index()
    df['ind'] = df['y'].map(lambda y: IND_J(y))
    df = pd.merge(df, area_gdf, on='ind', how='left')

    for layer in layers:
        df[f'soc_weight_{layer["name"]}'] = df.apply(lambda x: soc_weight(x[f'bulk_density_{layer["name"]}'], x[f'soc_{layer["name"]}'], layer['thickness']), axis=1)

    df[f'soc_weight_0-{int(TOTAL_DEPTH * 100)}cm'] = df[[f'soc_weight_{layer["name"]}' for layer in layers]].sum(axis=1, skipna=False)

    result = {}
    for t in LU_TYPES:
        area = df[df['lu'].isin(LU_TYPES[t])]['area_ha'].sum()
        result[f'{t}_area'] = area if area > MIN_REPORT_AREA else 0.0

        for layer in [l['name'] for l in layers] + [f'0-{int(TOTAL_DEPTH * 100)}cm']:
            sub_df = df.loc[df['lu'].isin(LU_TYPES[t]), f'soc_weight_{layer}']
            for f in FUNCS:
                result[f'soc_{t}_{f}_{layer}'] = np.nan if sub_df.empty or result[f'{t}_area'] == 0.0 else FUNCS[f](sub_df)

    return [result[v] for v in variables]


def main():
    # Read county boundaries from GADM shapefile
    usa_gdf = gpd.read_file(COUNTY_SHP)
    usa_gdf.set_index('GID_2', inplace=True)
    usa_gdf['GID'] = usa_gdf.index

    # Generate a CONUS GeoDataFrame by remoing Alaska and Hawaii
    conus_gdf = usa_gdf.drop(usa_gdf[(usa_gdf['NAME_1'] == 'Alaska') | (usa_gdf['NAME_1'] == 'Hawaii')].index)

    # Read cropland map
    conus_lu = rioxarray.open_rasterio(LU_MAP, masked=True)


    area_gdf = calculate_grid_areas(conus_lu.coords['y'], 'epsg:4326')


    # Create an empty csv to store results
    with open(AREA_SOC_CSV, 'w') as f: pass

    layers = [layer for layer in SOILGRIDS_LAYERS if layer['bottom'] <= TOTAL_DEPTH]

    # Generate a list of all variables that need to be calculated
    variables = [f'{t}_area' for t in LU_TYPES]
    for d in [layer['name'] for layer in layers] + [f'0-{int(TOTAL_DEPTH * 100)}cm']:
        for t in LU_TYPES:
            for v in FUNCS:
                variables.append(f'soc_{t}_{v}_{d}')

    conus_gdf[variables] = conus_gdf.apply(
        lambda x: calculate_cropland_soc(
            conus_lu, area_gdf, x['geometry'],
            x['GID'], x['NAME_2'], x['NAME_1'], x['HASC_2'].split('.')[1],
            layers, variables,
        ),
        axis=1,
        result_type='expand',
    )

    conus_gdf = conus_gdf[conus_gdf['rainfed_area'] + conus_gdf['irrigated_area'] > 0.0]

    with open(AREA_SOC_CSV, 'a') as f:
        f.write('# CONUS county cropland areas and SOC weight at top 30-cm soil depth\n')
        f.write('#\n')
        f.write('# DATA SOURCES\n')
        f.write('#  Cropland areas: LGRIP30 L3 version 2\n')
        f.write('#  SOC: SoilGrids250m version 2.0\n')
        f.write('#\n')
        f.write('# UNITS\n')
        f.write('#  Cropland areas: ha\n')
        f.write('#  Cropland SOC weight: Mg/ha\n')
        f.write('#\n')
        f.write('# NOTE\n')
        f.write('# Cropland areas under 10 ha is reported as 0.\n')
        conus_gdf[['NAME_1', 'NAME_2'] + variables].to_csv(
            f,
            float_format='%.2f',
        )


if __name__ == '__main__':
    main()
