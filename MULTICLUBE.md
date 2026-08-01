# Arquitetura multi-clube

Cada utilizador operacional pertence a um `Clube`. O superadministrador é global e só acede a dados operacionais depois de iniciar explicitamente uma sessão de suporte no painel `/superadmin/clubes`.

## Isolamento

- O middleware determina o clube a partir do utilizador autenticado, nunca do URL ou formulário.
- A sessão SQLAlchemy filtra automaticamente todos os modelos com `clube_id`.
- Novos registos recebem o clube atual no servidor e uma tentativa de atribuição cruzada é rejeitada.
- Recursos filhos consultados por ID também têm `clube_id`; os restantes são protegidos através da entidade principal.
- Clubes suspensos ficam bloqueados e clubes arquivados permitem apenas leitura.

## Migração

As migrações `0011_multiclube` e `0012_isolamento_filhos` criam o clube inicial a partir da identidade existente e preenchem a pertença dos dados através das relações atuais. IDs e relações são preservados. O downgrade é intencionalmente bloqueado para evitar perda da pertença.

## Primeiro superadministrador

Executar a partir da raiz e introduzir a password quando solicitado:

```powershell
$env:PYTHONPATH="backend"
.\venv\Scripts\python.exe backend\criar_superadmin.py --username superadmin --nome "Administrador Global" --email "admin@exemplo.pt"
```

Não existe password predefinida. A password inicial tem no mínimo 12 caracteres.
