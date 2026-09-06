"""Génère `static/contours.svg`, le fond de courbes de niveau du thème.

Outil de conception, pas d'exploitation : le SVG produit est versionné, ce script
n'est là que pour le rejouer autrement — changer SEED donne un autre relief,
LEVELS l'équidistance des isolignes. Rien ne l'appelle au déploiement.

    python3 theme/contours.py     # réécrit theme/static/contours.svg

Le principe est celui d'une carte topographique : on échantillonne un champ
scalaire (des dômes gaussiens sur une ondulation basse fréquence), puis on suit
ses lignes de niveau par marching squares, cellule par cellule.

Le fond est étiré en `cover` par la CSS : à l'écran il est agrandi de moitié.
Une polyligne, même dense, y montrerait ses facettes — d'où une sortie en
courbes de Bézier, lisses par construction et non par densité de points. La
chaîne est donc : marching squares -> lissage -> rééchantillonnage à pas
constant -> Catmull-Rom converti en Bézier cubique.
"""
import math
import pathlib
import random

W, H = 1200, 800          # viewBox
NX, NY = 150, 100         # grille d'échantillonnage
LEVELS = 28               # nombre d'isolignes
SEED = 20260906
STEP = 22.0               # pas de rééchantillonnage, en unités du viewBox
MIN_POINTS = 4            # en deçà, la boucle est un artefact : on la jette

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


# --- Marching squares ------------------------------------------------------

# Arêtes de la cellule, dans l'ordre : haut, droite, bas, gauche. Chacune est
# donnée par les deux coins qu'elle relie, en coordonnées de grille locales.
EDGES = {
    "T": ((0, 0), (1, 0)),
    "R": ((1, 0), (1, 1)),
    "B": ((0, 1), (1, 1)),
    "L": ((0, 0), (0, 1)),
}

# Cas de configuration -> arêtes traversées. Le code est tl*8 + tr*4 + br*2 + bl,
# un bit par coin au-dessus du niveau. 5 et 10 sont les selles : elles se
# tranchent au centre de la cellule, sinon on relie deux branches au hasard et
# la courbe fait un ressaut.
CASES = {
    0: (), 15: (),
    1: (("L", "B"),), 14: (("L", "B"),),
    2: (("B", "R"),), 13: (("B", "R"),),
    3: (("L", "R"),), 12: (("L", "R"),),
    4: (("T", "R"),), 11: (("T", "R"),),
    6: (("T", "B"),), 9: (("T", "B"),),
    7: (("L", "T"),), 8: (("L", "T"),),
}
SADDLE = {
    # (cas, centre au-dessus du niveau) -> les deux segments à tracer.
    (5, True): (("L", "T"), ("B", "R")),
    (5, False): (("T", "R"), ("L", "B")),
    (10, True): (("T", "R"), ("L", "B")),
    (10, False): (("L", "T"), ("B", "R")),
}


def segments_at(level):
    """Les segments d'une isoligne, cellule par cellule."""
    segs = []
    for y in range(NY - 1):
        for x in range(NX - 1):
            z = {
                (0, 0): grid[y][x], (1, 0): grid[y][x + 1],
                (1, 1): grid[y + 1][x + 1], (0, 1): grid[y + 1][x],
            }
            case = ((z[(0, 0)] >= level) << 3 | (z[(1, 0)] >= level) << 2
                    | (z[(1, 1)] >= level) << 1 | (z[(0, 1)] >= level))
            if case in (5, 10):
                center = sum(z.values()) / 4
                pairs = SADDLE[(case, center >= level)]
            else:
                pairs = CASES[case]

            def cut(edge):
                (ax, ay), (bx, by) = EDGES[edge]
                za, zb = z[(ax, ay)], z[(bx, by)]
                t = (level - za) / (zb - za)
                pa, pb = px(x + ax, y + ay), px(x + bx, y + by)
                return (pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]))

            for e1, e2 in pairs:
                segs.append((cut(e1), cut(e2)))
    return segs


