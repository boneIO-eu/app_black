"""SVG diagram templates for HVAC devices.

Generates inline SVG diagrams of heat recovery ventilation units
(recuperators) for use in Home Assistant picture-elements cards.
The SVG is embedded as a base64 data URI — no external file hosting needed.

Each template produces:
  - A static SVG background (house shape, airflow arrows, heat exchanger)
  - A list of HA picture-elements overlays (state-label, state-icon)
    positioned at the correct % coordinates over the SVG.
"""

from __future__ import annotations

import base64
from typing import Any

from boneio.webui.dashboard_cards import ha_slugify


# ─── SVG: Recuperator Diagram ────────────────────────────────────────────
# Clean structural-only diagram (no text labels — those come from HA overlays).
# ViewBox 520×400 gives more vertical space to separate top/bottom arrows.

_RECUPERATOR_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 400"
     style="background:#fff">
  <defs>
    <marker id="ab" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0L10 5 0 10z" fill="#2196F3"/>
    </marker>
    <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0L10 5 0 10z" fill="#E53935"/>
    </marker>
  </defs>

  <!-- House outline — shifted down, more vertical room -->
  <path d="M260 50 L60 170 L60 350 L460 350 L460 170Z"
        fill="none" stroke="#29B6F6" stroke-width="3.5"
        stroke-linejoin="round"/>

  <!-- Heat exchanger diamond -->
  <g transform="translate(260,245)">
    <rect x="-30" y="-30" width="60" height="60" rx="4"
          transform="rotate(45)" fill="#ECEFF1" stroke="#90A4AE"
          stroke-width="2"/>
    <line x1="-26" y1="-26" x2="26" y2="26"
          stroke="#B0BEC5" stroke-width="1.5"/>
    <line x1="26" y1="-26" x2="-26" y2="26"
          stroke="#B0BEC5" stroke-width="1.5"/>
    <line x1="-26" y1="0" x2="26" y2="0"
          stroke="#B0BEC5" stroke-width="1.2"/>
    <line x1="0" y1="-26" x2="0" y2="26"
          stroke="#B0BEC5" stroke-width="1.2"/>
  </g>

  <!-- BLUE arrows: fresh air (outside → HX → supply) -->
  <path d="M48 210 L210 210" stroke="#2196F3" stroke-width="3"
        fill="none" marker-end="url(#ab)"/>
  <path d="M310 210 L472 210" stroke="#2196F3" stroke-width="3"
        fill="none" marker-end="url(#ab)"/>

  <!-- RED arrows: exhaust (rooms → HX → outside) -->
  <path d="M472 280 L310 280" stroke="#E53935" stroke-width="3"
        fill="none" marker-end="url(#ar)"/>
  <path d="M210 280 L48 280" stroke="#E53935" stroke-width="3"
        fill="none" marker-end="url(#ar)"/>

  <!-- Small descriptive labels near arrows (inside house, small font) -->
  <text x="100" y="203" font-size="9" fill="#90CAF9"
        font-family="sans-serif">powietrze zewn.</text>
  <text x="380" y="203" font-size="9" fill="#90CAF9"
        font-family="sans-serif">wyrzut →</text>
  <text x="380" y="296" font-size="9" fill="#90CAF9"
        font-family="sans-serif">→ nawiew</text>
  <text x="100" y="296" font-size="9" fill="#EF9A9A"
        font-family="sans-serif">wywiew ←</text>
