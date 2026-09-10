MODELOS_QUESTIONARIO = {
    "acompanhamento-diario-original": {
        "nome": "Questionário Matinal",
        "descricao": "Modelo original completo: sessão, sono, esforço, dores e queixas do atleta.",
        "perguntas": [
            {"texto": "Tipo de sessão", "tipo": "escolha", "opcoes": ["Descanso", "Treino", "Jogo"]},
            {"texto": "Horas de sono", "tipo": "numero", "minimo": 0, "maximo": 24, "ajuda": "Podes usar meios valores, por exemplo 7,5."},
            {"texto": "Qualidade do sono", "tipo": "escala", "minimo": 1, "maximo": 5, "rotulo_minimo": "Muito má", "rotulo_maximo": "Muito boa"},
            {"texto": "Perceção subjetiva de esforço (PSE)", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Mínimo", "rotulo_maximo": "Fadiga máxima"},
            {"texto": "Dores musculares nos membros inferiores", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Dor leve", "rotulo_maximo": "Dor muito severa"},
            {"texto": "Dores musculares nos membros superiores", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Dor leve", "rotulo_maximo": "Dor muito severa"},
            {"texto": "Tens alguma dor ou queixa específica?", "tipo": "sim_nao"},
            {"texto": "Se sim, descreve onde e o que sentes", "tipo": "texto_longo", "obrigatoria": False},
            {"texto": "Algo mais que a equipa técnica deva saber?", "tipo": "texto_longo", "obrigatoria": False},
        ],
    },
    "pse-pos-treino": {
        "nome": "Perceção subjetiva de esforço - Pós-treino",
        "descricao": "Carga percebida, dores e observações imediatamente após o treino.",
        "perguntas": [
            {"texto": "Perceção subjetiva de esforço (PSE)", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Muito leve", "rotulo_maximo": "Máximo", "ajuda": "Avalia o esforço global da sessão."},
            {"texto": "Dores musculares nos membros inferiores", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Sem dor", "rotulo_maximo": "Muito severa"},
            {"texto": "Dores musculares nos membros superiores", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Sem dor", "rotulo_maximo": "Muito severa"},
            {"texto": "Tens alguma dor ou queixa específica?", "tipo": "sim_nao"},
            {"texto": "Descreve a dor, limitação ou observação", "tipo": "texto_longo", "obrigatoria": False},
        ],
    },
    "bem-estar-pre-treino": {
        "nome": "Bem-estar - Pré-treino",
        "descricao": "Leitura rápida da disponibilidade física e mental antes da sessão.",
        "perguntas": [
            {"texto": "Qualidade do sono", "tipo": "escala", "minimo": 1, "maximo": 5, "rotulo_minimo": "Muito má", "rotulo_maximo": "Muito boa"},
            {"texto": "Nível de fadiga", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Sem fadiga", "rotulo_maximo": "Fadiga máxima"},
            {"texto": "Dor muscular", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Sem dor", "rotulo_maximo": "Muito severa"},
            {"texto": "Estado de espírito", "tipo": "escala", "minimo": 1, "maximo": 5, "rotulo_minimo": "Muito baixo", "rotulo_maximo": "Muito bom"},
            {"texto": "Sentes-te disponível para treinar?", "tipo": "sim_nao"},
            {"texto": "Observações para a equipa técnica", "tipo": "texto_longo", "obrigatoria": False},
        ],
    },
    "recuperacao-diaria": {
        "nome": "Recuperação diária",
        "descricao": "Sono, recuperação e sintomas entre sessões.",
        "perguntas": [
            {"texto": "Horas de sono", "tipo": "numero", "minimo": 0, "maximo": 24, "ajuda": "Podes usar meios valores, por exemplo 7,5."},
            {"texto": "Qualidade do sono", "tipo": "escala", "minimo": 1, "maximo": 5, "rotulo_minimo": "Muito má", "rotulo_maximo": "Muito boa"},
            {"texto": "Sensação de recuperação", "tipo": "escala", "minimo": 1, "maximo": 10, "rotulo_minimo": "Nada recuperado", "rotulo_maximo": "Totalmente recuperado"},
            {"texto": "Existe alguma dor ou limitação?", "tipo": "sim_nao"},
            {"texto": "Onde sentes dor ou limitação?", "tipo": "texto_longo", "obrigatoria": False},
        ],
    },
}


TIPOS_PERGUNTA = {
    "escala": "Escala numérica",
    "escolha": "Escolha única",
    "sim_nao": "Sim / Não",
    "numero": "Número",
    "texto_curto": "Resposta curta",
    "texto_longo": "Resposta longa",
}
