"""Get SoilGrids data for each CONUS state
"""
import os
from soilgrids import SOILGRIDS_DIRECTORY, SOILGRIDS_PROPERTIES, SOILGRIDS_LAYERS
from soilgrids import download_soilgrids_data
from config import WGS84
from gadm import read_gadm


"""Get SoilGrids data given state boundary
"""
def get_soilgrids_data(path, gid, boundary):
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
        [layer for layer in SOILGRIDS_LAYERS],
        [v for v in SOILGRIDS_PROPERTIES],
        f'{path}/{gid}',
        bbox,
        WGS84,
    )


def main():
    # Read CONUS state maps
    conus_gdf = read_gadm('USA', 'state', conus=True)

    # Get SoilGrids data
    for index, row in conus_gdf.iterrows():
        get_soilgrids_data(SOILGRIDS_DIRECTORY, row['GID'], row['geometry'])


if __name__ == '__main__':
    main()
