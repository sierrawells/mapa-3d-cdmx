"""
Construye el mapa base topográfico de CDMX (instrucciones.pdf, pasos 1-40),
más las adiciones de "Publicación de mapas en la web" (pasos 1-13): capas de
Elevaciones (cerros y montañas) y Lago de Texcoco 1519.

Capas:
  1_ModeloDigitalElevacion: DEM_CDMX_hill, DEM_CDMX (pseudocolor YlOrBr, 25% transp.)
  2_RedHidrografica:        RedHidro_CDMX (categorizado por order_1, color HSV(200,90,70),
                             ancho de línea variable por categoría)
  3_TiposVegetacion:        TiposVegetacion_CDMX (categorizado por TipoVEG, relleno sin
                             borde, colores HSV por categoría, opacidad 20%)
  4_CurvasNivel:             CurvasOrdinarias_20m (ancho 0.05, color HSV(22,25,45))
                             CurvasMaestras_100m (mismo estilo, ancho 0.15, etiquetas
                             ELEV en Arial Bold 6 con buffer del mismo color, op. 30%)
  5_LimitesAdministrativos:  Alcaldias_CDMX (relleno transparente, borde blanco 0.5, 50% op.)
                             Estatal_CDMX (mismo estilo, borde 1.0)
  1_Elevaciones:             Elevaciones_CDMX (puntos tamaño 0, etiquetas NOMBRE en
                             Arial Black 7 con buffer, opacidad 50%)
  2_Lago:                    Lago1519_CDMX (relleno HSV(197,89,68), sin borde, op. 40%)

Orden final de capas (de arriba a abajo):
  Lago1519_CDMX, Elevaciones_CDMX, Estatal_CDMX, CurvasMaestras_100m,
  CurvasOrdinarias_20m, RedHidro_CDMX, Alcaldias_CDMX, DEM_CDMX,
  TiposVegetacion_CDMX, DEM_CDMX_hill
"""
import os
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsStyle,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsWkbTypes,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtCore import Qt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
PROJECT_PATH = os.path.join(OUTPUT_DIR, "MapaBase_WEB.qgz")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def hsv(h, s, v, a=255):
    """Crea un QColor a partir de H (0-360), S y V en porcentaje (0-100)."""
    return QColor.fromHsv(int(h) % 360, round(s * 255 / 100), round(v * 255 / 100), a)


qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
root = project.layerTreeRoot()


def load_raster(path, name):
    layer = QgsRasterLayer(path, name)
    if not layer.isValid():
        raise RuntimeError(f"No se pudo cargar la capa raster: {name}")
    project.addMapLayer(layer, addToLegend=False)
    return layer


def load_vector(path, name):
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"No se pudo cargar la capa vectorial: {name}")
    project.addMapLayer(layer, addToLegend=False)
    return layer


# ---------------------------------------------------------------------------
# 1. Modelo Digital de Elevación
# ---------------------------------------------------------------------------
dem_hill = load_raster(
    os.path.join(INPUT_DIR, "1_ModeloDigitalElevacion", "DEM_CDMX_hill.tif"),
    "DEM_CDMX_hill",
)
dem = load_raster(
    os.path.join(INPUT_DIR, "1_ModeloDigitalElevacion", "DEM_CDMX.tif"),
    "DEM_CDMX",
)

project.setCrs(dem.crs())

# Pasos 8-11: pseudocolor monobanda, rampa YlOrBr, interpolación lineal, 5 clases (intervalo igual)
provider = dem.dataProvider()
stats = provider.bandStatistics(1)
min_val, max_val = stats.minimumValue, stats.maximumValue

ramp = QgsStyle.defaultStyle().colorRamp("YlOrBr")

shader = QgsColorRampShader(min_val, max_val)
shader.setColorRampType(QgsColorRampShader.Interpolated)  # Interpolación: Lineal (paso 9)
shader.setClassificationMode(QgsColorRampShader.EqualInterval)  # Modo: Intervalo igual (paso 11)
shader.setSourceColorRamp(ramp)

n_classes = 5
step = (max_val - min_val) / (n_classes - 1)
items = []
for i in range(n_classes):
    value = min_val + i * step
    fraction = i / (n_classes - 1)
    color = ramp.color(fraction)
    if i == 0:
        label = "Menor elevación"
    elif i == n_classes - 1:
        label = "Mayor elevación"
    else:
        label = f"{value:,.0f}"
    items.append(QgsColorRampShader.ColorRampItem(value, color, label))
shader.setColorRampItemList(items)

