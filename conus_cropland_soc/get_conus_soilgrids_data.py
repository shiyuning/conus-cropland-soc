"""Get SoilGrids data for each CONUS state
"""
import os
from itertools import product
from cycles.gadm import read_gadm
from cycles.soilgrids import SOILGRIDS_PROPERTIES, SOILGRIDS_LAYERS
from cycles.soilgrids import download_soilgrids_data
from config import GADM_PATH, SOILGRIDS_PATH
from config import WGS84

"""Get SoilGrids data given state boundary
"""
def get_soilgrids_data(path, gid, boundary, maps):
    os.makedirs(f'{path}/{gid}', exist_ok=True)

    bbox = boundary.bounds

    # When using just the bounding box of the state boundaries, in some cases the downloaded data do not cover the
    # entire state. Therefore a buffer zone is being used to ensure data integrity.
    buffer = [min(2.0, 0.5 * (bbox[2] - bbox[0])), min(2.0, 0.5 * (bbox[3] - bbox[1]))]

    bbox = [
        bbox[0] - buffer[0],
        bbox[1] - buffer[1],
        bbox[2] + buffer[0],
        bbox[3] + buffer[1],
    ]

    download_soilgrids_data(
        maps,
        f'{path}/{gid}',
        bbox,
        WGS84,
    )


def main():
    # Read CONUS state maps
    conus_gdf = read_gadm(GADM_PATH, 'USA', 'state', conus=True)

    # List of maps to be downloaded
    maps = []
    for v in SOILGRIDS_PROPERTIES:
        maps = maps + [f'{v}@{layer}' for layer in SOILGRIDS_PROPERTIES[v]['layers']]

    # Get SoilGrids data
    for index, row in conus_gdf.iterrows():
        get_soilgrids_data(SOILGRIDS_PATH, row['GID'], row['geometry'], maps)


if __name__ == '__main__':
    main()
