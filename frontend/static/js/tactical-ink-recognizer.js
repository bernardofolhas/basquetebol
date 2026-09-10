(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TacticalInkRecognizer = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const point = (x, y) => ({ x, y });

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function bounds(strokes) {
    const points = strokes.flatMap(stroke => stroke.pontos || []);
    if (!points.length) return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, cx: 0, cy: 0 };
    const xs = points.map(p => Number(p.x)), ys = points.map(p => Number(p.y));
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    return { left, right, top, bottom, width: right - left, height: bottom - top, cx: (left + right) / 2, cy: (top + bottom) / 2 };
  }

  function pathLength(points) {
    let total = 0;
    for (let i = 1; i < points.length; i += 1) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    return total;
  }

  function interpolate(points, count = 32) {
    if (!points?.length) return [];
    if (points.length === 1) return Array.from({ length: count }, () => ({ ...points[0] }));
    const lengths = points.slice(1).map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
    const total = lengths.reduce((sum, length) => sum + length, 0);
    if (!total) return Array.from({ length: count }, () => ({ ...points[0] }));
    const output = [];
    for (let sample = 0; sample < count; sample += 1) {
      let distance = total * sample / (count - 1), index = 0;
      while (index < lengths.length - 1 && distance > lengths[index]) distance -= lengths[index++];
      const ratio = lengths[index] ? distance / lengths[index] : 0;
      output.push(point(points[index].x + (points[index + 1].x - points[index].x) * ratio, points[index].y + (points[index + 1].y - points[index].y) * ratio));
    }
    return output;
  }

  function normalize(strokes) {
    const box = bounds(strokes), scale = Math.max(1, box.width, box.height);
    const offsetX = (scale - box.width) / (2 * scale), offsetY = (scale - box.height) / (2 * scale);
    return strokes.flatMap(stroke => interpolate(stroke.pontos || [], Math.max(12, Math.min(36, (stroke.pontos || []).length))).map(p => point(offsetX + (p.x - box.left) / scale, offsetY + (p.y - box.top) / scale)));
  }

  function line(points) { return points.map(([x, y]) => point(x, y)); }
  function arc(cx, cy, rx, ry, start, end, steps = 18) {
    return Array.from({ length: steps }, (_, i) => {
      const angle = start + (end - start) * i / (steps - 1);
      return point(cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry);
    });
  }

  const templates = {
    0: [[...arc(.5, .5, .42, .48, -Math.PI / 2, Math.PI * 1.5, 28)]],
    1: [[...line([[.28, .2], [.5, 0], [.5, 1]])]],
    2: [[...arc(.46, .25, .42, .25, Math.PI, Math.PI * 2, 12), ...line([[.88, .25], [.12, 1], [.9, 1]])]],
    3: [[...arc(.34, .25, .5, .25, -Math.PI / 2, Math.PI / 2, 12), ...arc(.34, .75, .5, .25, -Math.PI / 2, Math.PI / 2, 12)]],
    4: [[...line([[.76, 1], [.76, 0], [.08, .65], [1, .65]])]],
    5: [[...line([[.92, 0], [.15, 0], [.12, .48], [.65, .48]]), ...arc(.5, .72, .42, .28, -Math.PI / 2, Math.PI / 1.8, 12)]],
    6: [[...arc(.55, .53, .42, .48, -.15 * Math.PI, 1.8 * Math.PI, 28)]],
    7: [[...line([[.05, 0], [.95, 0], [.35, 1]])]],
    8: [[...arc(.5, .25, .34, .25, -Math.PI / 2, Math.PI * 1.5, 16), ...arc(.5, .74, .4, .26, -Math.PI / 2, Math.PI * 1.5, 16)]],
    9: [[...arc(.48, .27, .4, .27, Math.PI * .45, Math.PI * 2.45, 20), ...line([[.86, .28], [.65, 1]])]],
  };

  function chamfer(a, b) {
    const oneWay = (source, target) => source.reduce((sum, p) => sum + Math.min(...target.map(q => Math.hypot(p.x - q.x, p.y - q.y))), 0) / Math.max(1, source.length);
    return (oneWay(a, b) + oneWay(b, a)) / 2;
  }

  function recogniseDigit(strokes) {
    const box = bounds(strokes);
    if (box.height < 14 || box.height > 125 || box.width > box.height * 1.35) return null;
    if (box.width < box.height * .22) return { digit: 1, score: 0 };
    const candidate = normalize(strokes);
    const scores = Object.entries(templates).map(([digit, template]) => ({ digit: Number(digit), score: chamfer(candidate, normalize(template.map(pontos => ({ pontos })))) }));
    scores.sort((a, b) => a.score - b.score);
    return scores[0].score <= .235 ? scores[0] : null;
  }

  function isClosed(stroke) {
    const points = stroke.pontos || [], box = bounds([stroke]), diagonal = Math.hypot(box.width, box.height);
    if (points.length < 8 || diagonal < 20 || box.width / Math.max(1, box.height) < .45 || box.width / Math.max(1, box.height) > 2.2) return false;
    return Math.hypot(points[0].x - points.at(-1).x, points[0].y - points.at(-1).y) < diagonal * .32 && pathLength(points) > diagonal * 1.65;
  }

  function isStraight(stroke) {
    const points = stroke.pontos || [];
    if (points.length < 2) return false;
    return Math.hypot(points[0].x - points.at(-1).x, points[0].y - points.at(-1).y) / Math.max(1, pathLength(points)) > .82;
  }

  function segmentIntersection(a, b, c, d) {
    const denominator = (a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x);
    if (Math.abs(denominator) < .001) return null;
    const t = ((a.x - c.x) * (c.y - d.y) - (a.y - c.y) * (c.x - d.x)) / denominator;
    const u = -((a.x - b.x) * (a.y - c.y) - (a.y - b.y) * (a.x - c.x)) / denominator;
    return t > .12 && t < .88 && u > .12 && u < .88 ? point(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y)) : null;
  }

  function crossed(a, b) {
    if (!isStraight(a) || !isStraight(b)) return null;
    const pa = a.pontos, pb = b.pontos;
    const intersection = segmentIntersection(pa[0], pa.at(-1), pb[0], pb.at(-1));
    if (!intersection) return null;
    const angleA = Math.atan2(pa.at(-1).y - pa[0].y, pa.at(-1).x - pa[0].x);
    const angleB = Math.atan2(pb.at(-1).y - pb[0].y, pb.at(-1).x - pb[0].x);
    const angle = Math.abs(Math.sin(angleA - angleB));
    const lengths = [pathLength(pa), pathLength(pb)];
    return angle > .55 && Math.min(...lengths) > 18 && Math.max(...lengths) < 130 && Math.max(...lengths) / Math.min(...lengths) < 2.2 ? intersection : null;
  }

  function simplify(points, tolerance = 4) {
    if (points.length < 3) return points;
    const first = points[0], last = points.at(-1);
    const dx = last.x - first.x, dy = last.y - first.y, denominator = Math.max(.001, Math.hypot(dx, dy));
    let furthest = 0, index = 0;
    for (let i = 1; i < points.length - 1; i += 1) {
      const distance = Math.abs(dy * points[i].x - dx * points[i].y + last.x * first.y - last.y * first.x) / denominator;
      if (distance > furthest) { furthest = distance; index = i; }
    }
    if (furthest <= tolerance) return [first, last];
    return [...simplify(points.slice(0, index + 1), tolerance).slice(0, -1), ...simplify(points.slice(index), tolerance)];
  }

  function selfCrossed(stroke) {
    const box = bounds([stroke]), points = simplify(stroke.pontos || []);
    if (box.width < 18 || box.height < 18 || box.width > 125 || box.height > 125 || points.length < 4 || points.length > 7) return null;
    for (let i = 0; i < points.length - 1; i += 1) for (let j = i + 2; j < points.length - 1; j += 1) {
      if (i === 0 && j === points.length - 2 && Math.hypot(points[0].x - points.at(-1).x, points[0].y - points.at(-1).y) < 8) continue;
      const centre = segmentIntersection(points[i], points[i + 1], points[j], points[j + 1]);
      if (centre) return centre;
    }
    return null;
  }

  function overlaps(a, b, margin = 10) {
    return a.left <= b.right + margin && a.right + margin >= b.left && a.top <= b.bottom + margin && a.bottom + margin >= b.top;
  }

  function cluster(strokes, margin = 10) {
    const groups = [];
    strokes.forEach(stroke => {
      const touching = groups.filter(group => overlaps(bounds(group), bounds([stroke]), margin));
      if (!touching.length) groups.push([stroke]);
      else {
        const merged = [stroke, ...touching.flat()];
        touching.forEach(group => groups.splice(groups.indexOf(group), 1));
        groups.push(merged);
      }
    });
    return groups;
  }

  function recogniseNumber(strokes) {
    const parts = cluster(strokes, 2).sort((a, b) => bounds(a).cx - bounds(b).cx);
    if (parts.length === 2) {
      const boxes = parts.map(bounds), digits = parts.map(recogniseDigit);
      const overlapY = Math.min(boxes[0].bottom, boxes[1].bottom) - Math.max(boxes[0].top, boxes[1].top);
      const height = Math.min(boxes[0].height, boxes[1].height);
      const gap = boxes[1].left - boxes[0].right;
      if (digits.every(Boolean) && overlapY > height * .35 && gap >= -2 && gap < Math.max(...boxes.map(box => box.height)) * .5) {
        return { number: digits[0].digit * 10 + digits[1].digit, score: Math.max(...digits.map(item => item.score)) };
      }
    }
    const digit = recogniseDigit(strokes);
    return digit ? { number: digit.digit, score: digit.score } : null;
  }

  function interpret(objects, options = {}) {
    const uid = options.uid || (() => `ink-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`);
    const freehand = objects.filter(object => object.tipo === "caneta" && object.pontos?.length > 1);
    const consumed = new Set(), replacements = [];
    let nextAttack = Number(options.nextAttack) || 1, nextDefence = Number(options.nextDefence) || 1;

    for (let i = 0; i < freehand.length; i += 1) for (let j = i + 1; j < freehand.length; j += 1) {
      if (consumed.has(freehand[i]) || consumed.has(freehand[j])) continue;
      const centre = crossed(freehand[i], freehand[j]);
      if (!centre) continue;
      replacements.push({ tipo: "jogador_defesa", x: centre.x, y: centre.y, tamanho: 1, numero: nextDefence++, origemReconhecimento: true });
      consumed.add(freehand[i]); consumed.add(freehand[j]);
    }

    freehand.filter(stroke => !consumed.has(stroke)).forEach(stroke => {
      const centre = selfCrossed(stroke);
      if (!centre) return;
      replacements.push({ tipo: "jogador_defesa", x: centre.x, y: centre.y, tamanho: 1, numero: nextDefence++, origemReconhecimento: true });
      consumed.add(stroke);
    });

    freehand.filter(stroke => !consumed.has(stroke) && isClosed(stroke)).forEach(circle => {
      const box = bounds([circle]);
      const inside = freehand.filter(stroke => !consumed.has(stroke) && stroke !== circle).filter(stroke => {
        const inner = bounds([stroke]);
        return inner.cx > box.left && inner.cx < box.right && inner.cy > box.top && inner.cy < box.bottom && inner.width < box.width * .82 && inner.height < box.height * .9;
      });
      const number = recogniseNumber(inside);
      if (!number) return;
      replacements.push({ tipo: "jogador_ataque", x: box.cx, y: box.cy, tamanho: 1, numero: number.number, origemReconhecimento: true });
      replacements.push({ tipo: "bola", x: box.cx + 19, y: box.cy + 14, tamanho: .72, numero: null, origemReconhecimento: true });
      consumed.add(circle); inside.forEach(stroke => consumed.add(stroke));
      nextAttack = Math.max(nextAttack, number.number + 1);
    });

    cluster(freehand.filter(stroke => !consumed.has(stroke))).forEach(group => {
      const number = recogniseNumber(group), box = bounds(group);
      if (!number) return;
      replacements.push({ tipo: "jogador_ataque", x: box.cx, y: box.cy, tamanho: 1, numero: number.number, origemReconhecimento: true });
      group.forEach(stroke => consumed.add(stroke));
      nextAttack = Math.max(nextAttack, number.number + 1);
    });

    const recognised = replacements.filter(object => object.tipo.startsWith("jogador_")).length;
    const kept = objects.filter(object => !consumed.has(object));
    replacements.forEach(object => { object.id = uid(); kept.push(object); });
    return { objects: kept, recognised, consumed: consumed.size, nextAttack, nextDefence };
  }

  return { bounds, crossed, interpret, isClosed, recogniseDigit };
});
