from fastapi.templating import Jinja2Templates as _Jinja2Templates

from formatacao import data_hora_pt, data_iso, data_pt, finalizar_valor_template


class Jinja2Templates(_Jinja2Templates):
    """Templates da aplicação com formatação portuguesa uniforme."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env.filters["data_pt"] = data_pt
        self.env.filters["data_hora_pt"] = data_hora_pt
        self.env.filters["data_iso"] = data_iso
        self.env.finalize = finalizar_valor_template
