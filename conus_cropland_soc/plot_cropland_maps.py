import geopandas as gpd
import matplotlib.pyplot as plt
import os
import rioxarray
from matplotlib.colors import ListedColormap
from config import LU_MAP
from config import WGS84
from gadm import STATE_ABBREVIATIONS
from gadm import read_gadm


def plot_cropland_area(lu_xds, county_boundary, gid, county, state, state_abbreviation):
    colors = [
        'blue',
        'silver',
        'lime',
        'yellow',
    ]
    cmap = ListedColormap(colors)

    gdf = gpd.GeoDataFrame({'id': [1], 'geometry': [county_boundary]}, crs=WGS84)

    lu_xds = lu_xds.rio.clip([county_boundary], from_disk=True)

    try:
        fig, ax = plt.subplots()
        img = lu_xds.plot(ax=ax, vmin=-0.5, vmax=3.5, cmap=cmap)
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


def main():
    # Read CONUS counties
    conus_gdf = read_gadm('USA', 'county', conus=True)

    # Read cropland map
    lu_xds = rioxarray.open_rasterio(LU_MAP, masked=True)

    os.makedirs('img', exist_ok=True)

    conus_gdf.apply(
        lambda x: plot_cropland_area(lu_xds, x['geometry'], x['GID'], x['NAME_2'], x['NAME_1'], STATE_ABBREVIATIONS[x['GID_1']]),
        axis=1,
    )


if __name__ == '__main__':
    main()
