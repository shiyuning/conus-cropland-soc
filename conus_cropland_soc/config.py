AREA_SOC_CSV = f'./conus_cropland_soc_0-30cm_soilgrids.csv'
MIN_REPORT_AREA = 10.0  # minimum area to report (ha)

GADM_PATH = '/storage/home/yzs123/work/data/gadm/'
SOILGRIDS_PATH = '/storage/home/yzs123/work/data/SoilGrids/'
GSSURGO_PATH = '/storage/home/yzs123/work/data/gSSURGO/'

LU_MAP = f'/storage/home/yzs123/work/data/LGRIP30_L3_v002/LGRIP30_L3_2020_v002.tif'
LU_TYPES = {
    'rainfed': [3],
    'irrigated': [2],
}
AG_TYPES = [2, 3]

# coordinate reference systems
WGS84 = 'epsg:4326'     # WGS84
AEAC = 'esri:102003'    # Albers Equal Area projection