def key(pt):
    return (round(pt[0], 4), round(pt[1], 4))


def chains(segs):
    """Recoud les segments en polylignes ; renvoie (points, fermée)."""
    adj = {}
    coord = {}
    for i, (a, b) in enumerate(segs):
        for p, q in ((a, b), (b, a)):
            adj.setdefault(key(p), []).append((key(q), i))
            coord[key(p)] = p

    used = set()

    def walk(start):
        path = [coord[start]]
        cur = start
        while True:
            nxt = [(k, i) for k, i in adj.get(cur, []) if i not in used]
            if not nxt:
                return path
            k, i = nxt[0]
            used.add(i)
            path.append(coord[k])
            cur = k
            if cur == start:
                return path

    out = []
    ends = [k for k, v in adj.items() if len(v) == 1]
    for start in ends + list(adj.keys()):
        if any(i not in used for _, i in adj.get(start, [])):
            path = walk(start)
            if len(path) > MIN_POINTS:
                out.append(path)
    return out


# --- Lissage et rééchantillonnage ------------------------------------------


def chaikin(pts, closed, passes=2):
    """Coupe les angles : chaque segment est remplacé par ses deux quarts."""
    for _ in range(passes):
        out = []
        n = len(pts)
        if not closed:
            out.append(pts[0])
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts


def resample(pts, closed, step=STEP):
    """Points équidistants le long de la polyligne.

    C'est ce qui rend la spline suivante fiable : Catmull-Rom uniforme suppose
    des points régulièrement espacés, sinon elle dépasse dans les virages.
    """
    seq = pts + [pts[0]] if closed else pts
    out = [seq[0]]
    carry = 0.0
    for a, b in zip(seq, seq[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d == 0:
            continue
        t = step - carry
        while t <= d:
            out.append((a[0] + (b[0] - a[0]) * t / d, a[1] + (b[1] - a[1]) * t / d))
            t += step
        carry = (carry + d) % step
    if closed:
        # Le dernier point rejoint le premier : la spline referme d'elle-même.
        if len(out) > 1 and math.hypot(out[-1][0] - out[0][0], out[-1][1] - out[0][1]) < step / 2:
            out.pop()
    elif math.hypot(out[-1][0] - seq[-1][0], out[-1][1] - seq[-1][1]) > step / 4:
        out.append(seq[-1])
    return out


def bezier_path(pts, closed):
    """Catmull-Rom uniforme converti en Bézier cubique : une courbe C¹."""
    n = len(pts)
    if n < 2:
        return None

    def at(i):
        if closed:
            return pts[i % n]
        return pts[min(max(i, 0), n - 1)]

    d = [f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"]
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        # Tangentes de Catmull-Rom, exprimées en points de contrôle de Bézier.
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} "
                 f"{fmt(p2[0])} {fmt(p2[1])}")
    if closed:
        d.append("Z")
    return "".join(d)


def fmt(v):
    """Un décimal : l'entier près faisait des marches, deux ne se voient pas."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


# --- Sortie ----------------------------------------------------------------

paths = []
for i in range(LEVELS):
    level = zmin + (zmax - zmin) * (i + 0.5) / LEVELS
    for chain in chains(segments_at(level)):
        closed = key(chain[0]) == key(chain[-1])
        pts = resample(chaikin(chain[:-1] if closed else chain, closed), closed)
        if len(pts) < MIN_POINTS:
            continue
        d = bezier_path(pts, closed)
        if d:
            paths.append(d)

body = "\n  ".join(f'<path d="{d}"/>' for d in paths)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice">
  <!-- Généré par theme/contours.py (marching squares). Ne pas retoucher à la main. -->
  <g fill="none" stroke="#4a6fae" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  {body}
  </g>
</svg>
'''

out = pathlib.Path(__file__).with_name("static") / "contours.svg"
out.write_text(svg)
print(f"{len(paths)} courbes écrites dans static/contours.svg ({len(svg) // 1024} Kio)")
