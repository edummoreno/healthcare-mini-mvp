# Health Care — Mini MVP

Mini app (1 função): sugerir especialidade médica com base em texto usando regras/keywords.
Sem diagnóstico, sem prescrição e sem urgência.

## Rodar local (Windows PowerShell)
```powershell
py -3.12 -m venv .\env
.\env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\requirements.txt
streamlit run .\app.py
```

## Testes

```powershell
pytest -q
```
