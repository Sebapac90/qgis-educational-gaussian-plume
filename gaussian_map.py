"""Notebook/browser display of computed georeferenced raster; optional UI layer."""
from html import escape
import math

import folium
from branca.element import MacroElement, Template
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import BoundaryNorm, ListedColormap, to_hex
from pyproj import Transformer

from gaussian_raster import web_preview, NODATA
from gaussian_contours import extract_isolines
from gaussian_labels import ContourLabels
from gaussian_units import canonical_unit, unit_label


def contour_color_scale(actual_max, raster_threshold, contour_levels):
    """Discrete YlOrRd scale whose changes coincide with visible isolines."""
    maximum = float(actual_max)
    threshold = float(raster_threshold)
    upper = max(maximum, threshold * 1.01)
    levels = np.asarray(contour_levels, dtype=float)
    interior = levels[(levels > threshold) & (levels < upper)]
    boundaries = np.unique(np.r_[threshold, interior, upper])
    colors = colormaps["YlOrRd"](np.linspace(.12, .95, len(boundaries) - 1))
    cmap = ListedColormap(colors, name="YlOrRd_contour_bands")
    return boundaries, cmap, BoundaryNorm(boundaries, cmap.N, clip=True)


def create_map(tif_path, source, grid, *, wind_from_deg, display_min_ug_m3,
               emission_g_s, wind_speed_m_s, height_m, stability, title,
               visualization="isolines", emission_value=None, emission_unit=None,
               concentration_unit="ug/m3", contour_minimum=None,
               contour_levels="auto_125_upper", wind_mode="constant",
               wind_direction_std_deg=None, wind_samples=1):
    """Folium map with OSM tiles and correctly reprojected raster preview.

    ImageOverlay is only the rendering mechanism for computed raster values:
    the background is a live tile map; no background photograph is fitted.
    Coordinates can be read by clicking; clicking does not rerun the model.
    Display threshold affects alpha only; original GeoTIFF retains all values.
    """
    if visualization not in ("isolines", "raster", "both"):
        raise ValueError("visualization must be isolines, raster or both")
    threshold = float(display_min_ug_m3)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("display_min_ug_m3 must be finite and > 0")
    values, bounds, _ = web_preview(tif_path)
    valid = (values != NODATA) & np.isfinite(values) & (values >= threshold)
    unit = canonical_unit(concentration_unit)
    unit_text = unit_label(unit)
    contour_minimum = threshold if contour_minimum is None else float(contour_minimum)
    lines, contour_info = extract_isolines(tif_path, minimum_display=contour_minimum,
                                           levels=contour_levels)
    if contour_info["concentration_unit"] != unit:
        raise ValueError("Map concentration unit must match the GeoTIFF unit")
    actual_max = contour_info["maximum"]
    color_boundaries, cmap, norm = contour_color_scale(
        actual_max, threshold, contour_info["levels"])
    rgba = cmap(norm(np.maximum(values, threshold)))
    rgba[:,:,3] = np.where(valid, .78, 0.)
    map_view = folium.Map(location=[source.latitude_deg,source.longitude_deg],
                          zoom_start=13, tiles="OpenStreetMap", control_scale=True)
    folium.raster_layers.ImageOverlay(rgba, bounds=bounds, origin="upper",
        name=f"Ráster con degradé ({unit_text})", opacity=1,
        show=visualization in ("raster", "both"),
        interactive=False, cross_origin=False).add_to(map_view)
    line_group = folium.FeatureGroup(name=f"Isolíneas etiquetadas ({unit_text})",
        show=visualization in ("isolines", "both")).add_to(map_view)
    label_records = []
    for feature in lines["features"]:
        props=feature["properties"]
        color=to_hex(cmap(norm(props["concentration"])))
        locations=[[lat,lon] for lon,lat in feature["geometry"]["coordinates"]]
        line = folium.PolyLine(locations,color=color,weight=2.5,opacity=.95,smooth_factor=0,
            tooltip=f"{props['label']} {unit_text}").add_to(line_group)
        label_records.append(dict(line=line.get_name(), label=props["label"]))
    maximum_group=folium.FeatureGroup(name="Máximo calculado",show=True).add_to(map_view)
    folium.CircleMarker([contour_info["maximum_latitude"],contour_info["maximum_longitude"]],
        radius=5,color="#8c1620",weight=2,fill=True,fill_color="white",fill_opacity=1,
        tooltip=folium.Tooltip(f"Máx. {actual_max:.4g} {unit_text}",permanent=True,
                              direction="right")).add_to(maximum_group)
    source_icon = folium.DivIcon(html='''<div class="source-chimney" style="width:34px;height:44px;
        filter:drop-shadow(0 1px 2px #0008);pointer-events:none">
        <svg viewBox="0 0 34 44" width="34" height="44" aria-label="Fuente: chimenea">
          <path d="M18 10 C12 7 15 3 10 1 M21 9 C18 5 23 3 20 0" fill="none"
                stroke="#647786" stroke-width="2" stroke-linecap="round"/>
          <path d="M11 13 H23 L25 38 H9 Z" fill="#425A6B" stroke="white" stroke-width="2"/>
          <path d="M8 10 H25 V15 H8 Z M5 36 H29 V41 H5 Z" fill="#D95F43"
                stroke="white" stroke-width="2"/>
        </svg></div>''', icon_size=(34,44), icon_anchor=(17,41), class_name="")
    folium.Marker([source.latitude_deg,source.longitude_deg],
        tooltip="Fuente de ejemplo · " + title,
        popup="Ubicación referencial de la central; chimenea exacta no verificada.",
        icon=source_icon).add_to(map_view)
    west,south,east,north = grid.bounds
    transform = Transformer.from_crs(source.crs,4326,always_xy=True)
    corners = [transform.transform(e,n) for e,n in
               [(west,south),(east,south),(east,north),(west,north)]]
    folium.Polygon([[lat,lon] for lon,lat in corners],color="#36536B",weight=1,
        dash_array="6,6",fill=False,tooltip="Límite del cálculo; no es un borde físico",
        name="Dominio calculado").add_to(map_view)
    to_deg = (float(wind_from_deg)+180) % 360
    if wind_mode == "constant":
        wind_text = (f"Viento constante <b>desde {float(wind_from_deg)%360:g}° "
                     f"→ hacia {to_deg:g}°</b>")
    elif wind_mode == "prevailing":
        wind_text = (f"Viento predominante <b>desde {float(wind_from_deg)%360:g}°</b> · "
                     f"σ={float(wind_direction_std_deg):g}° · {int(wind_samples)} intervalos")
    elif wind_mode == "fluctuating":
        wind_text = f"Viento fluctuante <b>0–360°</b> · {int(wind_samples)} intervalos"
    elif wind_mode == "table":
        wind_text = (f"Tabla de viento · <b>{int(wind_samples)} registros</b> · "
                     f"rapidez media {float(wind_speed_m_s):.3g} m/s")
    else:
        raise ValueError("wind_mode must be constant, fluctuating, prevailing or table")
    folium.LatLngPopup().add_to(map_view)
    wind_group = folium.FeatureGroup(name="Dirección del viento", show=True).add_to(map_view)
    info_group = folium.FeatureGroup(name="Información del escenario", show=True).add_to(map_view)
    folium.LayerControl(collapsed=False).add_to(map_view)
    if visualization == "isolines" and lines["features"]:
        coordinates = np.array([point for feature in lines["features"]
                                for point in feature["geometry"]["coordinates"]]
                               + [[source.longitude_deg, source.latitude_deg],
                                  [contour_info["maximum_longitude"], contour_info["maximum_latitude"]]])
        west_view, south_view = coordinates.min(axis=0)
        east_view, north_view = coordinates.max(axis=0)
        map_view.fit_bounds([[south_view, west_view], [north_view, east_view]],
                           padding=(50, 50), max_zoom=16)
    else:
        map_view.fit_bounds(bounds)
    color_blocks = "".join(
        f'<span style="flex:1;background:{to_hex(cmap(index))}"></span>'
        for index in range(cmap.N))
    scale_limits = (f'<span>{color_boundaries[0]:.4g}</span>'
                    f'<span>{color_boundaries[-1]:.4g}</span>')
    shown_emission = emission_g_s if emission_value is None else emission_value
    shown_emission_unit = "g/s" if emission_unit is None else unit_label(emission_unit)
    level_policy = ("serie 1–2–5 + nivel superior" if
                    contour_info["level_policy"] == "automatic_1_2_5_plus_upper"
                    else "niveles manuales")
    panel_id = info_group.get_name() + "_panel"
    panel = f'''<aside id="{panel_id}" style="position:fixed;bottom:26px;left:12px;z-index:999;
      background:white;padding:16px;border-radius:8px;box-shadow:0 2px 12px #0003;
      width:320px;max-width:calc(100vw - 48px);font:13px/1.5 Arial,sans-serif;">
      <b style="font-size:17px">{escape(title)}</b><br>
      Ejemplo docente · terreno plano<br>
      {wind_text}<br>
      Emisión {float(shown_emission):g} {escape(shown_emission_unit)} · viento {wind_speed_m_s:g} m/s<br>
      Altura {height_m:g} m · estabilidad {escape(stability)} · receptor z = 0 m<br>
      Dominio {(east-west)/1000:g} × {(north-south)/1000:g} km · celdas {grid.resolution_m:g} m
      <hr style="border:0;border-top:1px solid #ddd">
      <b>Concentración · {unit_text}</b> (bandas de isolíneas)
      <div style="height:12px;margin-top:6px;display:flex">{color_blocks}</div>
      <div style="display:flex;justify-content:space-between">{scale_limits}</div>
      <b>Máximo calculado: {actual_max:.4g} {unit_text}</b><br>
      Isolíneas: {', '.join(f'{v:.4g}' for v in contour_info['levels']) or 'sin niveles en el rango'} {unit_text}.<br>
      {level_policy}; mínimo {contour_minimum:g} {unit_text}.<br>
      Activa ráster, isolíneas o ambos en el control de capas.<br>
      Umbral del ráster: {threshold:g} {unit_text}.<br>
      La primera isolínea no delimita toda la influencia de la pluma.<br>
      El GeoTIFF conserva todos los valores calculados.<br>
      Borde punteado: límite de cálculo, no de dispersión.<br>
      <small>Fuente referencial; parámetros hipotéticos. El mapa requiere internet.
      Clic: consultar coordenadas, sin recalcular.</small></aside>'''
    map_view.get_root().html.add_child(folium.Element(panel))
    panel_toggle = MacroElement()
    panel_toggle.group_name = info_group.get_name()
    panel_toggle.map_name = map_view.get_name()
    panel_toggle.panel_id = panel_id
    panel_toggle._template = Template("""
        {% macro script(this, kwargs) %}
        (function () {
            const panel = document.getElementById({{ this.panel_id|tojson }});
            const group = {{ this.group_name }};
            function syncPanel() { panel.hidden = !{{ this.map_name }}.hasLayer(group); }
            group.on('add remove', syncPanel);
            syncPanel();
            L.DomEvent.disableClickPropagation(panel);
            L.DomEvent.disableScrollPropagation(panel);
        })();
        {% endmacro %}
    """)
    panel_toggle.add_to(map_view)
    wind_id = wind_group.get_name() + "_indicator"
    if wind_mode in ("fluctuating", "table"):
        variable_label = ("fluctuante · 0–360°" if wind_mode == "fluctuating" else
                          f"tabla · {int(wind_samples)} registros")
        wind_symbol = '''<svg viewBox="0 0 44 44" width="44" height="44"
          aria-label="Dirección fluctuante entre 0 y 360 grados">
          <text x="22" y="8" text-anchor="middle" font-size="8" fill="#52636F">N</text>
          <circle cx="22" cy="24" r="15" fill="none" stroke="#C8D1D7"/>
          <path d="M11 19 A12 12 0 1 1 15 33" fill="none" stroke="#168AAD" stroke-width="3"/>
          <path d="M10 14 L11 22 L18 18" fill="#168AAD"/>
        </svg><br>''' + variable_label
    else:
        mode_label = "constante" if wind_mode == "constant" else "predominante"
        spread_label = ("" if wind_mode == "constant" else
                        f" · σ={float(wind_direction_std_deg):g}°")
        wind_symbol = f'''<svg viewBox="0 0 44 44" width="44" height="44"
          aria-label="Hacia {to_deg:g} grados">
          <text x="22" y="8" text-anchor="middle" font-size="8" fill="#52636F">N</text>
          <circle cx="22" cy="24" r="15" fill="none" stroke="#C8D1D7"/>
          <g transform="rotate({to_deg:g} 22 24)">
            <path d="M22 7 L16 19 H20 V36 H24 V19 H28 Z" fill="#168AAD"
                  stroke="white" stroke-width="1"/>
          </g>
        </svg><br>{mode_label} · desde {float(wind_from_deg)%360:g}°{spread_label}'''
    wind_indicator = f'''<aside id="{wind_id}" class="wind-indicator" style="position:fixed;
      top:12px;left:52px;z-index:999;background:rgba(255,255,255,.94);padding:7px 10px;
      border-radius:7px;box-shadow:0 1px 6px #0003;font:11px/1.2 Arial,sans-serif;
      color:#263746;text-align:center;pointer-events:none">
      <b>Viento</b><br>
      {wind_symbol}</aside>'''
    map_view.get_root().html.add_child(folium.Element(wind_indicator))
    wind_toggle = MacroElement()
    wind_toggle.group_name = wind_group.get_name()
    wind_toggle.map_name = map_view.get_name()
    wind_toggle.element_id = wind_id
    wind_toggle._template = Template("""
        {% macro script(this, kwargs) %}
        (function () {
            const element = document.getElementById({{ this.element_id|tojson }});
            const group = {{ this.group_name }};
            function syncWind() { element.hidden = !{{ this.map_name }}.hasLayer(group); }
            group.on('add remove', syncWind);
            syncWind();
        })();
        {% endmacro %}
    """)
    wind_toggle.add_to(map_view)
    ContourLabels(map_view, label_records).add_to(map_view)
    return map_view
