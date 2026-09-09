"""Local UI fixture. Synthetic data only; never imports or accesses the database."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader

FRONTEND = Path(__file__).resolve().parents[1]
env = Environment(loader=FileSystemLoader(FRONTEND / 'templates'), autoescape=True)
env.filters['data_pt'] = str
env.globals['termo_jogador'] = lambda *args, **kwargs: 'Atletas'
team = NS(id=7, nome='Sub-18 Masculinos', escalao=NS(value='Sub-18'), genero=NS(value='Masculino'))
steps = [
    {'id': 1, 'ordem': 0, 'observacao': 'Abrir o corredor e atacar o cesto.', 'estado': {
        'campoTipo': 'meio', 'largura': 702, 'altura': 622, 'objectos': [
            {'id': 'p', 'tipo': 'jogador_ataque', 'x': 180, 'y': 400, 'numero': 1},
            {'id': 'q', 'tipo': 'jogador_defesa', 'x': 470, 'y': 190, 'numero': 2},
            {'id': 'ball', 'tipo': 'bola', 'x': 195, 'y': 405},
            {'id': 'a', 'tipo': 'seta_zigzag', 'pontos': [{'x': 180, 'y': 400}, {'x': 230, 'y': 310}, {'x': 350, 'y': 200}]},
        ]}},
    {'id': 2, 'ordem': 1, 'observacao': 'Finalizar em equilibrio.', 'estado': {
        'campoTipo': 'completo', 'largura': 697, 'altura': 1222, 'objectos': [
            {'id': 'p', 'tipo': 'jogador_ataque', 'x': 350, 'y': 200, 'numero': 1},
            {'id': 'ball', 'tipo': 'bola', 'x': 365, 'y': 205},
            {'id': 'shot', 'tipo': 'lancamento', 'pontos': [{'x': 365, 'y': 205}, {'x': 350, 'y': 110}]},
        ]}},
]


class Handler(BaseHTTPRequestHandler):
    def send(self, data, mime='text/html; charset=utf-8', status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/static/'):
            file = (FRONTEND / path.lstrip('/')).resolve()
            if file.is_relative_to((FRONTEND / 'static').resolve()) and file.is_file():
                return self.send(file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream')
            return self.send(b'Not found', status=404)
        if path not in ('/studio', '/studio-imported', '/dashboard'):
            return self.send(b'UI fixture: /studio or /dashboard', status=404)
        request = NS(url=NS(path='/dashboard'), session={}, state=NS(
            identidade_clube={'nome_curto': 'Clube de Basquetebol', 'cor_principal': '#c81724', 'cor_principal_escura': '#991b1b', 'cor_principal_superficie': '#fff1f2'},
            clube_atual=NS(id=1), flash=None,
            navegacao={'equipas': [team], 'dashboard_url': '/dashboard'}))
        context = dict(request=request, utilizador=NS(nome='Treinador', perfil=NS(value='treinador')),
            setplay=NS(id=1, nome='Ataque em continuidade', categoria='Ataque', descricao='', origem='ebp' if path.endswith('imported') else 'manual'),
            passos_studio=steps, categorias=['Ataque'], resumo_agenda=NS(tarefas=0, hoje=1, proximos_7_dias=3),
            tarefas=[], agenda_proxima=[], dados_equipas=[NS(equipa=team, proximo_jogo=None, ultimo_resultado=None, total_jogadores=12)])
        if path.startswith('/studio'):
            context['equipa'] = team
        template = 'playbook/detalhe.html' if path.startswith('/studio') else 'dashboard_treinador.html'
        self.send(env.get_template(template).render(**context).encode())

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        parts = urlsplit(self.path).path.split('/')
        if len(parts) == 5 and parts[1:3] == ['playbook', 'passos']:
            step = next((s for s in steps if str(s['id']) == parts[3]), None)
            if step and parts[4] == 'desenho':
                step.update(estado=payload['estado'], desenho=payload['dados'])
                return self.send(b'{"sucesso":true}', 'application/json')
            if step and parts[4] == 'observacao-json':
                step['observacao'] = payload['observacao']
                return self.send(b'{"sucesso":true}', 'application/json')
        self.send(b'{"erro":"Operacao fora do ensaio visual"}', 'application/json', 400)


if __name__ == '__main__':
    print('Synthetic UI fixture at http://127.0.0.1:8765/studio', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
