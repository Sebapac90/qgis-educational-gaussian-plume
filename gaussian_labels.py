"""Screen-space contour lettering for the Folium preview, without GIS changes."""
from branca.element import MacroElement, Template


class ContourLabels(MacroElement):
    """Place upright labels in gaps along visible, locally straight SVG curves."""

    def __init__(self, map_view, records):
        super().__init__()
        self._name = "ContourLabels"
        self.map_name = map_view.get_name()
        self.records = records

    _template = Template(r"""
    {% macro script(this, kwargs) %}
    (function () {
        const map = {{ this.map_name }};
        const records = [
        {% for record in this.records %}
            {line: {{ record.line }}, label: {{ record.label|tojson }}},
        {% endfor %}
        ];
        const ns = 'http://www.w3.org/2000/svg';
        let decorations = [], frame;
        function clear() {
            decorations.forEach(({path, text, mask}) => {
                path.removeAttribute('mask'); text.remove(); mask.remove();
            });
            decorations = [];
        }
        function element(tag, attrs) {
            const node = document.createElementNS(ns, tag);
            Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
            return node;
        }
        function redraw() {
            clear();
            const font = Math.max(10, Math.min(13, 11 + (map.getZoom() - 13) * .5));
            const top = map.containerPointToLayerPoint([0, 0]);
            const size = map.getSize(), occupied = [];
            records.forEach((record, index) => {
                const path = record.line.getElement();
                if (!map.hasLayer(record.line) || !path || !path.isConnected) return;
                const total = path.getTotalLength();
                const text = element('text', {
                    'class': 'contour-inline-label', 'font-size': font,
                    'font-family': 'Arial, sans-serif', 'font-weight': 500,
                    'fill': '#263746', 'stroke': 'white', 'stroke-width': 2.5,
                    'stroke-linejoin': 'round', 'paint-order': 'stroke',
                    'text-anchor': 'middle', 'dominant-baseline': 'central',
                    'pointer-events': 'none'
                });
                text.textContent = record.label;
                path.parentNode.appendChild(text);
                const width = text.getComputedTextLength() + 10, height = font + 5;
                let chosen;
                // Stagger levels; try alternatives when crowded, offscreen or curved.
                const fractions = [.25 + .1 * (index % 5), .5, .2, .8, .35, .65, .1, .9];
                if (total > width * 3) for (const fraction of fractions) {
                    const distance = total * fraction;
                    if (distance < width || distance > total - width) continue;
                    const p = path.getPointAtLength(distance);
                    const a = path.getPointAtLength(distance - width / 2);
                    const b = path.getPointAtLength(distance + width / 2);
                    const dx = b.x - a.x, dy = b.y - a.y, chord = Math.hypot(dx, dy);
                    if (chord < width * .97) continue;
                    let straight = true;
                    for (const fraction of [.25, .5, .75]) {
                        const q = path.getPointAtLength(distance - width / 2 + width * fraction);
                        if (Math.abs(dy * (q.x - a.x) - dx * (q.y - a.y)) / chord > 2) straight = false;
                    }
                    if (!straight) continue;
                    let angle = Math.atan2(dy, dx);
                    if (angle > Math.PI / 2) angle -= Math.PI;
                    if (angle < -Math.PI / 2) angle += Math.PI;
                    const w = Math.abs(Math.cos(angle)) * width + Math.abs(Math.sin(angle)) * height;
                    const h = Math.abs(Math.sin(angle)) * width + Math.abs(Math.cos(angle)) * height;
                    const box = {x: p.x - w / 2 - 6, y: p.y - h / 2 - 6, w: w + 12, h: h + 12};
                    if (box.x < top.x + 12 || box.y < top.y + 12 ||
                        box.x + box.w > top.x + size.x - 12 || box.y + box.h > top.y + size.y - 12) continue;
                    if (occupied.some(o => box.x < o.x + o.w && box.x + box.w > o.x &&
                        box.y < o.y + o.h && box.y + box.h > o.y)) continue;
                    chosen = {p, angle: angle * 180 / Math.PI, box}; break;
                }
                if (!chosen) { text.remove(); return; }
                occupied.push(chosen.box);
                const transform = `translate(${chosen.p.x} ${chosen.p.y}) rotate(${chosen.angle})`;
                text.setAttribute('transform', transform);
                // A mask cuts only this contour, leaving the basemap and raster visible.
                const bounds = path.getBBox(), id = '{{ this.get_name() }}_gap_' + index;
                const mask = element('mask', {id, maskUnits: 'userSpaceOnUse',
                    x: bounds.x - 20, y: bounds.y - 20,
                    width: bounds.width + 40, height: bounds.height + 40});
                mask.appendChild(element('rect', {x: bounds.x - 20, y: bounds.y - 20,
                    width: bounds.width + 40, height: bounds.height + 40, fill: 'white'}));
                mask.appendChild(element('rect', {x: -width / 2, y: -height / 2,
                    width, height, transform, fill: 'black'}));
                path.ownerSVGElement.appendChild(mask);
                path.setAttribute('mask', `url(#${id})`);
                decorations.push({path, text, mask});
            });
        }
        function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(redraw); }
        map.on('zoomstart', () => { cancelAnimationFrame(frame); clear(); });
        map.on('zoomend moveend resize overlayadd overlayremove', schedule);
        map.whenReady(schedule);
    })();
    {% endmacro %}
    """)