raster_shader = QgsRasterShader()
raster_shader.setRasterShaderFunction(shader)

renderer = QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
renderer.setClassificationMin(min_val)
renderer.setClassificationMax(max_val)
dem.setRenderer(renderer)

# Paso 12: 25% de transparencia (75% opacidad)
dem.renderer().setOpacity(0.25)
dem.triggerRepaint()


# ---------------------------------------------------------------------------
# 2. Red Hidrográfica (pasos 13-19)
# ---------------------------------------------------------------------------
red_hidro = load_vector(
    os.path.join(INPUT_DIR, "2_RedHidrografica", "RedHidro_CDMX.shp"),
    "RedHidro_CDMX",
)

ANCHURAS_HIDRO = {
    -1: 0.1,
    1: 0.1,
    2: 0.15,
    3: 0.2,
    4: 0.25,
    5: 0.3,
    6: 0.4,
    7: 0.5,
}
hidro_color = hsv(200, 90, 70)

categories = []
for value in sorted(ANCHURAS_HIDRO):
    symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
    symbol.setColor(hidro_color)
    symbol.setWidth(ANCHURAS_HIDRO[value])
    categories.append(QgsRendererCategory(value, symbol, str(value)))

red_hidro.setRenderer(QgsCategorizedSymbolRenderer("order_1", categories))
red_hidro.triggerRepaint()


# ---------------------------------------------------------------------------
# 3. Tipos de Vegetación (pasos 20-28)
# ---------------------------------------------------------------------------
tipos_veg = load_vector(
    os.path.join(INPUT_DIR, "3_TiposVegetacion", "TiposVegetacion_CDMX.shp"),
    "TiposVegetacion_CDMX",
)

COLORES_VEG = {
    "Agricultura": (50, 67, 60),
    "Agricultura de Riego": (50, 53, 77),
    "Agricultura Mixta": (50, 38, 90),
    "Bosque Encino": (108, 43, 76),
    "Bosque Mixto": (110, 25, 68),
    "Bosque Oyamel": (94, 30, 70),
    "Bosque Pino": (99, 25, 82),
    "Canal-Lago": (200, 55, 80),
    "Cantera": (5, 20, 100),
    "Humedal": (200, 44, 88),
    "Matorral": (94, 20, 77),
    "Pastizal": (94, 25, 66),
}

categories = []
for value, (h, s, v) in COLORES_VEG.items():
    symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
    symbol.setColor(hsv(h, s, v))
    # Borde transparente (paso 25)
    symbol.symbolLayer(0).setStrokeStyle(Qt.PenStyle.NoPen)
    categories.append(QgsRendererCategory(value, symbol, value))

tipos_veg.setRenderer(QgsCategorizedSymbolRenderer("TipoVEG", categories))

# Paso 28: opacidad 20%
tipos_veg.setOpacity(0.2)
tipos_veg.triggerRepaint()


# ---------------------------------------------------------------------------
# 4. Curvas de Nivel (pasos 29-34)
# ---------------------------------------------------------------------------
curvas_ordinarias = load_vector(
    os.path.join(INPUT_DIR, "4_CurvasNivel", "CurvasOrdinarias_20m.shp"),
    "CurvasOrdinarias_20m",
)
curvas_maestras = load_vector(
    os.path.join(INPUT_DIR, "4_CurvasNivel", "CurvasMaestras_100m.shp"),
    "CurvasMaestras_100m",
)

curvas_color = hsv(22, 25, 45)

symbol_ordinarias = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
symbol_ordinarias.setColor(curvas_color)
symbol_ordinarias.setWidth(0.05)  # paso 30
curvas_ordinarias.renderer().setSymbol(symbol_ordinarias)
curvas_ordinarias.triggerRepaint()

# Pasos 33-34: copiar símbolo y ajustar ancho a 0.15
symbol_maestras = symbol_ordinarias.clone()
symbol_maestras.setWidth(0.15)
curvas_maestras.renderer().setSymbol(symbol_maestras)
curvas_maestras.triggerRepaint()


# ---------------------------------------------------------------------------
# 5. Límites Administrativos (pasos 35-39)
# ---------------------------------------------------------------------------
alcaldias = load_vector(
    os.path.join(INPUT_DIR, "5_LimitesAdministrativos", "Alcaldias_CDMX.shp"),
    "Alcaldias_CDMX",
)
estatal = load_vector(
    os.path.join(INPUT_DIR, "5_LimitesAdministrativos", "Estatal_CDMX.shp"),
    "Estatal_CDMX",
)

