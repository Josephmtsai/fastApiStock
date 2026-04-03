# fastApiStock

python 3.10.11

# Initial Guide
https://docs.google.com/document/d/1jO_BJyd4XSfYT1-3vcpWNmJWR5945uqq/edit?usp=sharing&ouid=114656855852923435659&rtpof=true&sd=true
https://docs.google.com/document/d/1dweR8f-oT0-2DM_ms6QRPgA7wi9zAfZP/edit?usp=sharing&ouid=114656855852923435659&rtpof=true&sd=true


# Skill

- python-core → ~/.claude/skills/python-core
- pytest-testing → ~/.claude/skills/pytest-testing

# 啟動開發伺服器
uv run uvicorn src.fastapistock.main:app --reload

# 檢查與格式化
uv run ruff check --fix && uv run ruff format

# 執行測試
uv run pytest tests/ --cov=src
