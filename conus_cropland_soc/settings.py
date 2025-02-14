TOTAL_DEPTH = 0.3 # m
AREA_SOC_CSV = f'./conus_cropland_soc_0-{int(TOTAL_DEPTH * 100)}cm.csv'

STATE_SHP = f'/storage/home/yzs123/work/data/gadm/gadm41_USA_1.shp'
COUNTY_SHP = f'/storage/home/yzs123/work/data/gadm/gadm41_USA_2.shp'

LU_MAP = f'/storage/home/yzs123/work/data/LGRIP30_L3_v002/LGRIP30_L3_2020_v002.tif'
LU_TYPES = {
    'rainfed': [3],
    'irrigated': [2],
}
AG_TYPES = [2, 3]

SOIL_PARAMETERS = ['clay', 'sand', 'soc', 'bulk_density']
SOIL_LAYERS = [
    # units: top (m), bottom (m), thickness (m), NO3 (kg/ha), NH4 (Kg/ha)
    {'top': 0, 'bottom': 0.05, 'thickness': 0.05, 'no3': 10, 'nh4': 1},
    {'top': 0.05, 'bottom': 0.1, 'thickness': 0.05, 'no3': 10, 'nh4': 1},
    {'top': 0.1, 'bottom': 0.2, 'thickness': 0.1, 'no3': 7, 'nh4': 1},
    {'top': 0.2, 'bottom': 0.4, 'thickness': 0.2, 'no3': 4, 'nh4': 1},
    {'top': 0.4, 'bottom': 0.6, 'thickness': 0.2, 'no3': 2, 'nh4': 1},
    {'top': 0.6, 'bottom': 0.8, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 0.8, 'bottom': 1.0, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 1.0, 'bottom': 1.2, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 1.2, 'bottom': 1.4, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 1.4, 'bottom': 1.6, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 1.6, 'bottom': 1.8, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
    {'top': 1.8, 'bottom': 2.0, 'thickness': 0.2, 'no3': 1, 'nh4': 1},
]

GSSURGO = lambda state: f'/storage/work/yzs123/data/gSSURGO/gSSURGO_{state}.gdb/'
GSSURGO_LUT = lambda lut, state: f'/storage/work/yzs123/data/gSSURGO/{lut}_{state}.csv'
GSSURGO_PARAMETERS = {
    'clay': {'variable': 'claytotal_r', 'multiplier': 1.0}, # %
    'sand': {'variable': 'sandtotal_r', 'multiplier': 1.0}, # %
    'soc': {'variable': 'om_r', 'multiplier': 0.58},    # %
    'bulk_density': {'variable': 'dbthirdbar_r', 'multiplier': 1.0},    # Mg/m3
    'top': {'variable': 'hzdept_r', 'multiplier': 0.01},    # m
    'bottom': {'variable': 'hzdepb_r', 'multiplier': 0.01}, # m
}
GSSURGO_NON_SOIL_TYPES = ['Water', 'Pits', 'Dam', 'Dumps', 'Levee']

SOILGRIDS_DIRECTORY = f'/storage/home/yzs123/work/data/SoilGrids/'
SOILGRIDS_PARAMETERS = {
    'clay': {'variable': 'clay', 'multiplier': 0.1},    # %
    'sand': {'variable': 'sand', 'multiplier': 0.1},    # %
    'soc': {'variable': 'soc', 'multiplier': 0.01},     # %
    'bulk_density': {'variable': 'bdod', 'multiplier': 0.01},   # Mg/m3
}
SOILGRIDS_LAYERS = [
    # units: m
    {'name': '0-5cm', 'top': 0, 'bottom': 0.05, 'thickness': 0.05},
    {'name': '5-15cm', 'top': 0.05, 'bottom': 0.15, 'thickness': 0.10},
    {'name': '15-30cm', 'top': 0.15, 'bottom': 0.3, 'thickness': 0.15},
    {'name': '30-60cm', 'top': 0.3, 'bottom': 0.6, 'thickness': 0.3},
    {'name': '60-100cm', 'top': 0.6, 'bottom': 1.0, 'thickness': 0.4},
    {'name': '100-200cm', 'top': 1.0, 'bottom': 2.0, 'thickness': 1.0},
]

CURVE_NUMBERS = {
    #row crops, SR, Good
    'A': 67,
    'B': 78,
    'C': 85,
    'D': 89,
}

# coordinate reference systems
WGS84 = 'epsg:4326'     # WGS84
AEAC = 'esri:102003'    # Albers Equal Area projection
NAD83 = 'epsg:5070'     # NAD83 / Conus Albers, CRS of gSSURGO
HOMOLOSINE = 'urn:ogc:def:crs:EPSG::152160' # Interrupted Goode Homolosine, CRS of SoilGrids