</svg>"""


def _svg_to_data_uri(svg: str) -> str:
    """Encode SVG string as base64 data URI for HA picture-elements.

    Args:
        svg: Raw SVG XML string.

    Returns:
        data:image/svg+xml;base64,... string usable as card image.
    """
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def generate_recuperator_card(
    serial: str,
    device_id: str,
) -> list[dict[str, Any]]:
    """Generate picture-elements card YAML for a recuperator diagram.

    Creates a visual card with:
    - SVG background (house shape, airflow arrows, heat exchanger)
    - Temperature entity overlays at 4 corners
    - Flow rate entity overlays near arrows
    - Gear status overlays

    Args:
        serial: Device serial number (e.g. 'blk265f49').
        device_id: Device ID (e.g. '1_wanas415').

    Returns:
        List of HA card dicts (picture-elements + supporting tile cards).
    """

    def _eid(ha_type: str, decoded: str) -> str:
        """Build entity_id matching fake device / real coordinator format."""
        slug = ha_slugify(decoded.replace(" ", ""))
        return f"{ha_type}.{serial}_{device_id}_{slug}"

    # Entity IDs for the key sensors
    t_zewn = _eid("sensor", "temperaturazewnetrzna")
    t_pom = _eid("sensor", "temperaturapomieszczenia")
    t_naw = _eid("sensor", "temperaturanawiewu")
    t_wyrz = _eid("sensor", "temperaturawywrzutowa")
    w_naw = _eid("sensor", "wydateknawiewu")
    w_wyw = _eid("sensor", "wydatekwywiewu")
    b_naw = _eid("sensor", "biegnawiewu")
    b_wyw = _eid("sensor", "biegwywiewu")

    image_uri = _svg_to_data_uri(_RECUPERATOR_SVG)

    # ── picture-elements card ─────────────────────────────────────────
    # Positions are % of image dimensions (520×400 viewBox).
    # No suffix — HA already appends unit_of_measurement from entity.
    picture_card: dict[str, Any] = {
        "type": "picture-elements",
        "image": image_uri,
        "elements": [
            # ── Temperatures (4 corners) ──
            # Top-left: T zewnętrzna (cold intake from outside)
            {
                "type": "state-label",
                "entity": t_zewn,
                "style": {
                    "top": "42%",
                    "left": "10%",
                    "font-size": "1.2em",
                    "font-weight": "bold",
                    "color": "#1565C0",
                },
            },
            # Top-right: T wyrzutowa (cooled exhaust to outside)
            {
                "type": "state-label",
                "entity": t_wyrz,
                "style": {
                    "top": "42%",
                    "left": "90%",
                    "font-size": "1.2em",
                    "font-weight": "bold",
                    "color": "#C62828",
                },
            },
            # Bottom-left: T pomieszczenia / wywiew (warm room air)
            {
                "type": "state-label",
                "entity": t_pom,
                "style": {
                    "top": "62%",
                    "left": "10%",
                    "font-size": "1.2em",
                    "font-weight": "bold",
                    "color": "#C62828",
                },
            },
            # Bottom-right: T nawiewu (warm supply to rooms)
            {
                "type": "state-label",
                "entity": t_naw,
                "style": {
                    "top": "62%",
                    "left": "90%",
                    "font-size": "1.2em",
                    "font-weight": "bold",
                    "color": "#1565C0",
                },
            },
            # ── Flow rates (above/below HX center) ──
            {
                "type": "state-label",
                "entity": w_naw,
                "style": {
                    "top": "47%",
                    "left": "50%",
                    "font-size": "0.95em",
                    "font-weight": "bold",
                    "color": "#1E88E5",
                },
                "prefix": "↗ ",
            },
            {
                "type": "state-label",
                "entity": w_wyw,
                "style": {
                    "top": "76%",
                    "left": "50%",
                    "font-size": "0.95em",
                    "font-weight": "bold",
                    "color": "#E53935",
                },
                "prefix": "↙ ",
            },
            # ── Gear status (bottom, well separated) ──
            {
                "type": "state-label",
                "entity": b_naw,
                "style": {
                    "top": "92%",
                    "left": "25%",
                    "font-size": "0.8em",
                    "color": "#546E7A",
                },
                "prefix": "Nawiew: ",
            },
            {
                "type": "state-label",
                "entity": b_wyw,
                "style": {
                    "top": "92%",
                    "left": "75%",
                    "font-size": "0.8em",
                    "color": "#546E7A",
                },
                "prefix": "Wywiew: ",
            },
        ],
    }

    return [picture_card]
