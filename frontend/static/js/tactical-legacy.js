(function (global) {
  "use strict";

  const TIPO_RECORTE = "recorte_legado";
  const cacheImagens = new Map();

  function grupoCor(componente) {
    const divisor = Math.max(1, componente.totalCor);
    const r = componente.r / divisor;
    const g = componente.g / divisor;
    const b = componente.b / divisor;
    if (r > 120 && r > g * 1.22 && r > b * 1.18) return "quente";
    if (b > 110 && b > r * 1.18) return "azul";
    if ((r + g + b) / 3 < 145) return "escuro";
    return "claro";
  }

  function distanciaCaixas(a, b) {
    const dx = Math.max(0, Math.max(a.minX, b.minX) - Math.min(a.maxX, b.maxX) - 1);
    const dy = Math.max(0, Math.max(a.minY, b.minY) - Math.min(a.maxY, b.maxY) - 1);
    return { dx, dy };
  }

  function decomporImagem(imagem, largura, altura) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(largura));
    canvas.height = Math.max(1, Math.round(altura));
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(imagem, 0, 0, canvas.width, canvas.height);

    let dados;
    try {
      dados = ctx.getImageData(0, 0, canvas.width, canvas.height);
    } catch (_) {
      return [criarRecorteCompleto(canvas)];
    }

    const pixels = dados.data;
    const total = canvas.width * canvas.height;
    const ativos = new Uint8Array(total);
    const visitados = new Uint8Array(total);
    const fila = new Int32Array(total);
    for (let indice = 0; indice < total; indice += 1) {
      ativos[indice] = pixels[indice * 4 + 3] >= 24 ? 1 : 0;
    }

    const componentes = [];
    for (let inicio = 0; inicio < total; inicio += 1) {
      if (!ativos[inicio] || visitados[inicio]) continue;
      let cabeca = 0;
      let cauda = 0;
      let minX = canvas.width;
      let minY = canvas.height;
      let maxX = 0;
      let maxY = 0;
      let somaR = 0;
      let somaG = 0;
      let somaB = 0;
      let totalCor = 0;
      fila[cauda++] = inicio;
      visitados[inicio] = 1;

      while (cabeca < cauda) {
        const atual = fila[cabeca++];
        const x = atual % canvas.width;
        const y = Math.floor(atual / canvas.width);
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        const base = atual * 4;
        const alpha = pixels[base + 3] / 255;
        somaR += pixels[base] * alpha;
        somaG += pixels[base + 1] * alpha;
        somaB += pixels[base + 2] * alpha;
        totalCor += alpha;

        for (let oy = -1; oy <= 1; oy += 1) {
          const ny = y + oy;
          if (ny < 0 || ny >= canvas.height) continue;
          for (let ox = -1; ox <= 1; ox += 1) {
            if (ox === 0 && oy === 0) continue;
            const nx = x + ox;
            if (nx < 0 || nx >= canvas.width) continue;
            const vizinho = ny * canvas.width + nx;
            if (ativos[vizinho] && !visitados[vizinho]) {
              visitados[vizinho] = 1;
              fila[cauda++] = vizinho;
            }
          }
        }
      }

      if (cauda < 4) continue;
      const componente = {
        minX,
        minY,
        maxX,
        maxY,
        r: somaR,
        g: somaG,
        b: somaB,
        totalCor,
        pixels: fila.slice(0, cauda),
      };
      componente.grupo = grupoCor(componente);
      componentes.push(componente);
    }

    if (!componentes.length) return [criarRecorteCompleto(canvas)];

    const pais = componentes.map((_, indice) => indice);
    const encontrar = (indice) => {
      let raiz = indice;
      while (pais[raiz] !== raiz) raiz = pais[raiz];
      while (pais[indice] !== indice) {
        const proximo = pais[indice];
        pais[indice] = raiz;
        indice = proximo;
      }
      return raiz;
    };
    const unir = (a, b) => {
      const raizA = encontrar(a);
      const raizB = encontrar(b);
      if (raizA !== raizB) pais[raizB] = raizA;
    };
    const margemUniao = Math.max(4, Math.round(Math.min(canvas.width, canvas.height) * 0.006));
    for (let a = 0; a < componentes.length; a += 1) {
      for (let b = a + 1; b < componentes.length; b += 1) {
        if (componentes[a].grupo !== componentes[b].grupo) continue;
        const distancia = distanciaCaixas(componentes[a], componentes[b]);
        if (distancia.dx <= margemUniao && distancia.dy <= margemUniao) unir(a, b);
      }
    }

    const grupos = new Map();
    componentes.forEach((componente, indice) => {
      const raiz = encontrar(indice);
      if (!grupos.has(raiz)) grupos.set(raiz, []);
      grupos.get(raiz).push(componente);
    });

    const recortes = [];
    grupos.forEach((grupo) => {
      const margem = 2;
      const minX = Math.max(0, Math.min(...grupo.map((item) => item.minX)) - margem);
      const minY = Math.max(0, Math.min(...grupo.map((item) => item.minY)) - margem);
      const maxX = Math.min(canvas.width - 1, Math.max(...grupo.map((item) => item.maxX)) + margem);
      const maxY = Math.min(canvas.height - 1, Math.max(...grupo.map((item) => item.maxY)) + margem);
      const larguraRecorte = maxX - minX + 1;
      const alturaRecorte = maxY - minY + 1;
      const recorte = document.createElement("canvas");
      recorte.width = larguraRecorte;
      recorte.height = alturaRecorte;
      const recorteCtx = recorte.getContext("2d");
      const recorteDados = recorteCtx.createImageData(larguraRecorte, alturaRecorte);

      grupo.forEach((componente) => {
        componente.pixels.forEach((indicePixel) => {
          const origemX = indicePixel % canvas.width;
          const origemY = Math.floor(indicePixel / canvas.width);
          const origem = indicePixel * 4;
          const destino = ((origemY - minY) * larguraRecorte + (origemX - minX)) * 4;
          recorteDados.data[destino] = pixels[origem];
          recorteDados.data[destino + 1] = pixels[origem + 1];
          recorteDados.data[destino + 2] = pixels[origem + 2];
          recorteDados.data[destino + 3] = pixels[origem + 3];
        });
      });
      recorteCtx.putImageData(recorteDados, 0, 0);
      const origemRecorte = recorte.toDataURL("image/png");
      cacheImagens.set(origemRecorte, { imagem: recorte, pronta: true, canvas: recorte, ctx: recorteCtx, callbacks: new Set() });
      recortes.push({
        tipo: TIPO_RECORTE,
        x: minX + larguraRecorte / 2,
        y: minY + alturaRecorte / 2,
        largura: larguraRecorte,
        altura: alturaRecorte,
        tamanho: 1,
        imagem: origemRecorte,
      });
    });

    return recortes.sort((a, b) => a.y - b.y || a.x - b.x);
  }

  function criarRecorteCompleto(canvas) {
    const origem = canvas.toDataURL("image/png");
    cacheImagens.set(origem, { imagem: canvas, pronta: true, canvas, ctx: canvas.getContext("2d", { willReadFrequently: true }), callbacks: new Set() });
    return {
      tipo: TIPO_RECORTE,
      x: canvas.width / 2,
      y: canvas.height / 2,
      largura: canvas.width,
      altura: canvas.height,
      tamanho: 1,
      imagem: origem,
    };
  }

  function obterImagem(origem, aoCarregar) {
    let entrada = cacheImagens.get(origem);
    if (!entrada) {
      const imagem = new Image();
      entrada = { imagem, pronta: false, callbacks: new Set() };
      cacheImagens.set(origem, entrada);
      imagem.onload = () => {
        entrada.pronta = true;
        entrada.canvas = document.createElement("canvas");
        entrada.canvas.width = Math.max(1, imagem.naturalWidth);
        entrada.canvas.height = Math.max(1, imagem.naturalHeight);
        entrada.ctx = entrada.canvas.getContext("2d", { willReadFrequently: true });
        entrada.ctx.drawImage(imagem, 0, 0);
        entrada.callbacks.forEach((callback) => callback());
        entrada.callbacks.clear();
      };
      imagem.src = origem;
    }
    if (!entrada.pronta && aoCarregar) entrada.callbacks.add(aoCarregar);
    return entrada;
  }

  function desenharRecorte(ctx, objecto, aoCarregar) {
    const entrada = obterImagem(objecto.imagem, aoCarregar);
    if (!entrada.pronta) return;
    const tamanho = objecto.tamanho || 1;
    const largura = objecto.largura * tamanho;
    const altura = objecto.altura * tamanho;
    ctx.drawImage(entrada.imagem, objecto.x - largura / 2, objecto.y - altura / 2, largura, altura);
  }

  function contemPonto(objecto, posicao) {
    const entrada = obterImagem(objecto.imagem);
    const tamanho = objecto.tamanho || 1;
    const largura = objecto.largura * tamanho;
    const altura = objecto.altura * tamanho;
    const esquerda = objecto.x - largura / 2;
    const topo = objecto.y - altura / 2;
    if (posicao.x < esquerda || posicao.x > esquerda + largura || posicao.y < topo || posicao.y > topo + altura) return false;
    if (!entrada.pronta || !entrada.ctx) return true;

    const px = Math.round(((posicao.x - esquerda) / largura) * entrada.canvas.width);
    const py = Math.round(((posicao.y - topo) / altura) * entrada.canvas.height);
    const raio = Math.max(2, Math.round(8 / Math.max(0.3, tamanho)));
    const x = Math.max(0, px - raio);
    const y = Math.max(0, py - raio);
    const w = Math.min(entrada.canvas.width - x, raio * 2 + 1);
    const h = Math.min(entrada.canvas.height - y, raio * 2 + 1);
    const dados = entrada.ctx.getImageData(x, y, w, h).data;
    for (let indice = 3; indice < dados.length; indice += 4) {
      if (dados[indice] >= 24) return true;
    }
    return false;
  }

  function desenharSeleccao(ctx, objecto) {
    const tamanho = objecto.tamanho || 1;
    const largura = objecto.largura * tamanho;
    const altura = objecto.altura * tamanho;
    ctx.strokeRect(objecto.x - largura / 2, objecto.y - altura / 2, largura, altura);
  }

  function aguardarRecortes(objectos) {
    const pendentes = (objectos || []).filter((objecto) => objecto?.tipo === TIPO_RECORTE && objecto.imagem).map((objecto) => new Promise((resolve) => {
      const entrada = obterImagem(objecto.imagem, resolve);
      if (entrada.pronta) resolve();
    }));
    return Promise.all(pendentes);
  }

  global.TacticalLegacy = {
    tipo: TIPO_RECORTE,
    decomporImagem,
    aguardarRecortes,
    desenharRecorte,
    desenharSeleccao,
    contemPonto,
    eRecorte: (objecto) => objecto?.tipo === TIPO_RECORTE && Boolean(objecto.imagem),
  };
})(window);