# Paso 36: relleno transparente, borde blanco 0.5, opacidad 50%
symbol_alcaldias = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
fill_layer = symbol_alcaldias.symbolLayer(0)
fill_layer.setBrushStyle(Qt.BrushStyle.NoBrush)
fill_layer.setStrokeColor(QColor("white"))
fill_layer.setStrokeWidth(0.5)
alcaldias.renderer().setSymbol(symbol_alcaldias)
alcaldias.setOpacity(0.5)
alcaldias.triggerRepaint()

# Pasos 38-39: copiar símbolo de Alcaldias y ajustar ancho de borde a 1.0
symbol_estatal = symbol_alcaldias.clone()
symbol_estatal.symbolLayer(0).setStrokeWidth(1.0)
estatal.renderer().setSymbol(symbol_estatal)
estatal.setOpacity(0.5)
estatal.triggerRepaint()


# ---------------------------------------------------------------------------
# 6. Elevaciones (cerros y montañas) (pasos 5-8)
# ---------------------------------------------------------------------------
elevaciones = load_vector(
    os.path.join(INPUT_DIR, "1_Elevaciones", "Elevaciones_CDMX.shp"),
    "Elevaciones_CDMX",
)

# Paso 6: tamaño del símbolo de punto a 0.0
elev_symbol = elevaciones.renderer().symbol()
elev_symbol.setSize(0.0)

# Pasos 7-8: etiquetas con el campo NOMBRE, Arial Black 7, buffer activado, opacidad 50%
elev_label = QgsPalLayerSettings()
elev_label.fieldName = "NOMBRE"

elev_text_format = QgsTextFormat()
elev_text_format.setFont(QFont("Arial Black"))
elev_text_format.setSize(7)
elev_text_format.setOpacity(0.5)

elev_buffer = QgsTextBufferSettings()
elev_buffer.setEnabled(True)
elev_text_format.setBuffer(elev_buffer)

elev_label.setFormat(elev_text_format)

elevaciones.setLabeling(QgsVectorLayerSimpleLabeling(elev_label))
elevaciones.setLabelsEnabled(True)
elevaciones.triggerRepaint()


# ---------------------------------------------------------------------------
# 7. Lago de Texcoco 1519 (pasos 9-11)
# ---------------------------------------------------------------------------
lago = load_vector(
    os.path.join(INPUT_DIR, "2_Lago", "Lago1519_CDMX.shp"),
    "Lago1519_CDMX",
)

# Paso 10: relleno simple HSV(197, 89, 68), borde transparente
lago_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
lago_fill_layer = lago_symbol.symbolLayer(0)
lago_fill_layer.setColor(hsv(197, 89, 68))
lago_fill_layer.setStrokeStyle(Qt.PenStyle.NoPen)
lago.renderer().setSymbol(lago_symbol)

# Paso 11: opacidad 40%
lago.setOpacity(0.4)
lago.triggerRepaint()


# ---------------------------------------------------------------------------
# 8. Etiquetas de CurvasMaestras_100m (pasos 12-13)
# ---------------------------------------------------------------------------
curvas_maestras_color = hsv(22, 25, 45)

curvas_label = QgsPalLayerSettings()
curvas_label.fieldName = "ELEV"

curvas_text_format = QgsTextFormat()
curvas_font = QFont("Arial")
curvas_font.setBold(True)
curvas_text_format.setFont(curvas_font)
curvas_text_format.setSize(6)
curvas_text_format.setColor(curvas_maestras_color)

curvas_buffer = QgsTextBufferSettings()
curvas_buffer.setEnabled(True)
curvas_buffer.setColor(curvas_maestras_color)
curvas_buffer.setOpacity(0.3)
curvas_text_format.setBuffer(curvas_buffer)

curvas_label.setFormat(curvas_text_format)

curvas_maestras.setLabeling(QgsVectorLayerSimpleLabeling(curvas_label))
curvas_maestras.setLabelsEnabled(True)
curvas_maestras.triggerRepaint()


# ---------------------------------------------------------------------------
# Paso 40: orden de capas (de arriba a abajo)
# ---------------------------------------------------------------------------
layer_order = [
    lago,
    elevaciones,
    estatal,
    curvas_maestras,
    curvas_ordinarias,
    red_hidro,
    alcaldias,
    dem,
    tipos_veg,
    dem_hill,
]

for layer in layer_order:
    root.addLayer(layer)

project.write(PROJECT_PATH)
print(f"Proyecto guardado en: {PROJECT_PATH}")

qgs.exitQgis()
