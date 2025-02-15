import pandas as pd
import rioxarray
from rasterio.enums import Resampling

SOILGRIDS_DIRECTORY = f'/storage/home/yzs123/work/data/SoilGrids/'
SOILGRIDS_PARAMETERS = {
    'clay': {'variable': 'clay', 'multiplier': 0.1},    # %
    'sand': {'variable': 'sand', 'multiplier': 0.1},    # %
    'soc': {'variable': 'soc', 'multiplier': 0.01},     # %
    'bulk_density': {'variable': 'bdod', 'multiplier': 0.01},   # Mg/m3
}
SOILGRIDS_LAYERS = {
    # units: m
    '0-5cm': {'top': 0, 'bottom': 0.05, 'thickness': 0.05},
    '5-15cm': {'top': 0.05, 'bottom': 0.15, 'thickness': 0.10},
    '15-30cm': {'top': 0.15, 'bottom': 0.3, 'thickness': 0.15},
    '30-60cm': {'top': 0.3, 'bottom': 0.6, 'thickness': 0.3},
    '60-100cm': {'top': 0.6, 'bottom': 1.0, 'thickness': 0.4},
    '100-200cm': {'top': 1.0, 'bottom': 2.0, 'thickness': 1.0},
}
HOMOLOSINE = 'urn:ogc:def:crs:EPSG::152160' # Interrupted Goode Homolosine, CRS of SoilGrids

# Read state SoilGrids data
def read_soilgrids_maps(state_id, layers, parameters, crs=HOMOLOSINE):
    soilgrids_xds = {}
    for layer in layers:
        for v in parameters:
            soilgrids_xds[v + layer] = rioxarray.open_rasterio(f'{SOILGRIDS_DIRECTORY}/{state_id}/{SOILGRIDS_PARAMETERS[v]["variable"]}_{layer}.tif', masked=True).rio.reproject(crs)

    return soilgrids_xds


def reproject_match_soilgrids_maps(soilgrids_xds, reference_xds, reference_name, boundary, layers, parameters):
    reference_xds = reference_xds.rio.clip([boundary], from_disk=True)
    df = pd.DataFrame(reference_xds[0].to_series().rename(reference_name))

    for v in parameters:
        for layer in layers:
            soil_xds = soilgrids_xds[v + layer].rio.reproject_match(reference_xds, resampling=Resampling.nearest)
            soil_xds = soil_xds.rio.clip([boundary], from_disk=True)

            soil_df = pd.DataFrame(soil_xds[0].to_series().rename(f'{v}_{layer}')) * SOILGRIDS_PARAMETERS[v]['multiplier']
            df = pd.concat([df, soil_df], axis=1)

    return df
