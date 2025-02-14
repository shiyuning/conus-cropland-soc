"""Get SoilGrids data for each CONUS state
"""
import geopandas as gpd
import os
from owslib.wcs import WebCoverageService
from shapely.geometry import Point
from settings import STATE_SHP
from settings import SOILGRIDS_DIRECTORY, SOILGRIDS_PARAMETERS, SOILGRIDS_LAYERS


"""Convert bounding boxes in WGS84 to SoilGrids CRS
"""
def get_bounding_box(bbox, buffer, crs):
    d = {'col1': ['NW', 'SE'], 'geometry': [Point(bbox[0] - buffer[0], bbox[3] + buffer[1]), Point(bbox[2] + buffer[0], bbox[1] - buffer[1])]}
    gdf = gpd.GeoDataFrame(d, crs=crs)
    gdf = gdf.set_index('col1')

    _gdf = gpd.read_file(f'{SOILGRIDS_DIRECTORY}/bdod_index.shp')
    converted = gdf.to_crs(_gdf.crs)

    return [
        converted.loc['NW', 'geometry'].xy[0][0],
        converted.loc['SE', 'geometry'].xy[1][0],
        converted.loc['SE', 'geometry'].xy[0][0],
        converted.loc['NW', 'geometry'].xy[1][0],
    ]


"""Use WebCoverageService to get SoilGrids data
bbox should be the lat/lon of the bounding box, in the order of [west, south, east, north]
"""
def _get_data(gid, var, depth, bbox, buffer, crs):
    bbox = get_bounding_box(bbox, buffer, crs)
    wcs = WebCoverageService(f'http://maps.isric.org/mapserv?map=/map/{var}.map', version='1.0.0')
    while True:
        try:
            response = wcs.getCoverage(
                identifier=f'{var}_{depth}_mean',
                crs='urn:ogc:def:crs:EPSG::152160',
                bbox=bbox,
                resx=250, resy=250,
                format='GEOTIFF_INT16')

            with open(f'{SOILGRIDS_DIRECTORY}/{gid}/{var}_{depth}.tif', 'wb') as file: file.write(response.read())
            return
        except:
            continue


"""Get SoilGrids data given state boundary
When using just the bounding box of the state boundaries, in some cases the downloaded data do not cover the entire
state. Therefore a buffer zone is being used to ensure data integrity.
"""
def get_soilgrids_data(gid, boundary):
    print(gid)
    os.makedirs(f'{SOILGRIDS_DIRECTORY}/{gid}', exist_ok=True)
    bbox = boundary.bounds
    buffer = [min(2.0, 0.5 * (bbox[2] - bbox[0])), min(2.0, 0.5 * (bbox[3] - bbox[1]))]
    for v in SOILGRIDS_PARAMETERS:
        for layer in SOILGRIDS_LAYERS:
            _get_data(gid, SOILGRIDS_PARAMETERS[v]['variable'], layer['name'], bbox, buffer, 'epsg:4326')


def main():
    # Read state boundaries from GADM shapefile
    usa_gdf = gpd.read_file(f'{STATE_SHP}')
    usa_gdf.set_index('GID_1', inplace=True)
    usa_gdf['GID'] = usa_gdf.index

    # Generate a CONUS GeoDataFrame by removing Alaska and Hawaii
    conus_gdf = usa_gdf.drop(usa_gdf[(usa_gdf['NAME_1'] == 'Alaska') | (usa_gdf['NAME_1'] == 'Hawaii')].index)

    # Get SoilGrids data
    for index, row in conus_gdf.iterrows(): get_soilgrids_data(row['GID'], row['geometry'])


if __name__ == '__main__':
    main()
