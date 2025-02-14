import numpy as np
import pandas as pd
from settings import SOIL_PARAMETERS, SOIL_LAYERS
from settings import CURVE_NUMBERS

def overlapping_depth(top1, bottom1, top2, bottom2):
    return max(0.0, min(bottom1, bottom2) - max(top1, top2))


def calculate_parameter(soil_df, parameter, top, bottom):
    soil_df['weight'] = soil_df.apply(lambda x: overlapping_depth(x['top'], x['bottom'], top, bottom) / (bottom - top), axis=1)
    soil_df = soil_df[soil_df['weight'] > 0]

    return np.sum(np.array(soil_df[parameter] * soil_df['weight'])) / sum(soil_df['weight'])


def generate_soil_file(fn, source, county, state, irrigation_type, hsg, slope, soil_depth, soil_df, lat=-999, lon=-999):
    df = pd.DataFrame.from_dict(
        {v: [layer[v] for layer in SOIL_LAYERS if layer['bottom'] <= soil_depth] for v in SOIL_LAYERS[0]}
    )

    for v in SOIL_PARAMETERS:
        df[v] = df.apply(lambda x: calculate_parameter(soil_df, v, x['top'], x['bottom']), axis=1)

    cn = -999 if not hsg else CURVE_NUMBERS[hsg]

    with open(fn, 'w') as f:
        f.write(f"# Cycles soil file for {irrigation_type} cropland in {county}, {state}\n#\n")
        f.write(f"# Clay, sand, soil organic carbon, and bulk density are obtained from {source}.\n")
        f.write("# Hydrologic soil group, slope, and soil depth are obtained from gSSURGO.\n")
        if source == 'SoilGrids':
            f.write(f"# The data are sampled at Latitude {f'%.4f' % lat}, Longitude {f'%.4f' % lon}.\n")
        else:
            f.write(f"# The data are sampled from MUNAME: {soil_df.iloc[0]['muname']}, MUKEY: {soil_df.iloc[0]['mukey']}\n")
        f.write("# NO3, NH4, and fractions of horizontal and vertical bypass flows are default empirical values.\n#\n")
        if hsg == '':
            f.write("# Hydrologic soil group MISSING DATA.\n")
        else:
            f.write(f"# Hydrologic soil group {hsg}.\n")
            f.write("# The curve number for row crops with straight row treatment is used.\n")

        f.write("%-15s\t%d\n" % ("CURVE_NUMBER", cn))
        f.write("%-15s\t%.2f\n" % ("SLOPE", slope))

        f.write("%-15s\t%d\n" % ("TOTAL_LAYERS", len(soil_df)))
        f.write(('%-7s\t'*12 + '%s\n') % (
            "LAYER", "THICK", "CLAY", "SAND", "SOC", "BD", "FC", "PWP", "SON", "NO3", "NH4", "BYP_H", "BYP_V"
        ))

        f.write(('%-7s\t'*12 + '%s\n') % (
            "#", "m", "%", "%", "%", "Mg/m3", "m3/m3", "m3/m3", "kg/ha", "kg/ha", "kg/ha", "-", "-"
        ))

        layer = 1
        for _, row in df.iterrows():
            f.write('%-7d\t' % layer)
            f.write('%-7.2f\t' % float(row['thickness']))
            f.write('%-7s\t' % '-999' if np.isnan(row['clay']) else '%-7.1f\t' % float(row['clay']))
            f.write('%-7s\t' % '-999' if np.isnan(row['sand']) else '%-7.1f\t' % float(row['sand']))
            f.write('%-7s\t' % '-999' if np.isnan(row['soc']) else '%-7.2f\t' % float(row['soc']))
            f.write('%-7s\t' % '-999' if np.isnan(row['bulk_density']) else '%-7.2f\t' % float(row['bulk_density']))
            f.write(('%-7d\t'*3 + '%-7.1f\t'*2 + '%-7.1f\t%.1f\n') % (
                -999, -999, -999, float(row['no3']), float(row['nh4']), 0.0, 0.0
            ))
            layer += 1
