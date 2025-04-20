"""This script calculates cropland areas for CONUS counties.
The cropland map is based on the LGRIP30 L3 version 2 dataset.
"""
import geopandas as gpd
import pandas as pd
import rioxarray
from cycles.gadm import read_gadm
from shapely.geometry import Polygon
from config import GADM_PATH
from config import AREA_CSV, MIN_REPORT_AREA
from config import LU_MAP, MANAGEMENT_TYPES

CONUS_CENTRAL_LON = -98.583 # central longitude of the CONUS (degree)
DI = DJ = 0.00026949    # LGRI30 grid size (degree)
LAT0 = 24.0             # reference latitude (degree)
IND_J = lambda lat: int(round((lat - LAT0) / DJ))


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


def calculate_cropland_area(lu_xds, area_gdf, boundary, gid):
    xds = lu_xds.rio.clip([boundary], from_disk=True)
    df = pd.DataFrame(xds[0].to_series().rename('lu'))
    df = df[df['lu'].isin(sum(list(MANAGEMENT_TYPES.values()), []))]

    # No cropland
    if df.empty : return [0.0, 0.0]

    # Retrieve the areas of each LGRIP30 grid
    df = df.reset_index()
    df['ind'] = df['y'].map(lambda y: IND_J(y))
    df = pd.merge(df, area_gdf, on='ind', how='left')

    areas = {}
    for t in MANAGEMENT_TYPES:
        area = df[df['lu'].isin(MANAGEMENT_TYPES[t])]['area_ha'].sum()
        areas[t] = area if area > MIN_REPORT_AREA else 0.0

    return list(areas.values())


def main():
    # Read CONUS counties
    conus_gdf = read_gadm(GADM_PATH, 'USA', 'county', conus=True)

    # Read cropland map
    lu_xds = rioxarray.open_rasterio(LU_MAP, masked=True)

    # Calculate the areas of each row of LGRIP30 grid (all columns in the same row have the same area)
    area_gdf = calculate_grid_areas(lu_xds.coords['y'], lu_xds.rio.crs)

    # Calculate cropland areas
    conus_gdf[['rainfed_area', 'irrigated_area']] = conus_gdf.apply(
        lambda x: calculate_cropland_area(lu_xds, area_gdf, x['geometry'], x.name),
        axis=1,
        result_type='expand',
    )

    conus_gdf = conus_gdf[conus_gdf['rainfed_area'] + conus_gdf['irrigated_area'] > 0.0]
    conus_gdf.rename(columns={'NAME_1': 'state', 'NAME_2': 'county'}, inplace=True)

    conus_gdf[['state', 'county', 'rainfed_area', 'irrigated_area']].to_csv(
        AREA_CSV,
        float_format='%.2f',
    )


if __name__ == '__main__':
    main()
