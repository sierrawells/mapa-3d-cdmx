"""
Completa las secciones "Habilitar servicios de mapas base", "Exportar mapa
3D interactivo" y "Compartir mapa 3D interactivo" de instrucciones.pdf sobre
output/MapaBase_WEB.qgz:

1. Agrega el mapa base "ESRI Satellite" como capa XYZ al proyecto.
2. Activa la capa DEM_CDMX, ajusta Z exaggeration=3, fondo negro (Solid
   color) y resampling level=6.
3. Exporta el mapa 3D interactivo a output/index.html.

Ejecutar con:
    ./src/run_qgis_python.sh src/export_3d.py
"""

import os
import sys

from qgis.core import (
    QgsApplication,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)
from qgis.gui import QgsMapCanvas

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
PROJECT_PATH = os.path.join(OUTPUT_DIR, "MapaBase_WEB.qgz")


def open_project_and_canvas():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    qgs_app = QgsApplication([], False)
    qgs_app.initQgis()

    os.chdir(PROJECT_ROOT)

    project = QgsProject.instance()
    if not project.read(PROJECT_PATH):
        raise RuntimeError(f"No se pudo abrir el proyecto: {PROJECT_PATH}")

    root = project.layerTreeRoot()
    visible_layers = [
        node.layer()
        for node in root.findLayers()
        if node.isVisible() and node.layer() is not None
    ]

    canvas = QgsMapCanvas()
    canvas.setDestinationCrs(project.crs())
    canvas.setLayers(visible_layers)

    # Extensión que cubra todo el territorio del proyecto: se usa DEM_CDMX
    # como referencia (cubre toda el área de estudio).
    full_extent = QgsRectangle()
    full_extent.setMinimal()

    dem_layers = project.mapLayersByName("DEM_CDMX")
    reference_layers = dem_layers if dem_layers else visible_layers

    for layer in reference_layers:
        layer_extent = layer.extent()
        if layer.crs() != project.crs():
            transform = QgsCoordinateTransform(layer.crs(), project.crs(), project)
            try:
                layer_extent = transform.transformBoundingBox(layer_extent)
            except Exception:
                continue
        if not layer_extent.isNull():
            full_extent.combineExtentWith(layer_extent)

    if full_extent.isNull() or full_extent.isEmpty():
        full_extent = project.viewSettings().defaultViewExtent()

    # Amplía la extensión un 30% para que se vea el mapa base (ESRI
    # Satellite) más allá de los límites de la CDMX (DEM_CDMX).
    full_extent.scale(1.3)

    canvas.setExtent(full_extent)

    return qgs_app, project, canvas


# ---------------------------------------------------------------------------
# Habilitar servicios de mapas base
# ---------------------------------------------------------------------------
def agregar_mapa_base_esri_satellite(project):
    """Agrega ESRI Satellite como capa XYZ (equivalente a QuickMapServices
    Web > QuickMapServices > ESRI > ESRI Satellite)."""
    url = (
        "type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D&zmax=19&zmin=0"
        "&crs=EPSG3857"
    )
    layer = QgsRasterLayer(url, "ESRI Satellite", "wms")
    if not layer.isValid():
        raise RuntimeError("No se pudo cargar la capa base ESRI Satellite")

    project.addMapLayer(layer, False)

    root = project.layerTreeRoot()
    # Coloca el mapa base al final (debajo) del árbol de capas
    node = root.insertLayer(len(root.children()), layer)
    # Paso 3: selecciona/activa ESRI Satellite para que se muestre detrás
    # (debajo) del resto de las capas del mapa base
    node.setItemVisibilityChecked(True)

    return layer


# ---------------------------------------------------------------------------
# Exportar / Compartir mapa 3D interactivo (Qgis2threejs)
# ---------------------------------------------------------------------------
def exportar_mapa_3d(project, canvas):
    import Qgis2threejs.core.export.export as q3js_export
    from Qgis2threejs.core.export.export import ThreeJSExporter
    from Qgis2threejs.core.exportsettings import ExportSettings
    from Qgis2threejs.utils import logging as q3js_logging  # noqa: E402

    q3js_logging.configureLoggers(log_to_stream=True)

    # Varios submódulos hicieron `from ...utils.logging import logger` antes
    # de que configureLoggers() lo inicializara, por lo que conservan una
    # referencia a None. Se actualizan todas esas referencias.
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith("Qgis2threejs") and getattr(mod, "logger", "x") is None:
            mod.logger = q3js_logging.logger

    from osgeo import gdal

    gdal.UseExceptions()

    settings = ExportSettings()
    settings.initialize(mapSettings=canvas.mapSettings(), requiresJsonSerializable=True)
    settings.localMode = True
    settings.updateLayers()

    # Scene settings: Z exaggeration = 3, fondo negro (Solid color)
    settings.setSceneProperties(
        {
            "lineEdit_zFactor": "3",
            "radioButton_Color": True,
            "colorButton_Color": [0, 0, 0, 255],
        }
    )

    # Activar la capa DEM_CDMX con resampling level 6
    map_layers = project.mapLayersByName("DEM_CDMX")
    if not map_layers:
        raise RuntimeError("No se encontró la capa DEM_CDMX en el proyecto")
    dem_map_layer = map_layers[0]

    dem_layer = settings.getLayer(dem_map_layer.id())
    if dem_layer is None:
        raise RuntimeError("DEM_CDMX no está disponible para exportar en Qgis2threejs")

    dem_layer.visible = True
    dem_layer.properties.update(
        {
            "radioButton_Resampling": True,
            "horizontalSlider_DEMSize": 6,
            "checkBox_Visible": True,
        }
    )
    settings.setLayer(dem_layer)

    # Plano (Flat Plane) visible para que el mapa base ESRI Satellite se
    # vea también en las áreas fuera del DEM_CDMX (más allá de la CDMX).
    flat_layer = settings.getLayer("FLAT")
    if flat_layer is None:
        for lyr in settings.layers():
            if lyr.layerId.startswith("fp:"):
                flat_layer = lyr
                break
    if flat_layer is not None:
        flat_layer.visible = True
        flat_layer.properties.update({"checkBox_Visible": True})
        settings.setLayer(flat_layer)

    settings.setOutputFilename(os.path.join(OUTPUT_DIR, "index.html"))

    exporter = ThreeJSExporter(settings=settings)
    exporter.export()

    print("Mapa 3D exportado en:", os.path.join(OUTPUT_DIR, "index.html"))


def main():
    qgs_app, project, canvas = open_project_and_canvas()

    basemap = agregar_mapa_base_esri_satellite(project)
    project.write(PROJECT_PATH)
    print("Proyecto guardado con mapa base ESRI Satellite:", PROJECT_PATH)

    # Incluir el mapa base en el lienzo usado para generar la textura del
    # mapa 3D, debajo (al final) del resto de las capas visibles.
    canvas.setLayers(canvas.layers() + [basemap])

    exportar_mapa_3d(project, canvas)

    qgs_app.exitQgis()


if __name__ == "__main__":
    main()
