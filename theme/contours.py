"""Génère `static/contours.svg`, le fond de courbes de niveau du thème.

Outil de conception, pas d'exploitation : le SVG produit est versionné, ce script
n'est là que pour le rejouer autrement — changer SEED donne un autre relief,
LEVELS l'équidistance des isolignes. Rien ne l'appelle au déploiement.

    python3 theme/contours.py     # réécrit theme/static/contours.svg

Le principe est celui d'une carte topographique : on échantillonne un champ
scalaire (des dômes gaussiens sur une ondulation basse fréquence), puis on suit
ses lignes de niveau par marching squares, cellule par cellule.
"""
import math, random

W, H = 1200, 800          # viewBox
NX, NY = 150, 100          # grille d'échantillonnage
LEVELS = 28               # nombre d'isolignes
SEED = 20260906
DECIM = 3                 # décimation des points après lissage

rnd = random.Random(SEED)

# Reliefs : quelques dômes et cuvettes, plus un basculement général.
bumps = []
for _ in range(17):
    bumps.append((
        rnd.uniform(-0.15, 1.15),      # cx (unités normalisées)
        rnd.uniform(-0.15, 1.15),      # cy
        rnd.uniform(0.07, 0.26),       # rayon
        rnd.uniform(-1.0, 1.0),        # amplitude signée
        rnd.uniform(0.6, 1.6),         # anisotropie
    ))

def field(u, v):
    # Ondulation basse fréquence : évite les dômes trop concentriques.
    z = 0.34 * math.sin(2.4 * u + 0.7) * math.cos(2.0 * v - 0.4) + 0.30 * u - 0.24 * v
    for cx, cy, r, a, k in bumps:
        dx, dy = (u - cx) / r, (v - cy) / (r * k)
        z += a * math.exp(-(dx * dx + dy * dy))
    return z

grid = [[field(x / (NX - 1), y / (NY - 1)) for x in range(NX)] for y in range(NY)]
zmin = min(min(row) for row in grid)
zmax = max(max(row) for row in grid)

def px(x, y):
    return (x / (NX - 1) * W, y / (NY - 1) * H)

def interp(p, q, zp, zq, level):
    t = (level - zp) / (zq - zp)
    return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

def key(pt):
    return (round(pt[0], 3), round(pt[1], 3))

def chaikin(pts, closed, passes=2):
    for _ in range(passes):
        out = []
        n = len(pts)
        rng = range(n) if closed else range(n - 1)
        if not closed:
            out.append(pts[0])
        for i in rng:
            a, b = pts[i], pts[(i + 1) % n]
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * b[1] + 0.75 * b[1]))
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts

def segments_at(level):
    """Marching squares : les segments d'une isoligne, cellule par cellule."""
    segs = []
    for y in range(NY - 1):
        for x in range(NX - 1):
            corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            zs = [grid[cy][cx] for cx, cy in corners]
            pts = [px(cx, cy) for cx, cy in corners]
            crossings = []
            for i in range(4):
                j = (i + 1) % 4
                if (zs[i] < level) != (zs[j] < level):
                    crossings.append(interp(pts[i], pts[j], zs[i], zs[j], level))
            if len(crossings) == 2:
                segs.append(tuple(crossings))
            elif len(crossings) == 4:
                # Cellule ambiguë : on relie par paires dans l'ordre du parcours.
                segs.append((crossings[0], crossings[1]))
                segs.append((crossings[2], crossings[3]))
    return segs

def chains(segs):
    """Recoud les segments en polylignes ; renvoie (points, fermée)."""
    adj = {}
    for a, b in segs:
        adj.setdefault(key(a), []).append((key(b), b))
        adj.setdefault(key(b), []).append((key(a), a))
    coord = {}
    for a, b in segs:
        coord[key(a)] = a
        coord[key(b)] = b
    used = set()

    def walk(start):
        path = [coord[start]]
        cur, prev = start, None
        while True:
            nxts = [(k, p) for k, p in adj.get(cur, []) if (frozenset((cur, k)) not in used)]
            if not nxts:
                return path
            k, p = nxts[0]
            used.add(frozenset((cur, k)))
            path.append(p)
            prev, cur = cur, k
            if cur == start:
                return path

    out = []
    # D'abord les extrémités (lignes ouvertes), puis ce qui reste (boucles).
    for k in [k for k, v in adj.items() if len(v) == 1] + list(adj.keys()):
        if any(frozenset((k, n)) not in used for n, _ in adj.get(k, [])):
            path = walk(k)
            if len(path) > 3:
                out.append(path)
    return out

def fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")

curves = []
for i in range(LEVELS):
    level = zmin + (zmax - zmin) * (i + 0.5) / LEVELS
    for path in chains(segments_at(level)):
        closed = key(path[0]) == key(path[-1])
        pts = chaikin(path[:-1] if closed else path, closed)
        pts = pts[::DECIM] or pts
        curves.append((pts, closed))

def fmt(v):
    return f"{v:.0f}"

paths = []
for pts, closed in curves:
    d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + ("Z" if closed else "")
    paths.append(d)

body = "\n  ".join(f'<path d="{d}"/>' for d in paths)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice">
  <!-- Généré par theme/contours.py (marching squares). Ne pas retoucher à la main. -->
  <g fill="none" stroke="#4a6fae" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  {body}
  </g>
</svg>
'''
import pathlib
pathlib.Path(__file__).with_name("static").joinpath("contours.svg").write_text(svg)
print(f"{len(paths)} courbes écrites dans static/contours.svg")
