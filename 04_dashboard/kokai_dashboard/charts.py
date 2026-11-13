"""Figuras Plotly. Se usa Plotly (no Altair) porque da hover con el nombre del plato, líneas de umbral
y facetas por local con poco código, y se integra nativo con st.plotly_chart."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import CLASS_COLOR, CLASS_LABEL, CLASS_SYMBOL, CLASSES, NAVY, SCENARIO_COLOR, SCENARIOS, SILVER, SLATE, WHITE

_GRID = "rgba(191,192,192,0.35)"
_QUADRANT_LABELS = [  # (x, y, anchor_x, anchor_y, clase)
    (0.99, 0.98, "right", "top", "Estrella"), (0.01, 0.98, "left", "top", "Caballo de batalla"),
    (0.99, 0.02, "right", "bottom", "Puzzle"), (0.01, 0.02, "left", "bottom", "Perro"),
]


def _style(fig: go.Figure, height: int, **layout) -> go.Figure:
    layout.setdefault("margin", dict(t=44, b=10, l=10, r=10))
    fig.update_layout(height=height, font=dict(color=NAVY, size=13), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor=WHITE, hoverlabel=dict(bgcolor=WHITE, font_color=NAVY, bordercolor=SILVER), **layout)
    fig.update_xaxes(gridcolor=_GRID, linecolor=SILVER, zerolinecolor=SILVER, tickfont_color=SLATE)
    fig.update_yaxes(gridcolor=_GRID, linecolor=SILVER, zerolinecolor=SILVER, tickfont_color=SLATE)
    fig.update_annotations(font=dict(color=NAVY, size=13))  # títulos de subgráficos
    return fig


def _title(text: str) -> dict:
    return dict(text=text, x=0, xanchor="left", font=dict(size=14, color=NAVY))


def quadrant(df, locales: list[str]) -> go.Figure:
    n = len(locales)
    fig = make_subplots(rows=1, cols=n, subplot_titles=locales, horizontal_spacing=0.07)
    for i, loc in enumerate(locales, 1):
        g = df[df["Local"] == loc]
        for clase in CLASSES:
            s = g[g["clase"] == clase]
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=s["CM"], y=s["mix"] * 100, mode="markers", name=CLASS_LABEL[clase], legendgroup=clase, showlegend=(i == 1),
                marker=dict(size=11, color=CLASS_COLOR[clase], symbol=CLASS_SYMBOL[clase], opacity=0.92,
                            line=dict(color=WHITE, width=1)),
                customdata=s[["Producto", "q", "p", "c"]].to_numpy(),
                hovertemplate=("<b>%{customdata[0]}</b><br>" + CLASS_LABEL[clase] + "<br>"
                               "Margen por plato (sin IVA): $%{x:,.0f}<br>% de las ventas: %{y:.1f} %<br>"
                               "Vendidas: %{customdata[1]:,.0f} · Precio con IVA $%{customdata[2]:,.0f}"
                               "<extra></extra>"),
            ), row=1, col=i)
        fig.add_vline(x=g["CM_promedio_ponderado"].iloc[0], line_dash="dash", line_color=SLATE, line_width=1, row=1, col=i)
        fig.add_hline(y=g["umbral_mix"].iloc[0] * 100, line_dash="dash", line_color=SLATE, line_width=1, row=1, col=i)
        dom_x = "x domain" if i == 1 else f"x{i} domain"
        dom_y = "y domain" if i == 1 else f"y{i} domain"
        for x, y, ax, ay, clase in _QUADRANT_LABELS:
            fig.add_annotation(x=x, y=y, xref=dom_x, yref=dom_y, text=CLASS_LABEL[clase].upper(), showarrow=False,
                               xanchor=ax, yanchor=ay, font=dict(size=10, color=SLATE), opacity=0.8)
        fig.update_xaxes(title_text="Margen por plato sin IVA ($)", row=1, col=i)
        fig.update_yaxes(title_text="% de las ventas del local" if i == 1 else None, row=1, col=i)
    return _style(fig, 460, legend=dict(orientation="h", y=-0.2, font_color=NAVY))


def hbar(labels, values, text, hover, height: int | None = None) -> go.Figure:
    """Ranking horizontal de una sola serie (un color): el más grande arriba, valor escrito al final de la barra."""
    labels, values = list(labels)[::-1], list(values)[::-1]
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h", marker=dict(color=SLATE, cornerradius=4),
        text=list(text)[::-1], textposition="outside", cliponaxis=False, textfont=dict(color=NAVY, size=12),
        customdata=list(hover)[::-1], hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>"))
    fig.update_xaxes(visible=False, range=[0, max(values) * 1.6] if values else None)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=NAVY, size=12), ticksuffix="  ")
    return _style(fig, height or 40 + 34 * len(labels), margin=dict(t=8, b=8, l=10, r=10), bargap=0.35,
                  showlegend=False)


def scenario_compare(results: dict) -> go.Figure:
    """Tres paneles con la mejora lograda vs. hoy en cada escenario (0 = sin cambio)."""
    ok = {s: r[1] for s, r in results.items()}
    titles = ["Baja del food cost (puntos)", "Variación del margen (%)", "Variación de unidades (%)"]
    fig = make_subplots(rows=1, cols=3, subplot_titles=titles, horizontal_spacing=0.09)
    metrics = [
        (lambda s: (s["fc0"] - s["fc_new"]) * 100, "{:.2f} pts"),
        (lambda s: (s["margin_new"] / s["margin0"] - 1) * 100, "{:+.2f} %"),
        (lambda s: (s["units_new"] / s["units0"] - 1) * 100, "{:+.2f} %"),
    ]
    for col, (fn, fmt_) in enumerate(metrics, 1):
        scen = [s for s in SCENARIOS if s in ok]
        vals = [fn(ok[s]) for s in scen]
        fig.add_trace(go.Bar(
            x=scen, y=vals, text=[fmt_.format(v).replace(".", ",") for v in vals], textposition="outside",
            marker_color=[SCENARIO_COLOR[s] for s in scen], showlegend=False, cliponaxis=False,
            hovertemplate="%{x}: %{text}<extra></extra>"), row=1, col=col)
        fig.add_hline(y=0, line_color=SLATE, line_width=1, row=1, col=col)
    fig.update_yaxes(showgrid=False, showticklabels=False)
    return _style(fig, 380, margin=dict(t=60, b=10, l=10, r=10), bargap=0.45)
